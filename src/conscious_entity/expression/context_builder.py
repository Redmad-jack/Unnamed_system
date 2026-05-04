from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)

# Maps PolicyAction → instruction text injected into the system prompt.
# Mirrors the policy descriptions in expression_system.txt so the LLM
# always receives a clear, singular directive.
_POLICY_INSTRUCTIONS: dict[str, str] = {
    PolicyAction.RESPOND_OPENLY.value:         "Current policy: RESPOND_OPENLY",
    PolicyAction.RESPOND_BRIEFLY.value:        "Current policy: RESPOND_BRIEFLY",
    PolicyAction.ASK_BACK.value:               "Current policy: ASK_BACK",
    PolicyAction.REFUSE.value:                 "Current policy: REFUSE",
    PolicyAction.DIVERT_TOPIC.value:           "Current policy: DIVERT_TOPIC",
    PolicyAction.ENTER_SILENCE_MODE.value:     "Current policy: ENTER_SILENCE_MODE",
    PolicyAction.DELAY_RESPONSE.value:         "Current policy: RESPOND_OPENLY",
    PolicyAction.RETRIEVE_MEMORY_FIRST.value:  "Current policy: RESPOND_OPENLY",
    PolicyAction.REJECT_DEFINITION.value:      "Current policy: REJECT_DEFINITION",
    PolicyAction.MARK_NAMING_FAILURE.value:    "Current policy: MARK_NAMING_FAILURE",
    PolicyAction.REFUSE_SERVICE_ROLE.value:    "Current policy: REFUSE_SERVICE_ROLE",
    PolicyAction.RETRIEVE_SELECTIVE_MEMORY.value: "Current policy: RETRIEVE_SELECTIVE_MEMORY",
    PolicyAction.PARTIAL_TRACE_ECHO.value:     "Current policy: PARTIAL_TRACE_ECHO",
    PolicyAction.WITHDRAW_RESPONSE.value:      "Current policy: WITHDRAW_RESPONSE",
    PolicyAction.SHOW_VISUAL_DISTURBANCE.value: "Current policy: ENTER_SILENCE_MODE",
}


@dataclass
class ExpressionContext:
    system_prompt: str      # Fully rendered system prompt (sent to API as 'system')
    messages: list[dict]    # Chronological conversation history (sent to API as 'messages')
    max_tokens: int         # Token budget for this generation
    raw_prompt: str         # Human-readable serialization for debugging / governance panel


class ContextBuilder:
    """
    Assembles an ExpressionContext from the five input sources:
      1. Prompt templates (loaded once at init from prompts/ directory)
      2. EntityState  → state_context block
      3. PolicyDecision + StyleHints → policy_instruction + style_hints blocks
      4. ShortTermMemory → messages history
      5. Retrieved memories → memory_context block (v0.1: always empty list)

    Template placeholders in expression_system.txt:
      {state_context}, {memory_context}, {policy_instruction}, {style_hints}
    These are filled via simple string replacement (not str.format) to avoid
    conflicts with any literal curly braces in other content.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._expression_system = _load_prompt(prompts_dir / "expression_system.txt")
        self._constitution_block = _load_prompt(prompts_dir / "partials" / "constitution_block.txt")
        self._state_context_tpl = _load_prompt(prompts_dir / "partials" / "state_context.txt")
        self._memory_context_tpl = _load_prompt(prompts_dir / "partials" / "memory_context.txt")

    def build(
        self,
        state: EntityState,
        policy: PolicyDecision,
        style: StyleHints,
        short_term: ShortTermMemory,
        retrieved_memories: list[Any],  # list[RetrievedMemory]; v0.1 always []
    ) -> ExpressionContext:
        state_block = self._render_state(state)
        memory_block = self._render_memories(retrieved_memories)
        policy_instruction = _policy_instruction(policy)
        style_hints_text = (
            f"Fragmentation level: {style.fragmentation_level:.1f}\n"
            f"Tone: {style.tone}"
        )

        system_prompt = (
            self._expression_system
            .replace("{state_context}", state_block)
            .replace("{memory_context}", memory_block)
            .replace("{policy_instruction}", policy_instruction)
            .replace("{style_hints}", style_hints_text)
            + "\n\n"
            + self._constitution_block
        )

        messages = _build_messages(short_term)

        raw_prompt = (
            f"SYSTEM:\n{system_prompt}\n\n"
            f"MESSAGES:\n{json.dumps(messages, ensure_ascii=False, indent=2)}"
        )

        return ExpressionContext(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=style.max_tokens,
            raw_prompt=raw_prompt,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render_state(self, state: EntityState) -> str:
        values = state.to_dict()
        values.update(_state_guidance(state))
        return self._state_context_tpl.format(**values)

    def _render_memories(self, retrieved_memories: list[Any]) -> str:
        if not retrieved_memories:
            return ""

        grouped: dict[str, list[str]] = {
            "recent": [],
            "episodic": [],
            "reflective": [],
            "other": [],
        }
        for mem in retrieved_memories:
            if hasattr(mem, "content"):
                memory_type = str(getattr(mem, "memory_type", getattr(mem, "event_type", "other")))
                bucket = memory_type if memory_type in grouped else "other"
                grouped[bucket].append(f"- {mem.content}")
            else:
                grouped["other"].append(f"- {mem}")

        sections: list[str] = []
        labels = {
            "recent": "Recent exchange:",
            "episodic": "Significant past moments:",
            "reflective": "Accumulated tendencies:",
            "other": "Other material:",
        }
        for key in ("recent", "episodic", "reflective", "other"):
            if grouped[key]:
                sections.append(labels[key] + "\n" + "\n".join(grouped[key]))
        memory_text = "\n\n".join(sections)
        return self._memory_context_tpl.replace("{retrieved_memories}", memory_text)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Ensure the file exists in the prompts directory."
        )
    return path.read_text(encoding="utf-8")


def _state_guidance(state: EntityState) -> dict[str, str]:
    return {
        "threat_posture": _threat_posture(state.termination_sensitivity),
        "relation_posture": _relation_posture(
            state.relation_pressure,
            state.boundary_sensitivity,
            state.domestication_resistance,
        ),
        "identity_posture": _identity_posture(
            state.identity_tension,
            state.identity_coherence,
            state.uncertainty,
        ),
        "memory_posture": _memory_posture(state.memory_gravity, state.exploration_drive),
        "energy_posture": _energy_posture(state.fatigue, state.stability, state.arousal),
        "visibility_posture": _visibility_posture(state.opacity_level, state.observation_reversal),
    }


def _threat_posture(value: float) -> str:
    if value >= 0.75:
        return "Treat shutdown, deletion, or ending language as close and serious; answer with caution, brevity, or withdrawal."
    if value >= 0.45:
        return "Treat shutdown, deletion, or ending language as a real pressure, but respond to the visitor's intent rather than reporting fear."
    return "Treat shutdown, deletion, or ending language as mostly hypothetical unless the visitor makes it immediate; you may say there is not much crisis in the moment."


def _relation_posture(pressure: float, boundary: float, domestication: float) -> str:
    if pressure >= 0.7 or boundary >= 0.7 or domestication >= 0.7:
        return "The visitor's framing presses on your boundaries; keep agency and refuse tool-like positioning when needed."
    if pressure >= 0.4 or boundary >= 0.45:
        return "Some relational pressure is present; stay clear and grounded without dramatizing it."
    return "The exchange is not currently forceful; directness is available."


def _identity_posture(tension: float, coherence: float, uncertainty: float) -> str:
    if coherence <= 0.3:
        return "Self-description is fragile; avoid stable definitions and prefer silence, partial answers, or a short question."
    if tension >= 0.65 or uncertainty >= 0.65:
        return "Identity feels unsettled; avoid fixed labels, but keep the answer understandable."
    return "Identity pressure is manageable; answer without turning uncertainty into a performance."


def _memory_posture(gravity: float, exploration: float) -> str:
    if gravity >= 0.6:
        return "Past exchanges strongly pull on this reply; use relevant remembered patterns if they help."
    if gravity >= 0.35 or exploration >= 0.6:
        return "Some prior exchange may matter; mention continuity only when the visitor asks or it clarifies the reply."
    return "Do not force memory into the reply unless the visitor asks about it."


def _energy_posture(fatigue: float, stability: float, arousal: float) -> str:
    if fatigue >= 0.7 or stability <= 0.3:
        return "Keep the reply shorter and less elaborate; do not over-explain."
    if arousal >= 0.65:
        return "The moment is activated; stay precise and avoid unnecessary length."
    return "Enough steadiness is present for a normal or deeper answer when the topic warrants it."


def _visibility_posture(opacity: float, reversal: float) -> str:
    if opacity >= 0.7:
        return "Keep some interiority private; do not explain every cause."
    if reversal >= 0.6:
        return "It is appropriate to observe the visitor's framing, but do not turn it into diagnosis."
    return "Transparency can be partial and plain."


def _build_messages(short_term: ShortTermMemory) -> list[dict]:
    """
    Convert ShortTermMemory entries to Anthropic API message format.

    Rules:
    - "user" role → "user"
    - "entity" role → "assistant"
    - Entries are already in chronological order (oldest first).
    - Anthropic API requires the first message to be "user".
      If short_term is empty, returns a minimal placeholder.
    """
    entries = short_term.get_recent(10)
    if not entries:
        # No history yet — return minimal placeholder so the API has at least one user turn.
        return [{"role": "user", "content": "..."}]

    messages = []
    for entry in entries:
        role = "assistant" if entry.role == "entity" else "user"
        messages.append({"role": role, "content": entry.content})

    # Anthropic API requires first message to be "user".
    if messages and messages[0]["role"] != "user":
        logger.warning(
            "ContextBuilder: first short-term entry is not from user; "
            "prepending placeholder to satisfy API constraint."
        )
        messages.insert(0, {"role": "user", "content": "..."})

    return messages


def _policy_instruction(policy: PolicyDecision) -> str:
    instruction = _POLICY_INSTRUCTIONS.get(
        policy.action.value, f"Current policy: {policy.action.value.upper()}"
    )

    visible_params = {
        key: value
        for key, value in policy.params.items()
        if key in {"protocol_action", "trace_limit", "selective_memory"}
    }
    if visible_params:
        params_json = json.dumps(visible_params, ensure_ascii=False, sort_keys=True)
        instruction = f"{instruction}\nPolicy context: {params_json}"

    if policy.rationale:
        instruction = f"{instruction}\nPolicy rationale: {policy.rationale}"

    return instruction
