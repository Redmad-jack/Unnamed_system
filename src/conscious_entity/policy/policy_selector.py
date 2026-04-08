from __future__ import annotations

import logging
from typing import Any

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)

_FALLBACK_ACTION = PolicyAction.RESPOND_OPENLY
_FALLBACK_RATIONALE = "default:no_rule_matched"


def _state_matches(condition: dict[str, Any], state: EntityState) -> bool:
    """
    Evaluate a state condition block from policy_rules.yaml.

    Supports operators: gte, lte, gt, lt, eq.
    All specified sub-keys must pass for the block to match.
    """
    state_dict = state.to_dict()
    for var, constraint in condition.items():
        value = state_dict.get(var)
        if value is None:
            logger.warning("Policy rule references unknown state variable: %r", var)
            return False
        for op, threshold in constraint.items():
            threshold = float(threshold)
            passed = {
                "gte": value >= threshold,
                "lte": value <= threshold,
                "gt": value > threshold,
                "lt": value < threshold,
                "eq": value == threshold,
            }.get(op)
            if passed is None:
                logger.warning("Unknown operator in policy condition: %r", op)
                return False
            if not passed:
                return False
    return True


def _events_match(required_types: list[str], events: list[PerceptionEvent]) -> bool:
    """All required event types must be present in the current event list."""
    event_values = {e.event_type.value for e in events}
    return all(et in event_values for et in required_types)


def _rule_matches(
    rule: dict[str, Any],
    state: EntityState,
    events: list[PerceptionEvent],
) -> bool:
    """Return True if all conditions in a policy rule are satisfied."""
    conditions = rule.get("conditions", {})
    if not conditions:
        # No conditions means this is an unconditional rule (e.g. "default")
        return True

    if "events_include" in conditions:
        if not _events_match(conditions["events_include"], events):
            return False

    if "state" in conditions:
        if not _state_matches(conditions["state"], state):
            return False

    return True


class PolicySelector:
    """
    Evaluates policy_rules.yaml top-to-bottom and returns the first matching rule.

    Constitution is injected so it can be mocked in tests and swapped independently.
    If a rule has constitution_check: true, the proposed action is vetoed through
    Constitution.check() before being returned. On veto, evaluation continues to
    the next matching rule.

    LLM interface note: this class has no LLM calls. All decisions are rule-based.
    """

    def __init__(
        self,
        policy_rules: dict[str, Any],
        constitution: Constitution,
    ) -> None:
        self._rules: list[dict[str, Any]] = policy_rules.get("rules", [])
        self._constitution = constitution

    def select(
        self,
        state: EntityState,
        events: list[PerceptionEvent],
        short_term: ShortTermMemory,
    ) -> PolicyDecision:
        """
        Evaluate rules top-to-bottom. Return the first rule whose conditions
        are satisfied and whose action passes the constitution check (when required).

        Falls back to RESPOND_OPENLY if no rule matches.

        The returned PolicyDecision.rationale records the rule id that fired,
        enabling debug tracing and the v0.3 governance panel.
        """
        for rule in self._rules:
            if not _rule_matches(rule, state, events):
                continue

            raw_action = rule.get("action", _FALLBACK_ACTION.value)
            try:
                action = PolicyAction(raw_action)
            except ValueError:
                logger.error(
                    "Unknown policy action %r in rule %r — skipping",
                    raw_action,
                    rule.get("id", "?"),
                )
                continue

            rule_id = rule.get("id", "unnamed")
            params: dict = rule.get("params", {}) or {}

            if rule.get("constitution_check", False):
                permitted, reason = self._constitution.check(action, state, events)
                if not permitted:
                    logger.debug(
                        "Rule %r vetoed by Constitution: %s", rule_id, reason
                    )
                    # Continue evaluating subsequent rules.
                    continue

            delay_ms = int(params.get("delay_ms", 0))
            retrieve_query: str | None = None
            if action == PolicyAction.RETRIEVE_MEMORY_FIRST or params.get("retrieve_memory"):
                # Retrieve query is built from the most recent user turn if available.
                recent = short_term.get_recent(1)
                if recent:
                    retrieve_query = recent[0].content

            rationale = f"rule:{rule_id}"
            logger.debug("Policy selected: action=%s rationale=%s", action.value, rationale)

            return PolicyDecision(
                action=action,
                delay_ms=delay_ms,
                retrieve_query=retrieve_query,
                rationale=rationale,
                params=params,
            )

        # No rule matched — use unconditional fallback.
        logger.debug("Policy fallback: %s", _FALLBACK_RATIONALE)
        return PolicyDecision(
            action=_FALLBACK_ACTION,
            rationale=_FALLBACK_RATIONALE,
        )
