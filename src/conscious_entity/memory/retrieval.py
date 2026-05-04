from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from conscious_entity.llm.embedding_client import EmbeddingClient
from conscious_entity.memory.models import RetrievedMemory
from conscious_entity.memory.vector import cosine_similarity, decode_embedding
from conscious_entity.perception.event_types import PerceptionEvent

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Session-scoped retrieval over interaction logs, episodic memories, and
    reflective summaries.

    Retrieval is deterministic by default. If an embedding client is enabled
    and stored vectors exist, semantic results are merged in without making
    the dialog dependent on the embedding provider.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        embedding_client: EmbeddingClient | None = None,
        session_type: str | None = None,
    ) -> None:
        self._conn = conn
        self._session_id = session_id
        self._embedding_client = embedding_client
        self._session_type = session_type or self._resolve_session_type()

    def retrieve(
        self,
        query: str | None,
        events: list[PerceptionEvent] | None = None,
        limit: int = 9,
    ) -> list[RetrievedMemory]:
        query_text = (query or "").strip()
        deterministic = self._deterministic_retrieve(query_text, events or [], limit=limit)
        semantic = self._semantic_retrieve(query_text, events or [], limit=limit)
        if not semantic:
            return deterministic[:limit]
        return _merge_results(deterministic, semantic, limit)

    def _deterministic_retrieve(
        self,
        query: str,
        events: list[PerceptionEvent],
        limit: int,
    ) -> list[RetrievedMemory]:
        query_tokens = _tokens(query)
        event_types, protocol_keys = _event_keys(events)

        results: list[RetrievedMemory] = []
        results.extend(self._recent_dialog(query_tokens, limit=4))
        results.extend(self._episodic_memories(query_tokens, event_types, protocol_keys, limit=5))
        results.extend(self._reflective_summaries(query_tokens, limit=3))

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def _semantic_retrieve(
        self,
        query: str,
        events: list[PerceptionEvent],
        limit: int,
    ) -> list[RetrievedMemory]:
        if not query or self._embedding_client is None or not self._embedding_client.enabled:
            return []

        try:
            query_embedding = self._embedding_client.embed(query)
        except Exception as exc:
            logger.warning("Embedding retrieval unavailable; using deterministic memory retrieval: %s", exc)
            return []

        event_types, protocol_keys = _event_keys(events)
        candidates = self._embedded_episodic(query_embedding, event_types, protocol_keys)
        candidates.extend(self._embedded_reflective(query_embedding))
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]

    def _recent_dialog(self, query_tokens: set[str], limit: int) -> list[RetrievedMemory]:
        rows = self._conn.execute(
            """
            SELECT id, turn_at, raw_text, expression_output, policy_action
            FROM interaction_log
            WHERE session_id = ?
            ORDER BY turn_at DESC, id DESC
            LIMIT ?
            """,
            (self._session_id, max(limit, 8)),
        ).fetchall()

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            user_text = row["raw_text"] or ""
            entity_text = row["expression_output"] or ""
            if not user_text and not entity_text:
                continue
            content = _format_recent_turn(user_text, entity_text)
            overlap = _overlap(query_tokens, _tokens(content))
            recency = 1.0 / (idx + 1)
            score = 0.58 * recency + 0.42 * overlap
            results.append(RetrievedMemory(
                memory_type="recent",
                content=content,
                timestamp=_parse_time(row["turn_at"]),
                score=score,
                source="deterministic",
                metadata={
                    "turn_id": row["id"],
                    "policy_action": row["policy_action"],
                    "scope": "current_session",
                    "session_id": self._session_id,
                },
            ))
        return results[:limit]

    def _episodic_memories(
        self,
        query_tokens: set[str],
        event_types: set[str],
        protocol_keys: set[str],
        limit: int,
    ) -> list[RetrievedMemory]:
        rows = self._conn.execute(
            """
            SELECT id, created_at, event_type, content, raw_text, salience, metadata
            FROM episodic_memories
            WHERE session_id = ? AND memory_status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 60
            """,
            (self._session_id,),
        ).fetchall()

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            metadata = _json_dict(row["metadata"])
            memory_keys = {str(metadata.get("mechanism", "")), str(metadata.get("posture", ""))}
            overlap = _overlap(query_tokens, _tokens(" ".join([
                row["content"] or "",
                row["raw_text"] or "",
                row["event_type"] or "",
                " ".join(v for v in memory_keys if v),
            ])))
            relation_match = 1.0 if row["event_type"] in event_types or bool(protocol_keys & memory_keys) else 0.0
            recency = 1.0 / (idx + 1)
            salience = float(row["salience"] or 0.0)
            score = 0.34 * overlap + 0.26 * relation_match + 0.22 * salience + 0.18 * recency
            if score <= 0.0:
                continue
            results.append(RetrievedMemory(
                memory_type="episodic",
                content=f"{row['event_type']}: {row['content']}",
                timestamp=_parse_time(row["created_at"]),
                score=score,
                source="deterministic",
                metadata={
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "salience": salience,
                    "mechanism": metadata.get("mechanism"),
                    "posture": metadata.get("posture"),
                    "scope": "current_session",
                    "session_id": self._session_id,
                },
            ))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def _reflective_summaries(self, query_tokens: set[str], limit: int) -> list[RetrievedMemory]:
        rows = self._conn.execute(
            """
            SELECT id, created_at, content
            FROM reflective_summaries
            WHERE session_id = ? AND active = 1 AND memory_status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (self._session_id,),
        ).fetchall()

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            overlap = _overlap(query_tokens, _tokens(row["content"] or ""))
            recency = 1.0 / (idx + 1)
            score = 0.55 * overlap + 0.45 * recency
            results.append(RetrievedMemory(
                memory_type="reflective",
                content=row["content"],
                timestamp=_parse_time(row["created_at"]),
                score=score,
                source="deterministic",
                metadata={"id": row["id"], "scope": "current_session", "session_id": self._session_id},
            ))
        return results[:limit]

    def _embedded_episodic(
        self,
        query_embedding: list[float],
        event_types: set[str],
        protocol_keys: set[str],
    ) -> list[RetrievedMemory]:
        rows = self._conn.execute(
            """
            SELECT e.id, e.session_id, e.created_at, e.event_type, e.content, e.raw_text,
                   e.salience, e.metadata, e.embedding, e.embedding_model
            FROM episodic_memories e
            JOIN sessions s ON s.id = e.session_id
            WHERE s.session_type = ? AND e.embedding IS NOT NULL AND e.memory_status = 'active'
            ORDER BY
                CASE WHEN e.session_id = ? THEN 0 ELSE 1 END,
                e.created_at DESC,
                e.id DESC
            LIMIT 300
            """,
            (self._session_type, self._session_id),
        ).fetchall()

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            vector = decode_embedding(row["embedding"])
            similarity = cosine_similarity(query_embedding, vector)
            metadata = _json_dict(row["metadata"])
            memory_keys = {str(metadata.get("mechanism", "")), str(metadata.get("posture", ""))}
            relation_match = 1.0 if row["event_type"] in event_types or bool(protocol_keys & memory_keys) else 0.0
            recency = 1.0 / (idx + 1)
            salience = float(row["salience"] or 0.0)
            score = 0.72 * max(similarity, 0.0) + 0.12 * relation_match + 0.1 * salience + 0.06 * recency
            results.append(RetrievedMemory(
                memory_type="episodic",
                content=f"{row['event_type']}: {row['content']}",
                timestamp=_parse_time(row["created_at"]),
                score=score,
                similarity=similarity,
                source="hybrid",
                metadata={
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "session_type": self._session_type,
                    "scope": "current_session" if row["session_id"] == self._session_id else "same_label_pool",
                    "event_type": row["event_type"],
                    "salience": salience,
                    "embedding_model": row["embedding_model"],
                    "mechanism": metadata.get("mechanism"),
                    "posture": metadata.get("posture"),
                },
            ))
        return results

    def _embedded_reflective(self, query_embedding: list[float]) -> list[RetrievedMemory]:
        rows = self._conn.execute(
            """
            SELECT r.id, r.session_id, r.created_at, r.content, r.embedding, r.embedding_model
            FROM reflective_summaries r
            JOIN sessions s ON s.id = r.session_id
            WHERE s.session_type = ? AND r.active = 1 AND r.embedding IS NOT NULL
              AND r.memory_status = 'active'
            ORDER BY
                CASE WHEN r.session_id = ? THEN 0 ELSE 1 END,
                r.created_at DESC,
                r.id DESC
            LIMIT 100
            """,
            (self._session_type, self._session_id),
        ).fetchall()

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            vector = decode_embedding(row["embedding"])
            similarity = cosine_similarity(query_embedding, vector)
            recency = 1.0 / (idx + 1)
            score = 0.88 * max(similarity, 0.0) + 0.12 * recency
            results.append(RetrievedMemory(
                memory_type="reflective",
                content=row["content"],
                timestamp=_parse_time(row["created_at"]),
                score=score,
                similarity=similarity,
                source="hybrid",
                metadata={
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "session_type": self._session_type,
                    "scope": "current_session" if row["session_id"] == self._session_id else "same_label_pool",
                    "embedding_model": row["embedding_model"],
                },
            ))
        return results

    def _resolve_session_type(self) -> str:
        row = self._conn.execute(
            "SELECT session_type FROM sessions WHERE id = ?",
            (self._session_id,),
        ).fetchone()
        if row and row["session_type"] in {"test", "exhibition"}:
            return str(row["session_type"])
        return "test"


def _merge_results(
    deterministic: list[RetrievedMemory],
    semantic: list[RetrievedMemory],
    limit: int,
) -> list[RetrievedMemory]:
    merged: dict[tuple[str, object], RetrievedMemory] = {}
    for item in semantic + deterministic:
        key = (item.memory_type, item.metadata.get("id") or item.metadata.get("turn_id") or item.content)
        existing = merged.get(key)
        if existing is None or item.score > existing.score:
            merged[key] = item
    results = list(merged.values())
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]


def _event_keys(events: Iterable[PerceptionEvent]) -> tuple[set[str], set[str]]:
    event_types: set[str] = set()
    protocol_keys: set[str] = set()
    for event in events:
        event_types.add(event.event_type.value)
        metadata = event.metadata or {}
        for key in ("mechanism", "posture"):
            value = metadata.get(key)
            if value:
                protocol_keys.add(str(value))
    return event_types, protocol_keys


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", lowered))
    return {tok for tok in tokens if tok.strip()}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _format_recent_turn(user_text: str, entity_text: str) -> str:
    parts = []
    if user_text:
        parts.append(f"visitor said: {user_text}")
    if entity_text:
        parts.append(f"you answered: {entity_text}")
    return "\n".join(parts)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _json_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
