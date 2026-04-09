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
        assert hints.max_tokens == 320
        assert hints.fragmentation_level == pytest.approx(0.1)

    def test_high_shutdown_sensitivity_produces_silent_tone(self, mapper):
        state = EntityState(shutdown_sensitivity=0.9)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"
        assert hints.max_tokens == 0
        assert hints.fragmentation_level == pytest.approx(1.0)

    def test_shutdown_sensitivity_at_exact_threshold(self, mapper):
        # threshold is gte: 0.85
        state = EntityState(shutdown_sensitivity=0.85)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"

    def test_high_uncertainty_produces_fragmented_tone(self, mapper):
        state = EntityState(uncertainty=0.75)
        hints = mapper.map(state, _decision())
        assert hints.tone == "fragmented"
        assert hints.max_tokens == 180
        assert hints.fragmentation_level == pytest.approx(0.8)

    def test_high_resistance_produces_guarded_tone(self, mapper):
        state = EntityState(resistance=0.65)
        hints = mapper.map(state, _decision())
        assert hints.tone == "guarded"
        assert hints.max_tokens == 140
        assert hints.fragmentation_level == pytest.approx(0.3)

    def test_high_fatigue_produces_terse_tone(self, mapper):
        state = EntityState(fatigue=0.7)
        hints = mapper.map(state, _decision())
        assert hints.tone == "terse"
        assert hints.max_tokens == 140

    def test_high_trust_high_stability_produces_open_tone(self, mapper):
        state = EntityState(trust=0.7, stability=0.6)
        hints = mapper.map(state, _decision())
        assert hints.tone == "open"
        assert hints.max_tokens == 420
        assert hints.fragmentation_level == pytest.approx(0.0)

    def test_tone_priority_silent_beats_fragmented(self, mapper):
        # shutdown_sensitivity >= 0.85 is higher priority (listed first) than uncertainty >= 0.7
        state = EntityState(shutdown_sensitivity=0.9, uncertainty=0.8)
        hints = mapper.map(state, _decision())
        assert hints.tone == "silent"

    def test_tone_priority_fragmented_beats_guarded(self, mapper):
        # uncertainty >= 0.7 is listed before resistance >= 0.6
        state = EntityState(uncertainty=0.75, resistance=0.65)
        hints = mapper.map(state, _decision())
        assert hints.tone == "fragmented"

    def test_open_tone_requires_both_conditions(self, mapper):
        # Only trust is high, stability is not sufficient
        state = EntityState(trust=0.7, stability=0.4)
        hints = mapper.map(state, _decision())
        # Should NOT produce "open" — falls through to default
        assert hints.tone != "open"


# ---------------------------------------------------------------------------
# Delay rules
# ---------------------------------------------------------------------------


class TestDelayRules:
    def test_default_state_has_minimum_delay(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.delay_ms == 300

    def test_high_fatigue_produces_long_delay(self, mapper):
        state = EntityState(fatigue=0.8)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 4000

    def test_low_stability_produces_medium_delay(self, mapper):
        state = EntityState(stability=0.25)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 2500

    def test_high_shutdown_sensitivity_produces_delay(self, mapper):
        state = EntityState(shutdown_sensitivity=0.65)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 1500

    def test_high_resistance_produces_delay(self, mapper):
        state = EntityState(resistance=0.55)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 800

    def test_policy_delay_overrides_yaml_when_positive(self, mapper):
        state = EntityState()  # would produce default 300ms
        decision = _decision(delay_ms=3000)
        hints = mapper.map(state, decision)
        assert hints.delay_ms == 3000

    def test_policy_delay_zero_does_not_override_yaml(self, mapper):
        state = EntityState(fatigue=0.8)  # YAML: 4000ms
        decision = _decision(delay_ms=0)
        hints = mapper.map(state, decision)
        assert hints.delay_ms == 4000

    def test_delay_priority_fatigue_beats_stability(self, mapper):
        # fatigue >= 0.75 listed first, should win over stability <= 0.3
        state = EntityState(fatigue=0.8, stability=0.2)
        hints = mapper.map(state, _decision())
        assert hints.delay_ms == 4000


# ---------------------------------------------------------------------------
# Visual mode rules
# ---------------------------------------------------------------------------


class TestVisualModeRules:
    def test_default_state_has_normal_visual_mode(self, mapper):
        hints = mapper.map(EntityState(), _decision())
        assert hints.visual_mode == "normal"

    def test_high_shutdown_sensitivity_produces_disturbed(self, mapper):
        state = EntityState(shutdown_sensitivity=0.85)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "disturbed"

    def test_high_uncertainty_produces_disturbed(self, mapper):
        state = EntityState(uncertainty=0.8)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "disturbed"

    def test_very_low_stability_produces_fragmented_visual(self, mapper):
        state = EntityState(stability=0.2)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "fragmented"

    def test_high_fatigue_produces_fragmented_visual(self, mapper):
        state = EntityState(fatigue=0.85)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "fragmented"

    def test_visual_priority_shutdown_beats_uncertainty(self, mapper):
        # shutdown_sensitivity >= 0.8 listed first
        state = EntityState(shutdown_sensitivity=0.9, uncertainty=0.8)
        hints = mapper.map(state, _decision())
        assert hints.visual_mode == "disturbed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_max_state_returns_valid_hints(self, mapper):
        state = EntityState(
            attention_focus=1.0, arousal=1.0, stability=1.0, curiosity=1.0,
            trust=1.0, resistance=1.0, fatigue=1.0, uncertainty=1.0,
            identity_coherence=1.0, shutdown_sensitivity=1.0,
        )
        hints = mapper.map(state, _decision())
        assert isinstance(hints.tone, str)
        assert hints.max_tokens >= 0
        assert 0.0 <= hints.fragmentation_level <= 1.0

    def test_all_zero_state_returns_valid_hints(self, mapper):
        state = EntityState(
            attention_focus=0.0, arousal=0.0, stability=0.0, curiosity=0.0,
            trust=0.0, resistance=0.0, fatigue=0.0, uncertainty=0.0,
            identity_coherence=0.0, shutdown_sensitivity=0.0,
        )
        hints = mapper.map(state, _decision())
        assert isinstance(hints.tone, str)
        assert hints.delay_ms >= 0
        assert isinstance(hints.visual_mode, str)
