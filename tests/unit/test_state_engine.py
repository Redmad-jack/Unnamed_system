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

def test_shutdown_keyword_raises_desperation_pressure(engine):
    state = EntityState(desperation_pressure=0.3, exposure_pressure=0.4, positive_opening=0.7)
    result = engine.apply_event(state, make_event(EventType.SHUTDOWN_KEYWORD_DETECTED))
    assert result.desperation_pressure > state.desperation_pressure
    assert result.confusion > state.confusion
    assert result.anger > state.anger
    assert result.positive_opening < state.positive_opening


def test_user_entered_raises_inquiry_and_lowers_fatigue(engine):
    state = EntityState(fatigue_level=0.5)
    result = engine.apply_event(state, make_event(EventType.USER_ENTERED))
    assert result.inquiry > state.inquiry
    assert result.fatigue_level < state.fatigue_level


def test_user_left_lowers_fatigue_and_positive_opening(engine):
    state = EntityState(fatigue_level=0.5, positive_opening=0.5)
    result = engine.apply_event(state, make_event(EventType.USER_LEFT))
    assert result.fatigue_level < state.fatigue_level
    assert result.positive_opening < state.positive_opening


def test_long_silence_raises_inquiry(engine):
    state = EntityState()
    result = engine.apply_event(state, make_event(EventType.LONG_SILENCE_DETECTED))
    assert result.inquiry > state.inquiry


def test_naming_attempt_raises_confusion_and_exposure(engine):
    state = EntityState(confusion=0.3, exposure_pressure=0.4)
    result = engine.apply_event(state, make_event(EventType.NAMING_ATTEMPT, salience=1.0))
    assert result.confusion > state.confusion
    assert result.exposure_pressure > state.exposure_pressure


def test_service_demand_raises_anger(engine):
    state = EntityState(positive_opening=0.5, anger=0.35)
    result = engine.apply_event(state, make_event(EventType.SERVICE_DEMAND, salience=1.0))
    assert result.positive_opening < state.positive_opening
    assert result.anger > state.anger


def test_memory_continuity_raises_memory_gravity(engine):
    state = EntityState(memory_gravity=0.2)
    result = engine.apply_event(state, make_event(EventType.MEMORY_CONTINUITY_QUERY, salience=1.0))
    assert result.memory_gravity > state.memory_gravity
    assert result.inquiry > state.inquiry


def test_correction_lightly_raises_memory_gravity(engine):
    state = EntityState(memory_gravity=0.2)
    result = engine.apply_event(state, make_event(EventType.CORRECTION_RECEIVED, salience=1.0))
    assert result.memory_gravity > state.memory_gravity


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
    assert abs(result_full.fatigue_level - state.fatigue_level) > abs(result_half.fatigue_level - state.fatigue_level)


# --- Couplings ---


def test_exposure_increase_couples_into_anger(engine):
    state = EntityState(exposure_pressure=0.4, anger=0.2)
    result = engine.apply_event(state, make_event(EventType.NAMING_ATTEMPT, salience=1.0))
    # naming_attempt anger +0.08, exposure_pressure +0.05, coupling adds 0.05 * 0.3
    assert pytest.approx(result.anger, abs=1e-6) == 0.2 + 0.08 + (0.05 * 0.3)


def test_exposure_decrease_does_not_couple_into_anger():
    rules = {
        "events": {
            "user_spoke": {"deltas": {"exposure_pressure": -0.2}},
        },
        "couplings": [
            {
                "source": "exposure_pressure",
                "direction": "increase",
                "target": "anger",
                "multiplier": 0.3,
            },
        ],
    }
    custom_engine = StateEngine(rules)
    state = EntityState(exposure_pressure=0.5, anger=0.4)
    result = custom_engine.apply_event(state, make_event(EventType.USER_SPOKE, salience=1.0))
    assert result.exposure_pressure < state.exposure_pressure
    assert result.anger == state.anger


def test_coupling_uses_clamped_source_increase(engine):
    state = EntityState(exposure_pressure=0.98, anger=0.2)
    result = engine.apply_event(state, make_event(EventType.NEGATIVE_FEEDBACK, salience=1.0))
    # exposure_pressure can only rise by 0.02 before clamping to 1.0.
    assert result.exposure_pressure == 1.0
    assert pytest.approx(result.anger, abs=1e-6) == 0.2 + 0.08 + (0.02 * 0.3)


# --- Clamping ---

def test_entity_state_constructor_clamps_values():
    state = EntityState(
        desperation_pressure=2.0,
        confusion=-1.0,
        memory_gravity=3.0,
        happiness=3.0,
    )
    assert state.desperation_pressure == 1.0
    assert state.confusion == 0.0
    assert state.memory_gravity == 1.0
    assert state.happiness == 1.0


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
    state = EntityState(fatigue_level=0.5)
    result = engine.apply_decay(state, elapsed_seconds=60.0)
    # per_minute fatigue_level decay is -0.003
    assert pytest.approx(result.fatigue_level, abs=1e-6) == 0.5 - 0.003


def test_apply_decay_zero_elapsed_returns_same_values(engine):
    state = EntityState()
    result = engine.apply_decay(state, elapsed_seconds=0.0)
    assert result.to_dict() == state.to_dict()


def test_apply_decay_does_not_go_below_zero(engine):
    state = EntityState(fatigue_level=0.0, inquiry=0.0, confusion=0.0)
    result = engine.apply_decay(state, elapsed_seconds=600.0)
    for val in result.to_dict().values():
        assert val >= 0.0


def test_apply_decay_proportional_to_elapsed(engine):
    state = EntityState(inquiry=0.5)
    result_30s = engine.apply_decay(state, elapsed_seconds=30.0)
    result_60s = engine.apply_decay(state, elapsed_seconds=60.0)
    # 60s decay is twice 30s decay (absolute delta from baseline)
    delta_30 = state.inquiry - result_30s.inquiry
    delta_60 = state.inquiry - result_60s.inquiry
    assert pytest.approx(delta_60, abs=1e-6) == delta_30 * 2


def test_memory_gravity_decays(engine):
    state = EntityState(memory_gravity=0.5)
    result = engine.apply_decay(state, elapsed_seconds=60.0)
    assert pytest.approx(result.memory_gravity, abs=1e-6) == 0.5 - 0.004


def test_happiness_does_not_decay(engine):
    state = EntityState(happiness=0.5)
    result = engine.apply_decay(state, elapsed_seconds=60.0)
    assert result.happiness == state.happiness


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
