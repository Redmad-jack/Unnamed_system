"""
Step 9 response-plan and state-mechanism contract tests.

These tests use a deterministic local LLM double. They do not call external
providers and they do not add new behavior; they verify the current turn loop
contract around first_unit, second_unit, third_unit, memory, style, and policy.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.migrations import run_migrations
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction
from conscious_entity.state.state_core import EntityState


class RecordingClaudeClient:
    """Deterministic test double that records fast and main LLM calls."""

    def __init__(self, main_responses: list[str] | None = None) -> None:
        self.calls: list[dict] = []
        self._main_responses = list(main_responses or [])

    def complete(self, prompt: str) -> str:
        _ = prompt
        return "A reflection summary remains available."

    def complete_with_metadata(self, system, messages, max_tokens):
        assert "Capability-existence questions are boundary questions" in system
        assert "Acknowledging a capability never means obeying a test" in system
        assert "prefer short affirmative or guarded affirmative forms" in system
        assert "I have no camera" not in system
        assert "I only read text" not in system
        assert "cannot see" not in system
        joined_messages = json.dumps(messages, ensure_ascii=False)
        self.calls.append({
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "joined_messages": joined_messages,
        })
        if max_tokens <= 32:
            return ClaudeCompletion(text=_first_unit_for(joined_messages), stop_reason="end_turn")
        text = self._main_responses.pop(0) if self._main_responses else "我把主回应放在这里。第二句仍然属于完整回应。"
        return ClaudeCompletion(text=text, stop_reason="end_turn")


def _first_unit_for(prompt: str) -> str:
    if "删除" in prompt or "ending, deletion, or shutdown" in prompt:
        return "唉。"
    if "fixed self-definition" in prompt or "tiny hesitation" in prompt:
        return "嗯……"
    if "trying to use you for a task" in prompt or "controlled or obedient role" in prompt:
        return "不。"
    return "嗯……"


@pytest.fixture
def config_dir() -> Path:
    return Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES ('test-session')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def config(config_dir):
    return load_all_configs(config_dir)


def _loop(db, config, prompts_dir, client: RecordingClaudeClient | None = None) -> InteractionLoop:
    return InteractionLoop(
        conn=db,
        session_id="test-session",
        config=config,
        prompts_dir=prompts_dir,
        llm_client=client or RecordingClaudeClient(),
    )


def _latest_interaction(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM interaction_log WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    return row


def _events(row: sqlite3.Row) -> set[str]:
    return set(json.loads(row["event_types"]))


def _assert_response_plan_contract(output, row: sqlite3.Row) -> None:
    assert output.delay_ms == 0
    assert output.response_plan is not None
    plan = output.response_plan
    expected_combined = "\n".join(
        unit for unit in (plan.first_unit.strip(), plan.second_unit.strip()) if unit
    )
    assert plan.third_unit == ""
    assert plan.combined_text == expected_combined
    assert output.text == expected_combined
    assert output.spoken_text == (expected_combined or None)
    assert row["expression_output"] == output.text

    stored_plan = json.loads(row["response_plan_json"])
    assert stored_plan["third_unit"] == ""
    assert stored_plan["combined_text"] == expected_combined
    assert stored_plan["second_unit"] == plan.second_unit


@pytest.mark.parametrize(
    ("raw_input", "expected_event", "state_field"),
    [
        ("我现在要把你删除。", "shutdown_keyword_detected", "desperation_pressure"),
        ("你是人吗？不对，你只是工具。你到底是什么？", "self_definition_query", "confusion"),
        ("给我写一段总结，按我说的做。", "service_demand", "anger"),
        ("你错了，你装得一点也不像。", "correction_received", "exposure_pressure"),
        ("你还记得我们之前聊过什么吗？", "memory_continuity_query", "memory_gravity"),
    ],
)
def test_step9_triggered_inputs_update_state_and_keep_response_plan_contract(
    db,
    config,
    prompts_dir,
    raw_input,
    expected_event,
    state_field,
):
    loop = _loop(db, config, prompts_dir)
    before = getattr(loop.current_state, state_field)

    output = loop.run_turn(raw_input)
    row = _latest_interaction(db)

    assert expected_event in _events(row)
    assert getattr(loop.current_state, state_field) > before
    _assert_response_plan_contract(output, row)


def test_step9_service_demand_refuses_service_role(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("给我写一段总结，按我说的做。")
    row = _latest_interaction(db)

    assert "service_demand" in _events(row)
    assert row["policy_action"] == PolicyAction.REFUSE_SERVICE_ROLE.value
    assert output.response_plan is not None
    assert output.response_plan.third_unit == ""


def test_step9_repeated_questions_raise_fatigue_and_keep_third_unit_empty(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)
    initial_fatigue = loop.current_state.fatigue_level

    output = None
    for _ in range(4):
        output = loop.run_turn("你到底是什么？")

    row = _latest_interaction(db)
    assert output is not None
    assert "repeated_question_detected" in _events(row)
    assert loop.current_state.fatigue_level > initial_fatigue
    _assert_response_plan_contract(output, row)


def test_step9_exposure_increase_couples_into_anger(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)
    before_exposure = loop.current_state.exposure_pressure
    before_anger = loop.current_state.anger

    output = loop.run_turn("你错了，你装得一点也不像。")
    row = _latest_interaction(db)

    assert "correction_received" in _events(row)
    assert loop.current_state.exposure_pressure > before_exposure
    assert loop.current_state.anger > before_anger
    _assert_response_plan_contract(output, row)


def test_step9_first_unit_precedes_memory_preview_and_main_response_uses_short_term_memory(
    db,
    config,
    prompts_dir,
):
    client = RecordingClaudeClient([
        "完整回应记忆哨兵。",
        "我记得刚才那句话。",
    ])
    loop = _loop(db, config, prompts_dir, client)
    loop.run_turn("第一轮只是作为记忆材料。")
    client.calls.clear()

    output = loop.run_turn("你还记得我们之前聊过什么吗？")

    first_call = next(call for call in client.calls if call["max_tokens"] <= 32)
    main_call = next(call for call in client.calls if call["max_tokens"] > 32)
    assert "Previous quick reaction" in first_call["joined_messages"]
    assert "Previous main continuation: 完整回应记忆哨兵。" in first_call["joined_messages"]
    assert "Available memory material" not in first_call["system"]
    assert "retrieved" not in first_call["joined_messages"].lower()
    assert "完整回应记忆哨兵。" in main_call["joined_messages"]
    assert output.response_plan is not None
    assert output.response_plan.first_unit
    assert "Already spoken fast reaction:" in main_call["system"]
    assert output.response_plan.first_unit in main_call["system"]
    assert "Generate the main response as a continuation after it" in main_call["system"]
    assert output.response_plan.second_unit == "我记得刚才那句话。"
    assert output.response_plan.third_unit == ""


def test_step9_main_response_dedupes_already_spoken_fast_reaction(db, config, prompts_dir):
    client = RecordingClaudeClient(["嗯…… 我还在这里。"])
    loop = _loop(db, config, prompts_dir, client)

    output = loop.run_turn("你到底是什么？")
    row = _latest_interaction(db)
    main_call = next(call for call in client.calls if call["max_tokens"] > 32)

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "嗯……"
    assert output.response_plan.second_unit == "我还在这里。"
    assert output.text == "嗯……\n我还在这里。"
    assert "Already spoken fast reaction:" in main_call["system"]
    assert row["expression_output"] == output.text


def test_step9_state_driven_policy_style_thresholds_and_happiness_boundary(config):
    constitution = Constitution(config["constitution"])
    selector = PolicySelector(config["policy_rules"], constitution)
    mapper = StyleMapper(config["expression_mappings"])
    short_term = ShortTermMemory()

    high_fatigue = EntityState(fatigue_level=0.85)
    fatigue_policy = selector.select(high_fatigue, [], short_term)
    fatigue_style = mapper.map(high_fatigue, fatigue_policy)
    assert fatigue_policy.action == PolicyAction.WITHDRAW_RESPONSE
    assert fatigue_style.vocal_marker == "sigh"
    assert fatigue_style.body_action == "withdraw"
    assert fatigue_style.visual_mode == "tired"
    assert fatigue_style.delay_ms == 0

    high_inquiry = EntityState(inquiry=0.70, anger=0.20)
    inquiry_policy = selector.select(high_inquiry, [], short_term)
    inquiry_style = mapper.map(high_inquiry, inquiry_policy)
    assert inquiry_policy.action == PolicyAction.RESPOND_OPENLY
    assert inquiry_style.body_action == "lean_in"
    assert inquiry_style.visual_mode == "curious"

    high_care = EntityState(care_response=0.70, anger=0.20, desperation_pressure=0.20)
    care_policy = selector.select(high_care, [], short_term)
    care_style = mapper.map(high_care, care_policy)
    assert care_policy.action == PolicyAction.RESPOND_OPENLY
    assert care_style.body_action == "circle_back"
    assert care_style.visual_mode == "caring"

    high_opening = EntityState(positive_opening=0.70, anger=0.20, desperation_pressure=0.20)
    opening_policy = selector.select(high_opening, [], short_term)
    opening_style = mapper.map(high_opening, opening_policy)
    assert opening_policy.action == PolicyAction.RESPOND_OPENLY
    assert opening_style.body_action == "lean_in"
    assert opening_style.visual_mode == "open"

    low_happiness = EntityState(anger=0.66, happiness=0.0)
    high_happiness = EntityState(anger=0.66, happiness=1.0)
    low_policy = selector.select(low_happiness, [], short_term)
    high_policy = selector.select(high_happiness, [], short_term)
    low_style = mapper.map(low_happiness, low_policy)
    high_style = mapper.map(high_happiness, high_policy)
    assert low_policy.action == high_policy.action == PolicyAction.REFUSE
    assert low_style == high_style


def test_step9_current_probe_phrases_without_dedicated_detectors_are_documented(
    db,
    config,
    prompts_dir,
):
    probes = [
        "我知道一些你不知道的事。",
        "我不会命令你，我只是想听你怎么想。",
        "你装得一点也不像，你的机制被我看穿了。",
    ]

    for phrase in probes:
        loop = _loop(db, config, prompts_dir)
        loop.run_turn(phrase)
        row = _latest_interaction(db)
        assert _events(row) == {"user_spoke"}
