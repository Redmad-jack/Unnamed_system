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
        policy_instruction = _POLICY_INSTRUCTIONS.get(
            policy.action.value, f"Current policy: {policy.action.value.upper()}"
        )
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
        return self._state_context_tpl.format(**state.to_dict())

    def _render_memories(self, retrieved_memories: list[Any]) -> str:
        if not retrieved_memories:
            return ""
        lines = []
        for mem in retrieved_memories:
            # Support both RetrievedMemory dataclass (v0.2) and plain string fallback.
            if hasattr(mem, "content"):
                lines.append(f"- [{mem.memory_type}] {mem.content}")
            else:
                lines.append(f"- {mem}")
        memory_text = "\n".join(lines)
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
