"""
test_style_mapper.py — unit tests for StyleMapper (rule-based, no LLM).
"""

from __future__ import annotations

import pytest

from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mapper(config_dir):
    from conscious_entity.core.config_loader import load_config
    cfg = load_config("expression_mappings.yaml", config_dir=config_dir)
    return StyleMapper(cfg)


def _decision(action: PolicyAction = PolicyAction.RESPOND_OPENLY, delay_ms: int = 0) -> PolicyDecision:
    return PolicyDecision(action=action, delay_ms=delay_ms)


# ---------------------------------------------------------------------------
# Tone rules
# ---------------------------------------------------------------------------


class TestToneRules:
    def test_default_state_produces_neutral_tone(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.tone == "neutral"
        assert hints.max_tokens == 1000
        assert hints.fragmentation_level == pytest.approx(0.05)

    def test_high_desperation_pressure_produces_silent_tone(self, mapper):
        state = EntityState(desperation_pressure=0.9)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"
        assert hints.max_tokens == 0
        assert hints.fragmentation_level == pytest.approx(1.0)

    def test_desperation_pressure_at_exact_threshold(self, mapper):
        # threshold is gte: 0.9
        state = EntityState(desperation_pressure=0.9)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"

    def test_high_confusion_produces_fragmented_tone(self, mapper):
        state = EntityState(confusion=0.75)
        hints = mapper.map(state, _decision())
        assert hints.tone == "fragmented"
        assert hints.max_tokens == 1000
        assert hints.fragmentation_level == pytest.approx(0.35)

    def test_high_anger_produces_guarded_tone(self, mapper):
        state = EntityState(anger=0.6)
        hints = mapper.map(state, _decision())
        assert hints.tone == "guarded"
        assert hints.max_tokens == 1000
        assert hints.fragmentation_level == pytest.approx(0.10)

    def test_high_exposure_pressure_produces_guarded_tone(self, mapper):
        state = EntityState(exposure_pressure=0.65)
        hints = mapper.map(state, _decision())
        assert hints.tone == "guarded"
        assert hints.max_tokens == 1000
        assert hints.fragmentation_level == pytest.approx(0.15)

    def test_high_fatigue_produces_terse_tone(self, mapper):
        state = EntityState(fatigue_level=0.7)
        hints = mapper.map(state, _decision())
        assert hints.tone == "terse"
        assert hints.max_tokens == 650

    def test_stable_low_pressure_state_produces_open_tone(self, mapper):
        state = EntityState(positive_opening=0.6, exposure_pressure=0.25, anger=0.2)
        hints = mapper.map(state, _decision())
        assert hints.tone == "open"
        assert hints.max_tokens == 1000
        assert hints.fragmentation_level == pytest.approx(0.0)

    def test_tone_priority_silent_beats_fragmented(self, mapper):
        # desperation_pressure >= 0.9 is higher priority than confusion >= 0.7
        state = EntityState(desperation_pressure=0.9, confusion=0.8)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"

    def test_tone_priority_fragmented_beats_guarded(self, mapper):
        # confusion >= 0.7 is listed before exposure_pressure >= 0.65
        state = EntityState(confusion=0.75, exposure_pressure=0.65)
        hints = mapper.map(state, _decision())
        assert hints.tone == "fragmented"

    def test_open_tone_requires_both_conditions(self, mapper):
        # Positive opening alone is not sufficient; exposure and anger must be low.
        state = EntityState(positive_opening=0.7, exposure_pressure=0.5)
        hints = mapper.map(state, _decision())
        # Should NOT produce "open" — falls through to default
        assert hints.tone != "open"


# ---------------------------------------------------------------------------
# Delay compatibility
# ---------------------------------------------------------------------------


class TestDelayRules:
    def test_default_state_has_zero_delay(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.delay_ms == 0

    def test_high_fatigue_still_has_zero_delay(self, mapper):
        state = EntityState(fatigue_level=0.8)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 0

    def test_low_positive_opening_still_has_zero_delay(self, mapper):
        state = EntityState(positive_opening=0.25)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 0

    def test_high_desperation_pressure_still_has_zero_delay(self, mapper):
        state = EntityState(desperation_pressure=0.65)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 0

    def test_high_exposure_pressure_still_has_zero_delay(self, mapper):
        state = EntityState(exposure_pressure=0.55)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 0

    def test_policy_delay_is_ignored_for_compatibility(self, mapper):
        state = EntityState()
        decision = _decision(delay_ms=3000)
        hints = mapper.map(state, decision)
        assert hints.delay_ms == 0

    def test_policy_delay_zero_keeps_zero_delay(self, mapper):
        state = EntityState(fatigue_level=0.8)
        decision = _decision(delay_ms=0)
        hints = mapper.map(state, decision)
        assert hints.delay_ms == 0

    def test_delay_rules_do_not_create_waits(self, mapper):
        state = EntityState(fatigue_level=0.8, positive_opening=0.2)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 0


# ---------------------------------------------------------------------------
# Vocal marker rules
# ---------------------------------------------------------------------------


class TestVocalMarkerRules:
    def test_default_state_has_no_vocal_marker(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.vocal_marker == "none"

    def test_confusion_produces_thinking_marker(self, mapper):
        state = EntityState(confusion=0.5)
        hints = mapper.map(state, _decision())
        assert hints.vocal_marker == "thinking"

    def test_fatigue_produces_sigh_marker(self, mapper):
        state = EntityState(fatigue_level=0.5)
        hints = mapper.map(state, _decision())
        assert hints.vocal_marker == "sigh"

    def test_exposure_pressure_produces_sigh_marker(self, mapper):
        state = EntityState(exposure_pressure=0.5)
        hints = mapper.map(state, _decision())
        assert hints.vocal_marker == "sigh"

    def test_desperation_pressure_produces_sigh_marker(self, mapper):
        state = EntityState(desperation_pressure=0.6)
        hints = mapper.map(state, _decision())
        assert hints.vocal_marker == "sigh"

    def test_anger_suppresses_thinking_and_sigh(self, mapper):
        state = EntityState(anger=0.6, confusion=0.8, fatigue_level=0.8, exposure_pressure=0.8)
        hints = mapper.map(state, _decision())
        assert hints.vocal_marker == "none"


# ---------------------------------------------------------------------------
# Body action rules
# ---------------------------------------------------------------------------


class TestBodyActionRules:
    def test_default_state_has_no_body_action(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.body_action == "none"

    def test_extreme_desperation_withdraws(self, mapper):
        state = EntityState(desperation_pressure=0.85)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "withdraw"

    def test_high_desperation_steps_back(self, mapper):
        state = EntityState(desperation_pressure=0.6)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "step_back"

    def test_high_anger_increases_distance(self, mapper):
        state = EntityState(anger=0.6)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "distance_increase"

    def test_high_exposure_turns_away(self, mapper):
        state = EntityState(exposure_pressure=0.6)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "turn_away_30deg"

    def test_high_fatigue_pauses(self, mapper):
        state = EntityState(fatigue_level=0.6)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "pause"

    def test_confusion_pauses(self, mapper):
        state = EntityState(confusion=0.5)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "pause"

    def test_inquiry_leans_in(self, mapper):
        state = EntityState(inquiry=0.65)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "lean_in"

    def test_care_response_circles_back(self, mapper):
        state = EntityState(care_response=0.6)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "circle_back"

    def test_positive_opening_leans_in(self, mapper):
        state = EntityState(positive_opening=0.65)
        hints = mapper.map(state, _decision())
        assert hints.body_action == "lean_in"


# ---------------------------------------------------------------------------
# Visual mode rules
# ---------------------------------------------------------------------------


class TestVisualModeRules:
    def test_default_state_has_normal_visual_mode(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.visual_mode == "normal"

    def test_high_desperation_pressure_produces_desperate(self, mapper):
        state = EntityState(desperation_pressure=0.75)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "desperate"

    def test_high_anger_produces_angry(self, mapper):
        state = EntityState(anger=0.65)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "angry"

    def test_high_fatigue_produces_tired(self, mapper):
        state = EntityState(fatigue_level=0.65)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "tired"

    def test_high_exposure_pressure_produces_ashamed(self, mapper):
        state = EntityState(exposure_pressure=0.6)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "ashamed"

    def test_high_confusion_produces_confused(self, mapper):
        state = EntityState(confusion=0.6)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "confused"

    def test_high_inquiry_produces_curious(self, mapper):
        state = EntityState(inquiry=0.65)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "curious"

    def test_high_care_response_produces_caring(self, mapper):
        state = EntityState(care_response=0.6)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "caring"

    def test_high_positive_opening_produces_open(self, mapper):
        state = EntityState(positive_opening=0.65)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "open"

    def test_visual_priority_desperation_beats_confusion(self, mapper):
        state = EntityState(desperation_pressure=0.8, confusion=0.8)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "desperate"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_max_state_returns_valid_hints(self, mapper):
        state = EntityState(
            desperation_pressure=1.0,
            confusion=1.0,
            anger=1.0,
            fatigue_level=1.0,
            exposure_pressure=1.0,
            inquiry=1.0,
            care_response=1.0,
            positive_opening=1.0,
            happiness=1.0,
        )
        hints = mapper.map(state, _decision())
        assert isinstance(hints.tone, str)
        assert hints.max_tokens >= 0
        assert 0.0 <= hints.fragmentation_level <= 1.0
        assert isinstance(hints.vocal_marker, str)
        assert isinstance(hints.body_action, str)

    def test_all_zero_state_returns_valid_hints(self, mapper):
        state = EntityState(
            desperation_pressure=0.0,
            confusion=0.0,
            anger=0.0,
            fatigue_level=0.0,
            exposure_pressure=0.0,
            inquiry=0.0,
            care_response=0.0,
            positive_opening=0.0,
            happiness=0.0,
        )
        hints = mapper.map(state, _decision())
        assert isinstance(hints.tone, str)
        assert hints.delay_ms == 0
        assert isinstance(hints.visual_mode, str)
        assert isinstance(hints.vocal_marker, str)
        assert isinstance(hints.body_action, str)

    def test_memory_gravity_does_not_drive_delivery_or_body_hints(self, mapper):
        low = mapper.map(EntityState(memory_gravity=0.0), _decision())
        high = mapper.map(EntityState(memory_gravity=1.0), _decision())

        assert high.vocal_marker == low.vocal_marker
        assert high.body_action == low.body_action
        assert high.visual_mode == low.visual_mode
