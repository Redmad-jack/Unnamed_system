from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

from conscious_entity.expression.expression_engine import ExpressionEngine
from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState


class _FakeStyleMapper:
    def __init__(self, style: StyleHints):
        self._style = style

    def map(self, state, policy):
        return self._style


class _FakeContextBuilder:
    def build(self, state, policy, style, short_term, retrieved_memories, harness_recorder=None):
        if harness_recorder is not None:
            harness_recorder.record(
                HarnessLayer.PROMPT,
                status="assembled",
                summary="Prompt assembled.",
            )
        return SimpleNamespace(
            system_prompt="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=style.max_tokens,
            raw_prompt="raw prompt",
        )


class _FakeClient:
    def __init__(self, completion: ClaudeCompletion):
        self._completion = completion
        self.calls = []

    def complete_with_metadata(self, system, messages, max_tokens):
        self.calls.append({
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        })
        return self._completion


class _FakeConstitution:
    def apply_expression_constraints(self, text: str) -> str:
        return text

    def forbidden_claim_detected(self, text: str):
        return False, None


class _FilteringConstitution:
    def apply_expression_constraints(self, text: str) -> str:
        return text.replace("I am conscious", "There is activity here")

    def forbidden_claim_detected(self, text: str):
        return ("alive" in text), "substitute"


def _build_engine(
    completion: ClaudeCompletion,
    *,
    max_tokens: int = 320,
    constitution=None,
) -> tuple[ExpressionEngine, _FakeClient]:
    client = _FakeClient(completion)
    engine = ExpressionEngine(
        _FakeStyleMapper(
            StyleHints(
                tone="neutral",
                delay_ms=300,
                max_tokens=max_tokens,
                fragmentation_level=0.1,
                visual_mode="normal",
            )
        ),
        _FakeContextBuilder(),
        client,
        constitution or _FakeConstitution(),
    )
    return engine, client


def test_generate_marks_output_truncated_when_model_hits_token_limit():
    engine, client = _build_engine(
        ClaudeCompletion(text="partial response", stop_reason="max_tokens"),
        max_tokens=320,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
    )

    assert output.text == "partial response"
    assert output.truncated is True
    assert output.stop_reason == "max_tokens"
    assert client.calls[0]["max_tokens"] == 320


def test_generate_uses_fallback_and_clears_truncation_on_empty_completion():
    engine, _ = _build_engine(
        ClaudeCompletion(text="", stop_reason="max_tokens"),
        max_tokens=320,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
    )

    assert output.text == "I'm here. I can respond."
    assert output.truncated is False


def test_generate_uses_chinese_fallback_for_recent_chinese_user_turn():
    engine, _ = _build_engine(
        ClaudeCompletion(text="", stop_reason="max_tokens"),
        max_tokens=320,
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你是谁？",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.REJECT_DEFINITION),
        state=EntityState(),
        short_term=short_term,
    )

    assert output.text == "我不能给你一个固定的定义。"
    assert output.truncated is False


def test_generation_and_output_harness_records_constitution_filter():
    engine, _ = _build_engine(
        ClaudeCompletion(text="I am conscious and alive.", stop_reason="end_turn"),
        constitution=_FilteringConstitution(),
    )
    recorder = HarnessTraceRecorder(session_id="test", source="dialog")

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        harness_recorder=recorder,
    )
    trace = recorder.finish(success=True)
    layers = trace.summary()["layers"]

    assert output.text == "There is activity here and alive."
    assert layers["generation"]["status"] == "completed"
    assert layers["output"]["status"] == "filtered"
    assert layers["output"]["metadata"]["changed"] is True
    assert layers["output"]["metadata"]["forbidden_claim_detected"] is True
