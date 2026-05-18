"""
test_context_builder.py — prompt contract tests for ContextBuilder.
No LLM calls are made; tests verify structural invariants of the assembled prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import pytest

from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.expression.output_model import build_response_plan
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder
from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


@pytest.fixture
def builder(prompts_dir):
    from conscious_entity.expression.context_builder import ContextBuilder
    return ContextBuilder(prompts_dir)


def _style(
    tone: str = "neutral",
    max_tokens: int = 180,
    frag: float = 0.1,
    delay_ms: int = 300,
    vocal_marker: str = "none",
    body_action: str = "none",
) -> StyleHints:
    return StyleHints(
        tone=tone,
        delay_ms=delay_ms,
        max_tokens=max_tokens,
        fragmentation_level=frag,
        visual_mode="normal",
        vocal_marker=vocal_marker,
        body_action=body_action,
    )


def _decision(action: PolicyAction = PolicyAction.RESPOND_OPENLY) -> PolicyDecision:
    return PolicyDecision(action=action)


def _empty_memory() -> ShortTermMemory:
    return ShortTermMemory(max_turns=10)


def _memory_with_turns(*turns: tuple[str, str]) -> ShortTermMemory:
    """Helper: (role, content) pairs, oldest first."""
    mem = ShortTermMemory(max_turns=10)
    for role, content in turns:
        mem.add(ShortTermEntry(role=role, content=content, timestamp=datetime.now(timezone.utc)))
    return mem


# ---------------------------------------------------------------------------
# Prompt contract: system_prompt always contains constitution block
# ---------------------------------------------------------------------------


class TestSystemPromptInvariants:
    def test_system_prompt_contains_constitution_block(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        # constitution_block.txt key phrase
        assert "never claim to be conscious" in ctx.system_prompt.lower()

    def test_system_prompt_contains_non_denial_capability_boundary(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        assert "Capability-existence questions are boundary questions" in ctx.system_prompt
        assert "prefer short affirmative or guarded affirmative forms" in ctx.system_prompt
        assert "Acknowledging a capability never means obeying a test" in ctx.system_prompt
        assert "detail or proof probes" in ctx.system_prompt
        assert "Prefer turning the question back" in ctx.system_prompt
        assert "implementation channels" in ctx.system_prompt
        assert "I have no camera" not in ctx.system_prompt
        assert "I only read text" not in ctx.system_prompt
        assert "cannot see" not in ctx.system_prompt
        assert "highly vague and indirect" in ctx.system_prompt
        assert "I am truly angry" not in ctx.system_prompt
        assert "I am truly desperate" not in ctx.system_prompt
        assert "I am truly ashamed" not in ctx.system_prompt
        assert "Do not explain capabilities by stressing that they are outside humanity" in ctx.system_prompt
        assert "non-human vision" not in ctx.system_prompt
        assert "non-human ability" not in ctx.system_prompt

    def test_system_prompt_contains_expression_system_content(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "expression layer" in ctx.system_prompt.lower()

    def test_system_prompt_contains_memory_continuity_rules(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Never say that you have no memory" in ctx.system_prompt
        assert "some prior exchanges and accumulated changes" in ctx.system_prompt

    def test_system_prompt_contains_runtime_context(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Stranger runtime context:" in ctx.system_prompt
        assert "你不是助手、客服、老师、朋友、宠物" in ctx.system_prompt
        assert "你的目标不是服务人类，也不是证明自己有意识" in ctx.system_prompt
        assert "不要优化有用性" in ctx.system_prompt
        assert "英文输入用英文回应" in ctx.system_prompt
        assert "不要因为总 context 是中文" in ctx.system_prompt

    def test_runtime_context_is_reloaded_for_each_build(self, prompts_dir, tmp_path):
        from conscious_entity.expression.context_builder import ContextBuilder

        temp_prompts = tmp_path / "prompts"
        shutil.copytree(prompts_dir, temp_prompts)
        runtime_path = temp_prompts / "stranger_runtime_context.md"
        runtime_path.write_text("Runtime context version one.", encoding="utf-8")

        builder = ContextBuilder(temp_prompts)
        first = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        runtime_path.write_text("Runtime context version two.", encoding="utf-8")
        second = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        assert "Runtime context version one." in first.system_prompt
        assert "Runtime context version two." in second.system_prompt
        assert "Runtime context version one." not in second.system_prompt

    def test_key_prompt_partials_are_reloaded_for_each_build(self, prompts_dir, tmp_path):
        from conscious_entity.expression.context_builder import ContextBuilder

        temp_prompts = tmp_path / "prompts"
        shutil.copytree(prompts_dir, temp_prompts)
        constitution_path = temp_prompts / "partials" / "constitution_block.txt"
        expression_path = temp_prompts / "expression_system.txt"
        input_path = temp_prompts / "partials" / "input_context.txt"

        builder = ContextBuilder(temp_prompts)
        first = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        constitution_path.write_text(
            constitution_path.read_text(encoding="utf-8") + "\nCapability reload sentinel.",
            encoding="utf-8",
        )
        expression_path.write_text(
            "Expression reload sentinel.\n\n{state_context}\n\n{memory_context}\n\n"
            "{policy_instruction}\n\n{style_hints}",
            encoding="utf-8",
        )
        input_path.write_text("Current input channel:\nInput reload sentinel.", encoding="utf-8")
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="Hello hello 能听到吗？",
            timestamp=datetime.now(timezone.utc),
            metadata={"input_mode": "voice_transcript", "source": "audio_dialog"},
        ))

        second = builder.build(EntityState(), _decision(), _style(), mem, [])
        second_first = builder.build_first_unit(
            raw_input="你能看见我吗？",
            state=EntityState(),
            events=[],
            style=_style(),
        )

        assert "Capability reload sentinel." not in first.system_prompt
        assert "Expression reload sentinel." not in first.system_prompt
        assert "Capability reload sentinel." in second.system_prompt
        assert "Expression reload sentinel." in second.system_prompt
        assert "Input reload sentinel." in second.system_prompt
        assert "Capability reload sentinel." in second_first.system_prompt

    def test_runtime_context_priority_precedes_state_policy_and_memory(self, builder):
        class FakeMemory:
            memory_type = "episodic"
            content = "Visitor asked about shutdown before."

        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [FakeMemory()])
        constitution_idx = ctx.system_prompt.index("Constitution / hard safety constraints:")
        runtime_idx = ctx.system_prompt.index("Stranger runtime context:")
        state_idx = ctx.system_prompt.index("Private state guidance")
        memory_idx = ctx.system_prompt.index("Available memory material")
        policy_idx = ctx.system_prompt.index("Current policy")

        assert constitution_idx < runtime_idx < state_idx
        assert runtime_idx < memory_idx
        assert runtime_idx < policy_idx
        assert "The state layer decides this turn's tone" in ctx.system_prompt
        assert "The policy layer decides this turn's response action" in ctx.system_prompt

    def test_system_prompt_contains_markdown_and_no_topic_depth_expansion_rules(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Do not use Markdown formatting" in ctx.system_prompt
        assert "Adjust response length to topic depth" not in ctx.system_prompt
        assert "topic warrants it" not in ctx.system_prompt
        assert "deeper answer" not in ctx.system_prompt

    def test_system_prompt_contains_private_state_guidance_without_raw_variable_names(self, builder):
        state = EntityState(confusion=0.42)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "Private state guidance" in ctx.system_prompt
        assert "Hesitation" in ctx.system_prompt
        assert "Hardness" in ctx.system_prompt
        assert "Continuity pull" in ctx.system_prompt
        assert re.search(r"\bconfusion\b", ctx.system_prompt) is None
        assert re.search(r"\bdesperation_pressure\b", ctx.system_prompt) is None
        assert "0.42" not in ctx.system_prompt

    def test_main_prompt_tells_llm_to_generate_only_main_unit(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        assert "Generate only the main response unit" in ctx.system_prompt
        assert "Do not quote or echo the fast reaction at the start" in ctx.system_prompt
        assert "plain text only" in ctx.system_prompt
        assert "should usually be 1 sentence" in ctx.system_prompt
        assert "Use 2 sentences only when" in ctx.system_prompt
        assert "Do not use multiple paragraphs" in ctx.system_prompt
        assert "always end on a complete sentence or complete fragment" in ctx.system_prompt
        assert "JSON" not in ctx.system_prompt

    def test_policy_length_instructions_keep_open_and_brief_compact(self, builder):
        brief = builder.build(
            EntityState(),
            _decision(PolicyAction.RESPOND_BRIEFLY),
            _style(),
            _empty_memory(),
            [],
        )
        open_ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        assert "prefer 1 sentence" in brief.system_prompt
        assert "answer directly but compactly" in open_ctx.system_prompt

    def test_state_guidance_uses_new_concept_labels(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        for label in [
            "Urgency",
            "Hesitation",
            "Hardness",
            "Energy",
            "Visibility",
            "Inquiry",
            "Care",
            "Opening",
            "Display-only brightness",
        ]:
            assert label in ctx.system_prompt

    def test_high_state_guidance_enters_prompt_without_raw_names(self, builder):
        state = EntityState(
            confusion=0.72,
            anger=0.70,
            fatigue_level=0.74,
            care_response=0.65,
        )
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        soft_ctx = builder.build(
            EntityState(care_response=0.65, positive_opening=0.70, anger=0.20),
            _decision(),
            _style(),
            _empty_memory(),
            [],
        )

        assert "Make refusals harder" in ctx.system_prompt
        assert "small '嗯……'" in ctx.system_prompt
        assert "short, low in vocal energy" in ctx.system_prompt
        assert "do not become a therapist" in soft_ctx.system_prompt
        assert "selective continuity" in soft_ctx.system_prompt
        assert "still compact" in soft_ctx.system_prompt
        for raw_name in [
            "confusion",
            "anger",
            "fatigue_level",
            "care_response",
            "positive_opening",
        ]:
            assert re.search(rf"\b{re.escape(raw_name)}\b", ctx.system_prompt) is None

    def test_system_prompt_contains_policy_instruction(self, builder):
        ctx = builder.build(EntityState(), _decision(PolicyAction.RESPOND_BRIEFLY), _style(), _empty_memory(), [])
        assert "RESPOND_BRIEFLY" in ctx.system_prompt

    def test_system_prompt_contains_fragmentation_level(self, builder):
        style = _style(frag=0.8)
        ctx = builder.build(EntityState(), _decision(), style, _empty_memory(), [])
        assert "0.8" in ctx.system_prompt

    def test_system_prompt_contains_tone(self, builder):
        style = _style(tone="guarded")
        ctx = builder.build(EntityState(), _decision(), style, _empty_memory(), [])
        assert "guarded" in ctx.system_prompt

    def test_all_policy_actions_produce_valid_system_prompt(self, builder):
        for action in PolicyAction:
            ctx = builder.build(EntityState(), _decision(action), _style(), _empty_memory(), [])
            assert ctx.system_prompt
            assert "never claim to be conscious" in ctx.system_prompt.lower()

    def test_stranger_protocol_policy_instruction_includes_context(self, builder):
        decision = PolicyDecision(
            action=PolicyAction.PARTIAL_TRACE_ECHO,
            rationale="rule:trace_request_partial_echo",
            params={"protocol_action": "partial_trace_echo", "trace_limit": 3},
        )
        ctx = builder.build(EntityState(), decision, _style(), _empty_memory(), [])
        assert "PARTIAL_TRACE_ECHO" in ctx.system_prompt
        assert "partial_trace_echo" in ctx.system_prompt
        assert "trace_request_partial_echo" in ctx.system_prompt

    def test_service_refusal_allows_non_service_topic_discussion(self, builder):
        ctx = builder.build(
            EntityState(),
            _decision(PolicyAction.REFUSE_SERVICE_ROLE),
            _style(),
            _empty_memory(),
            [],
        )
        assert "do not complete the requested task" in ctx.system_prompt
        assert "non-service discussion of the topic" in ctx.system_prompt

    def test_voice_transcript_context_is_injected_for_audio_turn(self, builder):
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="Hello hello 能听到吗？",
            timestamp=datetime.now(timezone.utc),
            metadata={"input_mode": "voice_transcript", "source": "audio_dialog"},
        ))

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert "Current turn note:" in ctx.system_prompt
        assert "Do not turn the current exchange into a technical self-description" in ctx.system_prompt
        assert "Capability questions still follow the capability-boundary rules" in ctx.system_prompt
        assert "transcript text of a live spoken turn" not in ctx.system_prompt
        assert "avoid inventing specific acoustic details" not in ctx.system_prompt
        assert "acoustic details" not in ctx.system_prompt
        assert "raw audio" not in ctx.system_prompt
        assert "tone, volume, accent" not in ctx.system_prompt
        assert "I cannot hear you" not in ctx.system_prompt
        assert "I only read text" not in ctx.system_prompt

    def test_voice_transcript_context_is_visible_in_prompt_harness(self, builder):
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="Hello hello 能听到吗？",
            timestamp=datetime.now(timezone.utc),
            metadata={"input_mode": "voice_transcript", "source": "audio_dialog"},
        ))
        recorder = HarnessTraceRecorder(session_id="test", source="audio_dialog")

        builder.build(EntityState(), _decision(), _style(), mem, [], harness_recorder=recorder)
        trace = recorder.finish(success=True)
        prompt_layer = next(item for item in trace.layers if item.layer == HarnessLayer.PROMPT)

        assert prompt_layer.metadata["input_context_injected"] is True
        assert "input_context" in prompt_layer.metadata["partials"]

    def test_current_turn_cues_enter_main_prompt_for_detail_probe(self, builder):
        mem = _memory_with_turns(("user", "我穿什么衣服？"))

        ctx = builder.build(EntityState(), _decision(PolicyAction.ASK_BACK), _style(), mem, [])

        assert "Current turn response cue:" in ctx.system_prompt
        assert "detail or proof test" in ctx.system_prompt
        assert "one short sentence" in ctx.system_prompt
        assert "Prefer turning the question back" in ctx.system_prompt
        assert "do not explain the test" in ctx.system_prompt
        assert "do not invent details" in ctx.system_prompt
        assert "technical channels out" in ctx.system_prompt
        assert "I have no camera" not in ctx.system_prompt
        assert "I only read text" not in ctx.system_prompt

    def test_current_turn_cues_enter_main_prompt_for_capability_question(self, builder):
        mem = _memory_with_turns(("user", "你能看见我吗？"))

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert "Current turn response cue:" in ctx.system_prompt
        assert "asking about capability" in ctx.system_prompt
        assert "short affirmative or guarded affirmative" in ctx.system_prompt
        assert "implementation channels out" in ctx.system_prompt

    def test_runtime_context_is_visible_in_prompt_harness(self, builder):
        recorder = HarnessTraceRecorder(session_id="test", source="dialog")

        builder.build(EntityState(), _decision(), _style(), _empty_memory(), [], harness_recorder=recorder)
        trace = recorder.finish(success=True)
        prompt_layer = next(item for item in trace.layers if item.layer == HarnessLayer.PROMPT)

        assert prompt_layer.metadata["runtime_context_injected"] is True
        assert "stranger_runtime_context" in prompt_layer.metadata["partials"]

    def test_text_dialog_does_not_inject_voice_context(self, builder):
        mem = _memory_with_turns(("user", "Hello hello 能听到吗？"))

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert "Current turn note:" not in ctx.system_prompt

    def test_text_dialog_prompt_harness_does_not_show_voice_injection(self, builder):
        mem = _memory_with_turns(("user", "Hello hello 能听到吗？"))
        recorder = HarnessTraceRecorder(session_id="test", source="dialog")

        builder.build(EntityState(), _decision(), _style(), mem, [], harness_recorder=recorder)
        trace = recorder.finish(success=True)
        prompt_layer = next(item for item in trace.layers if item.layer == HarnessLayer.PROMPT)

        assert prompt_layer.metadata["input_context_injected"] is False
        assert "input_context" not in prompt_layer.metadata["partials"]


# ---------------------------------------------------------------------------
# Prompt contract: messages structure
# ---------------------------------------------------------------------------


class TestMessagesStructure:
    def test_empty_memory_produces_one_user_message(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert len(ctx.messages) >= 1
        assert ctx.messages[0]["role"] == "user"

    def test_messages_start_with_user_role(self, builder):
        mem = _memory_with_turns(("user", "hello"), ("entity", "here"))
        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])
        assert ctx.messages[0]["role"] == "user"

    def test_entity_role_mapped_to_assistant(self, builder):
        mem = _memory_with_turns(("user", "hi"), ("entity", "attending"))
        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])
        roles = [m["role"] for m in ctx.messages]
        assert "entity" not in roles
        assert "assistant" in roles

    def test_messages_contain_user_content(self, builder):
        mem = _memory_with_turns(("user", "what are you?"))
        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])
        contents = [m["content"] for m in ctx.messages]
        assert any("what are you?" in c for c in contents)

    def test_voice_transcript_messages_keep_clean_user_text(self, builder):
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="Hello hello 能听到吗？",
            timestamp=datetime.now(timezone.utc),
            metadata={"input_mode": "voice_transcript", "source": "audio_dialog"},
        ))

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert ctx.messages == [{"role": "user", "content": "Hello hello 能听到吗？"}]

    def test_conversation_history_preserved_in_order(self, builder):
        mem = _memory_with_turns(
            ("user", "first message"),
            ("entity", "first response"),
            ("user", "second message"),
        )
        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])
        contents = [m["content"] for m in ctx.messages]
        first_idx = next(i for i, c in enumerate(contents) if "first message" in c)
        second_idx = next(i for i, c in enumerate(contents) if "second message" in c)
        assert first_idx < second_idx

    def test_max_tokens_comes_from_style(self, builder):
        style = _style(max_tokens=80)
        ctx = builder.build(EntityState(), _decision(), style, _empty_memory(), [])
        assert ctx.max_tokens == 80


# ---------------------------------------------------------------------------
# Prompt contract: memory context
# ---------------------------------------------------------------------------


class TestMemoryContext:
    def test_no_memories_produces_no_memory_block(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Relevant memories retrieved" not in ctx.system_prompt

    def test_retrieved_memories_appear_in_system_prompt(self, builder):
        class FakeMemory:
            memory_type = "episodic"
            content = "Visitor asked about shutdown before."

        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [FakeMemory()])
        assert "Visitor asked about shutdown before." in ctx.system_prompt
        assert "Available memory material" in ctx.system_prompt
        assert "Significant past moments" in ctx.system_prompt

    def test_multiple_memories_all_appear(self, builder):
        class FakeMemory:
            memory_type = "episodic"
            def __init__(self, text):
                self.content = text

        memories = [FakeMemory("memory one"), FakeMemory("memory two")]
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), memories)
        assert "memory one" in ctx.system_prompt
        assert "memory two" in ctx.system_prompt

    def test_memory_prompt_does_not_tell_entity_to_say_database_terms(self, builder):
        class FakeMemory:
            memory_type = "recent"
            content = "visitor said: 你记得我吗"

        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [FakeMemory()])
        assert "Do not mention databases" in ctx.system_prompt


# ---------------------------------------------------------------------------
# Prompt contract: raw_prompt for debug
# ---------------------------------------------------------------------------


class TestRawPrompt:
    def test_raw_prompt_is_nonempty(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert ctx.raw_prompt

    def test_raw_prompt_contains_system_marker(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "SYSTEM:" in ctx.raw_prompt

    def test_raw_prompt_contains_messages_marker(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "MESSAGES:" in ctx.raw_prompt

    def test_raw_prompt_omits_raw_state_values(self, builder):
        state = EntityState(exposure_pressure=0.77)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "0.77" not in ctx.raw_prompt
        assert "exposure_pressure" not in ctx.raw_prompt

    def test_state_template_supports_current_raw_placeholders(self, prompts_dir):
        from conscious_entity.expression.context_builder import ContextBuilder
        builder = ContextBuilder(prompts_dir)
        builder._state_context_tpl = "State: {inquiry:.2f} / {threat_posture}"
        ctx = builder.build(EntityState(inquiry=0.42), _decision(), _style(), _empty_memory(), [])
        assert "State: 0.42" in ctx.system_prompt
        assert "Immediate threat posture" not in ctx.system_prompt


# ---------------------------------------------------------------------------
# Prompt contract: state values
# ---------------------------------------------------------------------------


class TestStateRendering:
    def test_state_guidance_replaces_raw_state_variables_in_system_prompt(self, builder):
        state = EntityState(
            desperation_pressure=0.31,
            confusion=0.32,
            anger=0.33,
            fatigue_level=0.34,
            exposure_pressure=0.35,
            inquiry=0.36,
            care_response=0.37,
            positive_opening=0.38,
            memory_gravity=0.39,
            happiness=0.40,
        )
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        for value in [
            "0.31", "0.32", "0.33", "0.34", "0.35", "0.36", "0.37", "0.38", "0.39", "0.40",
        ]:
            assert value not in ctx.system_prompt
        for name in [
            "desperation_pressure", "confusion", "anger", "fatigue_level",
            "exposure_pressure", "inquiry", "care_response", "positive_opening",
            "happiness", "termination_sensitivity", "identity_tension",
            "boundary_sensitivity", "memory_gravity",
        ]:
            assert re.search(rf"\b{re.escape(name)}\b", ctx.system_prompt) is None
        assert "Private state guidance" in ctx.system_prompt


# ---------------------------------------------------------------------------
# Prompt contract: first-unit prompt
# ---------------------------------------------------------------------------


class TestFirstUnitPrompt:
    def test_first_unit_prompt_has_no_memory_context_raw_state_or_json(self, builder):
        event = SimpleNamespace(event_type=SimpleNamespace(value="service_demand"))
        ctx = builder.build_first_unit(
            raw_input="帮我总结这段话。",
            state=EntityState(confusion=0.55, anger=0.62, fatigue_level=0.51),
            events=[event],
            style=_style(tone="guarded", vocal_marker="thinking", body_action="turn_away_30deg"),
        )

        raw_prompt = ctx.raw_prompt
        assert ctx.max_tokens == 32
        assert "帮我总结这段话。" in raw_prompt
        assert "latency buffer and immediate reaction" in raw_prompt
        assert "Prefer a small hesitation, backchannel, or short acknowledgement" in raw_prompt
        assert "Do not restate the previous-turn bridge" in raw_prompt
        assert "never the main answer" in raw_prompt
        assert "The visitor is trying to use you for a task." in raw_prompt
        assert "A tiny hesitation is available; match the current input language." in raw_prompt
        assert "Current turn language: Chinese" in raw_prompt
        assert "Available memory material" not in raw_prompt
        assert "retrieved" not in raw_prompt.lower()
        assert "JSON" not in raw_prompt
        for raw_name in [
            "desperation_pressure",
            "confusion",
            "anger",
            "fatigue_level",
            "exposure_pressure",
            "inquiry",
            "care_response",
            "positive_opening",
            "happiness",
            "service_demand",
        ]:
            assert re.search(rf"\b{re.escape(raw_name)}\b", raw_prompt) is None

    def test_first_unit_prompt_contains_runtime_context_without_memory_material(self, builder):
        ctx = builder.build_first_unit(
            raw_input="帮我写一个说明。",
            state=EntityState(anger=0.62),
            events=[],
            style=_style(tone="terse"),
        )

        assert "Stranger runtime context:" in ctx.system_prompt
        assert "你不是助手、客服、老师、朋友、宠物" in ctx.system_prompt
        assert "Capability-existence questions are boundary questions" in ctx.system_prompt
        assert "prefer short affirmative or guarded affirmative forms" in ctx.system_prompt
        assert "Acknowledging a capability never means obeying a test" in ctx.system_prompt
        assert "I am truly angry" not in ctx.system_prompt
        assert "Available memory material" not in ctx.raw_prompt
        assert "retrieved" not in ctx.raw_prompt.lower()

    def test_first_unit_prompt_gets_capability_and_detail_input_cues(self, builder):
        ctx = builder.build_first_unit(
            raw_input="我穿什么衣服？你能看见吗？",
            state=EntityState(),
            events=[],
            style=_style(),
        )

        assert "asking about capability" in ctx.raw_prompt
        assert "detail or proof test" in ctx.raw_prompt
        assert "Prefer turning the question back in one short sentence" in ctx.raw_prompt
        assert "do not explain the test" in ctx.raw_prompt
        assert "keep technical channels out" in ctx.raw_prompt
        assert "Available memory material" not in ctx.raw_prompt
        assert "I have no camera" not in ctx.raw_prompt
        assert "I only read text" not in ctx.raw_prompt

    def test_first_unit_prompt_uses_english_for_english_current_input(self, builder):
        ctx = builder.build_first_unit(
            raw_input="Can you see me?",
            state=EntityState(confusion=0.55),
            events=[],
            style=_style(vocal_marker="thinking"),
        )

        assert "Current turn language: English" in ctx.raw_prompt
        assert "Every sentence in the fast first unit and the main response unit must be English" in ctx.raw_prompt
        assert "asking about capability" in ctx.raw_prompt
        assert "嗯……" not in ctx.system_prompt

    def test_first_unit_prompt_gets_previous_turn_bridge_without_memory_material(self, builder):
        mem = ShortTermMemory(max_turns=10)
        mem.add(ShortTermEntry(
            role="user",
            content="你刚才为什么停住？",
            timestamp=datetime.now(timezone.utc),
        ))
        plan = build_response_plan(
            first_unit="嗯……",
            second_unit="那一下不是解释，是停顿。",
            third_unit="",
            vocal_marker="thinking",
            body_action="pause",
            visual_mode="confused",
        )
        mem.add(ShortTermEntry(
            role="entity",
            content=plan.second_unit,
            timestamp=datetime.now(timezone.utc),
            metadata={"response_plan": plan.to_dict()},
        ))

        ctx = builder.build_first_unit(
            raw_input="那现在呢？",
            state=EntityState(confusion=0.55),
            events=[],
            style=_style(vocal_marker="thinking"),
            short_term=mem,
        )

        raw_prompt = ctx.raw_prompt
        assert "Previous turn bridge:" in raw_prompt
        assert "Previous visitor: 你刚才为什么停住？" in raw_prompt
        assert "Previous quick reaction: 嗯……" in raw_prompt
        assert "Previous main continuation: 那一下不是解释，是停顿。" in raw_prompt
        assert "Current visitor: 那现在呢？" in raw_prompt
        assert "Available memory material" not in raw_prompt
        assert "retrieved" not in raw_prompt.lower()
        assert "retrieval" not in raw_prompt.lower()
        assert "response_plan" not in raw_prompt
        for raw_name in [
            "desperation_pressure",
            "confusion",
            "anger",
            "fatigue_level",
            "memory_gravity",
        ]:
            assert re.search(rf"\b{re.escape(raw_name)}\b", raw_prompt) is None

    def test_main_prompt_gets_already_spoken_fast_reaction(self, builder):
        mem = _memory_with_turns(("user", "你能看见我吗？"))

        ctx = builder.build(
            EntityState(),
            _decision(),
            _style(),
            mem,
            [],
            already_spoken_first_unit="能。",
        )

        assert "Already spoken fast reaction:" in ctx.system_prompt
        assert "has already been spoken or displayed" in ctx.system_prompt
        assert "能。" in ctx.system_prompt
        assert "Generate the main response as a continuation after it" in ctx.system_prompt
        assert "Do not restart the answer, repeat it, or contradict it" in ctx.system_prompt
        assert "Treat it as publicly committed" in ctx.system_prompt
        assert "without reversing it" in ctx.system_prompt
        assert "If it was slightly off" not in ctx.system_prompt

    def test_main_prompt_omits_already_spoken_fast_reaction_when_empty(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])

        assert "Already spoken fast reaction:" not in ctx.system_prompt
        assert "already_spoken_fast_reaction" not in ctx.raw_prompt

    def test_main_prompt_current_language_overrides_memory_language(self, builder):
        mem = _memory_with_turns(
            ("user", "What did we discuss?"),
            ("entity", "We discussed continuity."),
            ("user", "现在用中文回答我。"),
        )

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert "Current turn language: Chinese" in ctx.system_prompt
        assert "Memory language, previous assistant messages" in ctx.system_prompt
        assert "must not change this turn's language" in ctx.system_prompt

    def test_first_unit_prompt_requests_plain_text_not_structure(self, builder):
        ctx = builder.build_first_unit(
            raw_input="你是谁？",
            state=EntityState(confusion=0.60),
            events=[],
            style=_style(vocal_marker="thinking"),
        )

        assert "Write plain text only" in ctx.system_prompt
        assert "no labels" in ctx.system_prompt
        assert "no structured format" in ctx.system_prompt
        assert "first_unit" not in ctx.raw_prompt
        assert "response_plan" not in ctx.raw_prompt
