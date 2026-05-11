from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue

from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations


def test_connection_can_be_shared_across_threads_when_opted_in(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    conn = get_connection(db_path, check_same_thread=False)
    conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()

    results: Queue[object] = Queue()

    def worker() -> None:
        try:
            conn.execute("INSERT INTO sample (value) VALUES (?)", ("thread-ok",))
            conn.commit()
            row = conn.execute("SELECT value FROM sample LIMIT 1").fetchone()
            results.put(row["value"] if row is not None else None)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            results.put(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    result = results.get_nowait()
    assert result == "thread-ok"
    conn.close()


def test_migrations_add_visitor_columns_before_indexes_on_existing_db(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    conn = get_connection(db_path)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            session_type TEXT NOT NULL DEFAULT 'test',
            visitor_count INTEGER DEFAULT 0,
            notes TEXT
        );
        CREATE TABLE interaction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            turn_at TEXT NOT NULL DEFAULT (datetime('now')),
            role TEXT NOT NULL,
            raw_text TEXT,
            event_types TEXT,
            policy_action TEXT,
            expression_output TEXT,
            delay_ms INTEGER,
            visual_mode TEXT,
            state_snapshot_id INTEGER
        );
        """
    )
    conn.commit()

    run_migrations(conn)

    session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
    log_columns = {row["name"] for row in conn.execute("PRAGMA table_info(interaction_log)")}
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(interaction_log)")}
    assert "visitor_id" in session_columns
    assert "visitor_id" in log_columns
    assert "idx_log_visitor" in indexes
    conn.close()
