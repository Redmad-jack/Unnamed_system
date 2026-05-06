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


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply the full schema to a SQLite connection."""
    from conscious_entity.db.migrations import run_migrations
    run_migrations(conn)
