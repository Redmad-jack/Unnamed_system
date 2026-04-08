"""
test_context_builder.py — prompt contract tests for ContextBuilder.
No LLM calls are made; tests verify structural invariants of the assembled prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from conscious_entity.expression.style_mapper import StyleHints
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

    def test_system_prompt_contains_state_values(self, builder):
        state = EntityState(trust=0.42)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "0.42" in ctx.system_prompt

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
        assert "Relevant memories retrieved" in ctx.system_prompt

    def test_multiple_memories_all_appear(self, builder):
        class FakeMemory:
            memory_type = "episodic"
            def __init__(self, text):
                self.content = text

        memories = [FakeMemory("memory one"), FakeMemory("memory two")]
        ctx = builder.build(EntityState(), _decision(), _style(), _empty_memory(), memories)
        assert "memory one" in ctx.system_prompt
        assert "memory two" in ctx.system_prompt


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

    def test_raw_prompt_contains_state_values(self, builder):
        state = EntityState(resistance=0.77)
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        assert "0.77" in ctx.raw_prompt


# ---------------------------------------------------------------------------
# Prompt contract: state values
# ---------------------------------------------------------------------------


class TestStateRendering:
    def test_all_state_variables_appear_in_system_prompt(self, builder):
        state = EntityState(
            attention_focus=0.11,
            arousal=0.22,
            stability=0.33,
            curiosity=0.44,
            trust=0.55,
            resistance=0.66,
            fatigue=0.12,
            uncertainty=0.13,
            identity_coherence=0.14,
            shutdown_sensitivity=0.15,
        )
        ctx = builder.build(state, _decision(), _style(), _empty_memory(), [])
        for value in ["0.11", "0.22", "0.33", "0.44", "0.55", "0.66", "0.12", "0.13", "0.14", "0.15"]:
            assert value in ctx.system_prompt, f"Value {value} missing from system_prompt"
