from __future__ import annotations

from conscious_entity.audio.speech_text import extract_speakable_text
from conscious_entity.expression.output_model import ExpressionOutput


def _output(text: str, spoken_text: str | None = None) -> ExpressionOutput:
    return ExpressionOutput(
        text=text,
        spoken_text=spoken_text,
        delay_ms=0,
        visual_mode="normal",
        raw_prompt="prompt",
    )


def test_spoken_text_falls_back_to_output_text():
    speakable = extract_speakable_text(_output("我还不能确认。"))

    assert speakable.should_speak is True
    assert speakable.segments == ["我还不能确认。"]


def test_spoken_text_overrides_output_text():
    speakable = extract_speakable_text(_output("shown", spoken_text="spoken"))

    assert speakable.segments == ["spoken"]


def test_empty_output_returns_should_speak_false():
    speakable = extract_speakable_text(_output("   "))

    assert speakable.should_speak is False
    assert speakable.segments == []


def test_markdown_removed_for_tts():
    speakable = extract_speakable_text(
        _output("```debug\nsecret\n```\n我听见了 `边界`。[debug marker]")
    )

    assert speakable.segments == ["我听见了 边界。"]
    assert "debug" not in speakable.normalized_text.lower()


def test_long_text_is_segmented_by_byte_limit():
    text = "我看见你停在那里，" * 80
    speakable = extract_speakable_text(_output(text), max_segment_bytes=120)

    assert len(speakable.segments) > 1
    assert all(len(segment.encode("utf-8")) <= 120 for segment in speakable.segments)
