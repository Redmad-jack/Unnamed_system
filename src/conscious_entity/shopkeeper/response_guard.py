from __future__ import annotations

import re
from typing import Any, Mapping

from conscious_entity.shopkeeper.models import Language, Scene, ShopAction, StructuredTurn

_DEFAULT_FORBIDDEN = {
    Language.ZH: (
        "您好，请问需要什么帮助",
        "根据您的输入",
        "作为AI",
        "作为 AI",
    ),
    Language.EN: (
        "as an ai",
        "based on your input",
        "how may i assist you",
        "how can i assist",
    ),
}


class ShopkeeperResponseGuard:
    def __init__(self, config: Mapping[str, Any]) -> None:
        style_cfg = config.get("style", {})
        self._max_sentences = int(style_cfg.get("max_sentences", 3))
        configured = style_cfg.get("forbidden_phrases", {})
        self._forbidden = {
            Language.ZH: tuple(configured.get("zh", ())) + _DEFAULT_FORBIDDEN[Language.ZH],
            Language.EN: tuple(configured.get("en", ())) + _DEFAULT_FORBIDDEN[Language.EN],
        }

    def apply(self, text: str, turn: StructuredTurn) -> str:
        cleaned = _normalize_whitespace(text)
        if not cleaned:
            return _fallback_reply(turn)
        if self._contains_forbidden(cleaned, turn.language):
            return _fallback_reply(turn)
        cleaned = _limit_sentences(cleaned, self._max_sentences, turn.language)
        if not cleaned:
            return _fallback_reply(turn)
        return cleaned

    def _contains_forbidden(self, text: str, language: Language) -> bool:
        lowered = text.lower()
        for phrase in self._forbidden[language]:
            if phrase and phrase.lower() in lowered:
                return True
        return False


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _limit_sentences(text: str, max_sentences: int, language: Language) -> str:
    if max_sentences <= 0:
        return text
    if language == Language.ZH:
        return _limit_zh_sentences(text, max_sentences)
    return _limit_en_sentences(text, max_sentences)


def _limit_zh_sentences(text: str, max_sentences: int) -> str:
    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    limited = "".join(part.strip() for part in parts[:max_sentences]).strip()
    return limited or text


def _limit_en_sentences(text: str, max_sentences: int) -> str:
    parts = re.findall(r"[^.!?]+[.!?]?", text)
    limited = " ".join(part.strip() for part in parts[:max_sentences]).strip()
    return limited or text


def _fallback_reply(turn: StructuredTurn) -> str:
    if turn.language == Language.EN:
        if turn.action == ShopAction.PLACE_ORDER:
            return "Sure, I will get that started."
        if turn.action == ShopAction.CONFIRM_CHOICE:
            return "Sure, let me confirm that soup."
        if turn.action == ShopAction.CLARIFY:
            return "I missed that. Which soup would you like?"
        if turn.scene == Scene.APPEARANCE_CHAT:
            return "That looks nice on you. Want to see the soups?"
        return "Take a look. We have two soups today."

    if turn.action == ShopAction.PLACE_ORDER:
        return "好，我给你记上。"
    if turn.action == ShopAction.CONFIRM_CHOICE:
        return "好，我先跟你确认一下这碗汤。"
    if turn.action == ShopAction.CLARIFY:
        return "我刚没听清，你想要哪碗汤？"
    if turn.scene == Scene.APPEARANCE_CHAT:
        return "挺适合你的。要不要看看今天的汤？"
    return "看看今天这两碗汤吧。"
