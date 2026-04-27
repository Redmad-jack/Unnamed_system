"""
migrations.py — SQLite schema initialization and versioned migrations.
"""

from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    visitor_count   INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS state_snapshots (
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

CREATE INDEX IF NOT EXISTS idx_snapshots_session
    ON state_snapshots(session_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS shop_state_snapshots (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                 TEXT NOT NULL REFERENCES sessions(id),
    recorded_at                TEXT NOT NULL DEFAULT (datetime('now')),
    language                   TEXT NOT NULL,
    current_scene              TEXT NOT NULL,
    previous_scene             TEXT,
    order_status               TEXT NOT NULL,
    selected_soup              TEXT,
    has_complimented_appearance INTEGER NOT NULL DEFAULT 0,
    has_asked_item_origin      INTEGER NOT NULL DEFAULT 0,
    recent_turns               TEXT NOT NULL DEFAULT '[]',
    state_updates              TEXT,
    trigger_scene              TEXT,
    action                     TEXT,
    entity_state_snapshot_id   INTEGER REFERENCES state_snapshots(id)
);

CREATE INDEX IF NOT EXISTS idx_shop_snapshots_session
    ON shop_state_snapshots(session_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS interaction_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    turn_at           TEXT NOT NULL DEFAULT (datetime('now')),
    role              TEXT NOT NULL CHECK(role IN ('user', 'entity', 'system')),
    raw_text          TEXT,
    event_types       TEXT,
    policy_action     TEXT,
    expression_output TEXT,
    delay_ms          INTEGER,
    visual_mode       TEXT,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id)
);

CREATE INDEX IF NOT EXISTS idx_log_session
    ON interaction_log(session_id, turn_at DESC);

CREATE TABLE IF NOT EXISTS episodic_memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    event_type        TEXT NOT NULL,
    content           TEXT NOT NULL,
    raw_text          TEXT,
    salience          REAL NOT NULL,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id),
    embedding         BLOB,
    embedding_model   TEXT,
    reflected         INTEGER NOT NULL DEFAULT 0,
    reflection_id     INTEGER,
    metadata          TEXT
);

CREATE INDEX IF NOT EXISTS idx_episodic_session
    ON episodic_memories(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_reflected
    ON episodic_memories(reflected, created_at);

CREATE TABLE IF NOT EXISTS reflective_summaries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    content               TEXT NOT NULL,
    source_event_ids      TEXT NOT NULL,
    state_at_reflection   TEXT NOT NULL,
    embedding             BLOB,
    embedding_model       TEXT,
    active                INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_reflective_session
    ON reflective_summaries(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflective_active
    ON reflective_summaries(active, created_at DESC);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply the full schema to the given SQLite connection."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
