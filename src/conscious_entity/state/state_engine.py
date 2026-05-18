from __future__ import annotations

import re
from typing import Any

from conscious_entity.perception.event_types import PerceptionEvent
from conscious_entity.state.state_core import EntityState

# Matches patterns like "state.desperation_pressure > 0.7"
_CONDITION_RE = re.compile(
    r"state\.(\w+)\s*(>=|<=|>|<|==)\s*([\d.]+)"
)


def _evaluate_condition(expr: str, state: EntityState) -> bool:
    m = _CONDITION_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Cannot parse condition expression: {expr!r}")
    var, op, threshold = m.group(1), m.group(2), float(m.group(3))
    value = state.to_dict().get(var)
    if value is None:
        raise ValueError(f"Unknown state variable in condition: {var!r}")
    return {
        ">": value > threshold,
        "<": value < threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
        "==": value == threshold,
    }[op]


def _apply_deltas(state_dict: dict[str, float], deltas: dict[str, Any], weight: float = 1.0) -> None:
    for var, delta in deltas.items():
        if var in state_dict:
            state_dict[var] += float(delta) * weight


def _apply_couplings(
    before: dict[str, float],
    after: dict[str, float],
    couplings: list[dict[str, Any]],
) -> None:
    for rule in couplings:
        source = str(rule.get("source", ""))
        target = str(rule.get("target", ""))
        if source not in before or source not in after or target not in after:
            continue

        source_delta = _clamp01(after[source]) - before[source]
        direction = str(rule.get("direction", "increase"))
        if direction == "increase" and source_delta <= 0:
            continue
        if direction == "decrease" and source_delta >= 0:
            continue

        after[target] += abs(source_delta) * float(rule.get("multiplier", 0.0))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class StateEngine:
    def __init__(self, state_rules: dict[str, Any]) -> None:
        self._rules = state_rules

    def apply_event(self, state: EntityState, event: PerceptionEvent) -> EntityState:
        """Apply delta rules for the event type. Returns new EntityState (immutable)."""
        event_rules = self._rules.get("events", {}).get(event.event_type.value)
        if event_rules is None:
            return state

        before_vals = state.to_dict()
        new_vals = dict(before_vals)
        salience_weight = event.salience if event_rules.get("salience_weighted") else 1.0

        if "conditions" in event_rules:
            for branch in event_rules["conditions"]:
                if "if" in branch:
                    if _evaluate_condition(branch["if"], state):
                        _apply_deltas(new_vals, branch.get("deltas", {}), salience_weight)
                        break
                elif "else" in branch:
                    _apply_deltas(new_vals, branch.get("deltas", {}), salience_weight)
                    break
        elif "deltas" in event_rules:
            _apply_deltas(new_vals, event_rules["deltas"], salience_weight)

        _apply_couplings(before_vals, new_vals, self._rules.get("couplings", []))
        return EntityState(**new_vals).clamp_all()

    def apply_decay(self, state: EntityState, elapsed_seconds: float) -> EntityState:
        """Apply time-based decay. Returns new EntityState (immutable)."""
        decay_per_minute = self._rules.get("decay", {}).get("per_minute", {})
        if not decay_per_minute or elapsed_seconds <= 0:
            return state

        ratio = elapsed_seconds / 60.0
        before_vals = state.to_dict()
        new_vals = dict(before_vals)
        for var, rate in decay_per_minute.items():
            if var in new_vals:
                new_vals[var] += float(rate) * ratio

        _apply_couplings(before_vals, new_vals, self._rules.get("couplings", []))
        return EntityState(**new_vals).clamp_all()
