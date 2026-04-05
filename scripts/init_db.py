#!/usr/bin/env python3
"""
init_db.py — Bootstrap the SQLite database schema.

Usage:
    python scripts/init_db.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conscious_entity.db.migrations import run_migrations

DB_PATH = Path(os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        run_migrations(conn)
        print(f"Database initialized at {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
