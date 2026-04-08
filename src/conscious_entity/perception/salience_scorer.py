from __future__ import annotations

from typing import Optional

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType
from conscious_entity.state.state_core import EntityState


class SalienceScorer:
    """
    Rule-based salience scoring for perception events.

    Base weights come from entity_profile.yaml salience_weights.
    Context adjustments:
    - SHUTDOWN_KEYWORD_DETECTED: boosted by current shutdown_sensitivity state
    - REPEATED_QUESTION_DETECTED: boosted by repetition count
    - All scores clamped to [0.0, 1.0].
    """

    def __init__(
        self,
        salience_weights: dict[str, float],
    ) -> None:
        self._weights = salience_weights

    def score(
        self,
        event_type: EventType,
        raw_text: Optional[str],
        current_state: EntityState,
        short_term: ShortTermMemory,
    ) -> float:
        base = float(self._weights.get(event_type.value, 0.3))

        if event_type == EventType.SHUTDOWN_KEYWORD_DETECTED:
            # Amplify salience when the entity is already sensitized.
            sensitivity_boost = current_state.shutdown_sensitivity * 0.2
            base = min(1.0, base + sensitivity_boost)

        elif event_type == EventType.REPEATED_QUESTION_DETECTED and raw_text:
            count = short_term.count_repetitions(raw_text)
            repetition_boost = min(0.2, count * 0.05)
            base = min(1.0, base + repetition_boost)

        return max(0.0, min(1.0, base))
