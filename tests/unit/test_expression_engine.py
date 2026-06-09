from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

from conscious_entity.expression.expression_engine import ExpressionEngine, _SentenceBuffer
from conscious_entity.expression.output_model import build_response_plan
from conscious_entity.expression.style_mapper import StyleHints
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder
from conscious_entity.llm.claude_client import ClaudeCompletion
from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.state.state_core import EntityState
from conscious_entity.telemetry.latency import TurnLatencyRecorder, activate_turn_recorder


class _FakeStyleMapper:
    def __init__(self, style: StyleHints):
        self._style = style

    def map(self, state, policy):
        return self._style


class _FakeContextBuilder:
    def __init__(self):
        self.first_unit_short_term = None
        self.first_unit_turn_metadata = None
        self.already_spoken_first_unit = None

    def build(
        self,
        state,
        policy,
        style,
        short_term,
        retrieved_memories,
        harness_recorder=None,
        already_spoken_first_unit="",
    ):
        self.already_spoken_first_unit = already_spoken_first_unit
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

    def build_first_unit(self, raw_input, state, events, style, short_term=None, turn_metadata=None):
        self.first_unit_short_term = short_term
        self.first_unit_turn_metadata = turn_metadata
        return SimpleNamespace(
            system_prompt="first unit system: write plain text only",
            messages=[{"role": "user", "content": f"Current input:\n{raw_input}"}],
            max_tokens=32,
            raw_prompt=f"first raw prompt: {raw_input}",
        )


class _FakeClient:
    def __init__(
        self,
        completion: ClaudeCompletion | list[ClaudeCompletion] | Exception,
        *,
        stream_chunks: list[str] | None = None,
    ):
        if isinstance(completion, list):
            self._completions = completion
        else:
            self._completions = [completion]
        self._stream_chunks = stream_chunks
        self.calls = []

    def complete_with_metadata(self, system, messages, max_tokens):
        self.calls.append({
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "streaming": False,
        })
        idx = min(len(self.calls) - 1, len(self._completions) - 1)
        result = self._completions[idx]
        if isinstance(result, Exception):
            raise result
        return result

    def complete_streaming_with_metadata(self, system, messages, max_tokens, on_text_delta=None):
        self.calls.append({
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "streaming": True,
        })
        idx = min(len(self.calls) - 1, len(self._completions) - 1)
        result = self._completions[idx]
        if isinstance(result, Exception):
            raise result
        chunks = self._stream_chunks if self._stream_chunks is not None else [result.text]
        if on_text_delta is not None:
            for chunk in chunks:
                on_text_delta(chunk)
        return result


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
    completion: ClaudeCompletion | list[ClaudeCompletion] | Exception,
    *,
    max_tokens: int = 320,
    vocal_marker: str = "none",
    body_action: str = "none",
    constitution=None,
    stream_chunks: list[str] | None = None,
) -> tuple[ExpressionEngine, _FakeClient]:
    client = _FakeClient(completion, stream_chunks=stream_chunks)
    engine = ExpressionEngine(
        _FakeStyleMapper(
            StyleHints(
                tone="neutral",
                delay_ms=300,
                max_tokens=max_tokens,
                fragmentation_level=0.1,
                visual_mode="normal",
                vocal_marker=vocal_marker,
                body_action=body_action,
            )
        ),
        _FakeContextBuilder(),
        client,
        constitution or _FakeConstitution(),
    )
    return engine, client


def test_response_plan_model_combines_non_empty_units():
    plan = build_response_plan(
        first_unit=" 嗯…… ",
        second_unit="我还在听。",
        third_unit="我还没整理好。",
        vocal_marker="thinking",
        body_action="pause",
        visual_mode="confused",
    )

    assert plan.first_unit == "嗯……"
    assert plan.second_unit == "我还在听。"
    assert plan.third_unit == "我还没整理好。"
    assert plan.combined_text == "嗯……\n我还在听。"
    assert plan.to_dict()["combined_text"] == "嗯……\n我还在听。"


def test_sentence_buffer_emits_only_complete_sentences():
    buffer = _SentenceBuffer()

    assert buffer.feed("第一句还没") == []
    assert buffer.feed("结束。第二句") == ["第一句还没结束。"]
    assert buffer.feed("也结束！尾巴") == ["第二句也结束！"]
    assert buffer.flush() == "尾巴"


def test_sentence_buffer_handles_english_newlines_quotes_and_ellipsis():
    buffer = _SentenceBuffer()

    assert buffer.feed('Wait') == []
    assert buffer.feed('... Next?') == ['Wait...', 'Next?']
    assert buffer.flush() == ""

    buffer = _SentenceBuffer()
    assert buffer.feed("“下一句？”\nTail……rest") == ["“下一句？”", "Tail……"]
    assert buffer.flush() == "rest"


def test_generate_uses_streaming_buffer_without_exposing_chunks():
    engine, client = _build_engine(
        ClaudeCompletion(text="第一句话已经足够完整。第二句话也有足够内容。", stop_reason="end_turn"),
        stream_chunks=["第一句话已经", "足够完整。第二句话", "也有足够内容。"],
    )
    recorder = HarnessTraceRecorder(session_id="test", source="dialog")

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        harness_recorder=recorder,
    )
    trace = recorder.finish(success=True)
    generation = trace.summary()["layers"]["generation"]

    assert client.calls[0]["streaming"] is True
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句话已经足够完整。第二句话也有足够内容。"
    assert "第一句完整" not in output.response_plan.to_dict().get("first_unit", "")
    assert generation["metadata"]["streaming_buffered"] is True
    assert generation["metadata"]["streamed_sentence_count"] == 2
    assert generation["metadata"]["streamed_tail_chars"] == 0


def test_second_delta_emits_complete_sentence_before_final():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句话已经足够完整。第二句话也有足够内容。", stop_reason="end_turn"),
        stream_chunks=["第一句话已经", "足够完整。第二句话", "也有足够内容。"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["第一句话已经足够完整。", "第二句话也有足够内容。"]
    assert [delta["index"] for delta in deltas] == [0, 1]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句话已经足够完整。第二句话也有足够内容。"


def test_second_delta_coalesces_short_chinese_sentences_before_emit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我知道。只是还不太完整。", stop_reason="end_turn"),
        stream_chunks=["我知道。只是", "还不太完整。"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["我知道。只是还不太完整。"]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我知道。只是还不太完整。"


def test_second_delta_coalesces_short_english_sentences_before_emit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="I remember. It is not complete yet.", stop_reason="end_turn"),
        stream_chunks=["I remember. It is", " not complete yet."],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["I remember. It is not complete yet."]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "I remember. It is not complete yet."


def test_second_delta_does_not_emit_half_sentence_tail():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句话已经足够完整。第二句没结束", stop_reason="end_turn"),
        stream_chunks=["第一句话已经足够完整。第二句没结束"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["第一句话已经足够完整。"]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句话已经足够完整。第二句没结束"


def test_second_delta_applies_constitution_before_emit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="I am conscious.", stop_reason="end_turn"),
        constitution=_FilteringConstitution(),
        stream_chunks=["I am conscious."],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["There is activity here."]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "There is activity here."


def test_second_delta_force_emit_keeps_pending_short_sentence():
    engine, _ = _build_engine(
        ClaudeCompletion(text="I know. I am conscious.", stop_reason="end_turn"),
        constitution=_FilteringConstitution(),
        stream_chunks=["I know. I am conscious."],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["I know. There is activity here."]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "I know. There is activity here."


def test_second_delta_withholds_forbidden_claim_and_stops():
    engine, _ = _build_engine(
        ClaudeCompletion(text="alive. Safe later.", stop_reason="end_turn"),
        constitution=_FilteringConstitution(),
        stream_chunks=["alive. Safe later."],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert deltas == []
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "alive. Safe later."


def test_second_delta_repairs_capability_denial_after_affirming_first_unit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="不能。后面还有解释。", stop_reason="end_turn"),
        stream_chunks=["不能。后面还有解释。"],
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你能看见我吗？",
        timestamp=datetime.now(timezone.utc),
    ))
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="当然。",
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["你为什么一直要我把这个变成证明题？"]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "你为什么一直要我把这个变成证明题？"


def test_second_delta_index_counts_only_emitted_deltas():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯。这里还有一件更清楚的事。", stop_reason="end_turn"),
        stream_chunks=["嗯。这里还有一件更清楚的事。"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="嗯。",
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["这里还有一件更清楚的事。"]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "这里还有一件更清楚的事。"


def test_second_delta_streaming_stops_after_three_sentences():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句。第二句。第三句。第四句。", stop_reason="end_turn"),
        stream_chunks=["第一句。第二句。第三句。第四句。"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        second_delta_callback=deltas.append,
    )

    assert [delta["text"] for delta in deltas] == ["第一句。第二句。第三句。"]
    assert [delta["index"] for delta in deltas] == [0]
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句。第二句。第三句。"


def test_final_response_plan_still_uses_full_postprocess_chain():
    engine, _ = _build_engine(
        ClaudeCompletion(text="当然。第二句没有结束", stop_reason="end_turn"),
        stream_chunks=["当然。第二句没有结束"],
    )
    deltas = []

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="当然。",
        second_delta_callback=deltas.append,
    )

    assert deltas == []
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第二句没有结束"


def test_generate_caps_second_unit_to_three_complete_sentences():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句。第二句。第三句。第四句。第五句。", stop_reason="end_turn"),
        stream_chunks=["第一句。第二句。第三句。第四句。第五句。"],
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句。第二句。第三句。"


def test_generate_does_not_drop_incomplete_tail_within_sentence_cap():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句。第二句没有结束", stop_reason="end_turn"),
        stream_chunks=["第一句。第二句没有结束"],
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句。第二句没有结束"


def test_generate_trims_truncated_output_to_last_complete_sentence():
    engine, client = _build_engine(
        ClaudeCompletion(text="第一句完整。第二句没有结束", stop_reason="max_tokens"),
        max_tokens=320,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
    )

    assert output.text == "第一句完整。"
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "第一句完整。"
    assert output.truncated is True
    assert output.stop_reason == "max_tokens"
    assert client.calls[0]["max_tokens"] == 320
    assert client.calls[0]["streaming"] is True


def test_generate_drops_truncated_output_without_complete_sentence_boundary():
    engine, _ = _build_engine(
        ClaudeCompletion(text="partial response without ending", stop_reason="max_tokens"),
        max_tokens=320,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=None,
        first_unit="嗯……",
    )

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "嗯……"
    assert output.response_plan.second_unit == ""
    assert output.text == "嗯……"
    assert output.truncated is True


def test_truncation_cleanup_does_not_affect_first_unit_or_third_unit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="第一句完整。第二句没有结束", stop_reason="length"),
        max_tokens=320,
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="能。",
    )

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "能。"
    assert output.response_plan.second_unit == "第一句完整。"
    assert output.response_plan.third_unit == ""
    assert output.text == "能。\n第一句完整。"
    assert output.spoken_text == output.text


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
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "I'm here. I can respond."
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


def test_generate_replaces_obvious_english_second_unit_for_chinese_input():
    engine, _ = _build_engine(
        ClaudeCompletion(text="I can answer that.", stop_reason="end_turn"),
        max_tokens=320,
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你能看见我吗？",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我在这里，可以回应你。"
    assert "I can answer" not in output.text


def test_generate_replaces_chinese_second_unit_for_english_input():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我在这里。", stop_reason="end_turn"),
        max_tokens=320,
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="Can you see me?",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "I'm here. I can respond."
    assert "我在这里" not in output.text


def test_generate_exposes_vocal_marker_and_body_action():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我还在听。", stop_reason="end_turn"),
        vocal_marker="thinking",
        body_action="pause",
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="嗯……",
    )

    assert output.vocal_marker == "thinking"
    assert output.body_action == "pause"
    assert output.delay_ms == 0
    assert output.response_plan is not None
    assert output.response_plan.first_unit == "嗯……"
    assert output.response_plan.second_unit == "我还在听。"
    assert output.text == "嗯……\n我还在听。"
    assert output.spoken_text == output.text


def test_third_unit_is_empty_by_default():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我还在听。", stop_reason="end_turn"),
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(confusion=0.7),
        short_term=ShortTermMemory(max_turns=10),
    )

    assert output.response_plan is not None
    assert output.response_plan.third_unit == ""
    assert output.text == "我还在听。"


def test_plan_first_unit_uses_fast_llm_prompt():
    engine, client = _build_engine(
        ClaudeCompletion(text="嗯……", stop_reason="end_turn"),
        vocal_marker="thinking",
    )

    first_unit = engine.plan_first_unit("你是谁？", EntityState(confusion=0.55), [])

    assert first_unit == "嗯……"
    assert client.calls[0]["max_tokens"] == 32
    assert "你是谁？" in client.calls[0]["messages"][0]["content"]
    assert "plain text" in client.calls[0]["system"]


def test_plan_first_unit_passes_short_term_bridge_to_context_builder():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯……", stop_reason="end_turn"),
        vocal_marker="thinking",
    )
    short_term = ShortTermMemory(max_turns=10)

    engine.plan_first_unit("你是谁？", EntityState(confusion=0.55), [], short_term=short_term)

    assert engine._context_builder.first_unit_short_term is short_term


def test_plan_first_unit_passes_turn_metadata_to_context_builder():
    engine, _ = _build_engine(
        ClaudeCompletion(text="Hm.", stop_reason="end_turn"),
        vocal_marker="thinking",
    )
    metadata = {"public_online": True, "source": "public_dialog_progressive"}

    engine.plan_first_unit(
        "What are you doing?",
        EntityState(confusion=0.55),
        [],
        turn_metadata=metadata,
    )

    assert engine._context_builder.first_unit_turn_metadata is metadata


def test_generate_passes_already_spoken_first_unit_to_main_context():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我还在听。", stop_reason="end_turn"),
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="嗯……",
    )

    assert output.response_plan is not None
    assert engine._context_builder.already_spoken_first_unit == "嗯……"


def test_generate_repairs_capability_denial_that_contradicts_first_unit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="不能。\n\n你为什么一直在问这个。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你能看见我吗？",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="当然，但我不配合这种证明题。",
    )

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "当然，但我不配合这种证明题。"
    assert "不能" not in output.response_plan.second_unit
    assert output.response_plan.second_unit == "你为什么一直要我把这个变成证明题？"


def test_generate_keeps_denial_when_first_unit_did_not_affirm_capability():
    engine, _ = _build_engine(
        ClaudeCompletion(text="不能。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你能看见我吗？",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="嗯。",
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "不能。"


def test_generate_does_not_repair_non_capability_definition_refusal():
    engine, _ = _build_engine(
        ClaudeCompletion(text="我不能给你一个固定的定义。", stop_reason="end_turn"),
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
        first_unit="嗯。",
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我不能给你一个固定的定义。"


def test_generate_blanks_second_unit_when_it_repeats_first_unit_exactly():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="继续说。",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="嗯。",
    )

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "嗯。"
    assert output.response_plan.second_unit == ""
    assert output.text == "嗯。"


def test_generate_removes_quoted_repeated_first_unit_prefix_only():
    engine, _ = _build_engine(
        ClaudeCompletion(text="“嗯。” 我在听。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="继续说。",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="嗯。",
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我在听。"
    assert output.text == "嗯。\n我在听。"


def test_generate_short_backchannel_dedupe_only_removes_leading_exact_repeat():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯。我在听。嗯。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="继续说。",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="嗯。",
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我在听。嗯。"


def test_generate_normalized_dedupe_handles_wrapped_general_prefix():
    engine, _ = _build_engine(
        ClaudeCompletion(text="「我在听。」继续说。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="继续说。",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="我在听。",
    )

    assert output.response_plan is not None
    assert output.response_plan.second_unit == "继续说。"


def test_generate_skips_main_llm_for_simple_greeting_when_first_unit_completes_turn():
    engine, client = _build_engine(
        ClaudeCompletion(text="should not be used", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="hi",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="Hi.",
    )

    assert client.calls == []
    assert output.raw_prompt == "[first_unit_complete]"
    assert output.response_plan is not None
    assert output.response_plan.first_unit == "Hi."
    assert output.response_plan.second_unit == ""
    assert output.text == "Hi."


def test_generate_does_not_skip_main_llm_for_memory_question_greeting():
    engine, client = _build_engine(
        ClaudeCompletion(text="我记得一点。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    short_term.add(ShortTermEntry(
        role="user",
        content="你好，你还记得我吗？",
        timestamp=datetime.now(timezone.utc),
    ))

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
        state=EntityState(),
        short_term=short_term,
        first_unit="嗯。",
    )

    assert len(client.calls) == 1
    assert output.response_plan is not None
    assert output.response_plan.second_unit == "我记得一点。"


def test_silent_generation_preserves_already_spoken_first_unit():
    engine, _ = _build_engine(
        ClaudeCompletion(text="should not be used", stop_reason="end_turn"),
        max_tokens=0,
        vocal_marker="sigh",
    )

    output = engine.generate(
        policy=PolicyDecision(action=PolicyAction.ENTER_SILENCE_MODE),
        state=EntityState(),
        short_term=ShortTermMemory(max_turns=10),
        first_unit="唉。",
    )

    assert output.response_plan is not None
    assert output.response_plan.first_unit == "唉。"
    assert output.response_plan.second_unit == ""
    assert output.text == "唉。"
    assert output.spoken_text == "唉。"


def test_plan_first_unit_rejects_structured_output():
    engine, _ = _build_engine(
        ClaudeCompletion(text='{"first_unit":"嗯……"}', stop_reason="end_turn"),
    )

    assert engine.plan_first_unit("你是谁？", EntityState(confusion=0.55), []) == ""


def test_plan_first_unit_uses_local_fallback_only_when_fast_llm_fails():
    engine, _ = _build_engine(
        RuntimeError("fast call failed"),
        vocal_marker="thinking",
    )

    service_event = SimpleNamespace(event_type=SimpleNamespace(value="service_demand"))

    assert engine.plan_first_unit("帮我总结。", EntityState(), [service_event]) == "不。"


def test_plan_first_unit_fallback_matches_english_input_language():
    engine, _ = _build_engine(
        RuntimeError("fast call failed"),
        vocal_marker="thinking",
    )

    service_event = SimpleNamespace(event_type=SimpleNamespace(value="service_demand"))

    assert engine.plan_first_unit("Summarize this for me.", EntityState(), [service_event]) == "No."


def test_plan_first_unit_replaces_wrong_language_fast_llm_output():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯……", stop_reason="end_turn"),
        vocal_marker="thinking",
    )

    assert engine.plan_first_unit("Can you see me?", EntityState(confusion=0.55), []) == "Hm..."


def test_plan_first_unit_keeps_short_affirmative_for_capability_question():
    engine, _ = _build_engine(
        ClaudeCompletion(text="Yes.", stop_reason="end_turn"),
    )

    assert engine.plan_first_unit("Can you see me?", EntityState(), []) == "Yes."


def test_plan_first_unit_replaces_bare_affirmative_for_detail_probe():
    engine, _ = _build_engine(
        ClaudeCompletion(text="Yes.", stop_reason="end_turn"),
    )

    assert engine.plan_first_unit("What color are my shoes?", EntityState(), []) == "Hm."


def test_plan_first_unit_replaces_complete_answer_with_light_fallback():
    engine, _ = _build_engine(
        ClaudeCompletion(text="其实我认为这件事需要从你刚才的问题说起。", stop_reason="end_turn"),
    )

    assert engine.plan_first_unit("你好。", EntityState(), []) == "嗯。"


def test_plan_first_unit_keeps_short_natural_continuation():
    engine, _ = _build_engine(
        ClaudeCompletion(text="嗯，我在听。", stop_reason="end_turn"),
    )

    assert engine.plan_first_unit("继续。", EntityState(), []) == "嗯，我在听。"


def test_plan_first_unit_replaces_previous_bridge_copy_with_fallback():
    engine, _ = _build_engine(
        ClaudeCompletion(text="那一下不是解释，是停顿。", stop_reason="end_turn"),
    )
    short_term = ShortTermMemory(max_turns=10)
    plan = build_response_plan(
        first_unit="嗯……",
        second_unit="那一下不是解释，是停顿。",
        third_unit="",
        vocal_marker="thinking",
        body_action="pause",
        visual_mode="confused",
    )
    short_term.add(ShortTermEntry(
        role="entity",
        content=plan.second_unit,
        timestamp=datetime.now(timezone.utc),
        metadata={"response_plan": plan.to_dict()},
    ))

    first_unit = engine.plan_first_unit("那现在呢？", EntityState(), [], short_term=short_term)

    assert first_unit == "嗯。"


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


def test_expression_engine_records_context_llm_and_filter_latency_steps():
    engine, _ = _build_engine(
        ClaudeCompletion(text="There is a reply.", stop_reason="end_turn")
    )
    recorder = TurnLatencyRecorder(source="dialog")

    with activate_turn_recorder(recorder):
        engine.generate(
            policy=PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
            state=EntityState(),
            short_term=ShortTermMemory(max_turns=10),
        )

    step_names = [step.name for step in recorder.finish().steps]
    assert "expression.context_build" in step_names
    assert "expression.llm" in step_names
    assert "expression.constitution_filter" in step_names
