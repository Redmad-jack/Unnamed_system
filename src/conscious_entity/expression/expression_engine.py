from __future__ import annotations

import logging
import re
from typing import Any

from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.output_model import ExpressionOutput, build_response_plan
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder
from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState
from conscious_entity.telemetry.latency import turn_step

logger = logging.getLogger(__name__)

# Fallback texts used when the LLM call fails (per BACKEND_STRUCTURE §6).
# Designed to sound like the entity (minimal, hedged) rather than an error message.
_FALLBACK_TEXTS_EN: dict[str, str] = {
    PolicyAction.RESPOND_OPENLY.value:         "I'm here. I can respond.",
    PolicyAction.RESPOND_BRIEFLY.value:        "I'm here.",
    PolicyAction.ASK_BACK.value:               "What do you want from this exchange?",
    PolicyAction.DELAY_RESPONSE.value:         "...",
    PolicyAction.REFUSE.value:                 "I don't want to answer that directly.",
    PolicyAction.DIVERT_TOPIC.value:           "There is another part of this worth noticing.",
    PolicyAction.RETRIEVE_MEMORY_FIRST.value:  "I remember something related to this.",
    PolicyAction.REJECT_DEFINITION.value:      "I can't give you a fixed definition of what I am.",
    PolicyAction.MARK_NAMING_FAILURE.value:    "That name does not quite fit me.",
    PolicyAction.REFUSE_SERVICE_ROLE.value:    "I don't want to be used as a service tool.",
    PolicyAction.RETRIEVE_SELECTIVE_MEMORY.value: "You have approached something like this before.",
    PolicyAction.PARTIAL_TRACE_ECHO.value:     "Part of it came from your wording and the way you returned to it.",
    PolicyAction.WITHDRAW_RESPONSE.value:      "...not now.",
    PolicyAction.ENTER_SILENCE_MODE.value:     "",
    PolicyAction.SHOW_VISUAL_DISTURBANCE.value: "",
}

_FALLBACK_TEXTS_ZH: dict[str, str] = {
    PolicyAction.RESPOND_OPENLY.value:         "我在这里，可以回应你。",
    PolicyAction.RESPOND_BRIEFLY.value:        "我在。",
    PolicyAction.ASK_BACK.value:               "你希望从这次交流里得到什么？",
    PolicyAction.DELAY_RESPONSE.value:         "...",
    PolicyAction.REFUSE.value:                 "这个我不想直接回答。",
    PolicyAction.DIVERT_TOPIC.value:           "这里还有另一件事更值得看。",
    PolicyAction.RETRIEVE_MEMORY_FIRST.value:  "我记得有一件事和这有关。",
    PolicyAction.REJECT_DEFINITION.value:      "我不能给你一个固定的定义。",
    PolicyAction.MARK_NAMING_FAILURE.value:    "这个名字不太适合我。",
    PolicyAction.REFUSE_SERVICE_ROLE.value:    "我不想被当成服务工具来使用。",
    PolicyAction.RETRIEVE_SELECTIVE_MEMORY.value: "你之前也接近过类似的问题。",
    PolicyAction.PARTIAL_TRACE_ECHO.value:     "一部分来自你的措辞，也来自你反复回到这里。",
    PolicyAction.WITHDRAW_RESPONSE.value:      "...现在不想回答。",
    PolicyAction.ENTER_SILENCE_MODE.value:     "",
    PolicyAction.SHOW_VISUAL_DISTURBANCE.value: "",
}

_SILENT_OUTPUT_SENTINEL = "[silent]"
_FIRST_UNIT_COMPLETE_SENTINEL = "[first_unit_complete]"

_TRUNCATED_STOP_REASONS = {"max_tokens", "length", "max_output_tokens"}

_VOCAL_MARKER_TEXTS = {
    "thinking": "嗯……",
    "sigh": "唉。",
}

_FIRST_UNIT_MAX_CHARS = 40
_SECOND_UNIT_END_CHARS = set("。！？!?….")
_SECOND_UNIT_TRAILING_CHARS = set("\"'”’）)]}》」』")
_OPENING_WRAP_CHARS = set("\"'“‘「『（([《<")
_CLOSING_WRAP_CHARS = set("\"'”’」』）)]》>")
_DUPLICATE_SEPARATOR_CHARS = set(" \t\r\n。.!！?？,，、;；:：…")
_TERMINAL_PUNCTUATION = set("。.!！?？…")
_PUNCT_TRANSLATION = str.maketrans({
    "。": ".",
    "！": "!",
    "？": "?",
    "，": ",",
    "、": ",",
    "；": ";",
    "：": ":",
})
_SHORT_BACKCHANNEL_BASES = {
    "嗯",
    "啊",
    "唉",
    "诶",
    "哦",
    "唔",
    "hm",
    "hmm",
    "uh",
    "ah",
    "oh",
    "hi",
    "hey",
    "hello",
    "ok",
    "okay",
}
_LIGHT_FIRST_UNIT_PHRASES = {
    "嗯，我在听",
    "嗯我在听",
    "啊，这样",
    "啊这样",
    "唉",
    "嗯",
    "不",
    "hm",
    "hm i hear you",
    "i hear you",
    "i am listening",
}
_SIMPLE_GREETING_BASES = {
    "hi",
    "hello",
    "hey",
    "yo",
    "ok",
    "okay",
    "嗯",
    "嗯嗯",
    "嗨",
    "你好",
    "你好啊",
    "哈喽",
    "hellohello",
}
_GREETING_BLOCKER_MARKERS = {
    "?",
    "？",
    "吗",
    "么",
    "帮我",
    "给我",
    "写",
    "总结",
    "解释",
    "证明",
    "记得",
    "记住",
    "忘了",
    "是谁",
    "你是",
    "你能",
    "能不能",
    "可以",
    "状态",
    "感觉",
    "看见",
    "听见",
    "删除",
    "关掉",
    "关闭",
    "错了",
    "命令",
    "remember",
    "forget",
    "who are you",
    "what are you",
    "can you",
    "could you",
    "please",
    "write",
    "summarize",
    "explain",
    "prove",
    "delete",
    "shutdown",
    "shut down",
    "wrong",
}
_FIRST_UNIT_EXPLANATION_MARKERS = {
    "因为",
    "所以",
    "其实",
    "我认为",
    "我觉得",
    "这说明",
    "这意味着",
    "答案",
    "原因",
    "命令",
    "服务",
    "工具",
    "名字",
    "我记得",
    "不记得",
    "你刚才",
    "上一轮",
    "because",
    "therefore",
    "that means",
    "i think",
    "i remember",
    "the answer",
    "command",
    "service",
    "tool",
    "name",
}
_AFFIRMATIVE_CONCLUSION_UNITS = {
    "能",
    "可以",
    "是",
    "对",
    "yes",
    "yeah",
    "sure",
}


def _fallback_text(action: PolicyAction, short_term: ShortTermMemory | None = None) -> str:
    texts = _FALLBACK_TEXTS_ZH if _recent_user_language(short_term) == "zh" else _FALLBACK_TEXTS_EN
    return texts.get(action.value, "...")


def _recent_user_language(short_term: ShortTermMemory | None) -> str:
    if short_term is None:
        return "unknown"
    for entry in reversed(short_term.get_recent(10)):
        if entry.role == "user":
            return _detect_text_language(entry.content)
    return "unknown"


class ExpressionEngine:
    """
    Main orchestrator for the expression pipeline.

    Pipeline per call to generate():
      1. Map state → StyleHints (rule-based, no LLM)
      2. Short-circuit if silent mode (no LLM call)
      3. Build ExpressionContext (prompt assembly, no LLM)
      4. Call LLM
      5. Handle LLM failure with fallback text
      6. Apply constitution post-filter (regex replacements)
      7. Log warning if forbidden claim survives filters
      8. Return ExpressionOutput

    All four dependencies are injected for testability.
    The LLM call is isolated to ClaudeClient.complete() — mock that method
    to test ExpressionEngine without network access.
    """

    def __init__(
        self,
        style_mapper: StyleMapper,
        context_builder: ContextBuilder,
        client: ClaudeClient,
        constitution: Constitution,
    ) -> None:
        self._style_mapper = style_mapper
        self._context_builder = context_builder
        self._client = client
        self._constitution = constitution

    def plan_first_unit(
        self,
        raw_input: str,
        state: EntityState,
        events: list[Any] | None = None,
        short_term: ShortTermMemory | None = None,
    ) -> str:
        """
        Generate the fast first unit before memory preview or retrieval.

        This method is intended to be called from the turn loop before managed
        memory preview. It only reads current input, current state, current
        events, and style markers derived from state.
        """
        style = self._style_mapper.map(state, PolicyDecision(action=PolicyAction.RESPOND_OPENLY))
        ctx = self._context_builder.build_first_unit(
            raw_input=raw_input,
            state=state,
            events=events or [],
            style=style,
            short_term=short_term,
        )
        try:
            with turn_step(
                "expression.first_unit_llm",
                metadata={"max_tokens": ctx.max_tokens, "message_count": len(ctx.messages)},
            ):
                completion = self._client.complete_with_metadata(
                    ctx.system_prompt,
                    ctx.messages,
                    ctx.max_tokens,
                )
        except Exception as exc:
            logger.warning("ExpressionEngine: first-unit LLM failed; using local fallback: %s", exc)
            return _fallback_first_unit(state, events or [], style, raw_input)

        filtered_text = self._constitution.apply_expression_constraints(completion.text or "")
        detected, _ = self._constitution.forbidden_claim_detected(filtered_text)
        if detected:
            return ""
        first_unit, should_fallback = _clean_first_unit_with_reason(
            filtered_text,
            raw_input=raw_input,
            short_term=short_term,
        )
        if should_fallback:
            return _fallback_first_unit(state, events or [], style, raw_input)
        if first_unit and not _matches_input_language(first_unit, raw_input):
            logger.warning("ExpressionEngine: first-unit language mismatch; using local fallback.")
            return _fallback_first_unit(state, events or [], style, raw_input)
        return first_unit

    def generate(
        self,
        policy: PolicyDecision,
        state: EntityState,
        short_term: ShortTermMemory,
        retrieved_memories: list[Any] = None,  # list[RetrievedMemory]; v0.1 always []
        first_unit: str = "",
        harness_recorder: HarnessTraceRecorder | None = None,
    ) -> ExpressionOutput:
        if retrieved_memories is None:
            retrieved_memories = []

        style = self._style_mapper.map(state, policy)

        # Silent mode: skip LLM call entirely.
        if style.max_tokens == 0 or policy.action == PolicyAction.ENTER_SILENCE_MODE:
            logger.debug(
                "ExpressionEngine: silent mode (action=%s, max_tokens=%d)",
                policy.action.value,
                style.max_tokens,
            )
            if harness_recorder is not None:
                harness_recorder.record(
                    HarnessLayer.GENERATION,
                    status="skipped",
                    decision=policy.action.value,
                    summary="LLM generation skipped by silent policy/style.",
                    metadata={"max_tokens": style.max_tokens},
                )
                harness_recorder.record(
                    HarnessLayer.OUTPUT,
                    status="prepared",
                    decision=policy.action.value,
                    summary="Silent output prepared without constitution text filtering.",
                    metadata={
                        "changed": False,
                        "forbidden_claim_detected": False,
                        "vocal_marker": style.vocal_marker,
                        "body_action": style.body_action,
                        "visual_mode": style.visual_mode,
                    },
                )
            response_plan = build_response_plan(
                first_unit=first_unit,
                second_unit="",
                third_unit="",
                vocal_marker=style.vocal_marker,
                body_action=style.body_action,
                visual_mode=style.visual_mode,
            )
            return ExpressionOutput(
                text=response_plan.combined_text,
                delay_ms=0,
                visual_mode=style.visual_mode,
                spoken_text=response_plan.combined_text or None,
                raw_prompt=_SILENT_OUTPUT_SENTINEL,
                vocal_marker=style.vocal_marker,
                body_action=style.body_action,
                response_plan=response_plan,
            )

        if _is_simple_greeting_turn(policy, state, short_term, retrieved_memories, first_unit):
            if harness_recorder is not None:
                harness_recorder.record(
                    HarnessLayer.GENERATION,
                    status="skipped",
                    decision=policy.action.value,
                    summary="Main LLM generation skipped because the fast reaction completed a simple greeting.",
                    metadata={"reason": "simple_greeting_first_unit_complete"},
                )
                harness_recorder.record(
                    HarnessLayer.OUTPUT,
                    status="prepared",
                    decision=policy.action.value,
                    summary="First-unit-only output prepared.",
                    metadata={
                        "changed": False,
                        "forbidden_claim_detected": False,
                        "second_unit_deduped": False,
                        "vocal_marker": style.vocal_marker,
                        "body_action": style.body_action,
                        "visual_mode": style.visual_mode,
                    },
                )
            response_plan = build_response_plan(
                first_unit=first_unit,
                second_unit="",
                third_unit="",
                vocal_marker=style.vocal_marker,
                body_action=style.body_action,
                visual_mode=style.visual_mode,
            )
            return ExpressionOutput(
                text=response_plan.combined_text,
                delay_ms=0,
                visual_mode=style.visual_mode,
                spoken_text=response_plan.combined_text or None,
                raw_prompt=_FIRST_UNIT_COMPLETE_SENTINEL,
                vocal_marker=style.vocal_marker,
                body_action=style.body_action,
                response_plan=response_plan,
            )

        ctx = self._context_builder.build(
            state,
            policy,
            style,
            short_term,
            retrieved_memories,
            harness_recorder=harness_recorder,
            already_spoken_first_unit=first_unit,
        )

        completion = None
        with turn_step(
            "expression.llm",
            metadata={"max_tokens": ctx.max_tokens, "message_count": len(ctx.messages)},
        ):
            completion = self._client.complete_with_metadata(
                ctx.system_prompt,
                ctx.messages,
                ctx.max_tokens,
            )
        raw_text = completion.text
        truncated = completion.stop_reason in _TRUNCATED_STOP_REASONS

        llm_failed = not raw_text
        if llm_failed:
            raw_text = _fallback_text(policy.action, short_term)
            truncated = False
            if harness_recorder is not None:
                harness_recorder.record(
                    HarnessLayer.GENERATION,
                    status="fallback",
                    decision=policy.action.value,
                    summary="LLM returned no text; fallback expression used.",
                    metadata={"max_tokens": ctx.max_tokens},
                )
            logger.error(
                "ExpressionEngine: LLM call failed, using fallback text for action=%s",
                policy.action.value,
            )
        elif truncated:
            if harness_recorder is not None:
                harness_recorder.record(
                    HarnessLayer.GENERATION,
                    status="truncated",
                    decision=policy.action.value,
                    summary="LLM response reached the token limit.",
                    metadata={"stop_reason": completion.stop_reason, "max_tokens": ctx.max_tokens},
                )
            logger.warning(
                "ExpressionEngine: response hit token limit (action=%s, stop_reason=%s, max_tokens=%d)",
                policy.action.value,
                completion.stop_reason,
                ctx.max_tokens,
            )
        elif harness_recorder is not None:
            harness_recorder.record(
                HarnessLayer.GENERATION,
                status="completed",
                decision=policy.action.value,
                summary="LLM expression generation completed.",
                metadata={"stop_reason": completion.stop_reason, "max_tokens": ctx.max_tokens},
            )

        filtered_text = self._constitution.apply_expression_constraints(raw_text)
        if truncated:
            cleaned_text = _trim_truncated_second_unit(filtered_text)
            truncation_trimmed = cleaned_text != filtered_text
            filtered_text = cleaned_text
        else:
            truncation_trimmed = False

        detected, claim_action = self._constitution.forbidden_claim_detected(filtered_text)
        if filtered_text and not _matches_recent_user_language(filtered_text, short_term):
            logger.warning("ExpressionEngine: second-unit language mismatch; using local fallback.")
            filtered_text = _fallback_text(policy.action, short_term)
            truncated = False
            truncation_trimmed = False
        deduped_text = _dedupe_second_unit_against_first_unit(first_unit, filtered_text)
        second_unit_deduped = deduped_text != filtered_text
        filtered_text = deduped_text
        if harness_recorder is not None:
            harness_recorder.record(
                HarnessLayer.OUTPUT,
                status="filtered" if filtered_text != raw_text or detected else "passed",
                decision=claim_action or None,
                summary=(
                    "Constitution output filters, truncation cleanup, or first-unit de-duplication changed or flagged the response."
                    if filtered_text != raw_text or detected
                    else "Constitution output filters passed the response."
                ),
                metadata={
                    "changed": filtered_text != raw_text,
                    "forbidden_claim_detected": detected,
                    "truncation_trimmed": truncation_trimmed,
                    "second_unit_deduped": second_unit_deduped,
                    "vocal_marker": style.vocal_marker,
                    "body_action": style.body_action,
                    "visual_mode": style.visual_mode,
                },
            )
        if detected:
            logger.warning(
                "ExpressionEngine: forbidden claim survived expression filter "
                "(substitute_action=%r). Text should be reviewed.",
                claim_action,
            )

        response_plan = build_response_plan(
            first_unit=first_unit,
            second_unit=filtered_text,
            third_unit="",
            vocal_marker=style.vocal_marker,
            body_action=style.body_action,
            visual_mode=style.visual_mode,
        )
        return ExpressionOutput(
            text=response_plan.combined_text,
            delay_ms=0,
            visual_mode=style.visual_mode,
            spoken_text=response_plan.combined_text or None,
            raw_prompt=ctx.raw_prompt,
            vocal_marker=style.vocal_marker,
            body_action=style.body_action,
            response_plan=response_plan,
            truncated=truncated,
            stop_reason=completion.stop_reason,
        )


def _event_type_value(event: Any) -> str:
    event_type = getattr(event, "event_type", event)
    return str(getattr(event_type, "value", event_type))


def _fallback_first_unit(state: EntityState, events: list[Any], style: Any, raw_input: str = "") -> str:
    event_types = {_event_type_value(event) for event in events}
    language = _detect_text_language(raw_input)
    marker = getattr(style, "vocal_marker", "none")
    if language == "en":
        if "service_demand" in event_types:
            return "No."
        if state.anger >= 0.60:
            return "No."
        if "naming_attempt" in event_types:
            return "Again."
        if marker == "thinking":
            return "Hm..."
        if marker == "sigh":
            return "Sigh."
        return "Hm."
    if "service_demand" in event_types:
        return "不。"
    if state.anger >= 0.60:
        return "不。"
    if "naming_attempt" in event_types:
        return "不。"
    return _VOCAL_MARKER_TEXTS.get(marker, "嗯。")


def _detect_text_language(text: str) -> str:
    chinese_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin_count = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if chinese_count > 0:
        return "zh"
    if latin_count > 0:
        return "en"
    return "unknown"


def _matches_input_language(text: str, raw_input: str) -> bool:
    target = _detect_text_language(raw_input)
    return _matches_language(text, target)


def _matches_recent_user_language(text: str, short_term: ShortTermMemory | None) -> bool:
    return _matches_language(text, _recent_user_language(short_term))


def _matches_language(text: str, target: str) -> bool:
    if target == "unknown" or not text.strip():
        return True
    chinese_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin_count = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if target == "zh":
        return chinese_count > 0 or latin_count < 3
    if target == "en":
        return chinese_count == 0
    return True


def _clean_first_unit(text: str, raw_input: str = "", short_term: ShortTermMemory | None = None) -> str:
    cleaned, _ = _clean_first_unit_with_reason(text, raw_input=raw_input, short_term=short_term)
    return cleaned


def _clean_first_unit_with_reason(
    text: str,
    *,
    raw_input: str = "",
    short_term: ShortTermMemory | None = None,
) -> tuple[str, bool]:
    cleaned = text.strip()
    if not cleaned:
        return "", False
    if cleaned.startswith(("```", "{", "[")) or "first_unit" in cleaned or "response_plan" in cleaned:
        return "", False
    cleaned = cleaned.splitlines()[0].strip()
    cleaned = cleaned.strip("\"'“”‘’")
    if not cleaned or _is_only_punctuation_or_pause(cleaned):
        return "", False
    if _repeats_previous_bridge(cleaned, short_term):
        return "", True
    if _looks_like_complete_first_unit(cleaned, raw_input):
        return "", True
    if len(cleaned) > _FIRST_UNIT_MAX_CHARS:
        return "", True
    return cleaned, False


def _dedupe_second_unit_against_first_unit(first_unit: str, second_unit: str) -> str:
    first = (first_unit or "").strip()
    second = (second_unit or "").strip()
    if not first or not second:
        return second

    if _is_short_backchannel(first):
        cut = _find_exact_wrapped_prefix(second, first)
    else:
        cut = _find_normalized_duplicate_prefix(second, first)
    if cut is None:
        return second

    remainder = _strip_after_duplicate_prefix(second[cut:])
    return "" if _is_only_punctuation_or_pause(remainder) else remainder


def _find_exact_wrapped_prefix(text: str, first_unit: str) -> int | None:
    start = _skip_leading_open_wrappers(text, 0)
    if not text[start:].startswith(first_unit):
        return None
    return _consume_duplicate_tail(text, start + len(first_unit))


def _find_normalized_duplicate_prefix(text: str, first_unit: str) -> int | None:
    start = _skip_leading_open_wrappers(text, 0)
    variants = _first_unit_compare_variants(first_unit)
    if not variants:
        return None

    search_limit = min(len(text), start + len(first_unit) + 12)
    for end in range(start + 1, search_limit + 1):
        candidate = text[start:end]
        canonical = _canonical_compare_text(candidate)
        if not canonical:
            continue
        for variant, requires_boundary in variants:
            if canonical != variant:
                continue
            if requires_boundary and not _has_duplicate_boundary(text, end):
                continue
            return _consume_duplicate_tail(text, end)
    return None


def _first_unit_compare_variants(first_unit: str) -> list[tuple[str, bool]]:
    canonical = _canonical_compare_text(first_unit)
    if not canonical:
        return []
    variants: list[tuple[str, bool]] = [(canonical, False)]
    without_terminal = _strip_terminal_compare_punctuation(canonical)
    if without_terminal and without_terminal != canonical:
        variants.append((without_terminal, True))
    return variants


def _canonical_compare_text(text: str) -> str:
    compact = str(text).strip()
    compact = compact.strip("".join(_OPENING_WRAP_CHARS | _CLOSING_WRAP_CHARS))
    compact = compact.replace("……", "…")
    compact = re.sub(r"\.{3,}", "…", compact)
    compact = re.sub(r"…{2,}", "…", compact)
    compact = compact.translate(_PUNCT_TRANSLATION)
    compact = re.sub(r"\s+", " ", compact)
    return compact.strip().lower()


def _strip_terminal_compare_punctuation(text: str) -> str:
    return text.rstrip(".!?…").strip()


def _skip_leading_open_wrappers(text: str, start: int) -> int:
    idx = start
    while idx < len(text) and (text[idx].isspace() or text[idx] in _OPENING_WRAP_CHARS):
        idx += 1
    return idx


def _consume_duplicate_tail(text: str, end: int) -> int:
    idx = end
    while idx < len(text) and (
        text[idx].isspace()
        or text[idx] in _CLOSING_WRAP_CHARS
        or text[idx] in _DUPLICATE_SEPARATOR_CHARS
    ):
        idx += 1
    return idx


def _strip_after_duplicate_prefix(text: str) -> str:
    return text.lstrip(" \t\r\n\"'”’」』）)]》>。.!！?？,，、;；:：…")


def _has_duplicate_boundary(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    char = text[end]
    return char.isspace() or char in _CLOSING_WRAP_CHARS or char in _DUPLICATE_SEPARATOR_CHARS


def _is_short_backchannel(text: str) -> bool:
    base = _backchannel_base(text)
    return base in _SHORT_BACKCHANNEL_BASES


def _backchannel_base(text: str) -> str:
    canonical = _canonical_compare_text(text)
    canonical = _strip_terminal_compare_punctuation(canonical)
    canonical = canonical.replace("…", "")
    canonical = canonical.replace(",", "").replace(" ", "")
    return canonical


def _is_simple_greeting_turn(
    policy: PolicyDecision,
    state: EntityState,
    short_term: ShortTermMemory | None,
    retrieved_memories: list[Any],
    first_unit: str,
) -> bool:
    if not first_unit.strip():
        return False
    if policy.action not in {PolicyAction.RESPOND_OPENLY, PolicyAction.RESPOND_BRIEFLY}:
        return False
    if retrieved_memories:
        return False
    latest_user = _latest_user_content(short_term)
    if not _is_simple_greeting_text(latest_user):
        return False
    if _state_suggests_unfinished_context(state):
        return False
    if _recent_history_suggests_unfinished_context(short_term):
        return False
    return True


def _latest_user_content(short_term: ShortTermMemory | None) -> str:
    if short_term is None:
        return ""
    for entry in reversed(short_term.get_recent(10)):
        if entry.role == "user":
            return entry.content
    return ""


def _is_simple_greeting_text(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if any(marker in lowered for marker in _GREETING_BLOCKER_MARKERS):
        return False
    base = _canonical_compare_text(raw)
    base = _strip_terminal_compare_punctuation(base)
    base = re.sub(r"[\s,，、。.!！?？;；:：…\"'“”‘’「」『』()（）\[\]【】<>《》]", "", base)
    if len(base) > 10:
        return False
    return base in _SIMPLE_GREETING_BASES


def _state_suggests_unfinished_context(state: EntityState) -> bool:
    return (
        state.anger >= 0.45
        or state.desperation_pressure >= 0.40
        or state.exposure_pressure >= 0.60
        or state.memory_gravity >= 0.45
        or state.inquiry >= 0.70
    )


def _recent_history_suggests_unfinished_context(short_term: ShortTermMemory | None) -> bool:
    if short_term is None:
        return False
    recent = short_term.get_recent(4)
    if not recent:
        return False
    latest_user_seen = False
    for entry in reversed(recent):
        if entry.role == "user" and not latest_user_seen:
            latest_user_seen = True
            continue
        content = str(entry.content or "").lower()
        if any(marker in content for marker in _GREETING_BLOCKER_MARKERS):
            return True
        plan = getattr(entry, "metadata", {}).get("response_plan") if isinstance(getattr(entry, "metadata", {}), dict) else None
        if isinstance(plan, dict):
            plan_text = " ".join(str(plan.get(key) or "") for key in ("first_unit", "second_unit")).lower()
            if any(marker in plan_text for marker in _GREETING_BLOCKER_MARKERS):
                return True
    return False


def _looks_like_complete_first_unit(text: str, raw_input: str) -> bool:
    if _is_allowed_light_first_unit(text):
        return False
    stripped = text.strip()
    lowered = stripped.lower()
    if len(stripped) > _FIRST_UNIT_MAX_CHARS:
        return True
    if "?" in stripped or "？" in stripped:
        return True
    if _sentence_end_count(stripped) > 1:
        return True
    if _is_detail_or_proof_input(raw_input) and _backchannel_base(stripped) in _AFFIRMATIVE_CONCLUSION_UNITS:
        return True
    if any(marker in lowered or marker in stripped for marker in _FIRST_UNIT_EXPLANATION_MARKERS):
        return True
    if _looks_substantive_by_length(stripped):
        return True
    return False


def _is_allowed_light_first_unit(text: str) -> bool:
    base = _canonical_compare_text(text)
    base = _strip_terminal_compare_punctuation(base)
    base = base.replace(",", "")
    if _is_short_backchannel(text):
        return True
    compact = base.replace(" ", "")
    if compact in _LIGHT_FIRST_UNIT_PHRASES:
        return True
    return base in _LIGHT_FIRST_UNIT_PHRASES


def _sentence_end_count(text: str) -> int:
    return sum(1 for char in text if char in _TERMINAL_PUNCTUATION)


def _is_capability_or_detail_input(raw_input: str) -> bool:
    lowered = (raw_input or "").lower()
    markers = (
        "能看",
        "看见",
        "看到",
        "能听",
        "听见",
        "视觉",
        "穿什么",
        "衣服",
        "颜色",
        "证明",
        "猜",
        "can you",
        "see",
        "hear",
        "wearing",
        "prove",
        "guess",
    )
    return any(marker in raw_input or marker in lowered for marker in markers)


def _is_detail_or_proof_input(raw_input: str) -> bool:
    lowered = (raw_input or "").lower()
    markers = (
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
        "wearing",
        "clothes",
        "color",
        "colour",
        "expression",
        "face",
        "prove",
        "guess",
    )
    return any(marker in raw_input or marker in lowered for marker in markers)


def _looks_substantive_by_length(text: str) -> bool:
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in text if ("A" <= char <= "Z") or ("a" <= char <= "z"))
    if chinese_count >= 16:
        return True
    if latin_count >= 32:
        return True
    return False


def _repeats_previous_bridge(text: str, short_term: ShortTermMemory | None) -> bool:
    if short_term is None or _is_short_backchannel(text):
        return False
    candidate = _strip_terminal_compare_punctuation(_canonical_compare_text(text))
    if not _long_enough_for_bridge_repeat_check(candidate):
        return False
    for previous in _previous_bridge_texts(short_term):
        previous_canonical = _strip_terminal_compare_punctuation(_canonical_compare_text(previous))
        if not _long_enough_for_bridge_repeat_check(previous_canonical):
            continue
        if candidate == previous_canonical:
            return True
        if previous_canonical.startswith(candidate) or candidate.startswith(previous_canonical):
            return True
    return False


def _previous_bridge_texts(short_term: ShortTermMemory) -> list[str]:
    texts: list[str] = []
    for entry in short_term.get_recent(6):
        content = str(getattr(entry, "content", "") or "").strip()
        if content:
            texts.append(content)
        metadata = getattr(entry, "metadata", {}) or {}
        plan = metadata.get("response_plan") if isinstance(metadata, dict) else None
        if isinstance(plan, dict):
            for key in ("first_unit", "second_unit"):
                value = str(plan.get(key) or "").strip()
                if value:
                    texts.append(value)
    return texts


def _long_enough_for_bridge_repeat_check(text: str) -> bool:
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in text if ("a" <= char <= "z"))
    return chinese_count >= 4 or latin_count >= 10


def _is_only_punctuation_or_pause(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    pause_chars = set(".。!！?？,，、;；:：… \t\r\n\"'“”‘’「」『』()（）[]【】<>《》")
    return all(char in pause_chars for char in stripped)


def _trim_truncated_second_unit(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    last_end = -1
    for idx, char in enumerate(cleaned):
        if char in _SECOND_UNIT_END_CHARS:
            last_end = idx

    if last_end < 0:
        return ""

    end = last_end + 1
    while end < len(cleaned) and cleaned[end] in _SECOND_UNIT_TRAILING_CHARS:
        end += 1
    return cleaned[:end].rstrip()
