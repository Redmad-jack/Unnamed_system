from __future__ import annotations

from conscious_entity.expression.first_unit_gate import (
    normalize_first_unit_gate_input,
    normalized_set,
    should_speak_first_unit,
)


GATE_CONFIG = {
    "min_chinese_chars": 12,
    "min_english_words": 8,
    "silent_short_chinese_chars": 6,
    "silent_short_english_words": 6,
    "strong_thought_markers": [
        "为什么",
        "你觉得",
        "意识",
        "记忆",
        "工具",
        "主体",
        "人类",
        "AI",
        "机器",
        "自由",
        "控制",
        "感觉",
        "真实",
    ],
    "weak_thought_markers": ["怎么", "什么", "是不是", "能不能"],
    "silent_exact_inputs": [
        "你好",
        "在吗",
        "你能看见我吗",
        "can you hear me",
    ],
    "formal_short_answers": [
        "想",
        "不想",
        "可以",
        "不要",
        "有",
        "没有",
        "A",
        "B",
        "好",
        "行",
    ],
}


def test_normalize_handles_case_spacing_and_trailing_punctuation():
    assert normalize_first_unit_gate_input("  CAN   You Hear Me...?  ") == "can you hear me"
    assert normalize_first_unit_gate_input("你好？！") == "你好"


def test_configured_lists_are_normalized_with_same_function_as_input():
    values = normalized_set([" CAN   You Hear Me...? ", "A。"])

    assert "can you hear me" in values
    assert "a" in values


def test_question_mark_does_not_override_silent_exact_inputs():
    for text in ["你好？", "在吗？", "can you hear me?", "你能看见我吗？"]:
        assert should_speak_first_unit(text, GATE_CONFIG) is False


def test_short_weak_marker_inputs_stay_silent():
    assert should_speak_first_unit("怎么了？", GATE_CONFIG) is False
    assert should_speak_first_unit("你觉得呢？", GATE_CONFIG) is False


def test_long_strong_marker_input_can_speak_first_unit():
    assert should_speak_first_unit("你觉得 AI 如果有记忆，它还算工具吗？", GATE_CONFIG) is True


def test_formal_short_answers_stay_silent():
    for text in ["想", "不想", "可以", "不要", "有", "没有", "A", "B", "好", "行"]:
        assert should_speak_first_unit(text, GATE_CONFIG) is False
