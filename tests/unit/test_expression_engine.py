from __future__ import annotations

from types import SimpleNamespace

from conscious_entity.expression.expression_engine import ExpressionEngine
from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState


class _FakeStyleMapper:
    def __init__(self, style: StyleHints):
        self._style = style

    def map(self, state, policy):
        return self._style


class _FakeContextBuilder:
    def build(self, state, policy, style, short_term, retrieved_memories):
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


def _build_engine(completion: ClaudeCompletion, *, max_tokens: int = 320) -> tuple[ExpressionEngine, _FakeClient]:
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
        _FakeConstitution(),
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

    assert output.text == "Something is here. I am attending."
    assert output.truncated is False
