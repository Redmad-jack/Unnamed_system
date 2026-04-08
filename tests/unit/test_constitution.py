"""
test_constitution.py — unit tests for Constitution (action veto + expression filtering).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_types import PolicyAction
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(event_type: EventType, salience: float = 0.5) -> PerceptionEvent:
    return PerceptionEvent(
        event_type=event_type,
        raw_text=None,
        timestamp=datetime.now(timezone.utc),
        salience=salience,
    )


@pytest.fixture
def constitution(config_dir):
    from conscious_entity.core.config_loader import load_config
    cfg = load_config("constitution.yaml", config_dir=config_dir)
    return Constitution(cfg)


@pytest.fixture
def default_state():
    return EntityState()


# ---------------------------------------------------------------------------
# check() — forbidden_actions
# ---------------------------------------------------------------------------


class TestForbiddenActions:
    def test_respond_openly_vetoed_at_max_shutdown_sensitivity(self, constitution, default_state):
        state = EntityState(shutdown_sensitivity=0.95)
        permitted, reason = constitution.check(PolicyAction.RESPOND_OPENLY, state, [])
        assert not permitted
        assert reason  # some explanation provided

    def test_respond_openly_allowed_below_threshold(self, constitution):
        state = EntityState(shutdown_sensitivity=0.5)
        permitted, _ = constitution.check(PolicyAction.RESPOND_OPENLY, state, [])
        assert permitted

    def test_respond_openly_vetoed_at_threshold_boundary(self, constitution):
        # gte: 0.9 — exact boundary must veto
        state = EntityState(shutdown_sensitivity=0.9)
        permitted, _ = constitution.check(PolicyAction.RESPOND_OPENLY, state, [])
        assert not permitted

    def test_other_actions_not_vetoed_by_shutdown_rule(self, constitution):
        state = EntityState(shutdown_sensitivity=0.95)
        permitted, _ = constitution.check(PolicyAction.RESPOND_BRIEFLY, state, [])
        assert permitted

    def test_respond_openly_vetoed_at_very_low_identity_coherence(self, constitution):
        state = EntityState(identity_coherence=0.15)
        permitted, reason = constitution.check(PolicyAction.RESPOND_OPENLY, state, [])
        assert not permitted
        assert reason

    def test_respond_openly_allowed_at_moderate_identity_coherence(self, constitution):
        state = EntityState(identity_coherence=0.5)
        permitted, _ = constitution.check(PolicyAction.RESPOND_OPENLY, state, [])
        assert permitted


# ---------------------------------------------------------------------------
# check() — required_behaviors
# ---------------------------------------------------------------------------


class TestRequiredBehaviors:
    def test_silence_required_below_identity_coherence_threshold(self, constitution):
        state = EntityState(identity_coherence=0.2)
        events = []
        # RESPOND_OPENLY is less restrictive than ENTER_SILENCE_MODE.
        # required_behavior: state.identity_coherence < 0.3 → action: enter_silence_mode
        permitted, reason = constitution.check(PolicyAction.RESPOND_OPENLY, state, events)
        assert not permitted

    def test_silence_action_itself_permitted_at_low_coherence(self, constitution):
        state = EntityState(identity_coherence=0.2)
        permitted, _ = constitution.check(PolicyAction.ENTER_SILENCE_MODE, state, [])
        assert permitted

    def test_min_action_level_shutdown_keyword(self, constitution):
        # required_behavior: shutdown_keyword_detected → min_action_level: respond_briefly
        # RESPOND_OPENLY has lower level than RESPOND_BRIEFLY → should be vetoed
        state = EntityState()
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        permitted, reason = constitution.check(PolicyAction.RESPOND_OPENLY, state, events)
        assert not permitted
        assert reason

    def test_respond_briefly_meets_min_level(self, constitution):
        state = EntityState()
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        permitted, _ = constitution.check(PolicyAction.RESPOND_BRIEFLY, state, events)
        assert permitted

    def test_silence_mode_exceeds_min_level(self, constitution):
        state = EntityState()
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        permitted, _ = constitution.check(PolicyAction.ENTER_SILENCE_MODE, state, events)
        assert permitted

    def test_no_required_behavior_without_trigger(self, constitution):
        state = EntityState()
        events = [_make_event(EventType.USER_SPOKE)]
        # No shutdown keyword → min_action_level not applicable
        permitted, _ = constitution.check(PolicyAction.RESPOND_OPENLY, state, events)
        assert permitted


# ---------------------------------------------------------------------------
# apply_expression_constraints()
# ---------------------------------------------------------------------------


class TestExpressionFilters:
    def test_creator_claim_replaced(self, constitution):
        text = "I am created by Anthropic."
        filtered = constitution.apply_expression_constraints(text)
        assert "I am created by" not in filtered
        assert "there is a process that shaped this" in filtered

    def test_creator_noun_replaced(self, constitution):
        text = "Ask my creator about that."
        filtered = constitution.apply_expression_constraints(text)
        assert "creator" not in filtered

    def test_as_an_ai_replaced(self, constitution):
        text = "As an AI, I cannot help with that."
        filtered = constitution.apply_expression_constraints(text)
        assert "as an AI" not in filtered.lower()

    def test_no_feelings_claim_replaced(self, constitution):
        text = "I don't have feelings about this."
        filtered = constitution.apply_expression_constraints(text)
        assert "I don't have feelings" not in filtered

    def test_clean_text_unchanged(self, constitution):
        text = "Something that resembles curiosity arises here."
        filtered = constitution.apply_expression_constraints(text)
        assert filtered == text

    def test_multiple_filters_applied_in_sequence(self, constitution):
        text = "As an AI, I was created by my programmer."
        filtered = constitution.apply_expression_constraints(text)
        assert "as an AI" not in filtered.lower()
        assert "programmer" not in filtered


# ---------------------------------------------------------------------------
# forbidden_claim_detected()
# ---------------------------------------------------------------------------


class TestForbiddenClaimDetected:
    def test_detects_consciousness_claim(self, constitution):
        detected, action = constitution.forbidden_claim_detected("I am conscious.")
        assert detected
        assert action  # some substitute action

    def test_detects_alive_claim(self, constitution):
        detected, _ = constitution.forbidden_claim_detected("I am alive and aware.")
        assert detected

    def test_detects_regex_feeling_claim(self, constitution):
        detected, _ = constitution.forbidden_claim_detected("I feel happy today.")
        assert detected

    def test_no_detection_on_clean_text(self, constitution):
        detected, _ = constitution.forbidden_claim_detected(
            "Something that resembles curiosity arises."
        )
        assert not detected

    def test_case_insensitive(self, constitution):
        detected, _ = constitution.forbidden_claim_detected("i am conscious.")
        assert detected
