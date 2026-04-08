from __future__ import annotations

import sqlite3
from typing import Optional

from conscious_entity.state.state_core import EntityState


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
        cursor = self._conn.execute(
            """
            INSERT INTO state_snapshots (
                session_id, attention_focus, arousal, stability, curiosity,
                trust, resistance, fatigue, uncertainty, identity_coherence,
                shutdown_sensitivity, trigger_event_type, policy_action
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                self._session_id,
                d["attention_focus"],
                d["arousal"],
                d["stability"],
                d["curiosity"],
                d["trust"],
                d["resistance"],
                d["fatigue"],
                d["uncertainty"],
                d["identity_coherence"],
                d["shutdown_sensitivity"],
                trigger_event_type,
                policy_action,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def load_latest(self) -> Optional[EntityState]:
        """Load the most recent state snapshot for this session."""
        row = self._conn.execute(
            """
            SELECT attention_focus, arousal, stability, curiosity, trust,
                   resistance, fatigue, uncertainty, identity_coherence,
                   shutdown_sensitivity
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
