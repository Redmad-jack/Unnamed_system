from __future__ import annotations

import re
from typing import Any

from conscious_entity.perception.event_types import PerceptionEvent
from conscious_entity.state.state_core import EntityState

# Matches patterns like "state.shutdown_sensitivity > 0.7"
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


class StateEngine:
    def __init__(self, state_rules: dict[str, Any]) -> None:
        self._rules = state_rules

    def apply_event(self, state: EntityState, event: PerceptionEvent) -> EntityState:
        """Apply delta rules for the event type. Returns new EntityState (immutable)."""
        event_rules = self._rules.get("events", {}).get(event.event_type.value)
        if event_rules is None:
            return state

        new_vals = state.to_dict()
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

        return EntityState(**new_vals).clamp_all()

    def apply_decay(self, state: EntityState, elapsed_seconds: float) -> EntityState:
        """Apply time-based decay. Returns new EntityState (immutable)."""
        decay_per_minute = self._rules.get("decay", {}).get("per_minute", {})
        if not decay_per_minute or elapsed_seconds <= 0:
            return state

        ratio = elapsed_seconds / 60.0
        new_vals = state.to_dict()
        for var, rate in decay_per_minute.items():
            if var in new_vals:
                new_vals[var] += float(rate) * ratio

        return EntityState(**new_vals).clamp_all()
