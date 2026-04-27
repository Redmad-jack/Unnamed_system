from __future__ import annotations

from types import SimpleNamespace

from conscious_entity.expression.expression_engine import ExpressionEngine
from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.shopkeeper.models import Language, Scene, ShopAction, StructuredTurn
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


def test_generate_can_use_shopkeeper_prompt_context():
    engine, client = _build_engine(
        ClaudeCompletion(text="好，我给你确认一下。"),
        max_tokens=320,
    )
    prompt_context = SimpleNamespace(
        system_prompt="shopkeeper system",
        messages=[{"role": "user", "content": "shopkeeper turn"}],
        max_tokens=120,
        raw_prompt="shopkeeper raw prompt",
    )
    structured_turn = StructuredTurn(
        language=Language.ZH,
        scene=Scene.ORDER_TAKING,
        reply="",
        action=ShopAction.CONFIRM_CHOICE,
        next_scene=Scene.ORDER_CONFIRM,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
        prompt_context=prompt_context,
        structured_turn=structured_turn,
    )

    assert client.calls[0]["system"] == "shopkeeper system"
    assert client.calls[0]["max_tokens"] == 120
    assert output.raw_prompt == "shopkeeper raw prompt"
    assert output.turn["scene"] == "order_taking"
    assert output.turn["reply"] == "好，我给你确认一下。"


def test_shopkeeper_empty_completion_uses_shopkeeper_fallback():
    engine, _ = _build_engine(
        ClaudeCompletion(text="", stop_reason="max_tokens"),
        max_tokens=320,
    )
    prompt_context = SimpleNamespace(
        system_prompt="shopkeeper system",
        messages=[{"role": "user", "content": "shopkeeper turn"}],
        max_tokens=120,
        raw_prompt="shopkeeper raw prompt",
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
        prompt_context=prompt_context,
        structured_turn=StructuredTurn(
            language=Language.EN,
            scene=Scene.FALLBACK,
            reply="",
            action=ShopAction.CLARIFY,
            next_scene=Scene.MENU_INTRO,
        ),
    )

    assert output.text == "I missed that. Which soup would you like?"
    assert output.truncated is False
    assert output.turn["action"] == "clarify"
