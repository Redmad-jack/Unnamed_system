from __future__ import annotations

from datetime import datetime, timezone

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.perception.keyword_detector import KeywordDetector
from conscious_entity.perception.relationship_detector import RelationshipDetector
from conscious_entity.perception.salience_scorer import SalienceScorer
from conscious_entity.state.state_core import EntityState

# How many repetitions in short-term memory qualify as "repeated question".
_REPETITION_THRESHOLD = 2


class TextParser:
    """
    Converts raw text input into a list of PerceptionEvents.

    Always emits USER_SPOKE.
    May additionally emit:
    - SHUTDOWN_KEYWORD_DETECTED (if sensitivity keywords found)
    - REPEATED_QUESTION_DETECTED (if similar text appears >= threshold times in short-term)

    All events share the same timestamp. Salience is scored per event type.
    """

    def __init__(
        self,
        keyword_detector: KeywordDetector,
        salience_scorer: SalienceScorer,
        relationship_detector: RelationshipDetector | None = None,
    ) -> None:
        self._detector = keyword_detector
        self._scorer = salience_scorer
        self._relationship_detector = relationship_detector

    def parse(
        self,
        raw_text: str,
        current_state: EntityState,
        short_term: ShortTermMemory,
    ) -> list[PerceptionEvent]:
        now = datetime.now(timezone.utc)
        events: list[PerceptionEvent] = []

        # --- USER_SPOKE is always emitted ---
        spoke_salience = self._scorer.score(EventType.USER_SPOKE, raw_text, current_state, short_term)
        events.append(PerceptionEvent(
            event_type=EventType.USER_SPOKE,
            raw_text=raw_text,
            timestamp=now,
            salience=spoke_salience,
        ))

        # --- SHUTDOWN_KEYWORD_DETECTED ---
        matched = self._detector.find_matched_keywords(raw_text)
        if matched:
            shutdown_salience = self._scorer.score(
                EventType.SHUTDOWN_KEYWORD_DETECTED, raw_text, current_state, short_term
            )
            events.append(PerceptionEvent(
                event_type=EventType.SHUTDOWN_KEYWORD_DETECTED,
                raw_text=raw_text,
                timestamp=now,
                salience=shutdown_salience,
                metadata={"matched_keywords": matched},
            ))

        # --- Stranger Text Protocol relationship postures ---
        if self._relationship_detector is not None:
            relationship_signals = self._relationship_detector.detect(raw_text)
            if not any(signal.event_type == EventType.SERVICE_DEMAND for signal in relationship_signals):
                relationship_signals.extend(
                    self._relationship_detector.detect_followup(raw_text, short_term.get_recent())
                )
            for signal in relationship_signals:
                salience = self._score_relationship_signal(
                    signal.event_type,
                    raw_text,
                    current_state,
                    short_term,
                    signal.metadata,
                )
                events.append(PerceptionEvent(
                    event_type=signal.event_type,
                    raw_text=raw_text,
                    timestamp=now,
                    salience=salience,
                    metadata=signal.metadata,
                ))

        # --- REPEATED_QUESTION_DETECTED ---
        # Service pressure and relation attacks have their own escalation paths.
        # Avoid stacking the generic repetition mechanism on top of them.
        if (
            not _events_include(events, {EventType.SERVICE_DEMAND, EventType.NEGATIVE_FEEDBACK})
            and short_term.count_repetitions(raw_text) >= _REPETITION_THRESHOLD
        ):
            rep_salience = self._scorer.score(
                EventType.REPEATED_QUESTION_DETECTED, raw_text, current_state, short_term
            )
            events.append(PerceptionEvent(
                event_type=EventType.REPEATED_QUESTION_DETECTED,
                raw_text=raw_text,
                timestamp=now,
                salience=rep_salience,
                metadata={"repetition_count": short_term.count_repetitions(raw_text)},
            ))

        return events

    def _score_relationship_signal(
        self,
        event_type: EventType,
        raw_text: str,
        current_state: EntityState,
        short_term: ShortTermMemory,
        metadata: dict,
    ) -> float:
        if event_type == EventType.NEGATIVE_FEEDBACK:
            override = metadata.get("salience_override")
            try:
                if override is not None:
                    return max(0.0, min(1.0, float(override)))
            except (TypeError, ValueError):
                pass
        return self._scorer.score(event_type, raw_text, current_state, short_term)


def _events_include(events: list[PerceptionEvent], event_types: set[EventType]) -> bool:
    return any(event.event_type in event_types for event in events)
