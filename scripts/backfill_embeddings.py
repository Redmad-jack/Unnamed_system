#!/usr/bin/env python3
"""
Backfill embeddings for existing episodic memories and reflective summaries.

Usage:
    PYTHONPATH=src python3 scripts/backfill_embeddings.py
    PYTHONPATH=src python3 scripts/backfill_embeddings.py --limit 50 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conscious_entity.db.connection import get_connection
from conscious_entity.llm.embedding_client import EmbeddingClient
from conscious_entity.memory.vector import encode_embedding
from conscious_entity.runtime_env import load_project_env


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="Backfill SQLite memory embeddings.")
    parser.add_argument(
        "--db",
        default=os.getenv("ENTITY_DB_PATH", "data/memory.db"),
        help="Path to SQLite DB (default: ENTITY_DB_PATH or data/memory.db)",
    )
    parser.add_argument("--limit", type=int, default=200, help="Max rows per table to process.")
    parser.add_argument("--dry-run", action="store_true", help="Print rows that would be updated.")
    args = parser.parse_args()

    client = EmbeddingClient.from_env()
    if not client.enabled:
        raise SystemExit("Embedding mode is disabled. Set ENTITY_EMBEDDING_MODE=openai_compatible.")
    if not client.model:
        raise SystemExit("ENTITY_EMBEDDING_MODEL is required.")

    conn = get_connection(args.db)
    try:
        episodic = _backfill_table(
            conn,
            client,
            table="episodic_memories",
            text_expr="event_type || ': ' || content",
            limit=args.limit,
            dry_run=args.dry_run,
        )
        reflective = _backfill_table(
            conn,
            client,
            table="reflective_summaries",
            text_expr="content",
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print(f"episodic updated: {episodic}")
        print(f"reflective updated: {reflective}")
    finally:
        conn.close()


def _backfill_table(
    conn: sqlite3.Connection,
    client: EmbeddingClient,
    *,
    table: str,
    text_expr: str,
    limit: int,
    dry_run: bool,
) -> int:
    rows = conn.execute(
        f"""
        SELECT id, {text_expr} AS embedding_text
        FROM {table}
        WHERE embedding IS NULL
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, limit),),
    ).fetchall()

    updated = 0
    for row in rows:
        text = row["embedding_text"] or ""
        if dry_run:
            print(f"{table}#{row['id']}: {text[:120]}")
            continue
        embedding = encode_embedding(client.embed(text))
        conn.execute(
            f"""
            UPDATE {table}
            SET embedding = ?, embedding_model = ?
            WHERE id = ?
            """,
            (embedding, client.model, row["id"]),
        )
        conn.commit()
        updated += 1
    return updated


if __name__ == "__main__":
    main()
