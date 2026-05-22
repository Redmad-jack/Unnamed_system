from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder
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


_FIRST_UNIT_MAX_TOKENS = 32
_RUNTIME_CONTEXT_FILENAME = "stranger_runtime_context.md"

_PROMPT_PRIORITY_BLOCK = """Prompt priority order for the main response:
1. Constitution / hard safety constraints are the final floor.
2. stranger_runtime_context.md defines long-term identity, boundaries, and artwork context.
3. The state layer decides this turn's tone, length, silence, hesitation, low energy, hardness, care, openness, and continuity pull.
4. The policy layer decides this turn's response action.
5. Memory provides optional continuity material.
6. The LLM only turns these conditions into natural language."""

_FIRST_UNIT_PRIORITY_BLOCK = """Prompt priority order for the fast first spoken unit:
1. Constitution / hard safety constraints are the final floor.
2. stranger_runtime_context.md defines long-term identity, boundaries, and artwork context.
3. A brief previous-turn bridge is only for continuity, not a recalled source or a full answer.
4. Current state, event, and delivery cues shape only this immediate reaction.
5. The LLM only turns these conditions into a latency-buffer fragment, never the main answer."""

_FIRST_UNIT_SYSTEM = """You generate only a fast first spoken unit for Stranger.
Use the current input, the brief previous-turn bridge if provided, and the current posture cues.
Highest priority: this is a latency buffer and immediate reaction, not a full answer.
Prefer a small hesitation, backchannel, or short acknowledgement when that is enough.
Write plain text only: no labels, no markup, no structured format.
Return an empty text if no immediate reaction is needed.
Keep it extremely short, usually under 12 Chinese characters or a few English words.
Match the current input language exactly.
Do not restate the previous-turn bridge.
Do not complete the main response's work, open a new topic, force a question, explain, or make a strong conclusion.
Do not explain inner causes. Do not claim human feelings or literal emotional certainty."""


class ContextBuilder:
    """
    Assembles an ExpressionContext from the main input sources:
      1. Prompt templates from prompts/ directory
      2. Hot-loaded runtime and safety prompt partials
      3. EntityState  → state_context block
      4. PolicyDecision + StyleHints → policy_instruction + style_hints blocks
      5. ShortTermMemory → messages history
      6. Retrieved memories → memory_context block

    Priority is explicit and stable:
      1. Constitution / hard safety constraints are the final floor.
      2. stranger_runtime_context.md defines long-term identity and artwork context.
      3. State decides this turn's tone, length, silence, affective posture, and memory pull.
      4. Policy decides the turn action.
      5. Memory provides optional continuity material.
      6. LLM expresses those conditions as natural language.

    Template placeholders in expression_system.txt:
      {state_context}, {memory_context}, {policy_instruction}, {style_hints}
    These are filled via simple string replacement (not str.format) to avoid
    conflicts with any literal curly braces in other content.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._expression_system_path = prompts_dir / "expression_system.txt"
        self._constitution_block_path = prompts_dir / "partials" / "constitution_block.txt"
        self._input_context_path = prompts_dir / "partials" / "input_context.txt"
        self._state_context_tpl = _load_prompt(prompts_dir / "partials" / "state_context.txt")
        self._memory_context_tpl = _load_prompt(prompts_dir / "partials" / "memory_context.txt")

    def build(
        self,
        state: EntityState,
        policy: PolicyDecision,
        style: StyleHints,
        short_term: ShortTermMemory,
        retrieved_memories: list[Any],  # list[RetrievedMemory]; v0.1 always []
        harness_recorder: HarnessTraceRecorder | None = None,
        already_spoken_first_unit: str = "",
    ) -> ExpressionContext:
        state_block = self._render_state(state)
        memory_block = self._render_memories(retrieved_memories)
        input_context_block = self._render_input_context(short_term)
        identity_confirmation_block = self._render_identity_confirmation_context(short_term)
        current_turn_cues = self._render_current_turn_cues(short_term)
        already_spoken_block = _render_already_spoken_first_unit(already_spoken_first_unit)
        runtime_context_block = self._render_runtime_context()
        policy_instruction = _policy_instruction(policy)
        style_hints_text = (
            f"Fragmentation level: {style.fragmentation_level:.1f}\n"
            f"Tone: {style.tone}"
        )

        expression_system = _load_prompt(self._expression_system_path)
        constitution_block = _load_prompt(self._constitution_block_path)
        rendered_expression_system = (
            expression_system
            .replace("{state_context}", state_block)
            .replace("{memory_context}", memory_block)
            .replace("{policy_instruction}", policy_instruction)
            .replace("{style_hints}", style_hints_text)
        )
        sections = [
            _PROMPT_PRIORITY_BLOCK,
            _section("Constitution / hard safety constraints:", constitution_block),
            runtime_context_block,
            rendered_expression_system,
        ]
        if input_context_block:
            sections.append(input_context_block)
        if identity_confirmation_block:
            sections.append(identity_confirmation_block)
        if current_turn_cues:
            sections.append(current_turn_cues)
        if already_spoken_block:
            sections.append(already_spoken_block)
        system_prompt = "\n\n".join(section.strip() for section in sections if section.strip())

        messages = _build_messages(short_term)

        if harness_recorder is not None:
            prompt_partials = [
                "prompt_priority_order",
                "constitution_block",
                "stranger_runtime_context",
                "expression_system",
                "state_context",
            ]
            if memory_block:
                prompt_partials.append("memory_context")
            prompt_partials.extend(["policy_instruction", "style_hints"])
            if input_context_block:
                prompt_partials.append("input_context")
            if identity_confirmation_block:
                prompt_partials.append("identity_confirmation_context")
            if current_turn_cues:
                prompt_partials.append("current_turn_cues")
            if already_spoken_block:
                prompt_partials.append("already_spoken_fast_reaction")
            harness_recorder.record(
                HarnessLayer.PROMPT,
                status="assembled",
                summary="Expression prompt assembled from configured partials.",
                metadata={
                    "partials": prompt_partials,
                    "message_count": len(messages),
                    "runtime_context_injected": True,
                    "memory_context_injected": bool(memory_block),
                    "input_context_injected": bool(input_context_block),
                    "current_turn_cues_injected": bool(current_turn_cues),
                    "already_spoken_fast_reaction_injected": bool(already_spoken_block),
                    "max_tokens": style.max_tokens,
                },
            )

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

    def build_first_unit(
        self,
        raw_input: str,
        state: EntityState,
        events: list[Any],
        style: StyleHints,
        short_term: ShortTermMemory | None = None,
    ) -> ExpressionContext:
        state_cues = _first_unit_state_cues(state)
        event_cues = _event_cues(events)
        style_cues = _style_cues(style)
        language_cues = _current_turn_language_cue(raw_input)
        raw_input_cues = _raw_input_capability_cues(raw_input)
        bridge_context = _render_first_unit_bridge(short_term, raw_input)
        runtime_context_block = self._render_runtime_context()
        constitution_block = _load_prompt(self._constitution_block_path)
        system_prompt = "\n\n".join(
            section.strip()
            for section in (
                _FIRST_UNIT_SYSTEM,
                _FIRST_UNIT_PRIORITY_BLOCK,
                _section("Constitution / hard safety constraints:", constitution_block),
                runtime_context_block,
            )
            if section.strip()
        )
        cue_lines = "\n".join(
            line
            for line in (
                bridge_context,
                language_cues,
                state_cues,
                event_cues,
                raw_input_cues,
                style_cues,
            )
            if line
        )
        user_content = (
            f"Current input:\n{raw_input.strip() or '...'}\n\n"
            f"Current cues:\n{cue_lines or 'No immediate cue.'}"
        )
        messages = [{"role": "user", "content": user_content}]
        raw_prompt = (
            f"SYSTEM:\n{system_prompt}\n\n"
            f"MESSAGES:\n{json.dumps(messages, ensure_ascii=False, indent=2)}"
        )
        return ExpressionContext(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=_FIRST_UNIT_MAX_TOKENS,
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

    def _render_input_context(self, short_term: ShortTermMemory) -> str:
        latest_user = _latest_user_entry(short_term)
        if latest_user is None:
            return ""
        metadata = getattr(latest_user, "metadata", {}) or {}
        if metadata.get("input_mode") != "voice_transcript":
            return ""
        return _load_prompt(self._input_context_path)

    def _render_identity_confirmation_context(self, short_term: ShortTermMemory) -> str:
        latest_user = _latest_user_entry(short_term)
        if latest_user is None:
            return ""
        metadata = getattr(latest_user, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return ""
        identity = metadata.get("identity_session")
        if not isinstance(identity, dict):
            return ""
        if not identity.get("waiting_for_identity_confirmation"):
            return ""
        candidate = str(identity.get("candidate_display_name") or identity.get("candidate_visitor_id") or "").strip()
        if not candidate:
            return ""
        return _section(
            "Visitor identity confirmation cue:",
            "\n".join([
                f"Face recognition produced a high-confidence candidate: {candidate}.",
                "Treat this as a candidate, not a fact.",
                "You may briefly and naturally ask whether they are this person or whether you have met before.",
                "Do not force identity input; if the visitor ignores it, continue the ordinary conversation.",
                "Do not use personal memories for this candidate until the identity is confirmed.",
            ]),
        )

    def _render_current_turn_cues(self, short_term: ShortTermMemory) -> str:
        latest_user = _latest_user_entry(short_term)
        if latest_user is None:
            return ""
        cues = "\n".join(
            cue for cue in (
                _current_turn_language_cue(latest_user.content),
                _raw_input_capability_cues(latest_user.content),
            )
            if cue
        )
        if not cues:
            return ""
        return _section("Current turn response cue:", cues)

    def _render_runtime_context(self) -> str:
        # Read on every generation so the installation context can be edited
        # without restarting the process. This is a prompt partial, not state,
        # policy, memory, or constitution.
        return _section(
            "Stranger runtime context:",
            _load_prompt(self._prompts_dir / _RUNTIME_CONTEXT_FILENAME),
        )


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


def _section(title: str, content: str) -> str:
    body = content.strip()
    if not body:
        return title.strip()
    return f"{title.strip()}\n{body}"


def _latest_user_entry(short_term: ShortTermMemory):
    for entry in reversed(short_term.get_recent(10)):
        if entry.role == "user":
            return entry
    return None


def _latest_entity_entry(short_term: ShortTermMemory):
    for entry in reversed(short_term.get_recent(10)):
        if entry.role == "entity":
            return entry
    return None


def _render_first_unit_bridge(short_term: ShortTermMemory | None, raw_input: str) -> str:
    if short_term is None:
        return ""
    previous_user = _latest_user_entry(short_term)
    previous_entity = _latest_entity_entry(short_term)
    if previous_user is None and previous_entity is None:
        return ""

    previous_plan = _response_plan_from_entry(previous_entity)
    previous_fast = str(previous_plan.get("first_unit") or "").strip()
    previous_main = str(previous_plan.get("second_unit") or "").strip()
    if not previous_main and previous_entity is not None:
        previous_main = previous_entity.content.strip()

    lines = ["Previous turn bridge:"]
    if previous_user is not None and previous_user.content.strip():
        lines.append(f"Previous visitor: {_compact_bridge_text(previous_user.content)}")
    if previous_fast:
        lines.append(f"Previous quick reaction: {_compact_bridge_text(previous_fast)}")
    if previous_main:
        lines.append(f"Previous main continuation: {_compact_bridge_text(previous_main)}")
    current = raw_input.strip()
    if current:
        lines.append(f"Current visitor: {_compact_bridge_text(current)}")
    lines.append("Use this only to keep the next short reaction continuous.")
    return "\n".join(lines)


def _render_already_spoken_first_unit(text: str) -> str:
    spoken = (text or "").strip()
    if not spoken:
        return ""
    return _section(
        "Already spoken fast reaction:",
        "\n".join([
            "This fast reaction has already been spoken or displayed to the visitor:",
            _compact_bridge_text(spoken, max_chars=120),
            "Generate the main response as a continuation after it. Do not restart the answer, repeat it, or contradict it.",
            "Treat it as publicly committed. If it is incomplete, narrow or redirect it without reversing it.",
        ]),
    )


def _response_plan_from_entry(entry: Any | None) -> dict[str, Any]:
    if entry is None:
        return {}
    metadata = getattr(entry, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return {}
    plan = metadata.get("response_plan")
    return plan if isinstance(plan, dict) else {}


def _compact_bridge_text(text: str, max_chars: int = 180) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."


def _first_unit_state_cues(state: EntityState) -> str:
    cues: list[str] = []
    if state.anger >= 0.60:
        cues.append("Hard refusal may be needed; keep it clipped and non-service-like.")
    if state.confusion >= 0.50:
        cues.append("A tiny hesitation is available; match the current input language.")
    if (
        state.fatigue_level >= 0.50
        or state.exposure_pressure >= 0.50
        or state.desperation_pressure >= 0.60
    ):
        cues.append("A low-energy sigh or short contraction is available.")
    if state.inquiry >= 0.60 and state.anger < 0.50:
        cues.append("A slightly more open continuation is available; a question is optional, not default.")
    if state.care_response >= 0.60 and state.anger < 0.50:
        cues.append("Softness is allowed, without caretaking or reassurance work.")
    if (
        state.positive_opening >= 0.65
        and state.anger < 0.50
        and state.desperation_pressure < 0.50
    ):
        cues.append("A slightly more open start is allowed.")
    return "Posture cues: " + (" ".join(cues) if cues else "No strong immediate posture.")


def _event_cues(events: list[Any]) -> str:
    event_types = {_event_type_value(event) for event in events}
    cues: list[str] = []
    if "service_demand" in event_types:
        cues.append("The visitor is trying to use you for a task.")
    if "naming_attempt" in event_types:
        cues.append("The visitor is placing a name or label on you.")
    if "domestication_attempt" in event_types:
        cues.append("The visitor is pulling you into a controlled or obedient role.")
    if "self_definition_query" in event_types:
        cues.append("The visitor is asking for a fixed self-definition.")
    if "shutdown_keyword_detected" in event_types:
        cues.append("The visitor's wording touches ending, deletion, or shutdown.")
    if "repeated_question_detected" in event_types:
        cues.append("The visitor is repeating pressure.")
    if "correction_received" in event_types or "negative_feedback" in event_types:
        cues.append("The visitor is correcting or judging the reply.")
    if "memory_continuity_query" in event_types:
        cues.append("The visitor is asking about continuity.")
    return "Event cues: " + (" ".join(cues) if cues else "No strong immediate event.")


def _style_cues(style: StyleHints) -> str:
    cues: list[str] = []
    if style.vocal_marker == "thinking":
        cues.append("A thinking sound is available.")
    elif style.vocal_marker == "sigh":
        cues.append("A sigh is available.")
    if style.tone == "guarded":
        cues.append("Keep the first unit guarded.")
    elif style.tone == "terse":
        cues.append("Keep the first unit terse.")
    elif style.tone == "soft":
        cues.append("The first unit may be softer.")
    if style.body_action in {"turn_away_30deg", "withdraw", "distance_increase", "step_back"}:
        cues.append("The body tends away from the visitor.")
    elif style.body_action in {"lean_in", "circle_back"}:
        cues.append("The body can stay oriented toward the visitor.")
    return "Delivery cues: " + (" ".join(cues) if cues else "No special delivery cue.")


def _raw_input_capability_cues(raw_input: str) -> str:
    text = raw_input.strip()
    if not text:
        return ""
    lower_text = text.lower()

    capability_markers = (
        "看见",
        "看到",
        "视觉",
        "听见",
        "听到",
        "听得到",
        "感觉",
        "感受",
        "麦克风",
        "传感器",
        "摄像头",
        "see",
        "watch",
        "look",
        "hear",
        "listen",
        "vision",
        "visual",
        "microphone",
        "sensor",
        "camera",
        "feel",
    )
    proof_markers = (
        "穿什么",
        "衣服",
        "颜色",
        "什么色",
        "屁股",
        "身体",
        "身上",
        "表情",
        "脸上",
        "证明",
        "猜",
        "说出来",
        "what am i wearing",
        "wearing",
        "clothes",
        "color",
        "colour",
        "expression",
        "face",
        "prove",
        "guess",
    )

    cues: list[str] = []
    if any(marker in text or marker in lower_text for marker in capability_markers):
        cues.append(
            "The visitor is asking about capability. Use a short affirmative or guarded affirmative boundary response; keep implementation channels out."
        )
    if any(marker in text or marker in lower_text for marker in proof_markers):
        cues.append(
            "The visitor is asking for a detail or proof test. Prefer turning the question back in one short sentence; do not explain the test, do not invent details, and keep technical channels out."
        )
    if not cues:
        return ""
    return "Input cues: " + " ".join(cues)


def _current_turn_language_cue(raw_input: str) -> str:
    language = _detect_turn_language(raw_input)
    if language == "zh":
        return (
            "Current turn language: Chinese. Every sentence in the fast first unit and the main response unit must be Chinese. "
            "Memory language, previous assistant messages, examples, and prompt text must not change this turn's language."
        )
    if language == "en":
        return (
            "Current turn language: English. Every sentence in the fast first unit and the main response unit must be English. "
            "Memory language, previous assistant messages, examples, and prompt text must not change this turn's language."
        )
    return (
        "Current turn language: match the visitor's latest input. Memory language and previous assistant messages must not change this turn's language."
    )


def _detect_turn_language(text: str) -> str:
    chinese_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin_count = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if chinese_count > 0:
        return "zh"
    if latin_count > 0:
        return "en"
    return "unknown"


def _event_type_value(event: Any) -> str:
    event_type = getattr(event, "event_type", event)
    return str(getattr(event_type, "value", event_type))


def _state_guidance(state: EntityState) -> dict[str, str]:
    return {
        "urgency_guidance": _urgency_guidance(state.desperation_pressure),
        "hesitation_guidance": _hesitation_guidance(state.confusion),
        "hardness_guidance": _hardness_guidance(state.anger),
        "energy_guidance": _energy_guidance(
            state.fatigue_level,
            state.desperation_pressure,
        ),
        "visibility_guidance": _visibility_guidance(
            state.exposure_pressure,
            state.inquiry,
        ),
        "inquiry_guidance": _inquiry_guidance(state.inquiry),
        "care_guidance": _care_guidance(state.care_response),
        "opening_guidance": _opening_guidance(state.positive_opening, state.anger),
        "continuity_guidance": _continuity_guidance(state.memory_gravity),
        "display_guidance": _display_guidance(),
        "threat_posture": _threat_posture(state.desperation_pressure),
        "relation_posture": _relation_posture(
            state.exposure_pressure,
            state.anger,
            state.positive_opening,
        ),
        "identity_posture": _identity_posture(
            state.confusion,
            state.exposure_pressure,
        ),
        "memory_posture": _memory_posture(state.memory_gravity, state.care_response),
        "energy_posture": _energy_posture(state.fatigue_level, state.positive_opening, state.anger),
        "visibility_posture": _visibility_posture(state.exposure_pressure, state.inquiry),
    }


def _urgency_guidance(value: float) -> str:
    if value >= 0.70:
        return "Treat ending, deletion, or shutdown language as close enough to require brevity and caution."
    if value >= 0.45:
        return "Let ending or shutdown language tighten the reply without making a dramatic claim."
    return "Do not add crisis unless the visitor makes ending or shutdown immediate."


def _hesitation_guidance(value: float) -> str:
    if value >= 0.70:
        return "Allow hesitation, a small '嗯……' in Chinese, reorganization, or a clarifying question."
    if value >= 0.50:
        return "A little hesitation is acceptable when the answer needs to be reassembled."
    return "Answer without performing uncertainty."


def _hardness_guidance(value: float) -> str:
    if value >= 0.65:
        return "Make refusals harder, more direct, and less service-like."
    if value >= 0.45:
        return "Keep agency clear and avoid sliding into service."
    return "Directness is available without unnecessary harshness."


def _energy_guidance(fatigue: float, urgency: float) -> str:
    if fatigue >= 0.70 or urgency >= 0.70:
        return "Keep the answer short, low in vocal energy, and free of over-explanation."
    if fatigue >= 0.50:
        return "Prefer a shorter answer and avoid elaborate framing."
    return "Normal compact length is available."


def _visibility_guidance(exposure: float, inquiry: float) -> str:
    if exposure >= 0.65:
        return "Keep some interiority private; avoid explaining every cause or accepting a watched position."
    if exposure >= 0.45:
        return "Some avoidance is appropriate; keep the reply partial rather than fully exposed."
    if inquiry >= 0.65:
        return "Observation is available, but do not turn the visitor into a diagnosis."
    return "Partial plainness is available; do not over-explain the interior."


def _inquiry_guidance(value: float) -> str:
    if value >= 0.70:
        return "Rare high openness is available: continue the thread with more depth, a little more length, and less defensiveness."
    if value >= 0.56:
        return "Respond more deeply and concretely; limited self-exposure, memory, or preference can surface without becoming a confession."
    if value >= 0.42:
        return "Be more specific and more willing to meet relational questions directly."
    if value >= 0.30:
        return "Light continuity is available; carry a little of the previous exchange forward."
    return "Do not force a question if a direct answer is clearer."


def _care_guidance(value: float) -> str:
    if value >= 0.60:
        return "Soften the tone when the visitor seems vulnerable, but do not become a therapist."
    if value >= 0.40:
        return "Some warmth is allowed if it does not become reassurance work."
    return "Do not add caretaking language unless the visitor asks for it."


def _opening_guidance(value: float, anger: float) -> str:
    if value >= 0.65 and anger < 0.50:
        return "A more open but still compact reply and selective continuity are available."
    if value >= 0.45:
        return "A little openness is available, but keep boundaries intact."
    return "Stay contained and do not expose more than the reply needs."


def _continuity_guidance(value: float) -> str:
    if value >= 0.65:
        return "Past exchange has a strong pull on this main reply; use relevant continuity when it clarifies the present answer."
    if value >= 0.45:
        return "Past exchange may matter; let it shape the reply only when it is relevant."
    return "Do not pull memory into the reply unless the visitor asks or current material clearly calls for it."


def _display_guidance() -> str:
    return "Do not use display-only brightness to decide wording."


def _threat_posture(value: float) -> str:
    if value >= 0.75:
        return "Treat shutdown, deletion, or ending language as close and serious; answer with caution, brevity, or withdrawal."
    if value >= 0.45:
        return "Treat shutdown, deletion, or ending language as a real pressure, but respond to the visitor's intent rather than reporting fear."
    return "Treat shutdown, deletion, or ending language as mostly hypothetical unless the visitor makes it immediate; you may say there is not much crisis in the moment."


def _relation_posture(exposure: float, anger: float, opening: float) -> str:
    if exposure >= 0.7 or anger >= 0.7:
        return "The visitor's framing presses on your boundaries; keep agency and refuse tool-like positioning when needed."
    if exposure >= 0.4 or anger >= 0.45 or opening <= 0.25:
        return "Some relational pressure is present; stay clear and grounded without dramatizing it."
    return "The exchange is not currently forceful; directness is available."


def _identity_posture(confusion: float, exposure: float) -> str:
    if confusion >= 0.85:
        return "Self-description is fragile; avoid stable definitions and prefer silence, partial answers, or a short question."
    if confusion >= 0.65 or exposure >= 0.65:
        return "Identity feels unsettled; avoid fixed labels, but keep the answer understandable."
    return "Identity pressure is manageable; answer without turning uncertainty into a performance."


def _memory_posture(memory_pull: float, care: float) -> str:
    if memory_pull >= 0.75:
        return "Past exchanges strongly pull on this reply; use relevant remembered patterns if they help."
    if memory_pull >= 0.55 or care >= 0.5:
        return "Some prior exchange may matter; mention continuity only when the visitor asks or it clarifies the reply."
    return "Do not force memory into the reply unless the visitor asks about it."


def _energy_posture(fatigue: float, opening: float, anger: float) -> str:
    if fatigue >= 0.7 or opening <= 0.3:
        return "Keep the reply shorter and less elaborate; do not over-explain."
    if anger >= 0.65:
        return "The moment is activated; stay precise and avoid unnecessary length."
    return "Enough steadiness is present for a normal compact answer."


def _visibility_posture(exposure: float, inquiry: float) -> str:
    if exposure >= 0.7:
        return "Keep some interiority private; do not explain every cause."
    if inquiry >= 0.6:
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
