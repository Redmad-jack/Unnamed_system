from __future__ import annotations

import re

from conscious_entity.audio.types import SpeakableText
from conscious_entity.expression.output_model import ExpressionOutput


_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_DEBUG_MARKER_RE = re.compile(r"\[(?:debug|system|trace|raw_prompt)[^\]]*\]", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def extract_speakable_text(
    output: ExpressionOutput,
    *,
    max_segment_bytes: int = 800,
) -> SpeakableText:
    raw = output.spoken_text if output.spoken_text is not None else output.text
    raw = raw or ""
    normalized = normalize_for_speech(raw)
    segments = split_for_tts(normalized, max_segment_bytes=max_segment_bytes)
    return SpeakableText(
        should_speak=bool(segments),
        segments=segments,
        raw_text=raw,
        normalized_text=normalized,
    )


def normalize_for_speech(text: str) -> str:
    cleaned = _CODE_FENCE_RE.sub(" ", text)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _DEBUG_MARKER_RE.sub(" ", cleaned)
    cleaned = _CONTROL_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_for_tts(text: str, *, max_segment_bytes: int = 800) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    segments: list[str] = []
    for paragraph in re.split(r"\n{2,}", cleaned):
        _split_recursive(paragraph.strip(), segments, max_segment_bytes=max_segment_bytes)
    return [segment for segment in segments if segment.strip()]


def _split_recursive(text: str, out: list[str], *, max_segment_bytes: int) -> None:
    if not text:
        return
    if _byte_len(text) <= max_segment_bytes:
        out.append(text.strip())
        return

    for pattern in (r"(?<=[。！？!?])", r"(?<=[；;：:])", r"(?<=[，,])"):
        parts = [part.strip() for part in re.split(pattern, text) if part.strip()]
        if len(parts) > 1:
            _merge_parts(parts, out, max_segment_bytes=max_segment_bytes)
            return

    _hard_split(text, out, max_segment_bytes=max_segment_bytes)


def _merge_parts(parts: list[str], out: list[str], *, max_segment_bytes: int) -> None:
    current = ""
    for part in parts:
        candidate = f"{current}{part}" if current else part
        if current and _byte_len(candidate) > max_segment_bytes:
            _split_recursive(current, out, max_segment_bytes=max_segment_bytes)
            current = part
        else:
            current = candidate
    if current:
        _split_recursive(current, out, max_segment_bytes=max_segment_bytes)


def _hard_split(text: str, out: list[str], *, max_segment_bytes: int) -> None:
    current = ""
    for char in text:
        candidate = current + char
        if current and _byte_len(candidate) > max_segment_bytes:
            out.append(current.strip())
            current = char
        else:
            current = candidate
    if current.strip():
        out.append(current.strip())


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))
