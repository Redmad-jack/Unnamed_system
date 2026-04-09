#!/usr/bin/env python3
"""
monitor.py — Real-time TUI dashboard for the Conscious Entity system.

Polls SQLite every 2 seconds. Read-only — does not affect the running system.

Usage:
    python scripts/monitor.py [--db PATH]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
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

_ROLE_COLOR = {"user": "cyan", "entity": "magenta", "system": "yellow"}


def _db_path(override: str | None) -> Path:
    return Path(override or os.getenv("ENTITY_DB_PATH", "data/memory.db"))


def _build_state_panel(conn: sqlite3.Connection) -> Panel:
    row = conn.execute(
        "SELECT * FROM state_snapshots ORDER BY recorded_at DESC LIMIT 1"
    ).fetchone()

    table = Table(box=None, show_header=False, padding=(0, 0), expand=True)
    table.add_column("var", style="dim", width=26)
    table.add_column("bar", ratio=1)
    table.add_column("val", width=6, justify="right")

    if row is None:
        table.add_row("[dim]no snapshots yet[/dim]", "", "")
    else:
        for key in STATE_KEYS:
            val = float(row[key])
            filled = int(val * 20)
            bar = "[green]" + "█" * filled + "[/green]" + "[dim]" + "░" * (20 - filled) + "[/dim]"
            table.add_row(key, bar, f"{val:.3f}")

    ts = row["recorded_at"] if row else "—"
    return Panel(table, title=f"[bold]Entity State[/bold]  [dim]{ts}[/dim]", border_style="green")


def _build_dialog_panel(conn: sqlite3.Connection) -> Panel:
    rows = conn.execute(
        "SELECT role, raw_text, turn_at FROM interaction_log "
        "WHERE role IN ('user', 'entity') ORDER BY turn_at DESC LIMIT 10"
    ).fetchall()
    rows = list(reversed(rows))

    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("role", width=8, no_wrap=True)
    table.add_column("text", ratio=1)

    if not rows:
        table.add_row("[dim]—[/dim]", "[dim]no interactions yet[/dim]")
    else:
        for r in rows:
            color = _ROLE_COLOR.get(r["role"], "white")
            text = (r["raw_text"] or "").replace("\n", " ")
            if len(text) > 80:
                text = text[:77] + "..."
            table.add_row(f"[{color}]{r['role']}[/{color}]", text)

    return Panel(table, title="[bold]Recent Dialog[/bold]", border_style="cyan")


def _build_policy_panel(conn: sqlite3.Connection) -> Panel:
    rows = conn.execute(
        "SELECT turn_at, policy_action, event_types FROM interaction_log "
        "WHERE role = 'entity' AND policy_action IS NOT NULL "
        "ORDER BY turn_at DESC LIMIT 5"
    ).fetchall()
    rows = list(reversed(rows))

    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("time", width=20, style="dim")
    table.add_column("action", width=22, style="yellow")
    table.add_column("events", ratio=1, style="dim")

    if not rows:
        table.add_row("—", "[dim]no decisions yet[/dim]", "")
    else:
        for r in rows:
            table.add_row(r["turn_at"], r["policy_action"] or "—", r["event_types"] or "")

    return Panel(table, title="[bold]Recent Policy Decisions[/bold]", border_style="yellow")


def _build_memory_panel(conn: sqlite3.Connection) -> Panel:
    ep_count = conn.execute("SELECT COUNT(*) FROM episodic_memories").fetchone()[0]
    ref_count = conn.execute(
        "SELECT COUNT(*) FROM reflective_summaries WHERE active = 1"
    ).fetchone()[0]
    unreflected = conn.execute(
        "SELECT COUNT(*) FROM episodic_memories WHERE reflected = 0"
    ).fetchone()[0]

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("key", style="dim", width=22)
    table.add_column("val", style="bold")
    table.add_row("episodic memories", str(ep_count))
    table.add_row("active reflections", str(ref_count))
    table.add_row("unreflected events", str(unreflected))

    return Panel(table, title="[bold]Memory System[/bold]", border_style="blue")


def _render(conn: sqlite3.Connection) -> Layout:
    conn.row_factory = sqlite3.Row

    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=3),
        Layout(name="bottom", ratio=2),
    )
    layout["top"].split_row(
        Layout(_build_state_panel(conn), name="state", ratio=2),
        Layout(_build_dialog_panel(conn), name="dialog", ratio=3),
    )
    layout["bottom"].split_row(
        Layout(_build_policy_panel(conn), name="policy", ratio=3),
        Layout(_build_memory_panel(conn), name="memory", ratio=2),
    )
    return layout


def main() -> None:
    parser = argparse.ArgumentParser(description="Conscious Entity real-time TUI monitor")
    parser.add_argument("--db", help="Path to memory.db (overrides ENTITY_DB_PATH)")
    args = parser.parse_args()

    load_project_env()
    db = _db_path(args.db)

    if not db.exists():
        Console().print(f"[red]Database not found at {db}. Run scripts/init_db.py first.[/red]")
        sys.exit(1)

    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    console = Console()
    console.print(f"[dim]Watching {db} — Ctrl+C to exit[/dim]\n")

    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    live.update(_render(conn))
                except sqlite3.OperationalError:
                    pass
                time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        console.print("[dim]Monitor stopped.[/dim]")


if __name__ == "__main__":
    main()
