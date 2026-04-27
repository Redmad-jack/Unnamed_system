from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.migrations import run_migrations
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeCompletion
from conscious_entity.shopkeeper.models import TurnInput


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES ('shop-flow')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def loop(db):
    client = MagicMock(spec=ClaudeClient)
    client.complete.return_value = "A quiet pattern formed."
    client.complete_with_metadata.return_value = ClaudeCompletion(text="好，看看今天这两碗汤。")
    return InteractionLoop(
        db,
        "shop-flow",
        load_all_configs(Path("config")),
        Path("prompts"),
        llm_client=client,
    )


def test_shopkeeper_flow_greeting_menu_order_confirm_waiting(loop, db):
    greeting = loop.run_turn("你好老板")
    assert greeting.turn["scene"] == "greeting"
    assert greeting.turn["next_scene"] == "menu_intro"

    menu = loop.run_turn("菜单有什么")
    assert menu.turn["scene"] == "menu_intro"
    assert loop.current_shop_state.order_status.value == "selecting"

    order = loop.run_turn("来一碗艾苗汤")
    assert order.turn["scene"] == "order_taking"
    assert order.turn["action"] == "confirm_choice"
    assert order.turn["state_updates"]["selected_soup"] == "ai_miao"

    confirm = loop.run_turn("对，就这个")
    assert confirm.turn["scene"] == "order_confirm"
    assert confirm.turn["action"] == "place_order"
    assert loop.current_shop_state.order_status.value == "placed"

    waiting = loop.run_turn("那我等一下")
    assert waiting.turn["scene"] == "waiting_chat"

    count = db.execute("SELECT COUNT(*) AS cnt FROM shop_state_snapshots").fetchone()["cnt"]
    assert count == 5


def test_shopkeeper_flow_visual_tags_and_fallback(loop):
    appearance = loop.run_turn(TurnInput(text="", visual_tags=["bag", "face"]))
    assert appearance.turn["scene"] == "appearance_chat"
    assert loop.current_shop_state.has_complimented_appearance is True

    fallback = loop.run_turn("")
    assert fallback.turn["scene"] == "fallback"
    assert fallback.turn["action"] == "clarify"


def test_shopkeeper_does_not_repeat_appearance_flags(loop):
    loop.run_turn(TurnInput(text="", visual_tags=["bag"]))
    second = loop.run_turn(TurnInput(text="这个包怎么样", visual_tags=["bag"]))

    assert second.turn["scene"] == "appearance_chat"
    assert loop.current_shop_state.has_complimented_appearance is True
    assert loop.current_shop_state.has_asked_item_origin is True
