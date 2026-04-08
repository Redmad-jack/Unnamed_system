from __future__ import annotations

import sqlite3

from conscious_entity.memory.models import ReflectiveSummary


class ReflectiveStore:
    def __init__(self, conn: sqlite3.Connection, session_id: str) -> None:
        self._conn = conn
        self._session_id = session_id

    def store(self, summary: ReflectiveSummary) -> int:
        """Insert a reflective summary. Returns the new row id."""
        cursor = self._conn.execute(
            """
            INSERT INTO reflective_summaries (
                session_id, content, source_event_ids, state_at_reflection, active
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                self._session_id,
                summary.content,
                summary.source_event_ids_json(),
                summary.state_json(),
                1 if summary.active else 0,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_all(self, active_only: bool = True) -> list[ReflectiveSummary]:
        """Return reflective summaries for this session, newest first."""
        if active_only:
            rows = self._conn.execute(
                """
                SELECT * FROM reflective_summaries
                WHERE session_id = ? AND active = 1
                ORDER BY created_at DESC, id DESC
                """,
                (self._session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM reflective_summaries
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (self._session_id,),
            ).fetchall()
        return [ReflectiveSummary.from_row(r) for r in rows]

    def mark_superseded(self, summary_id: int) -> None:
        """Mark a reflective summary as superseded (active=0)."""
        self._conn.execute(
            "UPDATE reflective_summaries SET active = 0 WHERE id = ?",
            (summary_id,),
        )
        self._conn.commit()
