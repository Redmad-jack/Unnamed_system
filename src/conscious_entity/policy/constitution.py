from __future__ import annotations

import logging
import re
from typing import Any

from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision, action_level
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)


def _state_matches(condition: dict[str, Any], state: EntityState) -> bool:
    """Evaluate a state condition block (same operator schema as policy_rules)."""
    state_dict = state.to_dict()
    for var, constraint in condition.items():
        value = state_dict.get(var)
        if value is None:
            logger.warning("Constitution condition references unknown state var: %r", var)
            return False
        for op, threshold in constraint.items():
            threshold = float(threshold)
            if op == "gte" and not (value >= threshold):
                return False
            if op == "lte" and not (value <= threshold):
                return False
            if op == "gt" and not (value > threshold):
                return False
            if op == "lt" and not (value < threshold):
                return False
    return True


class Constitution:
    """
    Hard behavioral constraints that cannot be overridden by policy rules.

    Two responsibilities:
      1. check()                     — veto a proposed action before it is returned
      2. apply_expression_constraints() — post-hoc filter on generated text

    Both are driven entirely by constitution.yaml; no logic is inlined in Python.

    LLM interface note: this class has no LLM calls. It is purely rule-based.
    If post-hoc semantic filtering (beyond regex) is ever needed, wire a
    ClaudeClient dependency in __init__ and add a separate method.
    """

    def __init__(self, constitution_cfg: dict[str, Any]) -> None:
        self._cfg = constitution_cfg
        self._forbidden_actions: list[dict] = constitution_cfg.get("forbidden_actions", [])
        self._required_behaviors: list[dict] = constitution_cfg.get("required_behaviors", [])
        self._forbidden_claims: list[dict] = constitution_cfg.get("forbidden_claims", [])
        self._expression_filters: list[dict] = constitution_cfg.get("expression_filters", [])

        # Pre-compile expression filter regexes once at init time.
        self._compiled_filters: list[tuple[re.Pattern, str]] = []
        for f in self._expression_filters:
            pattern = re.compile(f["pattern"], re.IGNORECASE)
            self._compiled_filters.append((pattern, f["replacement"]))

        # Pre-compile forbidden claim patterns.
        self._compiled_claims: list[tuple[re.Pattern, str]] = []
        for claim in self._forbidden_claims:
            flags = re.IGNORECASE
            if claim.get("mode") == "regex":
                pattern = re.compile(claim["pattern"], flags)
            else:
                pattern = re.compile(re.escape(claim["pattern"]), flags)
            substitute = claim.get("substitute_action", PolicyAction.RESPOND_BRIEFLY.value)
            self._compiled_claims.append((pattern, substitute))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        proposed_action: PolicyAction,
        state: EntityState,
        events: list[PerceptionEvent],
    ) -> tuple[bool, str]:
        """
        Veto a proposed action if it violates a hard constraint.

        Returns:
            (is_permitted, reason)
            is_permitted=True  → action is allowed
            is_permitted=False → action is vetoed; reason explains which rule fired
        """
        event_types = {e.event_type for e in events}

        # 1. forbidden_actions — state-based veto
        for rule in self._forbidden_actions:
            if rule["action"] != proposed_action.value:
                continue
            when = rule.get("when", {})
            if "state" in when and _state_matches(when["state"], state):
                reason = rule.get("reason", f"forbidden_action:{rule['action']}")
                logger.debug("Constitution veto [forbidden_action]: %s", reason)
                return False, reason

        # 2. required_behaviors — action must meet minimum restrictiveness
        for req in self._required_behaviors:
            trigger = req.get("trigger", "")

            triggered = False
            if trigger.startswith("state."):
                # e.g. "state.identity_coherence < 0.3"
                expr = trigger[len("state."):]
                # Simple two-part parse: "var op value"
                m = re.match(r"(\w+)\s*([<>]=?|==)\s*([\d.]+)", expr)
                if m:
                    var, op, threshold = m.group(1), m.group(2), float(m.group(3))
                    val = state.to_dict().get(var, 0.0)
                    triggered = {
                        "<": val < threshold,
                        "<=": val <= threshold,
                        ">": val > threshold,
                        ">=": val >= threshold,
                        "==": val == threshold,
                    }.get(op, False)
            else:
                try:
                    triggered = EventType(trigger) in event_types
                except ValueError:
                    pass

            if not triggered:
                continue

            # If a required action is specified, the proposed action must match.
            if "action" in req and proposed_action.value != req["action"]:
                reason = req.get("note", f"required_behavior:{trigger}")
                logger.debug("Constitution veto [required_behavior action]: %s", reason)
                return False, reason

            # If a minimum action level is set, the proposed action must be at least that level.
            if "min_action_level" in req:
                try:
                    min_action = PolicyAction(req["min_action_level"])
                    if action_level(proposed_action) < action_level(min_action):
                        reason = req.get("note", f"required_min_level:{req['min_action_level']}")
                        logger.debug("Constitution veto [required_behavior min_level]: %s", reason)
                        return False, reason
                except ValueError:
                    logger.warning(
                        "Unknown min_action_level in required_behaviors: %r", req["min_action_level"]
                    )

        return True, ""

    def apply_expression_constraints(self, draft_response: str) -> str:
        """
        Post-hoc regex filter applied to generated text.

        Applies expression_filters from constitution.yaml in order.
        Also checks forbidden_claims — if a claim is found, logs a warning
        (downstream callers should re-generate or substitute, but this method
        only filters what it can via substitution and returns the cleaned text).

        Returns the filtered string.
        """
        result = draft_response

        # Apply expression_filters (replacement rules)
        for pattern, replacement in self._compiled_filters:
            result = pattern.sub(replacement, result)

        # Check forbidden_claims — warn if any remain after filtering
        # (generation-time filtering is the LLM's responsibility via system prompt;
        # this is a last-resort safeguard)
        for pattern, substitute_action in self._compiled_claims:
            if pattern.search(result):
                logger.warning(
                    "Forbidden claim detected after expression filters "
                    "(substitute_action=%r). Pattern: %r",
                    substitute_action,
                    pattern.pattern,
                )

        return result

    def forbidden_claim_detected(self, text: str) -> tuple[bool, str]:
        """
        Check whether a text contains a forbidden claim.

        Returns (detected, substitute_action_value).
        Useful for callers that want to decide whether to re-generate
        instead of silently patching the text.
        """
        for pattern, substitute_action in self._compiled_claims:
            if pattern.search(text):
                return True, substitute_action
        return False, ""
