#!/usr/bin/env python3
"""
init_db.py — Bootstrap the SQLite database schema.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --db path/to/custom.db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.runtime_env import load_project_env


def main() -> None:
    load_project_env()

    parser = argparse.ArgumentParser(description="Initialize the entity database.")
    parser.add_argument(
        "--db",
        default=os.getenv("ENTITY_DB_PATH", "data/memory.db"),
        help="Path to the SQLite database file (default: data/memory.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path)
    try:
        run_migrations(conn)
        print(f"Database initialized at {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
