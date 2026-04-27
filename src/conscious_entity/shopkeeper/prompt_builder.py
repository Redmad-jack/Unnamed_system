from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from conscious_entity.shopkeeper.menu import MenuCatalog
from conscious_entity.shopkeeper.models import Language, ShopSessionState, SoupId
from conscious_entity.shopkeeper.router import RouteDecision
from conscious_entity.state.state_core import EntityState


@dataclass(frozen=True)
class ShopkeeperPromptContext:
    system_prompt: str
    messages: list[dict[str, str]]
    max_tokens: int
    raw_prompt: str


class ShopkeeperPromptBuilder:
    def __init__(
        self,
        prompts_dir: Path,
        config: Mapping[str, Any],
        menu: MenuCatalog,
    ) -> None:
        self._template = _load_prompt(prompts_dir / "shopkeeper_system.txt")
        self._config = config
        self._menu = menu

    def build(
        self,
        *,
        route: RouteDecision,
        shop_state: ShopSessionState,
        entity_state: EntityState,
        user_input: str,
        retrieved_context: Iterable[str] = (),
    ) -> ShopkeeperPromptContext:
        context = {
            "language": route.language.value,
            "scene": route.scene.value,
            "action": route.action.value,
            "next_scene": route.next_scene.value,
            "state_summary": _shop_state_summary(shop_state),
            "entity_state_summary": _entity_state_summary(entity_state),
            "user_current_input": user_input,
            "visual_tags": list(route.visual_tags),
            "retrieved_context": list(retrieved_context),
            "menu": _menu_summary(self._menu, route.language),
            "selected_soup": route.state_updates.get("selected_soup"),
        }
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
        system_prompt = self._template.replace("{context}", context_json)
        messages = [{
            "role": "user",
            "content": (
                "Write the shopkeeper reply for the controlled context above. "
                "Return only the spoken reply."
            ),
        }]
        raw_prompt = (
            f"SYSTEM:\n{system_prompt}\n\n"
            f"MESSAGES:\n{json.dumps(messages, ensure_ascii=False, indent=2)}"
        )
        return ShopkeeperPromptContext(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=int(self._config.get("style", {}).get("max_tokens", 120)),
            raw_prompt=raw_prompt,
        )


def _shop_state_summary(state: ShopSessionState) -> dict[str, Any]:
    return {
        "language": state.language.value,
        "current_scene": state.current_scene.value,
        "previous_scene": state.previous_scene.value if state.previous_scene else None,
        "order_status": state.order_status.value,
        "selected_soup": state.selected_soup.value if state.selected_soup else None,
        "has_complimented_appearance": state.has_complimented_appearance,
        "has_asked_item_origin": state.has_asked_item_origin,
        "recent_turns": state.recent_turns[-4:],
    }


def _entity_state_summary(state: EntityState) -> dict[str, float]:
    values = state.to_dict()
    return {
        "attention_focus": round(values["attention_focus"], 2),
        "curiosity": round(values["curiosity"], 2),
        "trust": round(values["trust"], 2),
        "fatigue": round(values["fatigue"], 2),
        "resistance": round(values["resistance"], 2),
    }


def _menu_summary(menu: MenuCatalog, language: Language) -> dict[str, str]:
    return {
        "ai_miao": menu.display_name(SoupId.AI_MIAO, language),
        "no_ai": menu.display_name(SoupId.NO_AI, language),
    }


def _load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Shopkeeper prompt not found: {path}")
    return path.read_text(encoding="utf-8")
