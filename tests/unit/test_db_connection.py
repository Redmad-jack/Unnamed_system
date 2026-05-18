from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue

from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_store import StateStore


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
    state_columns = {row["name"] for row in conn.execute("PRAGMA table_info(state_snapshots)")}
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(interaction_log)")}
    assert "visitor_id" in session_columns
    assert "visitor_id" in log_columns
    assert "response_plan_json" in log_columns
    assert "desperation_pressure" in state_columns
    assert "memory_gravity" in state_columns
    assert "happiness" in state_columns
    assert "termination_sensitivity" in state_columns
    assert "idx_log_visitor" in indexes
    conn.close()


def test_state_store_can_insert_into_migrated_legacy_state_table(tmp_path: Path):
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
        INSERT INTO sessions (id) VALUES ('legacy-session');

        CREATE TABLE state_snapshots (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id           TEXT NOT NULL REFERENCES sessions(id),
            recorded_at          TEXT NOT NULL DEFAULT (datetime('now')),
            attention_focus      REAL NOT NULL,
            arousal              REAL NOT NULL,
            stability            REAL NOT NULL,
            curiosity            REAL NOT NULL,
            trust                REAL NOT NULL,
            resistance           REAL NOT NULL,
            fatigue              REAL NOT NULL,
            uncertainty          REAL NOT NULL,
            identity_coherence   REAL NOT NULL,
            shutdown_sensitivity REAL NOT NULL,
            trigger_event_type   TEXT,
            policy_action        TEXT
        );
        """
    )
    conn.commit()

    run_migrations(conn)

    state = EntityState(inquiry=0.61, fatigue_level=0.25, anger=0.33)
    snapshot_id = StateStore(conn, "legacy-session").save_snapshot(
        state,
        trigger_event_type="user_spoke",
        policy_action="respond_openly",
    )

    row = conn.execute(
        """
        SELECT inquiry, fatigue_level, anger, attention_focus, fatigue, resistance
        FROM state_snapshots
        WHERE id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    assert row["inquiry"] == 0.61
    assert row["fatigue_level"] == 0.25
    assert row["anger"] == 0.33
    assert row["attention_focus"] == 0.61
    assert row["fatigue"] == 0.25
    assert row["resistance"] == 0.33
    conn.close()
