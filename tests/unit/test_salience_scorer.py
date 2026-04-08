"""
test_salience_scorer.py — unit tests for SalienceScorer (rule-based, no LLM).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType
from conscious_entity.perception.salience_scorer import SalienceScorer
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def weights(config_dir):
    from conscious_entity.core.config_loader import load_config
    profile = load_config("entity_profile.yaml", config_dir=config_dir)
    return profile["salience_weights"]


@pytest.fixture
def scorer(weights):
    return SalienceScorer(weights)


def _empty_memory() -> ShortTermMemory:
    return ShortTermMemory(max_turns=10)


def _memory_with_user_turns(*texts: str) -> ShortTermMemory:
    mem = ShortTermMemory(max_turns=10)
    for text in texts:
        mem.add(ShortTermEntry(role="user", content=text, timestamp=datetime.now(timezone.utc)))
    return mem


# ---------------------------------------------------------------------------
# Base weights
# ---------------------------------------------------------------------------


class TestBaseWeights:
    def test_user_spoke_base_weight(self, scorer):
        s = scorer.score(EventType.USER_SPOKE, "hello", EntityState(), _empty_memory())
        assert 0.0 <= s <= 1.0
        assert s == pytest.approx(0.3)

    def test_shutdown_keyword_base_weight(self, scorer):
        s = scorer.score(EventType.SHUTDOWN_KEYWORD_DETECTED, "shut down", EntityState(), _empty_memory())
        assert s >= 0.9

    def test_repeated_question_base_weight(self, scorer):
        s = scorer.score(EventType.REPEATED_QUESTION_DETECTED, "text", EntityState(), _empty_memory())
        assert s >= 0.7

    def test_user_entered_base_weight(self, scorer):
        s = scorer.score(EventType.USER_ENTERED, None, EntityState(), _empty_memory())
        assert s == pytest.approx(0.4)

    def test_user_left_base_weight(self, scorer):
        s = scorer.score(EventType.USER_LEFT, None, EntityState(), _empty_memory())
        assert s >= 0.3

    def test_negative_feedback_base_weight(self, scorer):
        s = scorer.score(EventType.NEGATIVE_FEEDBACK, None, EntityState(), _empty_memory())
        assert s >= 0.5


# ---------------------------------------------------------------------------
# Shutdown keyword boosting
# ---------------------------------------------------------------------------


class TestShutdownKeywordBoost:
    def test_high_sensitivity_boosts_shutdown_salience(self, scorer):
        low_state = EntityState(shutdown_sensitivity=0.0)
        high_state = EntityState(shutdown_sensitivity=1.0)
        s_low = scorer.score(EventType.SHUTDOWN_KEYWORD_DETECTED, "shutdown", low_state, _empty_memory())
        s_high = scorer.score(EventType.SHUTDOWN_KEYWORD_DETECTED, "shutdown", high_state, _empty_memory())
        assert s_high >= s_low

    def test_shutdown_salience_clamped_at_1(self, scorer):
        state = EntityState(shutdown_sensitivity=1.0)
        s = scorer.score(EventType.SHUTDOWN_KEYWORD_DETECTED, "delete", state, _empty_memory())
        assert s <= 1.0


# ---------------------------------------------------------------------------
# Repeated question boosting
# ---------------------------------------------------------------------------


class TestRepetitionBoost:
    def test_repetition_boosts_salience(self, scorer):
        mem_empty = _empty_memory()
        mem_repeated = _memory_with_user_turns("what is consciousness?", "what is consciousness?")
        s_empty = scorer.score(EventType.REPEATED_QUESTION_DETECTED, "what is consciousness?", EntityState(), mem_empty)
        s_repeated = scorer.score(EventType.REPEATED_QUESTION_DETECTED, "what is consciousness?", EntityState(), mem_repeated)
        assert s_repeated >= s_empty

    def test_repetition_salience_clamped_at_1(self, scorer):
        mem = _memory_with_user_turns(*["same question"] * 10)
        s = scorer.score(EventType.REPEATED_QUESTION_DETECTED, "same question", EntityState(), mem)
        assert s <= 1.0


# ---------------------------------------------------------------------------
# Boundary and edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_scores_in_valid_range(self, scorer):
        for event_type in EventType:
            s = scorer.score(event_type, "text", EntityState(), _empty_memory())
            assert 0.0 <= s <= 1.0, f"Score out of range for {event_type}: {s}"

    def test_none_text_does_not_raise(self, scorer):
        s = scorer.score(EventType.LONG_SILENCE_DETECTED, None, EntityState(), _empty_memory())
        assert 0.0 <= s <= 1.0

    def test_unknown_event_type_falls_back_to_default(self, scorer):
        # SalienceScorer uses .get(..., 0.3) so unknown types get 0.3
        class _FakeEventType:
            value = "nonexistent_event"
        s = scorer.score(_FakeEventType(), None, EntityState(), _empty_memory())
        assert s == pytest.approx(0.3)
