from __future__ import annotations

import re
from typing import Any

_TRAILING_PUNCT_RE = re.compile(r"[\s。！？!?….,，、;；:：\"'“”‘’）)\]】》>]+$")
_ELLIPSIS_RE = re.compile(r"(?:\.\.\.|…)+$")
_SPACE_RE = re.compile(r"\s+")
_ENGLISH_WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?", re.IGNORECASE)


def normalize_first_unit_gate_input(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = _SPACE_RE.sub(" ", text)
    while text:
        next_text = _ELLIPSIS_RE.sub("", text).strip()
        next_text = _TRAILING_PUNCT_RE.sub("", next_text).strip()
        if next_text == text:
            break
        text = next_text
    return _SPACE_RE.sub(" ", text).strip()


def normalized_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    result: set[str] = set()
    for value in values:
        normalized = normalize_first_unit_gate_input(value)
        if normalized:
            result.add(normalized)
    return result


def should_speak_first_unit(raw_input: str, gate_config: dict[str, Any]) -> bool:
    cfg = gate_config if isinstance(gate_config, dict) else {}
    normalized = normalize_first_unit_gate_input(raw_input)
    if not normalized:
        return False

    if normalized in normalized_set(cfg.get("silent_exact_inputs")):
        return False
    if normalized in normalized_set(cfg.get("formal_short_answers")):
        return False

    chinese_count = _chinese_char_count(normalized)
    english_word_count = _english_word_count(normalized)
    if chinese_count > 0:
        if chinese_count <= _int_cfg(cfg.get("silent_short_chinese_chars"), 6):
            return False
    elif english_word_count > 0 and english_word_count <= _int_cfg(
        cfg.get("silent_short_english_words"),
        6,
    ):
        return False

    if _contains_any_marker(normalized, cfg.get("strong_thought_markers")):
        return True

    if chinese_count >= _int_cfg(cfg.get("min_chinese_chars"), 12):
        return True
    if english_word_count >= _int_cfg(cfg.get("min_english_words"), 8):
        return True

    return False


def _contains_any_marker(normalized: str, markers: Any) -> bool:
    for marker in normalized_set(markers):
        if marker and marker in normalized:
            return True
    return False


def _chinese_char_count(value: str) -> int:
    return sum(1 for char in value if "\u4e00" <= char <= "\u9fff")


def _english_word_count(value: str) -> int:
    return len(_ENGLISH_WORD_RE.findall(value))


def _int_cfg(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
