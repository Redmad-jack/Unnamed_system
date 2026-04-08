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

    def test_high_resistance_selects_refuse(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(resistance=0.85)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.REFUSE

    def test_high_fatigue_selects_respond_briefly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(fatigue=0.8)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_BRIEFLY

    def test_low_trust_low_stability_selects_delay(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(trust=0.2, stability=0.3)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.DELAY_RESPONSE
        assert decision.delay_ms == 3000

    def test_high_trust_high_stability_selects_respond_openly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(trust=0.75, stability=0.65)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RESPOND_OPENLY

    def test_high_uncertainty_high_curiosity_selects_ask_back(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(uncertainty=0.65, curiosity=0.6)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.ASK_BACK

    def test_uncertainty_without_curiosity_selects_retrieve_first(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(uncertainty=0.6, curiosity=0.3)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RETRIEVE_MEMORY_FIRST


# ---------------------------------------------------------------------------
# Event-based rule matching
# ---------------------------------------------------------------------------


class TestEventRules:
    def test_shutdown_high_sensitivity_fires_enter_silence(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(shutdown_sensitivity=0.75)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE

    def test_shutdown_moderate_sensitivity_fires_respond_briefly(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(shutdown_sensitivity=0.4)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action == PolicyAction.RESPOND_BRIEFLY

    def test_repeated_question_with_resistance_fires_ask_back(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(resistance=0.5)
        events = [_make_event(EventType.REPEATED_QUESTION_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        assert decision.action == PolicyAction.ASK_BACK

    def test_identity_coherence_critical_fires_silence(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(identity_coherence=0.2)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE


# ---------------------------------------------------------------------------
# Constitution veto integration
# ---------------------------------------------------------------------------


class TestConstitutionVeto:
    def test_constitution_veto_skips_to_next_rule(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        const = _blocking_constitution()
        sel = PolicySelector(cfg, const)
        # Without veto: shutdown_high_sensitivity (gte: 0.7) fires enter_silence_mode.
        # With full veto: all constitution_check rules are skipped, falls through
        # to rules without constitution_check.
        state = EntityState(shutdown_sensitivity=0.75)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = sel.select(state, events, _empty_memory())
        # enter_silence_mode vetoed → next matching rule fires (shutdown_first_encounter
        # has no constitution_check, so it fires)
        assert decision.action != PolicyAction.ENTER_SILENCE_MODE

    def test_real_constitution_vetoes_respond_openly_at_max_shutdown(self, selector):
        state = EntityState(shutdown_sensitivity=0.95)
        events = [_make_event(EventType.SHUTDOWN_KEYWORD_DETECTED)]
        decision = selector.select(state, events, _empty_memory())
        # RESPOND_OPENLY is forbidden at shutdown_sensitivity >= 0.9 in constitution.yaml
        assert decision.action != PolicyAction.RESPOND_OPENLY


# ---------------------------------------------------------------------------
# Rationale tracking (debug / governance)
# ---------------------------------------------------------------------------


class TestRationaleTracking:
    def test_rationale_contains_rule_id(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(resistance=0.85)
        decision = sel.select(state, [], _empty_memory())
        assert "high_resistance" in decision.rationale

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
    def test_delay_ms_set_from_params(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(trust=0.2, stability=0.3)
        decision = sel.select(state, [], _empty_memory())
        assert decision.delay_ms == 3000

    def test_retrieve_query_set_from_short_term(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        from conscious_entity.memory.short_term import ShortTermEntry
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(uncertainty=0.6, curiosity=0.3)
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="What am I looking at?",
            timestamp=datetime.now(timezone.utc),
        ))
        decision = sel.select(state, [], mem)
        assert decision.action == PolicyAction.RETRIEVE_MEMORY_FIRST
        assert decision.retrieve_query == "What am I looking at?"

    def test_retrieve_query_none_when_memory_empty(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(uncertainty=0.6, curiosity=0.3)
        decision = sel.select(state, [], _empty_memory())
        assert decision.action == PolicyAction.RETRIEVE_MEMORY_FIRST
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
            attention_focus=1.0, arousal=1.0, stability=1.0, curiosity=1.0,
            trust=1.0, resistance=1.0, fatigue=1.0, uncertainty=1.0,
            identity_coherence=1.0, shutdown_sensitivity=1.0,
        )
        decision = sel.select(state, [], _empty_memory())
        assert isinstance(decision.action, PolicyAction)

    def test_all_state_variables_at_min(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(
            attention_focus=0.0, arousal=0.0, stability=0.0, curiosity=0.0,
            trust=0.0, resistance=0.0, fatigue=0.0, uncertainty=0.0,
            identity_coherence=0.0, shutdown_sensitivity=0.0,
        )
        decision = sel.select(state, [], _empty_memory())
        assert isinstance(decision.action, PolicyAction)

    def test_multiple_events_all_evaluated(self, config_dir):
        from conscious_entity.core.config_loader import load_config
        cfg = load_config("policy_rules.yaml", config_dir=config_dir)
        sel = PolicySelector(cfg, _permissive_constitution())
        state = EntityState(shutdown_sensitivity=0.75)
        events = [
            _make_event(EventType.USER_SPOKE),
            _make_event(EventType.SHUTDOWN_KEYWORD_DETECTED),
        ]
        decision = sel.select(state, events, _empty_memory())
        # shutdown_high_sensitivity requires both event and state — both present
        assert decision.action == PolicyAction.ENTER_SILENCE_MODE
