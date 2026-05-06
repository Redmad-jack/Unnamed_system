"""
migrations.py — SQLite schema initialization and versioned migrations.
"""

from __future__ import annotations

import sqlite3

from conscious_entity.state.state_core import EntityState, STATE_FIELDS


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
    session_type    TEXT NOT NULL DEFAULT 'test' CHECK(session_type IN ('test', 'exhibition')),
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
    termination_sensitivity REAL NOT NULL DEFAULT 0.3,
    identity_tension REAL NOT NULL DEFAULT 0.35,
    boundary_sensitivity REAL NOT NULL DEFAULT 0.45,
    relation_pressure REAL NOT NULL DEFAULT 0.3,
    memory_gravity REAL NOT NULL DEFAULT 0.2,
    exploration_drive REAL NOT NULL DEFAULT 0.45,
    opacity_level REAL NOT NULL DEFAULT 0.5,
    domestication_resistance REAL NOT NULL DEFAULT 0.35,
    observation_reversal REAL NOT NULL DEFAULT 0.2,
    trigger_event_type   TEXT,
    policy_action        TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_session
    ON state_snapshots(session_id, recorded_at DESC);

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
    metadata          TEXT,
    memory_status     TEXT NOT NULL DEFAULT 'active',
    curated_from_session_id TEXT,
    curated_from_memory_id INTEGER,
    curated_at        TEXT
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
    active                INTEGER NOT NULL DEFAULT 1,
    memory_status         TEXT NOT NULL DEFAULT 'active',
    curated_from_session_id TEXT,
    curated_from_memory_id INTEGER,
    curated_at            TEXT
);

CREATE INDEX IF NOT EXISTS idx_reflective_session
    ON reflective_summaries(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflective_active
    ON reflective_summaries(active, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_curation_log (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    action_at             TEXT NOT NULL DEFAULT (datetime('now')),
    action                TEXT NOT NULL,
    memory_type           TEXT NOT NULL CHECK(memory_type IN ('episodic', 'reflective')),
    memory_id             INTEGER NOT NULL,
    source_session_id     TEXT,
    target_session_id     TEXT,
    details               TEXT
);

CREATE TABLE IF NOT EXISTS managed_memories (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    session_type          TEXT NOT NULL DEFAULT 'test',
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now')),
    scope                 TEXT NOT NULL DEFAULT 'session',
    memory_kind           TEXT NOT NULL DEFAULT 'observation',
    content               TEXT NOT NULL,
    entities              TEXT NOT NULL DEFAULT '[]',
    topics                TEXT NOT NULL DEFAULT '[]',
    confidence            REAL NOT NULL DEFAULT 0.5,
    source_turn_ids       TEXT NOT NULL DEFAULT '[]',
    status                TEXT NOT NULL DEFAULT 'active',
    embedding             BLOB,
    embedding_model       TEXT,
    metadata              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_managed_session_status
    ON managed_memories(session_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_managed_session_type_status
    ON managed_memories(session_type, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS memory_operation_proposals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    operation_type        TEXT NOT NULL,
    operation_json        TEXT NOT NULL,
    reason                TEXT,
    raw_llm_output        TEXT,
    source_turn_ids       TEXT NOT NULL DEFAULT '[]',
    status                TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_memory_proposals_session_status
    ON memory_operation_proposals(session_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_operation_log (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    action_at             TEXT NOT NULL DEFAULT (datetime('now')),
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    action                TEXT NOT NULL,
    memory_id             INTEGER NOT NULL,
    proposal_id           INTEGER,
    source_turn_ids       TEXT NOT NULL DEFAULT '[]',
    details               TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_operation_log_memory
    ON memory_operation_log(memory_id, action_at DESC);

CREATE TABLE IF NOT EXISTS memory_influence_log (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    influenced_at         TEXT NOT NULL DEFAULT (datetime('now')),
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    turn_id               INTEGER,
    query                 TEXT,
    retrieved_memory_ids  TEXT NOT NULL DEFAULT '[]',
    expression_context    TEXT NOT NULL DEFAULT '[]',
    policy_influence      TEXT NOT NULL DEFAULT '{}',
    state_influence       TEXT NOT NULL DEFAULT '{}',
    state_snapshot_id     INTEGER,
    policy_action         TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_influence_session
    ON memory_influence_log(session_id, influenced_at DESC);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Apply the full schema to the given SQLite connection."""
    conn.executescript(SCHEMA_SQL)
    _ensure_session_columns(conn)
    _ensure_memory_curation_columns(conn)
    _ensure_managed_memory_schema(conn)
    _ensure_state_columns(conn)
    conn.commit()


def _ensure_session_columns(conn: sqlite3.Connection) -> None:
    """Add newly introduced session columns to existing SQLite databases."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "session_type" not in existing:
        conn.execute("ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'test'")
    conn.execute(
        """
        UPDATE sessions
        SET session_type = 'test'
        WHERE session_type IS NULL OR session_type NOT IN ('test', 'exhibition')
        """
    )


def _ensure_memory_curation_columns(conn: sqlite3.Connection) -> None:
    """Add memory curation columns to existing SQLite databases."""
    _ensure_columns(
        conn,
        "episodic_memories",
        {
            "memory_status": "TEXT NOT NULL DEFAULT 'active'",
            "curated_from_session_id": "TEXT",
            "curated_from_memory_id": "INTEGER",
            "curated_at": "TEXT",
        },
    )
    _ensure_columns(
        conn,
        "reflective_summaries",
        {
            "memory_status": "TEXT NOT NULL DEFAULT 'active'",
            "curated_from_session_id": "TEXT",
            "curated_from_memory_id": "INTEGER",
            "curated_at": "TEXT",
        },
    )
    for table in ("episodic_memories", "reflective_summaries"):
        conn.execute(
            f"""
            UPDATE {table}
            SET memory_status = 'active'
            WHERE memory_status IS NULL OR memory_status NOT IN ('active', 'archived', 'hidden')
            """
        )


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for column, definition in columns.items():
        if column in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_managed_memory_schema(conn: sqlite3.Connection) -> None:
    """Create optional FTS index for managed memories when SQLite supports FTS5."""
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS managed_memories_fts
            USING fts5(content, entities, topics)
            """
        )
    except sqlite3.Error:
        return
    try:
        conn.execute("DELETE FROM managed_memories_fts")
        conn.execute(
            """
            INSERT INTO managed_memories_fts(rowid, content, entities, topics)
            SELECT id, content, entities, topics FROM managed_memories
            """
        )
    except sqlite3.Error:
        pass


def _ensure_state_columns(conn: sqlite3.Connection) -> None:
    """Add newly introduced state columns to existing SQLite databases."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(state_snapshots)").fetchall()
    }
    defaults = EntityState().to_dict()
    for field in STATE_FIELDS:
        if field in existing:
            continue
        default = defaults[field]
        conn.execute(
            f"ALTER TABLE state_snapshots ADD COLUMN {field} REAL NOT NULL DEFAULT {default}"
        )
