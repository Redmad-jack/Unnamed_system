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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from conscious_entity.runtime_env import load_project_env

STATE_KEYS = [
    "attention_focus",
    "arousal",
    "stability",
    "curiosity",
    "trust",
    "resistance",
    "fatigue",
    "uncertainty",
    "identity_coherence",
    "shutdown_sensitivity",
]

console = Console()


def _db_path() -> Path:
    return Path(os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def main() -> None:
    load_project_env()

    db_path = _db_path()
    if not db_path.exists():
        console.print(f"[red]Database not found at {db_path}. Run scripts/init_db.py first.[/red]")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # --- EntityState panel ---
    row = conn.execute(
        "SELECT * FROM state_snapshots ORDER BY recorded_at DESC LIMIT 1"
    ).fetchone()

    state_table = Table(box=None, show_header=False, padding=(0, 0), expand=True)
    state_table.add_column("var", style="dim", width=26)
    state_table.add_column("bar", ratio=1)
    state_table.add_column("val", width=6, justify="right")

    if row is None:
        console.print("[yellow]No state snapshots found.[/yellow]")
    else:
        for key in STATE_KEYS:
            val = float(row[key])
            filled = int(val * 20)
            bar = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (20 - filled) + "[/dim]"
            state_table.add_row(key, bar, f"{val:.3f}")

        trigger = row["trigger_event_type"] or "—"
        action = row["policy_action"] or "—"
        console.print(
            Panel(
                state_table,
                title=f"[bold]EntityState[/bold]  [dim]{row['recorded_at']}[/dim]  "
                      f"[dim]trigger=[/dim][cyan]{trigger}[/cyan]  "
                      f"[dim]action=[/dim][yellow]{action}[/yellow]",
                border_style="green",
            )
        )

    # --- Recent entity turns panel ---
    rows = conn.execute(
        "SELECT turn_at, policy_action, event_types, expression_output "
        "FROM interaction_log "
        "WHERE role = 'entity' ORDER BY turn_at DESC LIMIT 5"
    ).fetchall()

    turns_table = Table(box=box.SIMPLE_HEAVY, show_header=True, padding=(0, 1), expand=True)
    turns_table.add_column("Time", style="dim", width=20)
    turns_table.add_column("Action", style="yellow", width=22)
    turns_table.add_column("Events", style="dim", width=30)
    turns_table.add_column("Response (truncated)", ratio=1)

    if not rows:
        turns_table.add_row("—", "[dim]no entity turns yet[/dim]", "", "")
    else:
        for r in rows:
            resp = (r["expression_output"] or "")
            if len(resp) > 60:
                resp = resp[:57] + "..."
            turns_table.add_row(
                r["turn_at"],
                r["policy_action"] or "—",
                r["event_types"] or "—",
                f"[italic]{resp}[/italic]",
            )

    console.print(Panel(turns_table, title="[bold]Last 5 Entity Turns[/bold]", border_style="blue"))

    conn.close()


if __name__ == "__main__":
    main()
