#!/usr/bin/env python3
"""
inspect_state.py — Print the current entity state and recent policy decisions.

Usage:
    python scripts/inspect_state.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DB_PATH = Path(os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run scripts/init_db.py first.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Latest state snapshot
    row = conn.execute(
        "SELECT * FROM state_snapshots ORDER BY recorded_at DESC LIMIT 1"
    ).fetchone()

    if row is None:
        print("No state snapshots found.")
    else:
        print(f"\nEntityState ({row['recorded_at']}):")
        for key in [
            "attention_focus", "arousal", "stability", "curiosity", "trust",
            "resistance", "fatigue", "uncertainty", "identity_coherence",
            "shutdown_sensitivity",
        ]:
            print(f"  {key:<24} {row[key]:.3f}")

    # Recent policy decisions
    rows = conn.execute(
        "SELECT turn_at, policy_action, event_types FROM interaction_log "
        "WHERE role = 'entity' ORDER BY turn_at DESC LIMIT 5"
    ).fetchall()

    print("\nLast 5 entity turns:")
    for r in rows:
        print(f"  [{r['turn_at']}] action={r['policy_action']}  events={r['event_types']}")

    conn.close()


if __name__ == "__main__":
    main()
