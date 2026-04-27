from __future__ import annotations

import json
import sqlite3
from typing import Any

from conscious_entity.shopkeeper.models import ShopSessionState


class ShopStateStore:
    def __init__(self, conn: sqlite3.Connection, session_id: str) -> None:
        self._conn = conn
        self._session_id = session_id

    def save_snapshot(
        self,
        state: ShopSessionState,
        *,
        state_updates: dict[str, Any] | None = None,
        trigger_scene: str | None = None,
        action: str | None = None,
        entity_state_snapshot_id: int | None = None,
    ) -> int:
        d = state.to_dict()
        cursor = self._conn.execute(
            """
            INSERT INTO shop_state_snapshots (
                session_id, language, current_scene, previous_scene,
                order_status, selected_soup, has_complimented_appearance,
                has_asked_item_origin, recent_turns, state_updates,
                trigger_scene, action, entity_state_snapshot_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._session_id,
                d["language"],
                d["current_scene"],
                d["previous_scene"],
                d["order_status"],
                d["selected_soup"],
                1 if d["has_complimented_appearance"] else 0,
                1 if d["has_asked_item_origin"] else 0,
                json.dumps(d["recent_turns"], ensure_ascii=False),
                json.dumps(state_updates or {}, ensure_ascii=False),
                trigger_scene,
                action,
                entity_state_snapshot_id,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def load_latest(self) -> ShopSessionState | None:
        row = self._conn.execute(
            """
            SELECT language, current_scene, previous_scene, order_status,
                   selected_soup, has_complimented_appearance,
                   has_asked_item_origin, recent_turns
            FROM shop_state_snapshots
            WHERE session_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (self._session_id,),
        ).fetchone()
        if row is None:
            return None

        data = dict(row)
        raw_recent = data.get("recent_turns")
        data["recent_turns"] = json.loads(raw_recent) if raw_recent else []
        data["has_complimented_appearance"] = bool(data["has_complimented_appearance"])
        data["has_asked_item_origin"] = bool(data["has_asked_item_origin"])
        return ShopSessionState.from_dict(data)
