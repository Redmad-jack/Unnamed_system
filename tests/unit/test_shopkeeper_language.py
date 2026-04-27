from __future__ import annotations

from conscious_entity.shopkeeper.language import detect_language
from conscious_entity.shopkeeper.models import Language


def test_detects_chinese_input():
    assert detect_language("今天想喝点汤") == Language.ZH


def test_detects_english_input():
    assert detect_language("I would like soup today") == Language.EN


def test_mixed_input_uses_primary_signal():
    assert detect_language("I want no ai soup 你好") == Language.EN
    assert detect_language("我要 General Soup") == Language.ZH


def test_empty_input_uses_previous_language():
    assert detect_language("   ", previous=Language.EN) == Language.EN


def test_ambiguous_input_defaults_to_chinese():
    assert detect_language("...") == Language.ZH


def test_invalid_previous_falls_back_to_default():
    assert detect_language("", previous="fr", default=Language.EN) == Language.EN
