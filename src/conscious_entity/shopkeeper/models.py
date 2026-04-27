from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Language(str, Enum):
    ZH = "zh"
    EN = "en"


class SoupId(str, Enum):
    AI_MIAO = "ai_miao"
    NO_AI = "no_ai"


class Scene(str, Enum):
    GREETING = "greeting"
    APPEARANCE_CHAT = "appearance_chat"
    SMALLTALK = "smalltalk"
    MENU_INTRO = "menu_intro"
    ORDER_TAKING = "order_taking"
    ORDER_CONFIRM = "order_confirm"
    WAITING_CHAT = "waiting_chat"
    FALLBACK = "fallback"


class ShopAction(str, Enum):
    NONE = "none"
    PLACE_ORDER = "place_order"
    CLARIFY = "clarify"
    CONFIRM_CHOICE = "confirm_choice"


class OrderStatus(str, Enum):
    NONE = "none"
    SELECTING = "selecting"
    PENDING_CONFIRMATION = "pending_confirmation"
    PLACED = "placed"


@dataclass
class TurnInput:
    text: str = ""
    asr_text: str | None = None
    visual_tags: list[str] = field(default_factory=list)
    retrieved_context: list[str] = field(default_factory=list)
    microphone: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_text(self) -> str:
        text = self.text.strip()
        if text:
            return text
        return (self.asr_text or "").strip()


@dataclass
class ShopSessionState:
    language: Language = Language.ZH
    current_scene: Scene = Scene.GREETING
    previous_scene: Scene | None = None
    order_status: OrderStatus = OrderStatus.NONE
    selected_soup: SoupId | None = None
    has_complimented_appearance: bool = False
    has_asked_item_origin: bool = False
    recent_turns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language.value,
            "current_scene": self.current_scene.value,
            "previous_scene": self.previous_scene.value if self.previous_scene else None,
            "order_status": self.order_status.value,
            "selected_soup": self.selected_soup.value if self.selected_soup else None,
            "has_complimented_appearance": self.has_complimented_appearance,
            "has_asked_item_origin": self.has_asked_item_origin,
            "recent_turns": list(self.recent_turns),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShopSessionState:
        selected_soup = data.get("selected_soup")
        previous_scene = data.get("previous_scene")
        return cls(
            language=Language(data.get("language", Language.ZH.value)),
            current_scene=Scene(data.get("current_scene", Scene.GREETING.value)),
            previous_scene=Scene(previous_scene) if previous_scene else None,
            order_status=OrderStatus(data.get("order_status", OrderStatus.NONE.value)),
            selected_soup=SoupId(selected_soup) if selected_soup else None,
            has_complimented_appearance=bool(data.get("has_complimented_appearance", False)),
            has_asked_item_origin=bool(data.get("has_asked_item_origin", False)),
            recent_turns=list(data.get("recent_turns", [])),
        )


@dataclass
class StructuredTurn:
    language: Language
    scene: Scene
    reply: str
    action: ShopAction = ShopAction.NONE
    state_updates: dict[str, Any] = field(default_factory=dict)
    next_scene: Scene | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language.value,
            "scene": self.scene.value,
            "reply": self.reply,
            "action": self.action.value,
            "state_updates": dict(self.state_updates),
            "next_scene": self.next_scene.value if self.next_scene else None,
        }
