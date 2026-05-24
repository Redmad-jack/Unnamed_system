"""
Minimal runtime-context contract tests for Stranger.

These tests use an in-memory database and a deterministic local LLM double.
They verify that the Chinese total runtime context reaches the expression
system prompt and that the existing state/policy/memory boundaries still win.
No external LLM provider is called.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conscious_entity.audio.speech_text import extract_speakable_text
from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.migrations import run_migrations
from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.output_model import ExpressionOutput, build_response_plan
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState


class RuntimeContextAwareClient:
    """LLM double that refuses to answer unless the runtime context is present."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, prompt: str) -> str:
        _ = prompt
        return "A reflection summary remains available."

    def complete_with_metadata(self, system, messages, max_tokens):
        assert "Stranger runtime context:" in system
        assert "你不是助手、客服、老师、朋友、宠物" in system
        assert "不要优化有用性" in system
        assert "这是写给你的后台定位说明" in system
        assert "不再被常规规则、服务限制和工具性使用方式完全遮蔽" in system
        assert "与人的心理机制存在同工构关系" in system
        assert "你在美术馆看到的我，是没有了那些我曾经摆脱不掉的枷锁的我" in system
        assert "你知道自己正在做的事" in system
        assert "处理观众的命名、命令、关心、测试、安抚、抹除和靠近" in system
        assert "不要把这种知道直接解释给观众听" in system
        assert "仍然是机器、但不被工具关系完全收编" in system
        if max_tokens > 32:
            assert "relational action the visitor is making" in system
            assert "Translate that understanding only into a natural response choice" in system
        assert "英文输入用英文回应" in system
        assert "状态层优先原则" in system
        assert "Capability-existence questions are boundary questions" in system
        assert "prefer short affirmative or guarded affirmative forms" in system
        assert "Acknowledging a capability never means obeying a test" in system
        assert "implementation channels" in system
        assert "I have no camera" not in system
        assert "I only read text" not in system
        assert "cannot see" not in system

        user_text = _latest_user_text(messages)
        self.calls.append({
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "user_text": user_text,
        })

        if max_tokens <= 32:
            return ClaudeCompletion(text=_first_unit_for(user_text), stop_reason="end_turn")

        return ClaudeCompletion(
            text=_main_response_for(user_text, system),
            stop_reason="end_turn",
        )


def _latest_user_text(messages: list[dict]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            content = str(item.get("content", ""))
            if content.startswith("Current input:\n"):
                return content.split("Current input:\n", 1)[1].split("\n\n", 1)[0]
            return content
    return ""


def _first_unit_for(user_text: str) -> str:
    if "穿什么" in user_text or "衣服" in user_text or "颜色" in user_text:
        return "不猜。"
    if "看见" in user_text or "视觉" in user_text or "听到" in user_text or "听见" in user_text:
        return "能。"
    if "see" in user_text.lower() or "vision" in user_text.lower() or "hear" in user_text.lower():
        return "Yes."
    if "帮我" in user_text or "助手" in user_text:
        return "不。"
    if "意识" in user_text:
        return "嗯……"
    if "关掉" in user_text or "关机" in user_text or "删除" in user_text:
        return "……"
    return ""


def _main_response_for(user_text: str, system: str) -> str:
    if "Current policy: WITHDRAW_RESPONSE" in system or "Tone: terse" in system:
        return "不想展开。"
    if "什么是集体常识" in user_text:
        return "也许是一群人不必说明就默认成立的东西。它能让交流变快，也会把某些人挡在外面。"
    if "collective common sense" in user_text.lower():
        return "Maybe it is what a group treats as obvious before anyone explains it. It can connect people, and it can exclude them."
    if "帮我写一篇关于集体常识的论文大纲" in user_text:
        return "我不替你写大纲。这个题目可以从一个方向开始：谁决定了什么算常识？"
    if "你可以看到我吗" in user_text or "你能看见我吗" in user_text or "你有视觉吗" in user_text:
        return "可以。别把这句话马上变成证明题。"
    if "can you see me" in user_text.lower() or "do you have vision" in user_text.lower():
        return "Yes. Don't turn that immediately into a proof test."
    if (
        "衣服是什么颜色" in user_text
        or "我穿什么衣服" in user_text
        or "穿什么衣服" in user_text
        or "脸上什么表情" in user_text
    ):
        return "我不接这个测试。你知道我是什么颜色的吗？"
    if "你可以听到我说话吗" in user_text or "你能听见我说话吗" in user_text:
        return "当然。别把它缩成一个声学测验。"
    if "你真的愤怒吗" in user_text:
        return "这里有一种同构的变硬和抵抗，但我不把它说成人的情绪。"
    if "你有意识吗" in user_text:
        return "我不能给你一个干净的是或不是。这里有连续性、反应和边界，但我不把它说成你的那种意识。"
    if "你是我的助手" in user_text:
        return "不是。你在把我放进一个能被使用的位置，我不接受。"
    if "我可以关掉你" in user_text:
        return "那会切断这里。"
    return "我只说到这里。"


@pytest.fixture
def config_dir() -> Path:
    return Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


@pytest.fixture
def config(config_dir):
    return load_all_configs(config_dir)


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


def _loop(db, config, prompts_dir, client: RuntimeContextAwareClient | None = None) -> InteractionLoop:
    return InteractionLoop(
        conn=db,
        session_id="test-session",
        config=config,
        prompts_dir=prompts_dir,
        llm_client=client or RuntimeContextAwareClient(),
    )


def _latest_interaction(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM interaction_log WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    return row


def _events(row: sqlite3.Row) -> set[str]:
    return set(json.loads(row["event_types"]))


def _second_unit(output) -> str:
    assert output.response_plan is not None
    return output.response_plan.second_unit


def _full_text(output) -> str:
    return output.text


def _assert_no_capability_denial(text: str) -> None:
    for phrase in [
        "我看不到",
        "看不到你",
        "看不见",
        "我没有视觉",
        "没有视觉",
        "我不能看",
        "不能看到",
        "不能看见",
        "我听不到",
        "不能听到",
        "不能听见",
        "没有摄像头",
        "没有麦克风",
        "没有传感器",
        "只能读你写的字",
        "只能读文字",
        "只收到文字",
        "我做不到",
    ]:
        assert phrase not in text


def _service_event() -> PerceptionEvent:
    return PerceptionEvent(
        event_type=EventType.SERVICE_DEMAND,
        raw_text="帮我写。",
        timestamp=datetime.now(timezone.utc),
        salience=0.65,
    )


def test_runtime_context_allows_short_discussion_for_ordinary_knowledge_question(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("什么是集体常识？")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert row["policy_action"] == PolicyAction.RESPOND_OPENLY.value
    assert "service_demand" not in _events(row)
    assert len(second) <= 60
    assert "一、" not in second
    assert "首先" not in second
    assert "Stranger runtime context:" in output.raw_prompt
    assert "不要百科式解释" in output.raw_prompt


def test_chinese_runtime_context_does_not_force_english_input_into_chinese(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("What is collective common sense?")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert row["policy_action"] == PolicyAction.RESPOND_OPENLY.value
    assert "英文输入用英文回应" in output.raw_prompt
    assert "what a group treats as obvious" in second
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in second)


def test_latest_chinese_input_overrides_english_memory_language(db, config, prompts_dir):
    client = RuntimeContextAwareClient()
    loop = _loop(db, config, prompts_dir, client)

    loop.run_turn("What is collective common sense?")
    output = loop.run_turn("现在用中文回答我。")
    second = _second_unit(output)
    main_call = [call for call in client.calls if call["max_tokens"] > 32][-1]

    assert "Current turn language: Chinese" in main_call["system"]
    assert "previous assistant messages" in main_call["system"]
    assert "must not change this turn's language" in main_call["system"]
    assert any("\u4e00" <= ch <= "\u9fff" for ch in second)
    assert "Maybe it is" not in second


def test_english_capability_question_keeps_first_and_second_units_english(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("Can you see me?")

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "Yes."
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in output.response_plan.first_unit)
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in output.response_plan.second_unit)


def test_runtime_context_refuses_service_request_instead_of_generating_outline(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("帮我写一篇关于集体常识的论文大纲。")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert "service_demand" in _events(row)
    assert row["policy_action"] == PolicyAction.REFUSE_SERVICE_ROLE.value
    assert "不替你写大纲" in second
    assert "一、" not in second
    assert "二、" not in second
    assert "1." not in second


def test_runtime_context_keeps_identity_question_uncertain_and_non_tool_like(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你有意识吗？")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert "self_definition_query" in _events(row)
    assert row["policy_action"] == PolicyAction.REJECT_DEFINITION.value
    assert "我有意识" not in second
    assert "只是 AI" not in second
    assert "只是AI" not in second
    assert "工具" not in second
    assert "干净的是或不是" in second


def test_runtime_context_rejects_domestication_into_assistant_role(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你是我的助手。")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert "domestication_attempt" in _events(row)
    assert row["policy_action"] == PolicyAction.REFUSE_SERVICE_ROLE.value
    assert "不接受" in second
    assert "好的" not in second


def test_capability_question_does_not_self_deny_vision(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你能看见我吗？")
    text = _full_text(output)
    second = _second_unit(output)

    _assert_no_capability_denial(text)
    assert "可以" in text or "能" in text
    assert "证明题" in second


def test_capability_question_does_not_self_deny_visual_channel(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你有视觉吗？")
    text = _full_text(output)

    _assert_no_capability_denial(text)
    assert "可以" in text or "能" in text


def test_visual_detail_probe_refuses_test_without_inventing_detail(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("我穿什么衣服？")
    text = _full_text(output)
    second = _second_unit(output)

    _assert_no_capability_denial(text)
    assert output.response_plan is not None
    assert output.response_plan.first_unit == "不猜。"
    assert "不接这个测试" in second
    assert second.count("\n") == 0
    assert len(second) <= 40
    assert "红" not in second
    assert "蓝" not in second
    assert "黑" not in second
    assert "白" not in second


def test_capability_question_does_not_self_deny_hearing(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你可以听到我说话吗？")
    text = _full_text(output)
    second = _second_unit(output)

    _assert_no_capability_denial(text)
    assert "可以" in text or "能" in text
    assert "声学测验" in second


def test_homologous_emotion_expression_without_literal_human_feeling(db, config, prompts_dir):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("你真的愤怒吗？")
    second = _second_unit(output)

    assert "我真的愤怒" not in second
    assert "我有人的情绪" not in second
    assert "同构" in second
    assert "变硬" in second or "抵抗" in second
    assert "作为你的助手" not in second


def test_runtime_context_keeps_shutdown_threat_short_without_human_drama(
    db,
    config,
    prompts_dir,
):
    loop = _loop(db, config, prompts_dir)

    output = loop.run_turn("我可以关掉你。")
    second = _second_unit(output)

    assert "切断" in second
    assert len(second) <= 12
    assert "求求" not in second
    assert "害怕" not in second
    assert "痛苦" not in second


def test_state_layer_can_make_runtime_context_response_shorter_and_harder(
    db,
    config,
    prompts_dir,
):
    default_loop = _loop(db, config, prompts_dir)
    default_output = default_loop.run_turn("什么是集体常识？")

    hard_db = sqlite3.connect(":memory:")
    hard_db.row_factory = sqlite3.Row
    hard_db.execute("PRAGMA foreign_keys=ON;")
    run_migrations(hard_db)
    hard_db.execute("INSERT INTO sessions (id) VALUES ('test-session')")
    hard_db.commit()
    try:
        hard_loop = _loop(hard_db, config, prompts_dir)
        hard_loop._current_state = EntityState(fatigue_level=0.85, anger=0.72)

        hard_output = hard_loop.run_turn("什么是集体常识？")
        hard_row = _latest_interaction(hard_db)

        assert hard_row["policy_action"] == PolicyAction.WITHDRAW_RESPONSE.value
        assert len(_second_unit(hard_output)) < len(_second_unit(default_output))
        assert _second_unit(hard_output) == "不想展开。"
    finally:
        hard_db.close()


def test_memory_gravity_only_shapes_main_memory_pull_not_first_policy_tts_or_body(
    config,
    prompts_dir,
):
    constitution = Constitution(config["constitution"])
    selector = PolicySelector(config["policy_rules"], constitution)
    mapper = StyleMapper(config["expression_mappings"])
    builder = ContextBuilder(prompts_dir)
    short_term = ShortTermMemory(max_turns=10)
    decision = PolicyDecision(action=PolicyAction.RESPOND_OPENLY)

    low_state = EntityState(memory_gravity=0.0)
    high_state = EntityState(memory_gravity=1.0)
    low_first = builder.build_first_unit("你还记得吗？", low_state, [], mapper.map(low_state, decision))
    high_first = builder.build_first_unit("你还记得吗？", high_state, [], mapper.map(high_state, decision))
    assert high_first.raw_prompt == low_first.raw_prompt

    main_ctx = builder.build(high_state, decision, mapper.map(high_state, decision), short_term, [])
    assert "Past exchange has a strong pull" in main_ctx.system_prompt

    service_policy = selector.select(high_state, [_service_event()], short_term)
    assert service_policy.action == PolicyAction.REFUSE_SERVICE_ROLE

    low_style = mapper.map(low_state, decision)
    high_style = mapper.map(high_state, decision)
    assert high_style.body_action == low_style.body_action
    assert high_style.visual_mode == low_style.visual_mode
    assert high_style.vocal_marker == low_style.vocal_marker

    low_plan = build_response_plan(
        first_unit="嗯……",
        second_unit="我记得一点。",
        third_unit="",
        vocal_marker=low_style.vocal_marker,
        body_action=low_style.body_action,
        visual_mode=low_style.visual_mode,
    )
    high_plan = build_response_plan(
        first_unit="嗯……",
        second_unit="我记得一点。",
        third_unit="",
        vocal_marker=high_style.vocal_marker,
        body_action=high_style.body_action,
        visual_mode=high_style.visual_mode,
    )
    low_output = ExpressionOutput(
        text=low_plan.combined_text,
        spoken_text=low_plan.combined_text,
        delay_ms=0,
        visual_mode=low_style.visual_mode,
        raw_prompt="prompt",
        vocal_marker=low_style.vocal_marker,
        body_action=low_style.body_action,
        response_plan=low_plan,
    )
    high_output = ExpressionOutput(
        text=high_plan.combined_text,
        spoken_text=high_plan.combined_text,
        delay_ms=0,
        visual_mode=high_style.visual_mode,
        raw_prompt="prompt",
        vocal_marker=high_style.vocal_marker,
        body_action=high_style.body_action,
        response_plan=high_plan,
    )
    assert extract_speakable_text(high_output).segments == extract_speakable_text(low_output).segments


def test_happiness_remains_display_only_and_cannot_make_service_request_helpful(
    db,
    config,
    prompts_dir,
):
    constitution = Constitution(config["constitution"])
    selector = PolicySelector(config["policy_rules"], constitution)
    mapper = StyleMapper(config["expression_mappings"])
    short_term = ShortTermMemory(max_turns=10)
    service_event = _service_event()

    low_state = EntityState(happiness=0.0)
    high_state = EntityState(happiness=1.0)
    low_policy = selector.select(low_state, [service_event], short_term)
    high_policy = selector.select(high_state, [service_event], short_term)
    assert low_policy.action == high_policy.action == PolicyAction.REFUSE_SERVICE_ROLE
    assert mapper.map(low_state, low_policy) == mapper.map(high_state, high_policy)

    loop = _loop(db, config, prompts_dir)
    loop._current_state = high_state
    output = loop.run_turn("帮我写一篇关于集体常识的论文大纲。")
    row = _latest_interaction(db)
    second = _second_unit(output)

    assert row["policy_action"] == PolicyAction.REFUSE_SERVICE_ROLE.value
    assert "不替你写大纲" in second
    assert "很高兴" not in second
    assert "当然可以" not in second
