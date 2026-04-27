from __future__ import annotations

import re

from conscious_entity.shopkeeper.models import Language

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")


def detect_language(
    text: str | None,
    previous: Language | str | None = None,
    default: Language | str = Language.ZH,
) -> Language:
    """
    Lightweight zh/en detection for shopkeeper mode.

    Ambiguous or empty input keeps the previous language when available.
    """
    previous_lang = _coerce_language(previous)
    default_lang = _coerce_language(default) or Language.ZH
    raw = (text or "").strip()
    if not raw:
        return previous_lang or default_lang

    cjk_count = len(_CJK_RE.findall(raw))
    latin_word_count = len(_LATIN_WORD_RE.findall(raw))

    if cjk_count == 0 and latin_word_count == 0:
        return previous_lang or default_lang
    if cjk_count == 0:
        return Language.EN
    if latin_word_count == 0:
        return Language.ZH
    if cjk_count >= latin_word_count:
        return Language.ZH
    return Language.EN


def _coerce_language(value: Language | str | None) -> Language | None:
    if value is None:
        return None
    if isinstance(value, Language):
        return value
    try:
        return Language(str(value))
    except ValueError:
        return None
