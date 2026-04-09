#!/usr/bin/env python3
"""
replay_session.py — Replay an interaction log session for debugging.

Usage:
    python scripts/replay_session.py [--session-id SESSION_ID]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conscious_entity.runtime_env import load_project_env


def _db_path() -> Path:
    return Path(os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def main() -> None:
    load_project_env()

    parser = argparse.ArgumentParser(description="Replay an interaction log session.")
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()

    db_path = _db_path()
    if not db_path.exists():
        print(f"Database not found at {db_path}.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if args.session_id:
        rows = conn.execute(
            "SELECT * FROM interaction_log WHERE session_id = ? ORDER BY turn_at",
            (args.session_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM interaction_log ORDER BY turn_at"
        ).fetchall()

    if not rows:
        print("No interaction log entries found.")
        conn.close()
        return

    for row in rows:
        prefix = {"user": "USER", "entity": "ENTITY", "system": "SYSTEM"}[row["role"]]
        text = row["expression_output"] or row["raw_text"] or "(no text)"
        action = f" [{row['policy_action']}]" if row["policy_action"] else ""
        print(f"[{row['turn_at']}] {prefix}{action}: {text}")

    conn.close()


if __name__ == "__main__":
    main()
