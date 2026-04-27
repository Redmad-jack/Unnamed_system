from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.interfaces.api import DialogRequest, _dialog_response, _turn_input_from_dialog


def test_dialog_request_accepts_optional_shopkeeper_inputs():
    body = DialogRequest(
        asr_text="来一碗艾苗汤",
        visual_tags=["bag"],
        retrieved_context=["repeat visitor"],
    )

    turn_input = _turn_input_from_dialog(body)
    assert turn_input.effective_text == "来一碗艾苗汤"
    assert turn_input.visual_tags == ["bag"]
    assert turn_input.retrieved_context == ["repeat visitor"]


def test_dialog_response_includes_structured_shopkeeper_fields():
    output = ExpressionOutput(
        text="好，我给你确认一下。",
        delay_ms=300,
        visual_mode="normal",
        spoken_text=None,
        raw_prompt="raw",
        turn={
            "language": "zh",
            "scene": "order_taking",
            "reply": "好，我给你确认一下。",
            "action": "confirm_choice",
            "state_updates": {"selected_soup": "ai_miao"},
            "next_scene": "order_confirm",
        },
    )
    shop_state = {
        "language": "zh",
        "current_scene": "order_confirm",
        "previous_scene": "order_taking",
        "order_status": "pending_confirmation",
        "selected_soup": "ai_miao",
        "has_complimented_appearance": False,
        "has_asked_item_origin": False,
        "recent_turns": [],
    }

    response = _dialog_response(output, shop_state)
    assert response["language"] == "zh"
    assert response["scene"] == "order_taking"
    assert response["action"] == "confirm_choice"
    assert response["selected_soup"] == "ai_miao"
    assert response["order_status"] == "pending_confirmation"
