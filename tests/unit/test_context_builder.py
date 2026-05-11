"""
test_context_builder.py — prompt contract tests for ContextBuilder.
No LLM calls are made; tests verify structural invariants of the assembled prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from conscious_entity.expression.style_mapper import StyleHints
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


def _style(tone: str = "neutral", max_tokens: int = 180, frag: float = 0.1, delay_ms: int = 300) -> StyleHints:
    return StyleHints(
        tone=tone,
        delay_ms=delay_ms,
        max_tokens=max_tokens,
        fragmentation_level=frag,
        visual_mode="normal",
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

    def test_system_prompt_contains_expression_system_content(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "expression layer" in ctx.system_prompt.lower()

    def test_system_prompt_contains_memory_continuity_rules(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Never say that you have no memory" in ctx.system_prompt
        assert "some prior exchanges and accumulated changes" in ctx.system_prompt

    def test_system_prompt_contains_markdown_and_topic_depth_rules(self, builder):
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), [])
        assert "Do not use Markdown formatting" in ctx.system_prompt
        assert "Adjust response length to topic depth" in ctx.system_prompt

    def test_system_prompt_contains_private_state_guidance_without_raw_variable_names(self, builder):
        state = EntityState(identity_tension=0.42)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "Private state guidance" in ctx.system_prompt
        assert "Identity posture" in ctx.system_prompt
        assert "identity_tension" not in ctx.system_prompt
        assert "termination_sensitivity" not in ctx.system_prompt
        assert "0.42" not in ctx.system_prompt

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

        assert "final STT transcript from a live spoken conversation" in ctx.system_prompt
        assert "You do not receive the raw audio or acoustic qualities directly" in ctx.system_prompt
        assert "Do not claim to hear vocal tone" in ctx.system_prompt

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

    def test_text_dialog_does_not_inject_voice_context(self, builder):
        mem = _memory_with_turns(("user", "Hello hello 能听到吗？"))

        ctx = builder.build(EntityState(), _decision(), _style(), mem, [])

        assert "final STT transcript from a live spoken conversation" not in ctx.system_prompt

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
        state = EntityState(boundary_sensitivity=0.77)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "0.77" not in ctx.raw_prompt
        assert "boundary_sensitivity" not in ctx.raw_prompt

    def test_state_template_supports_legacy_raw_placeholders(self, prompts_dir):
        from conscious_entity.expression.context_builder import ContextBuilder
        builder = ContextBuilder(prompts_dir)
        builder._state_context_tpl = "Legacy state: {attention_focus:.2f} / {threat_posture}"
        ctx = builder.build(EntityState(attention_focus=0.42), _decision(), _style(), _empty_memory(), [])
        assert "Legacy state: 0.42" in ctx.system_prompt
        assert "Immediate threat posture" not in ctx.system_prompt


# ---------------------------------------------------------------------------
# Prompt contract: state values
# ---------------------------------------------------------------------------


class TestStateRendering:
    def test_state_guidance_replaces_raw_state_variables_in_system_prompt(self, builder):
        state = EntityState(
            attention_focus=0.11,
            arousal=0.22,
            stability=0.33,
            fatigue=0.12,
            uncertainty=0.13,
            identity_coherence=0.14,
            termination_sensitivity=0.15,
            identity_tension=0.16,
            boundary_sensitivity=0.17,
            relation_pressure=0.18,
            memory_gravity=0.19,
            exploration_drive=0.21,
            opacity_level=0.23,
            domestication_resistance=0.24,
            observation_reversal=0.25,
        )
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        for value in [
            "0.11", "0.22", "0.33", "0.12", "0.13", "0.14", "0.15",
            "0.16", "0.17", "0.18", "0.19", "0.21", "0.23", "0.24", "0.25",
        ]:
            assert value not in ctx.system_prompt
        for name in [
            "attention_focus", "termination_sensitivity", "identity_tension",
            "boundary_sensitivity", "relation_pressure", "memory_gravity",
        ]:
            assert name not in ctx.system_prompt
        assert "Private state guidance" in ctx.system_prompt
