from __future__ import annotations

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


def test_enum_values_are_stable_english_keys():
    assert Language.ZH.value == "zh"
    assert Language.EN.value == "en"
    assert SoupId.AI_MIAO.value == "ai_miao"
    assert SoupId.NO_AI.value == "no_ai"
    assert Scene.ORDER_TAKING.value == "order_taking"
    assert ShopAction.CONFIRM_CHOICE.value == "confirm_choice"
    assert OrderStatus.PENDING_CONFIRMATION.value == "pending_confirmation"


def test_turn_input_prefers_text_over_asr_text():
    turn_input = TurnInput(text=" typed text ", asr_text="asr text")
    assert turn_input.effective_text == "typed text"


def test_turn_input_falls_back_to_asr_text():
    turn_input = TurnInput(asr_text=" heard text ")
    assert turn_input.effective_text == "heard text"


def test_shop_session_state_defaults_are_shopkeeper_ready():
    state = ShopSessionState()
    assert state.language == Language.ZH
    assert state.current_scene == Scene.GREETING
    assert state.previous_scene is None
    assert state.order_status == OrderStatus.NONE
    assert state.selected_soup is None
    assert state.has_complimented_appearance is False
    assert state.has_asked_item_origin is False


def test_structured_turn_serializes_enum_values():
    turn = StructuredTurn(
        language=Language.EN,
        scene=Scene.MENU_INTRO,
        reply="Two soups today.",
        action=ShopAction.NONE,
        next_scene=Scene.ORDER_TAKING,
    )

    assert turn.to_dict() == {
        "language": "en",
        "scene": "menu_intro",
        "reply": "Two soups today.",
        "action": "none",
        "state_updates": {},
        "next_scene": "order_taking",
    }
