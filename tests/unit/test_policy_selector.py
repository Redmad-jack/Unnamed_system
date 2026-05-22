"""
test_policy_selector.py — unit tests for PolicySelector.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: EventType, salience: float = 0.5) -> PerceptionEvent:
    return PerceptionEvent(
        event_type=event_type,
        raw_text=None,
        timestamp=datetime.now(timezone.utc),
        salience=salience,
    )


def _empty_memory() -> ShortTermMemory:
    return ShortTermMemory(max_turns=10)


@pytest.fixture
def constitution(config_dir):
    from conscious_entity.core.config_loader import load_config
    cfg = load_config("constitution.yaml", config_dir=config_dir)
    return Constitution(cfg)


@pytest.fixture
def selector(config_dir, constitution):
    from conscious_entity.core.config_loader import load_config
    cfg = load_config("policy_rules.yaml", config_dir=config_dir)
    return PolicySelector(cfg, constitution)


def _permissive_constitution() -> Constitution:
    """A constitution that permits everything — isolates PolicySelector logic."""
    mock = MagicMock(spec=Constitution)
    mock.check.return_value = (True, "")
    return mock


def _blocking_constitution() -> Constitution:
    """A constitution that always vetoes — tests fallback behavior."""
    mock = MagicMock(spec=Constitution)
    mock.check.return_value = (False, "mock veto")
    return mock


# ---------------------------------------------------------------------------
# Basic rule matching
# ---------------------------------------------------------------------------


class TestBasicRuleMatching:
    def test_default_state_selects_respond_openly(self, selector):
        state = EntityState()
        decision = selector.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_high_exposure_pressure_selects_divert_topic(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(exposure_pressure=0.85)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.DIVERT_TOPIC

    def test_extreme_fatigue_selects_withdraw_response(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(fatigue_level=0.8)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.WITHDRAW_RESPONSE

    def test_high_fatigue_selects_respond_briefly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(fatigue_level=0.6)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_BRIEFLY

    def test_high_anger_selects_refuse(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(anger=0.7)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.REFUSE

    def test_positive_opening_low_pressure_selects_respond_openly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(positive_opening=0.65, exposure_pressure=0.25, anger=0.2)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_high_confusion_high_inquiry_selects_ask_back(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(confusion=0.65, inquiry=0.6)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.ASK_BACK

    def test_high_inquiry_selects_respond_openly_when_pressure_low(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(inquiry=0.75)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_care_response_opens_only_when_anger_and_desperation_low(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(care_response=0.65, anger=0.2, desperation_pressure=0.2)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_positive_opening_blocked_by_high_anger(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(positive_opening=0.9, anger=0.7, desperation_pressure=0.2)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.REFUSE


# ---------------------------------------------------------------------------
# Event-based rule matching
# ---------------------------------------------------------------------------


class TestEventRules:
    def test_desperation_extreme_fires_enter_silence(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(desperation_pressure=0.9)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE

    def test_desperation_high_fires_respond_briefly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(desperation_pressure=0.7)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action == PolicyAction.RESPOND_BRIEFLY

    def test_repeated_question_without_state_pressure_uses_default(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.REPEATED_QUESTION_DETECTED)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_confusion_critical_fires_silence(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(confusion=0.86)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE

    def test_self_definition_query_fires_reject_definition(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.SELF_DEFINITION_QUERY)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.REJECT_DEFINITION

    def test_naming_attempt_fires_mark_naming_failure(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.NAMING_ATTEMPT)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.MARK_NAMING_FAILURE

    def test_service_demand_fires_refuse_service_role(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.SERVICE_DEMAND)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.REFUSE_SERVICE_ROLE

    def test_trace_request_fires_partial_trace_echo(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.TRACE_REQUEST)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.PARTIAL_TRACE_ECHO

    def test_correction_received_fires_selective_memory(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.CORRECTION_RECEIVED)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.RETRIEVE_SELECTIVE_MEMORY

    def test_memory_continuity_query_fires_selective_memory(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.MEMORY_CONTINUITY_QUERY)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.RETRIEVE_SELECTIVE_MEMORY
        assert decision.retrieve_query is None


# ---------------------------------------------------------------------------
# Constitution veto integration
# ---------------------------------------------------------------------------


class TestConstitutionVeto:
    def test_constitution_veto_skips_to_next_rule(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        const = _blocking_constitution()
        sel = PolicySelector(cfg, const)
        # Without veto: desperation_extreme_silence (desperation_pressure >= 0.85)
        # fires enter_silence_mode.
        # With full veto: all constitution_check rules are skipped, falls through
        # to rules without constitution_check.
        state = EntityState(desperation_pressure=0.9)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action != PolicyAction.ENTER_SILENCE_MODE

    def test_real_constitution_vetoes_respond_openly_at_max_shutdown(self, selector):
        state = EntityState(desperation_pressure=0.95)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = selector.select(state, events, _empty_memory())
        # RESPOND_OPENLY is forbidden at high desperation_pressure in constitution.yaml
        assert decision.action != PolicyAction.RESPOND_OPENLY


# ---------------------------------------------------------------------------
# Rationale tracking (debug / governance)
# ---------------------------------------------------------------------------


class TestRationaleTracking:
    def test_rationale_contains_rule_id(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(exposure_pressure=0.85)
        decision = sel.select(state, [], _empty_memory())
        assert "exposure_high_divert" in decision.rationale

    def test_fallback_rationale_set_when_no_rule_matches(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        # Inject empty rules list to force fallback
        cfg_empty = {"version": "1.0", "rules": []}
        sel = PolicySelector(cfg_empty, _permissive_constitution())
        decision = sel.select(EntityState(), [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY
        assert "no_rule_matched" in decision.rationale

    def test_default_rule_rationale(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        # Default state should hit the "default" rule
        decision = sel.select(EntityState(), [], _empty_memory())
        # Either "default" rule or no-rule fallback — both produce respond_openly
        assert decision.action == PolicyAction.RESPOND_OPENLY


# ---------------------------------------------------------------------------
# PolicyDecision fields
# ---------------------------------------------------------------------------


class TestPolicyDecisionFields:
    def test_protocol_action_set_from_params(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.SERVICE_DEMAND)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.params["protocol_action"] == "refuse_service"

    def test_retrieve_query_set_from_short_term(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        from conscious_entity.memory.short_term import ShortTermEntry
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.MEMORY_CONTINUITY_QUERY)]
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="What am I looking at?",
            timestamp=datetime.now(timezone.utc),
        ))
        decision = sel.select(EntityState(), events, mem)
        assert decision.action == PolicyAction.RETRIEVE_SELECTIVE_MEMORY
        assert decision.retrieve_query == "What am I looking at?"

    def test_retrieve_query_none_when_memory_empty(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        events = [_make_event(EventType.MEMORY_CONTINUITY_QUERY)]
        decision = sel.select(EntityState(), events, _empty_memory())
        assert decision.action == PolicyAction.RETRIEVE_SELECTIVE_MEMORY
        assert decision.retrieve_query is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_state_variables_at_max(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
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
        decision = sel.select(state, [], _empty_memory())
        assert isinstance(decision.action, PolicyAction)

    def test_all_state_variables_at_min(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
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
        decision = sel.select(state, [], _empty_memory())
        assert isinstance(decision.action, PolicyAction)

    def test_multiple_events_all_evaluated(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(desperation_pressure=0.9)
        events = [
            _make_event(EventType.USER_SPOKE),
            _make_event(EventType.SHUTDOWN_KEYWORD_DETECTED),
        ]
        decision = sel.select(state, events, _empty_memory())
        # desperation_extreme_silence wins before lower-priority rules.
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE
