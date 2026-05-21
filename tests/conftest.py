"""
conftest.py — shared pytest fixtures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def in_memory_db():
    """Provide a fresh in-memory SQLite connection with migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def config_dir() -> Path:
    """Return the project config directory."""
    return Path(__file__).parent.parent / "config"


@pytest.fixture(autouse=True)
def isolated_latency_logs(tmp_path):
    """Keep developer latency JSONL out of real project data during tests."""
    from conscious_entity.llm.stats_tracker import reset_tracker_for_tests
    from conscious_entity.telemetry.latency import reset_latency_tracker_for_tests

    storage_dir = tmp_path / "latency_logs"
    reset_latency_tracker_for_tests(storage_dir)
    reset_tracker_for_tests(storage_dir)
    yield
    reset_latency_tracker_for_tests()
    reset_tracker_for_tests()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply the full schema to a SQLite connection."""
    from conscious_entity.db.migrations import run_migrations
    run_migrations(conn)
