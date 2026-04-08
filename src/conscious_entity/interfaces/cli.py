"""
cli.py — terminal interface for the Conscious Entity System (v0.1 MVP).

Usage:
    python -m conscious_entity.interfaces.cli
    python -m conscious_entity.interfaces.cli --debug
    python -m conscious_entity.interfaces.cli --session my-session-id
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent  # project root


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _find_config_dir() -> Path:
    candidate = _PROJECT_ROOT / "config"
    if not candidate.exists():
        candidate = Path(os.getenv("ENTITY_CONFIG_DIR", "config"))
    return candidate


def _find_prompts_dir() -> Path:
    candidate = _PROJECT_ROOT / "prompts"
    if not candidate.exists():
        candidate = Path(os.getenv("ENTITY_PROMPTS_DIR", "prompts"))
    return candidate


def _find_db_path() -> Path:
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "memory.db"


def _ensure_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id) VALUES (?)",
        (session_id,),
    )
    conn.commit()


def _print_state(state) -> None:
    d = state.to_dict()
    print("\n  [state]", file=sys.stderr)
    for k, v in d.items():
        bar = "█" * int(v * 20)
        print(f"    {k:<24} {v:.2f}  {bar}", file=sys.stderr)
    print(file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Conscious Entity — CLI interface")
    parser.add_argument("--debug", action="store_true", help="Show debug logs and state after each turn")
    parser.add_argument("--session", default=None, help="Session ID (default: new UUID)")
    args = parser.parse_args()

    _setup_logging(args.debug)

    config_dir = _find_config_dir()
    prompts_dir = _find_prompts_dir()
    db_path = _find_db_path()

    # --- Load config ---
    from conscious_entity.core.config_loader import load_all_configs
    try:
        config = load_all_configs(config_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Database ---
    from conscious_entity.db.connection import get_connection
    from conscious_entity.db.migrations import run_migrations
    conn = get_connection(db_path)
    run_migrations(conn)

    session_id = args.session or str(uuid.uuid4())
    _ensure_session(conn, session_id)

    # --- Build loop ---
    from conscious_entity.core.loop import InteractionLoop
    from conscious_entity.perception.event_types import EventType

    loop = InteractionLoop(
        conn=conn,
        session_id=session_id,
        config=config,
        prompts_dir=prompts_dir,
    )

    # System event: entity becomes aware of a presence
    loop.handle_system_event(EventType.USER_ENTERED)

    designation = config["entity_profile"]["identity"].get("designation", "Entity")
    print(f"\n{designation}  [session: {session_id[:8]}]")
    print("Type your message. Press Ctrl+C or enter empty line to exit.\n")

    try:
        while True:
            try:
                raw = input("> ").strip()
            except EOFError:
                break

            if not raw:
                break

            output = loop.run_turn(raw)

            if output.text:
                print(f"\n{designation}: {output.text}\n")
            else:
                print(f"\n{designation}: ...\n")  # silent mode placeholder

            if args.debug:
                _print_state(loop.current_state)

    except KeyboardInterrupt:
        pass

    loop.handle_system_event(EventType.USER_LEFT)
    print(f"\n[session {session_id[:8]} ended]", file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    main()
