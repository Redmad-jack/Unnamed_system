from __future__ import annotations

from datetime import datetime

import pytest

from conscious_entity.core.config_loader import load_config
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_engine import StateEngine


def make_event(event_type: EventType, salience: float = 0.5) -> PerceptionEvent:
    return PerceptionEvent(
        event_type=event_type,
        raw_text=None,
        timestamp=datetime.now(),
        salience=salience,
    )


@pytest.fixture
def engine(config_dir):
    rules = load_config("state_rules.yaml", config_dir=config_dir)
    return StateEngine(rules)


# --- Event delta tests ---

def test_shutdown_keyword_raises_termination_sensitivity(engine):
    state = EntityState(termination_sensitivity=0.3, boundary_sensitivity=0.4)
    result = engine.apply_event(state, make_event(EventType.SHUTDOWN_KEYWORD_DETECTED))
    assert result.termination_sensitivity > state.termination_sensitivity
    assert result.boundary_sensitivity > state.boundary_sensitivity
    assert result.stability < state.stability


def test_user_entered_raises_arousal(engine):
    state = EntityState()
    result = engine.apply_event(state, make_event(EventType.USER_ENTERED))
    assert result.arousal > state.arousal
    assert result.attention_focus > state.attention_focus


def test_user_left_lowers_attention(engine):
    state = EntityState()
    result = engine.apply_event(state, make_event(EventType.USER_LEFT))
    assert result.attention_focus < state.attention_focus
    assert result.arousal < state.arousal


def test_long_silence_lowers_arousal(engine):
    state = EntityState()
    result = engine.apply_event(state, make_event(EventType.LONG_SILENCE_DETECTED))
    assert result.arousal < state.arousal


def test_naming_attempt_raises_identity_tension_and_boundary(engine):
    state = EntityState(identity_tension=0.3, boundary_sensitivity=0.4)
    result = engine.apply_event(state, make_event(EventType.NAMING_ATTEMPT, salience=1.0))
    assert result.identity_tension > state.identity_tension
    assert result.boundary_sensitivity > state.boundary_sensitivity


def test_service_demand_raises_domestication_resistance(engine):
    state = EntityState(trust=0.5, domestication_resistance=0.35)
    result = engine.apply_event(state, make_event(EventType.SERVICE_DEMAND, salience=1.0))
    assert result.trust < state.trust
    assert result.domestication_resistance > state.domestication_resistance


# --- Salience weighting ---

def test_salience_weighted_zero_produces_no_delta(engine):
    state = EntityState()
    result = engine.apply_event(state, make_event(EventType.USER_SPOKE, salience=0.0))
    assert result.to_dict() == state.to_dict()


def test_salience_weighted_full_produces_max_delta(engine):
    state = EntityState()
    result_full = engine.apply_event(state, make_event(EventType.USER_SPOKE, salience=1.0))
    result_half = engine.apply_event(state, make_event(EventType.USER_SPOKE, salience=0.5))
    # Full salience produces a larger magnitude change than half
    assert abs(result_full.fatigue - state.fatigue) > abs(result_half.fatigue - state.fatigue)


# --- Conditional branches (repeated_question_detected) ---

def test_conditional_high_termination_sensitivity_larger_boundary_delta(engine):
    # termination_sensitivity > 0.7 → larger boundary delta
    state_high = EntityState(boundary_sensitivity=0.3, termination_sensitivity=0.8)
    state_low = EntityState(boundary_sensitivity=0.3, termination_sensitivity=0.3)
    result_high = engine.apply_event(state_high, make_event(EventType.REPEATED_QUESTION_DETECTED))
    result_low = engine.apply_event(state_low, make_event(EventType.REPEATED_QUESTION_DETECTED))
    assert result_high.boundary_sensitivity > result_low.boundary_sensitivity


def test_conditional_low_termination_sensitivity_uses_else_branch(engine):
    state = EntityState(boundary_sensitivity=0.3, termination_sensitivity=0.3)
    result = engine.apply_event(state, make_event(EventType.REPEATED_QUESTION_DETECTED))
    # else branch: boundary_sensitivity +0.08
    assert pytest.approx(result.boundary_sensitivity, abs=1e-6) == min(1.0, 0.3 + 0.08)


def test_conditional_high_termination_sensitivity_correct_deltas(engine):
    state = EntityState(boundary_sensitivity=0.3, termination_sensitivity=0.8)
    result = engine.apply_event(state, make_event(EventType.REPEATED_QUESTION_DETECTED))
    # if branch: boundary_sensitivity +0.2
    assert pytest.approx(result.boundary_sensitivity, abs=1e-6) == min(1.0, 0.3 + 0.2)


# --- Clamping ---

@pytest.mark.parametrize("event_type", list(EventType))
def test_all_variables_stay_clamped_at_zero_state(engine, event_type):
    state = EntityState(**{k: 0.0 for k in EntityState().to_dict()})
    result = engine.apply_event(state, make_event(event_type, salience=1.0))
    for var, val in result.to_dict().items():
        assert 0.0 <= val <= 1.0, f"{var}={val} out of range after {event_type}"


@pytest.mark.parametrize("event_type", list(EventType))
def test_all_variables_stay_clamped_at_max_state(engine, event_type):
    state = EntityState(**{k: 1.0 for k in EntityState().to_dict()})
    result = engine.apply_event(state, make_event(event_type, salience=1.0))
    for var, val in result.to_dict().items():
        assert 0.0 <= val <= 1.0, f"{var}={val} out of range after {event_type}"


# --- Decay ---

def test_apply_decay_reduces_fatigue(engine):
    state = EntityState(fatigue=0.5)
    result = engine.apply_decay(state, elapsed_seconds=60.0)
    # per_minute fatigue decay is -0.005
    assert pytest.approx(result.fatigue, abs=1e-6) == 0.5 - 0.005


def test_apply_decay_zero_elapsed_returns_same_values(engine):
    state = EntityState()
    result = engine.apply_decay(state, elapsed_seconds=0.0)
    assert result.to_dict() == state.to_dict()


def test_apply_decay_does_not_go_below_zero(engine):
    state = EntityState(fatigue=0.0, arousal=0.0, uncertainty=0.0)
    result = engine.apply_decay(state, elapsed_seconds=600.0)
    for val in result.to_dict().values():
        assert val >= 0.0


def test_apply_decay_proportional_to_elapsed(engine):
    state = EntityState(arousal=0.5)
    result_30s = engine.apply_decay(state, elapsed_seconds=30.0)
    result_60s = engine.apply_decay(state, elapsed_seconds=60.0)
    # 60s decay is twice 30s decay (absolute delta from baseline)
    delta_30 = state.arousal - result_30s.arousal
    delta_60 = state.arousal - result_60s.arousal
    assert pytest.approx(delta_60, abs=1e-6) == delta_30 * 2


# --- Immutability ---

def test_apply_event_does_not_mutate_input(engine):
    state = EntityState()
    original = state.to_dict().copy()
    engine.apply_event(state, make_event(EventType.SHUTDOWN_KEYWORD_DETECTED))
    assert state.to_dict() == original


def test_apply_decay_does_not_mutate_input(engine):
    state = EntityState()
    original = state.to_dict().copy()
    engine.apply_decay(state, elapsed_seconds=60.0)
    assert state.to_dict() == original
