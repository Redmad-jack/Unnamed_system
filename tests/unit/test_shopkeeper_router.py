from __future__ import annotations

import pytest

from conscious_entity.core.config_loader import load_config
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.shopkeeper.menu import MenuCatalog
from conscious_entity.shopkeeper.models import OrderStatus, Scene, ShopAction, ShopSessionState, SoupId, TurnInput
from conscious_entity.shopkeeper.router import ShopSceneRouter
from conscious_entity.state.state_core import EntityState


@pytest.fixture
def router(config_dir):
    cfg = load_config("shopkeeper_mode.yaml", config_dir=config_dir)
    return ShopSceneRouter(cfg, MenuCatalog.from_config(cfg))


def _route(router, text="", state=None, visual_tags=None):
    return router.route(
        TurnInput(text=text, visual_tags=visual_tags or []),
        state or ShopSessionState(),
        ShortTermMemory(),
        EntityState(),
    )


def test_routes_first_text_turn_to_greeting(router):
    decision = _route(router, "hello")
    assert decision.scene == Scene.GREETING
    assert decision.next_scene == Scene.MENU_INTRO
    assert decision.action == ShopAction.NONE


def test_routes_menu_question_to_menu_intro(router):
    decision = _route(router, "菜单有什么")
    assert decision.scene == Scene.MENU_INTRO
    assert decision.next_state.order_status == OrderStatus.SELECTING


def test_routes_soup_choice_to_confirm_choice(router):
    decision = _route(router, "no-ai soup please")
    assert decision.scene == Scene.ORDER_TAKING
    assert decision.action == ShopAction.CONFIRM_CHOICE
    assert decision.state_updates["selected_soup"] == "no_ai"
    assert decision.next_state.selected_soup == SoupId.NO_AI


def test_pending_order_confirmation_places_order(router):
    state = ShopSessionState(
        order_status=OrderStatus.PENDING_CONFIRMATION,
        selected_soup=SoupId.AI_MIAO,
    )
    decision = _route(router, "yes", state)
    assert decision.scene == Scene.ORDER_CONFIRM
    assert decision.action == ShopAction.PLACE_ORDER
    assert decision.next_state.order_status == OrderStatus.PLACED
    assert decision.next_state.selected_soup == SoupId.AI_MIAO


def test_pending_order_denial_clarifies(router):
    state = ShopSessionState(
        order_status=OrderStatus.PENDING_CONFIRMATION,
        selected_soup=SoupId.AI_MIAO,
    )
    decision = _route(router, "no", state)
    assert decision.action == ShopAction.CLARIFY
    assert decision.next_state.order_status == OrderStatus.SELECTING
    assert decision.next_state.selected_soup is None


def test_visual_tags_are_allowlisted(router):
    decision = _route(router, "", visual_tags=["bag", "face", "unknown"])
    assert decision.scene == Scene.APPEARANCE_CHAT
    assert decision.visual_tags == ("bag",)
    assert decision.next_state.has_complimented_appearance is True


def test_empty_input_routes_to_fallback(router):
    decision = _route(router, "")
    assert decision.scene == Scene.FALLBACK
    assert decision.action == ShopAction.CLARIFY
