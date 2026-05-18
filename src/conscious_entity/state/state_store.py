from __future__ import annotations

import sqlite3
from typing import Optional

from conscious_entity.state.state_core import EntityState, LEGACY_STATE_FIELDS, STATE_FIELDS


class StateStore:
    def __init__(self, conn: sqlite3.Connection, session_id: str) -> None:
        self._conn = conn
        self._session_id = session_id

    def save_snapshot(
        self,
        state: EntityState,
        trigger_event_type: Optional[str] = None,
        policy_action: Optional[str] = None,
    ) -> int:
        """Insert a state snapshot. Returns the new row id."""
        d = state.to_dict()
        legacy_values = {
            field: float(getattr(state, field))
            for field in LEGACY_STATE_FIELDS
        }
        # Existing installation databases may still have legacy NOT NULL columns
        # that were created before defaults were added.
        columns = [
            "session_id",
            *STATE_FIELDS,
            *LEGACY_STATE_FIELDS,
            "trigger_event_type",
            "policy_action",
        ]
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        values = [
            self._session_id,
            *(d[field] for field in STATE_FIELDS),
            *(legacy_values[field] for field in LEGACY_STATE_FIELDS),
            trigger_event_type,
            policy_action,
        ]
        cursor = self._conn.execute(
            f"INSERT INTO state_snapshots ({column_sql}) VALUES ({placeholders})",
            values,
        )
        self._conn.commit()
        return cursor.lastrowid

    def load_latest(self) -> Optional[EntityState]:
        """Load the most recent state snapshot for this session."""
        field_sql = ", ".join(STATE_FIELDS)
        row = self._conn.execute(
            f"""
            SELECT {field_sql}
            FROM state_snapshots
            WHERE session_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (self._session_id,),
        ).fetchone()

        if row is None:
            return None
        return EntityState.from_dict(dict(row))
