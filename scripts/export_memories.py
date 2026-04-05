#!/usr/bin/env python3
"""
export_memories.py — Export all memory tables to a JSON file.

Usage:
    python scripts/export_memories.py [--output data/export.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DB_PATH = Path(os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export memory database to JSON.")
    parser.add_argument("--output", default="data/export.json")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run scripts/init_db.py first.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    export = {
        "interaction_log": [
            row_to_dict(r) for r in conn.execute("SELECT * FROM interaction_log ORDER BY turn_at")
        ],
        "episodic_memories": [
            row_to_dict(r) for r in conn.execute(
                "SELECT id, session_id, created_at, event_type, content, raw_text, "
                "salience, reflected, metadata FROM episodic_memories ORDER BY created_at"
            )
        ],
        "reflective_summaries": [
            row_to_dict(r) for r in conn.execute(
                "SELECT id, session_id, created_at, content, source_event_ids, "
                "state_at_reflection, active FROM reflective_summaries ORDER BY created_at"
            )
        ],
    }

    conn.close()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"Exported to {output_path}")
    print(f"  interaction_log:      {len(export['interaction_log'])} rows")
    print(f"  episodic_memories:    {len(export['episodic_memories'])} rows")
    print(f"  reflective_summaries: {len(export['reflective_summaries'])} rows")


if __name__ == "__main__":
    main()
