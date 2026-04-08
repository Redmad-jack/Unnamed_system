from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from conscious_entity.memory.models import EpisodicMemory


class EpisodicStore:
    def __init__(self, conn: sqlite3.Connection, session_id: str) -> None:
        self._conn = conn
        self._session_id = session_id

    def store(self, memory: EpisodicMemory) -> int:
        """Insert an episodic memory. Returns the new row id."""
        cursor = self._conn.execute(
            """
            INSERT INTO episodic_memories (
                session_id, event_type, content, raw_text,
                salience, state_snapshot_id, reflected, reflection_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._session_id,
                memory.event_type,
                memory.content,
                memory.raw_text,
                memory.salience,
                memory.state_snapshot_id,
                1 if memory.reflected else 0,
                memory.reflection_id,
                memory.metadata_json(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_recent(self, limit: int = 20) -> list[EpisodicMemory]:
        """Return the most recent episodes for this session, newest first."""
        rows = self._conn.execute(
            """
            SELECT * FROM episodic_memories
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (self._session_id, limit),
        ).fetchall()
        return [EpisodicMemory.from_row(r) for r in rows]

    def get_unreflected(self) -> list[EpisodicMemory]:
        """Return all episodes not yet reflected, oldest first."""
        rows = self._conn.execute(
            """
            SELECT * FROM episodic_memories
            WHERE session_id = ? AND reflected = 0
            ORDER BY created_at ASC, id ASC
            """,
            (self._session_id,),
        ).fetchall()
        return [EpisodicMemory.from_row(r) for r in rows]

    def mark_reflected(self, event_id: int, reflection_id: int) -> None:
        """Mark an episodic memory as reflected and record its reflection id."""
        self._conn.execute(
            """
            UPDATE episodic_memories
            SET reflected = 1, reflection_id = ?
            WHERE id = ?
            """,
            (reflection_id, event_id),
        )
        self._conn.commit()
