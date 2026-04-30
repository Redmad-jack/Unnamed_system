from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meal_schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meal_participants (
    id            TEXT PRIMARY KEY,
    public_code   TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    notes         TEXT,
    safety_flags  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_meal_participants_status
    ON meal_participants(status, created_at DESC);

CREATE TABLE IF NOT EXISTS meal_question_draws (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT NOT NULL REFERENCES meal_participants(id) ON DELETE CASCADE,
    module_id      TEXT NOT NULL,
    question_id    TEXT NOT NULL,
    question_text  TEXT NOT NULL,
    options_json   TEXT NOT NULL,
    drawn_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(participant_id, module_id)
);

CREATE INDEX IF NOT EXISTS idx_meal_draws_participant
    ON meal_question_draws(participant_id, drawn_at);

CREATE TABLE IF NOT EXISTS meal_answers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT NOT NULL REFERENCES meal_participants(id) ON DELETE CASCADE,
    question_id    TEXT NOT NULL,
    option_id      TEXT NOT NULL,
    answered_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(participant_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_meal_answers_participant
    ON meal_answers(participant_id, answered_at);

CREATE TABLE IF NOT EXISTS meal_observation_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT NOT NULL REFERENCES meal_participants(id) ON DELETE CASCADE,
    event_type     TEXT NOT NULL,
    confidence     REAL NOT NULL DEFAULT 1.0,
    duration_ms    INTEGER,
    metadata       TEXT NOT NULL DEFAULT '{}',
    observed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_meal_observations_participant
    ON meal_observation_events(participant_id, observed_at);

CREATE TABLE IF NOT EXISTS meal_assignments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id      TEXT NOT NULL UNIQUE REFERENCES meal_participants(id) ON DELETE CASCADE,
    food_code           TEXT NOT NULL,
    food_label          TEXT NOT NULL,
    final_food_code     TEXT NOT NULL,
    final_food_label    TEXT NOT NULL,
    ai_trace_score      REAL NOT NULL,
    relational_score    REAL NOT NULL,
    rationale_json      TEXT NOT NULL,
    override_reason     TEXT,
    assigned_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_meal_assignments_food
    ON meal_assignments(final_food_code, assigned_at DESC);

CREATE TABLE IF NOT EXISTS meal_staff_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id  INTEGER NOT NULL UNIQUE REFERENCES meal_assignments(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL REFERENCES meal_participants(id) ON DELETE CASCADE,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    staff_notes    TEXT
);

CREATE INDEX IF NOT EXISTS idx_meal_staff_queue_status
    ON meal_staff_queue(status, created_at);

INSERT OR IGNORE INTO meal_schema_version(version) VALUES (1);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
