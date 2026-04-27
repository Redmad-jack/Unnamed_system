from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.shopkeeper.language import detect_language
from conscious_entity.shopkeeper.menu import MenuCatalog, SoupMatch
from conscious_entity.shopkeeper.models import (
    Language,
    OrderStatus,
    Scene,
    ShopAction,
    ShopSessionState,
    SoupId,
    StructuredTurn,
    TurnInput,
)
from conscious_entity.state.state_core import EntityState


@dataclass(frozen=True)
class RouteDecision:
    language: Language
    scene: Scene
    action: ShopAction
    next_scene: Scene
    state_updates: dict[str, Any]
    next_state: ShopSessionState
    soup_match: SoupMatch | None = None
    visual_tags: tuple[str, ...] = ()

    def structured_turn(self) -> StructuredTurn:
        return StructuredTurn(
            language=self.language,
            scene=self.scene,
            reply="",
            action=self.action,
            state_updates=self.state_updates,
            next_scene=self.next_scene,
        )


class ShopSceneRouter:
    def __init__(self, config: Mapping[str, Any], menu: MenuCatalog) -> None:
        self._config = config
        self._menu = menu
        self._default_language = Language(
            config.get("language", {}).get("default", Language.ZH.value)
        )
        self._keywords = config.get("scenes", {}).get("keywords", {})
        self._allowed_visual_tags = set(config.get("visual_tags", {}).get("allowed", []))

    def route(
        self,
        turn_input: TurnInput,
        current_state: ShopSessionState,
        short_term: ShortTermMemory,
        entity_state: EntityState,
    ) -> RouteDecision:
        text = turn_input.effective_text
        language = detect_language(
            text,
            previous=current_state.language,
            default=self._default_language,
        )
        soup_match = self._menu.normalize_soup(text)
        visual_tags = tuple(
            tag for tag in turn_input.visual_tags
            if tag in self._allowed_visual_tags
        )

        if current_state.order_status == OrderStatus.PENDING_CONFIRMATION:
            if self._matches("confirm", text, language):
                return self._decision(
                    current_state, text, language, Scene.ORDER_CONFIRM,
                    ShopAction.PLACE_ORDER, Scene.WAITING_CHAT,
                    {
                        "order_status": OrderStatus.PLACED,
                    },
                    soup_match=soup_match,
                    visual_tags=visual_tags,
                )
            if self._matches("deny", text, language):
                return self._decision(
                    current_state, text, language, Scene.ORDER_CONFIRM,
                    ShopAction.CLARIFY, Scene.ORDER_TAKING,
                    {
                        "order_status": OrderStatus.SELECTING,
                        "selected_soup": None,
                    },
                    visual_tags=visual_tags,
                )

        if soup_match is not None:
            return self._decision(
                current_state, text, language, Scene.ORDER_TAKING,
                ShopAction.CONFIRM_CHOICE, Scene.ORDER_CONFIRM,
                {
                    "order_status": OrderStatus.PENDING_CONFIRMATION,
                    "selected_soup": soup_match.soup_id,
                },
                soup_match=soup_match,
                visual_tags=visual_tags,
            )

        if self._matches("menu_intro", text, language):
            updates: dict[str, Any] = {}
            if current_state.order_status == OrderStatus.NONE:
                updates["order_status"] = OrderStatus.SELECTING
            return self._decision(
                current_state, text, language, Scene.MENU_INTRO,
                ShopAction.NONE, Scene.ORDER_TAKING,
                updates,
                visual_tags=visual_tags,
            )

        if visual_tags or self._matches("appearance_chat", text, language):
            updates = {}
            if not current_state.has_complimented_appearance:
                updates["has_complimented_appearance"] = True
            elif not current_state.has_asked_item_origin:
                updates["has_asked_item_origin"] = True
            return self._decision(
                current_state, text, language, Scene.APPEARANCE_CHAT,
                ShopAction.NONE, Scene.MENU_INTRO,
                updates,
                visual_tags=visual_tags,
            )

        if not _has_meaningful_text(text):
            return self._decision(
                current_state, text, language, Scene.FALLBACK,
                ShopAction.CLARIFY, Scene.MENU_INTRO,
                {},
                visual_tags=visual_tags,
            )

        if self._matches("greeting", text, language) or not current_state.recent_turns:
            return self._decision(
                current_state, text, language, Scene.GREETING,
                ShopAction.NONE, Scene.MENU_INTRO,
                {},
                visual_tags=visual_tags,
            )

        if current_state.order_status == OrderStatus.PLACED:
            return self._decision(
                current_state, text, language, Scene.WAITING_CHAT,
                ShopAction.NONE, Scene.WAITING_CHAT,
                {},
                visual_tags=visual_tags,
            )

        return self._decision(
            current_state, text, language, Scene.SMALLTALK,
            ShopAction.NONE, Scene.MENU_INTRO,
            {},
            visual_tags=visual_tags,
        )

    def _matches(self, key: str, text: str, language: Language) -> bool:
        phrases = self._keywords.get(key, {}).get(language.value, [])
        normalized = _normalize(text)
        for phrase in phrases:
            normalized_phrase = _normalize(str(phrase))
            if not normalized_phrase:
                continue
            if language == Language.ZH:
                if normalized_phrase in normalized:
                    return True
            elif _ascii_phrase_matches(normalized, normalized_phrase):
                return True
        return False

    def _decision(
        self,
        current_state: ShopSessionState,
        text: str,
        language: Language,
        scene: Scene,
        action: ShopAction,
        next_scene: Scene,
        updates: dict[str, Any],
        *,
        soup_match: SoupMatch | None = None,
        visual_tags: tuple[str, ...] = (),
    ) -> RouteDecision:
        next_state = _apply_updates(
            current_state, text, language, scene, next_scene, updates
        )
        serializable_updates = {
            key: _serialize_update_value(value)
            for key, value in updates.items()
        }
        return RouteDecision(
            language=language,
            scene=scene,
            action=action,
            next_scene=next_scene,
            state_updates=serializable_updates,
            next_state=next_state,
            soup_match=soup_match,
            visual_tags=visual_tags,
        )


def _apply_updates(
    current: ShopSessionState,
    text: str,
    language: Language,
    scene: Scene,
    next_scene: Scene,
    updates: dict[str, Any],
) -> ShopSessionState:
    selected_soup = updates.get("selected_soup", current.selected_soup)
    if selected_soup is not None and not isinstance(selected_soup, SoupId):
        selected_soup = SoupId(selected_soup)

    order_status = updates.get("order_status", current.order_status)
    if not isinstance(order_status, OrderStatus):
        order_status = OrderStatus(order_status)

    recent_turns = list(current.recent_turns)
    if text.strip():
        recent_turns.append(text.strip())

    return ShopSessionState(
        language=language,
        current_scene=next_scene,
        previous_scene=scene,
        order_status=order_status,
        selected_soup=selected_soup,
        has_complimented_appearance=bool(
            updates.get("has_complimented_appearance", current.has_complimented_appearance)
        ),
        has_asked_item_origin=bool(
            updates.get("has_asked_item_origin", current.has_asked_item_origin)
        ),
        recent_turns=recent_turns[-6:],
    )


def _serialize_update_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def _ascii_phrase_matches(text: str, phrase: str) -> bool:
    words = text.split()
    phrase_words = phrase.split()
    if not phrase_words:
        return False
    for i in range(len(words) - len(phrase_words) + 1):
        if words[i:i + len(phrase_words)] == phrase_words:
            return True
    return False


def _has_meaningful_text(text: str) -> bool:
    return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text)
