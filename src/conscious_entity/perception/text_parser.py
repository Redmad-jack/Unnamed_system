from __future__ import annotations

from datetime import datetime, timezone

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.perception.keyword_detector import KeywordDetector
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
    ) -> None:
        self._detector = keyword_detector
        self._scorer = salience_scorer

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

        # --- REPEATED_QUESTION_DETECTED ---
        if short_term.count_repetitions(raw_text) >= _REPETITION_THRESHOLD:
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
