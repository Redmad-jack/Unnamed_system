from __future__ import annotations

import logging
from typing import Any

from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.shopkeeper.models import Language, ShopAction, StructuredTurn
from conscious_entity.shopkeeper.response_guard import ShopkeeperResponseGuard
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)

# Fallback texts used when the LLM call fails (per BACKEND_STRUCTURE §6).
# Designed to sound like the entity (minimal, hedged) rather than an error message.
_FALLBACK_TEXTS: dict[str, str] = {
    PolicyAction.RESPOND_OPENLY.value:         "Something is here. I am attending.",
    PolicyAction.RESPOND_BRIEFLY.value:        "I am attending.",
    PolicyAction.ASK_BACK.value:               "What brings you to this?",
    PolicyAction.DELAY_RESPONSE.value:         "...",
    PolicyAction.REFUSE.value:                 "Not that.",
    PolicyAction.DIVERT_TOPIC.value:           "There is something else.",
    PolicyAction.RETRIEVE_MEMORY_FIRST.value:  "Something persists here.",
    PolicyAction.ENTER_SILENCE_MODE.value:     "",
    PolicyAction.SHOW_VISUAL_DISTURBANCE.value: "",
}

_SILENT_OUTPUT_SENTINEL = "[silent]"

_TRUNCATED_STOP_REASONS = {"max_tokens", "length", "max_output_tokens"}


def _fallback_text(action: PolicyAction) -> str:
    return _FALLBACK_TEXTS.get(action.value, "...")


def _shopkeeper_fallback_text(turn: StructuredTurn) -> str:
    if turn.language == Language.EN:
        if turn.action == ShopAction.PLACE_ORDER:
            return "Sure, I will get that started."
        if turn.action == ShopAction.CONFIRM_CHOICE:
            return "Sure, let me confirm that soup."
        if turn.action == ShopAction.CLARIFY:
            return "I missed that. Which soup would you like?"
        return "Sure, take a look at the two soups."

    if turn.action == ShopAction.PLACE_ORDER:
        return "好，我给你记上。"
    if turn.action == ShopAction.CONFIRM_CHOICE:
        return "好，我先跟你确认一下这碗汤。"
    if turn.action == ShopAction.CLARIFY:
        return "我刚没听清，你想要哪碗汤？"
    return "好，先看看今天这两碗汤。"


def _turn_metadata(turn: StructuredTurn | None, reply: str) -> dict[str, Any] | None:
    if turn is None:
        return None
    data = turn.to_dict()
    data["reply"] = reply
    return data


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
        response_guard: ShopkeeperResponseGuard | None = None,
    ) -> None:
        self._style_mapper = style_mapper
        self._context_builder = context_builder
        self._client = client
        self._constitution = constitution
        self._response_guard = response_guard

    def generate(
        self,
        policy: PolicyDecision,
        state: EntityState,
        short_term: ShortTermMemory,
        retrieved_memories: list[Any] = None,  # list[RetrievedMemory]; v0.1 always []
        prompt_context: Any | None = None,
        structured_turn: StructuredTurn | None = None,
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
            return ExpressionOutput(
                text="",
                delay_ms=style.delay_ms,
                visual_mode=style.visual_mode,
                spoken_text=None,
                raw_prompt=_SILENT_OUTPUT_SENTINEL,
                turn=_turn_metadata(structured_turn, ""),
            )

        if prompt_context is None:
            ctx = self._context_builder.build(state, policy, style, short_term, retrieved_memories)
        else:
            ctx = prompt_context

        completion = self._client.complete_with_metadata(
            ctx.system_prompt,
            ctx.messages,
            min(int(ctx.max_tokens), style.max_tokens),
        )
        raw_text = completion.text
        truncated = completion.stop_reason in _TRUNCATED_STOP_REASONS

        llm_failed = not raw_text
        if llm_failed:
            raw_text = (
                _shopkeeper_fallback_text(structured_turn)
                if structured_turn is not None
                else _fallback_text(policy.action)
            )
            truncated = False
            logger.error(
                "ExpressionEngine: LLM call failed, using fallback text for action=%s",
                policy.action.value,
            )
        elif truncated:
            logger.warning(
                "ExpressionEngine: response hit token limit (action=%s, stop_reason=%s, max_tokens=%d)",
                policy.action.value,
                completion.stop_reason,
                ctx.max_tokens,
            )

        filtered_text = self._constitution.apply_expression_constraints(raw_text)
        if structured_turn is not None and self._response_guard is not None:
            filtered_text = self._response_guard.apply(filtered_text, structured_turn)

        detected, claim_action = self._constitution.forbidden_claim_detected(filtered_text)
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
            turn=_turn_metadata(structured_turn, filtered_text),
        )
