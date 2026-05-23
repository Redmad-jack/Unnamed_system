from __future__ import annotations

from conscious_entity.language import detect_text_language, matches_language


def test_detect_text_language_prefers_chinese_when_mixed():
    assert detect_text_language("hello，但我先用中文") == "zh"


def test_detect_text_language_detects_english_and_unknown():
    assert detect_text_language("Can you see me?") == "en"
    assert detect_text_language("...") == "unknown"


def test_matches_language_preserves_existing_tolerances():
    assert matches_language("嗯。", "zh") is True
    assert matches_language("OK", "zh") is True
    assert matches_language("I am here.", "zh") is False
    assert matches_language("I am here.", "en") is True
    assert matches_language("我在。", "en") is False
    assert matches_language("我在。", "unknown") is True
