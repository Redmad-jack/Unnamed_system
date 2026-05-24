from __future__ import annotations

from typing import Literal


TextLanguage = Literal["zh", "en", "unknown"]


def detect_text_language(text: str) -> TextLanguage:
    value = str(text or "")
    chinese_count = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    latin_count = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if chinese_count > 0:
        return "zh"
    if latin_count > 0:
        return "en"
    return "unknown"


def matches_language(text: str, target: TextLanguage) -> bool:
    value = str(text or "")
    if target == "unknown" or not value.strip():
        return True
    chinese_count = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    latin_count = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if target == "zh":
        return chinese_count > 0 or latin_count < 3
    if target == "en":
        return chinese_count == 0
    return True
