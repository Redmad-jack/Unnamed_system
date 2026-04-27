from __future__ import annotations

import json
from pathlib import Path

import pytest

from conscious_entity.core.config_loader import load_config
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.shopkeeper.menu import MenuCatalog
from conscious_entity.shopkeeper.models import Scene, ShopSessionState, TurnInput
from conscious_entity.shopkeeper.prompt_builder import ShopkeeperPromptBuilder
from conscious_entity.shopkeeper.router import ShopSceneRouter
from conscious_entity.state.state_core import EntityState


@pytest.fixture
def shopkeeper_cfg(config_dir):
    return load_config("shopkeeper_mode.yaml", config_dir=config_dir)


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


@pytest.fixture
def builder(prompts_dir, shopkeeper_cfg):
    menu = MenuCatalog.from_config(shopkeeper_cfg)
    return ShopkeeperPromptBuilder(prompts_dir, shopkeeper_cfg, menu)


def test_prompt_contains_controlled_context(builder, shopkeeper_cfg):
    menu = MenuCatalog.from_config(shopkeeper_cfg)
    router = ShopSceneRouter(shopkeeper_cfg, menu)
    route = router.route(
        TurnInput(text="no-ai soup please", visual_tags=["bag"]),
        ShopSessionState(),
        ShortTermMemory(),
        EntityState(),
    )

    ctx = builder.build(
        route=route,
        shop_state=route.next_state,
        entity_state=EntityState(trust=0.66),
        user_input="no-ai soup please",
        retrieved_context=["Customer liked quiet replies."],
    )

    assert "shopkeeper mode" in ctx.system_prompt
    assert "no_ai" in ctx.system_prompt
    assert "Customer liked quiet replies." in ctx.system_prompt
    assert ctx.messages[0]["role"] == "user"
    assert ctx.max_tokens == 120
    assert "SYSTEM:" in ctx.raw_prompt


def test_prompt_uses_scene_and_language(builder, shopkeeper_cfg):
    menu = MenuCatalog.from_config(shopkeeper_cfg)
    router = ShopSceneRouter(shopkeeper_cfg, menu)
    route = router.route(
        TurnInput(text="菜单有什么"),
        ShopSessionState(),
        ShortTermMemory(),
        EntityState(),
    )

    ctx = builder.build(
        route=route,
        shop_state=route.next_state,
        entity_state=EntityState(),
        user_input="菜单有什么",
    )
    context_json = ctx.system_prompt.split("Current controlled context:\n", 1)[1]
    data = json.loads(context_json)

    assert data["language"] == "zh"
    assert data["scene"] == Scene.MENU_INTRO.value
    assert data["menu"]["ai_miao"] == "艾苗汤"
