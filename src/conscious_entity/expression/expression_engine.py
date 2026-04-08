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


def _fallback_text(action: PolicyAction) -> str:
    return _FALLBACK_TEXTS.get(action.value, "...")


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
            )

        ctx = self._context_builder.build(state, policy, style, short_term, retrieved_memories)

        raw_text = self._client.complete(ctx.system_prompt, ctx.messages, ctx.max_tokens)

        llm_failed = not raw_text
        if llm_failed:
            raw_text = _fallback_text(policy.action)
            logger.error(
                "ExpressionEngine: LLM call failed, using fallback text for action=%s",
                policy.action.value,
            )

        filtered_text = self._constitution.apply_expression_constraints(raw_text)

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
        )
