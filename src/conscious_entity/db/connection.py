from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign key enforcement."""
    conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
