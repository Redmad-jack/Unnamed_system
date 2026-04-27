from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from conscious_entity.shopkeeper.models import Language, SoupId


@dataclass(frozen=True)
class MenuItem:
    soup_id: SoupId
    display: dict[Language, str]
    aliases: dict[Language, tuple[str, ...]]


@dataclass(frozen=True)
class SoupMatch:
    soup_id: SoupId
    display_name: str
    matched_alias: str
    language: Language
    confidence: float


class MenuCatalog:
    def __init__(self, items: Mapping[SoupId, MenuItem]) -> None:
        self._items = dict(items)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> MenuCatalog:
        menu_cfg = config.get("menu", config)
        items_cfg = menu_cfg.get("items")
        if not isinstance(items_cfg, Mapping):
            raise ValueError("shopkeeper menu config must contain menu.items")

        items: dict[SoupId, MenuItem] = {}
        for raw_id, raw_item in items_cfg.items():
            try:
                soup_id = SoupId(str(raw_id))
            except ValueError as exc:
                raise ValueError(f"Unsupported soup id: {raw_id}") from exc
            if not isinstance(raw_item, Mapping):
                raise ValueError(f"Menu item {raw_id} must be a mapping")

            display = _load_localized_strings(raw_item.get("display"), f"{raw_id}.display")
            aliases = _load_aliases(raw_item.get("aliases"), f"{raw_id}.aliases")
            if soup_id == SoupId.AI_MIAO:
                _reject_bare_ai_aliases(aliases)
            items[soup_id] = MenuItem(soup_id=soup_id, display=display, aliases=aliases)

        expected = {SoupId.AI_MIAO, SoupId.NO_AI}
        if set(items) != expected:
            raise ValueError("shopkeeper menu must define exactly ai_miao and no_ai")
        return cls(items)

    def normalize_soup(self, text: str | None) -> SoupMatch | None:
        raw = (text or "").strip()
        if not raw:
            return None

        normalized_text = _normalize_phrase(raw)
        candidates = self._candidate_aliases()
        for soup_id, language, alias, is_display_name in candidates:
            normalized_alias = _normalize_phrase(alias)
            if not normalized_alias:
                continue
            if _phrase_matches(normalized_text, normalized_alias):
                item = self._items[soup_id]
                return SoupMatch(
                    soup_id=soup_id,
                    display_name=item.display[language],
                    matched_alias=alias,
                    language=language,
                    confidence=1.0 if is_display_name else 0.9,
                )
        return None

    def display_name(self, soup_id: SoupId, language: Language) -> str:
        return self._items[soup_id].display[language]

    def _candidate_aliases(self) -> list[tuple[SoupId, Language, str, bool]]:
        candidates: list[tuple[SoupId, Language, str, bool]] = []
        for soup_id in (SoupId.NO_AI, SoupId.AI_MIAO):
            item = self._items[soup_id]
            for language, display_name in item.display.items():
                candidates.append((soup_id, language, display_name, True))
            for language, aliases in item.aliases.items():
                for alias in aliases:
                    candidates.append((soup_id, language, alias, False))

        return sorted(
            candidates,
            key=lambda c: (
                0 if c[0] == SoupId.NO_AI else 1,
                -len(_normalize_phrase(c[2])),
            ),
        )


def normalize_soup(text: str | None, catalog: MenuCatalog) -> SoupMatch | None:
    return catalog.normalize_soup(text)


def _load_localized_strings(raw: object, path: str) -> dict[Language, str]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be a mapping")
    result: dict[Language, str] = {}
    for lang in (Language.ZH, Language.EN):
        value = raw.get(lang.value)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}.{lang.value} must be a non-empty string")
        result[lang] = value.strip()
    return result


def _load_aliases(raw: object, path: str) -> dict[Language, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must be a mapping")
    result: dict[Language, tuple[str, ...]] = {}
    for lang in (Language.ZH, Language.EN):
        values = raw.get(lang.value, [])
        if not isinstance(values, list):
            raise ValueError(f"{path}.{lang.value} must be a list")
        aliases = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path}.{lang.value} entries must be non-empty strings")
            aliases.append(value.strip())
        result[lang] = tuple(aliases)
    return result


def _reject_bare_ai_aliases(aliases: Mapping[Language, tuple[str, ...]]) -> None:
    for values in aliases.values():
        for alias in values:
            if _normalize_phrase(alias) == "ai":
                raise ValueError("Bare 'ai' cannot be an alias for ai_miao")


def _normalize_phrase(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[-_/]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _phrase_matches(normalized_text: str, normalized_alias: str) -> bool:
    if re.search(r"[a-z0-9]", normalized_alias):
        pattern = r"(?<![a-z0-9])" + re.escape(normalized_alias) + r"(?![a-z0-9])"
        return re.search(pattern, normalized_text) is not None
    return normalized_alias in normalized_text
