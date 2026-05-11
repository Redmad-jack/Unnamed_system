from __future__ import annotations

import logging
from typing import Any

from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.output_model import ExpressionOutput
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

_TRUNCATED_STOP_REASONS = {"max_tokens", "length", "max_output_tokens"}


def _fallback_text(action: PolicyAction, short_term: ShortTermMemory | None = None) -> str:
    texts = _FALLBACK_TEXTS_ZH if _recent_user_text_is_chinese(short_term) else _FALLBACK_TEXTS_EN
    return texts.get(action.value, "...")


def _recent_user_text_is_chinese(short_term: ShortTermMemory | None) -> bool:
    if short_term is None:
        return False
    for entry in reversed(short_term.get_recent(10)):
        if entry.role == "user":
            return any("\u4e00" <= ch <= "\u9fff" for ch in entry.content)
    return False


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

    def generate(
        self,
        policy: PolicyDecision,
        state: EntityState,
        short_term: ShortTermMemory,
        retrieved_memories: list[Any] = None,  # list[RetrievedMemory]; v0.1 always []
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
                    metadata={"changed": False, "forbidden_claim_detected": False},
                )
            return ExpressionOutput(
                text="",
                delay_ms=style.delay_ms,
                visual_mode=style.visual_mode,
                spoken_text=None,
                raw_prompt=_SILENT_OUTPUT_SENTINEL,
            )

        ctx = self._context_builder.build(
            state,
            policy,
            style,
            short_term,
            retrieved_memories,
            harness_recorder=harness_recorder,
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

        detected, claim_action = self._constitution.forbidden_claim_detected(filtered_text)
        if harness_recorder is not None:
            harness_recorder.record(
                HarnessLayer.OUTPUT,
                status="filtered" if filtered_text != raw_text or detected else "passed",
                decision=claim_action or None,
                summary=(
                    "Constitution output filters changed or flagged the response."
                    if filtered_text != raw_text or detected
                    else "Constitution output filters passed the response."
                ),
                metadata={
                    "changed": filtered_text != raw_text,
                    "forbidden_claim_detected": detected,
                },
            )
        if detected:
            logger.warning(
                "ExpressionEngine: forbidden claim survived expression filter "
                "(substitute_action=%r). Text should be reviewed.",
                claim_action,
            )

        return ExpressionOutput(
            text=filtered_text,
            delay_ms=style.delay_ms,
            visual_mode=style.visual_mode,
            spoken_text=None,
            raw_prompt=ctx.raw_prompt,
            truncated=truncated,
            stop_reason=completion.stop_reason,
        )
