from __future__ import annotations

import sqlite3

from conscious_entity.db.migrations import run_migrations
from conscious_entity.shopkeeper.models import Language, OrderStatus, Scene, ShopSessionState, SoupId
from conscious_entity.shopkeeper.state_store import ShopStateStore


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES ('shop-session')")
    conn.commit()
    return conn


def test_save_and_load_latest_shop_state_snapshot():
    conn = _db()
    store = ShopStateStore(conn, "shop-session")
    state = ShopSessionState(
        language=Language.EN,
        current_scene=Scene.ORDER_CONFIRM,
        previous_scene=Scene.ORDER_TAKING,
        order_status=OrderStatus.PENDING_CONFIRMATION,
        selected_soup=SoupId.NO_AI,
        has_complimented_appearance=True,
        has_asked_item_origin=True,
        recent_turns=["hello", "no ai soup"],
    )

    store.save_snapshot(
        state,
        state_updates={"selected_soup": "no_ai"},
        trigger_scene="order_taking",
        action="confirm_choice",
    )

    loaded = store.load_latest()
    assert loaded == state
    conn.close()


def test_shop_state_snapshots_are_append_only():
    conn = _db()
    store = ShopStateStore(conn, "shop-session")
    store.save_snapshot(ShopSessionState())
    store.save_snapshot(ShopSessionState(order_status=OrderStatus.PLACED))

    count = conn.execute("SELECT COUNT(*) AS cnt FROM shop_state_snapshots").fetchone()["cnt"]
    assert count == 2
    assert store.load_latest().order_status == OrderStatus.PLACED
    conn.close()
