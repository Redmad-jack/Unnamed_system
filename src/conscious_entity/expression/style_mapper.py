from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from conscious_entity.policy.policy_types import PolicyDecision
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)


@dataclass
class StyleHints:
    tone: str               # "silent" | "fragmented" | "guarded" | "terse" | "open" | "neutral"
    delay_ms: int
    max_tokens: int
    fragmentation_level: float  # 0.0–1.0, injected into expression prompt
    visual_mode: str        # "normal" | "fragmented" | "disturbed" | "silent"


def _condition_matches(condition: dict[str, Any], state: EntityState) -> bool:
    """
    Evaluate an expression_mappings condition block against the current state.
    All sub-conditions must pass. Operators: gte, lte, gt, lt, eq.
    """
    state_dict = state.to_dict()
    for var, constraint in condition.items():
        value = state_dict.get(var)
        if value is None:
            logger.warning("StyleMapper condition references unknown state var: %r", var)
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
                logger.warning("Unknown operator in StyleMapper condition: %r", op)
                return False
            if not passed:
                return False
    return True


class StyleMapper:
    """
    Maps EntityState + PolicyDecision → StyleHints by evaluating expression_mappings.yaml.

    Three independent rule groups, each evaluated top-to-bottom (first match wins):
    - tone_rules     → tone, max_tokens, fragmentation_level
    - delay_rules    → delay_ms  (PolicyDecision.delay_ms overrides if > 0)
    - visual_mode_rules → visual_mode
    """

    def __init__(self, expression_mappings: dict[str, Any]) -> None:
        self._tone_rules: list[dict] = expression_mappings.get("tone_rules", [])
        self._delay_rules: list[dict] = expression_mappings.get("delay_rules", [])
        self._visual_rules: list[dict] = expression_mappings.get("visual_mode_rules", [])

    def map(self, state: EntityState, policy: PolicyDecision) -> StyleHints:
        tone, max_tokens, fragmentation = self._resolve_tone(state)
        delay_ms = self._resolve_delay(state, policy)
        visual_mode = self._resolve_visual_mode(state)
        return StyleHints(
            tone=tone,
            delay_ms=delay_ms,
            max_tokens=max_tokens,
            fragmentation_level=fragmentation,
            visual_mode=visual_mode,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_tone(self, state: EntityState) -> tuple[str, int, float]:
        """Return (tone, max_tokens, fragmentation_level). Empty condition = unconditional."""
        for rule in self._tone_rules:
            condition = rule.get("condition", {})
            if not condition or _condition_matches(condition, state):
                s = rule["style"]
                return (
                    s.get("tone", "neutral"),
                    int(s.get("max_tokens", 180)),
                    float(s.get("fragmentation_level", 0.1)),
                )
        logger.warning("StyleMapper: no tone rule matched, using hardcoded defaults")
        return "neutral", 180, 0.1

    def _resolve_delay(self, state: EntityState, policy: PolicyDecision) -> int:
        """
        Return delay_ms. PolicyDecision.delay_ms overrides YAML value when > 0.
        YAML rule with 'default_delay_ms' key is treated as unconditional fallback.
        """
        yaml_delay = 300  # safety default
        for rule in self._delay_rules:
            if "default_delay_ms" in rule:
                yaml_delay = int(rule["default_delay_ms"])
                break
            condition = rule.get("condition", {})
            if _condition_matches(condition, state):
                yaml_delay = int(rule["delay_ms"])
                break

        return policy.delay_ms if policy.delay_ms > 0 else yaml_delay

    def _resolve_visual_mode(self, state: EntityState) -> str:
        """
        Return visual_mode string. YAML rule with 'default_mode' key is unconditional fallback.
        """
        for rule in self._visual_rules:
            if "default_mode" in rule:
                return str(rule["default_mode"])
            condition = rule.get("condition", {})
            if _condition_matches(condition, state):
                return str(rule["mode"])
        logger.warning("StyleMapper: no visual mode rule matched, using 'normal'")
        return "normal"
