from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.llm.embedding_client import EmbeddingClient
from conscious_entity.memory.models import MemoryOperationProposal, RetrievedMemory
from conscious_entity.memory.vector import cosine_similarity, decode_embedding, encode_embedding
from conscious_entity.telemetry.latency import turn_step

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {"active"}
_RESTORABLE_STATUSES = {"archived", "hidden"}
_VALID_STATUSES = {"active", "superseded", "archived", "hidden"}
_VALID_OPERATIONS = {"add", "update", "supersede", "archive", "restore"}


class MemoryProvider(Protocol):
    auto_commit: bool

    def propose(self, messages: list[dict], context: dict[str, Any]) -> list[MemoryOperationProposal]:
        ...

    def commit(
        self,
        proposal_ids: Iterable[int] | None = None,
        operations: Iterable[MemoryOperationProposal | dict] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 9,
        explain: bool = True,
    ) -> list[RetrievedMemory]:
        ...

    def preview_influence(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def update(self, memory_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        ...

    def archive(self, memory_id: int) -> dict[str, Any]:
        ...

    def restore(self, memory_id: int) -> dict[str, Any]:
        ...

    def get_all(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    def explain(self, memory_id: int) -> dict[str, Any]:
        ...

    def log_influence(
        self,
        turn_id: int | None,
        query: str,
        influence: dict[str, Any],
        state_snapshot_id: int | None = None,
        policy_action: str | None = None,
    ) -> None:
        ...


@dataclass(frozen=True)
class MemoryProviderConfig:
    backend: str = "local"
    auto_commit: bool = True
    inference_enabled: bool = True
    policy_influence_enabled: bool = True
    state_influence_enabled: bool = True

    @classmethod
    def from_env(cls) -> MemoryProviderConfig:
        return cls(
            backend=os.getenv("ENTITY_MEMORY_BACKEND", "local").strip().lower() or "local",
            auto_commit=_env_bool("ENTITY_MEMORY_AUTO_COMMIT", True),
            inference_enabled=_env_bool("ENTITY_MEMORY_INFERENCE", True),
            policy_influence_enabled=_env_bool("ENTITY_MEMORY_POLICY_INFLUENCE", True),
            state_influence_enabled=_env_bool("ENTITY_MEMORY_STATE_INFLUENCE", True),
        )


class LocalManagedMemoryProvider:
    def __init__(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        llm_client: ClaudeClient | None = None,
        embedding_client: EmbeddingClient | None = None,
        prompts_dir: Path | None = None,
        config: MemoryProviderConfig | None = None,
    ) -> None:
        self._conn = conn
        self._session_id = session_id
        self._llm_client = llm_client
        self._embedding_client = embedding_client
        self._prompts_dir = prompts_dir
        self._config = config or MemoryProviderConfig.from_env()
        self.auto_commit = self._config.auto_commit
        self._session_type = self._resolve_session_type()

    def propose(self, messages: list[dict], context: dict[str, Any]) -> list[MemoryOperationProposal]:
        if not self._config.inference_enabled:
            return []

        source_turn_ids = _source_turn_ids(context)
        raw_output = self._proposal_llm_output(messages, context)
        proposals = _parse_proposals(raw_output, source_turn_ids)
        if not proposals:
            proposals = _fallback_proposals(messages, source_turn_ids)

        stored: list[MemoryOperationProposal] = []
        for proposal in proposals:
            proposal.session_id = self._session_id
            proposal.raw_llm_output = raw_output
            if proposal.operation not in _VALID_OPERATIONS:
                continue
            cursor = self._conn.execute(
                """
                INSERT INTO memory_operation_proposals (
                    session_id, operation_type, operation_json, reason,
                    raw_llm_output, source_turn_ids, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    self._session_id,
                    proposal.operation,
                    proposal.operation_json(),
                    proposal.reason,
                    raw_output,
                    json.dumps(proposal.source_turn_ids),
                ),
            )
            proposal.id = int(cursor.lastrowid)
            row = self._conn.execute(
                "SELECT created_at FROM memory_operation_proposals WHERE id = ?",
                (proposal.id,),
            ).fetchone()
            if row:
                proposal.created_at = _parse_time(row["created_at"])
            stored.append(proposal)
        self._conn.commit()
        return stored

    def commit(
        self,
        proposal_ids: Iterable[int] | None = None,
        operations: Iterable[MemoryOperationProposal | dict] | None = None,
    ) -> list[dict[str, Any]]:
        proposals: list[MemoryOperationProposal] = []
        if proposal_ids is not None:
            ids = [int(value) for value in proposal_ids]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = self._conn.execute(
                    f"""
                    SELECT * FROM memory_operation_proposals
                    WHERE id IN ({placeholders}) AND status = 'pending'
                    ORDER BY id
                    """,
                    ids,
                ).fetchall()
                proposals.extend(MemoryOperationProposal.from_row(row) for row in rows)

        if operations is not None:
            proposals.extend(_coerce_operation(item) for item in operations)

        committed: list[dict[str, Any]] = []
        for proposal in proposals:
            result = self._commit_one(proposal)
            if result:
                committed.append(result)
                if proposal.id is not None:
                    self._conn.execute(
                        "UPDATE memory_operation_proposals SET status = 'committed' WHERE id = ?",
                        (proposal.id,),
                    )
        self._conn.commit()
        return committed

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 9,
        explain: bool = True,
    ) -> list[RetrievedMemory]:
        filters = filters or {}
        limit = max(1, min(int(limit), 50))
        query_tokens = _tokens(query)
        rows = self._candidate_rows(query, filters, limit=max(limit * 8, 30))
        query_embedding = self._query_embedding(query)

        results: list[RetrievedMemory] = []
        for idx, row in enumerate(rows):
            entities = _json_list(row["entities"])
            topics = _json_list(row["topics"])
            haystack = " ".join([row["content"] or "", " ".join(entities), " ".join(topics)])
            overlap = _overlap(query_tokens, _tokens(haystack))
            recency = 1.0 / (idx + 1)
            confidence = float(row["confidence"] or 0.5)
            similarity = None
            semantic = 0.0
            if query_embedding and row["embedding"]:
                similarity = cosine_similarity(query_embedding, decode_embedding(row["embedding"]))
                semantic = max(similarity, 0.0)
            score = 0.42 * overlap + 0.28 * semantic + 0.18 * confidence + 0.12 * recency
            if score <= 0.0 and query_tokens:
                continue
            explanation = {
                "overlap": round(overlap, 4),
                "semantic": round(semantic, 4),
                "confidence": round(confidence, 4),
                "recency": round(recency, 4),
            } if explain else {}
            results.append(RetrievedMemory(
                memory_type="managed",
                content=row["content"],
                timestamp=_parse_time(row["created_at"]),
                score=score,
                similarity=similarity,
                source="managed",
                metadata={
                    "id": row["id"],
                    "status": row["status"],
                    "scope": row["scope"],
                    "session_id": row["session_id"],
                    "session_type": row["session_type"],
                    "memory_kind": row["memory_kind"],
                    "source_turn_ids": _json_int_list(row["source_turn_ids"]),
                    "entities": entities,
                    "topics": topics,
                    "explanation": explanation,
                },
            ))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def preview_influence(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        with turn_step("managed_memory.search_preview"):
            results = self.search(query, context.get("filters") if isinstance(context.get("filters"), dict) else None)
        expression_context = [item.to_public_dict() for item in results[:5]]
        policy_influence = {
            "enabled": self._config.policy_influence_enabled,
            "suggested_action": "retrieve_selective_memory" if results and self._config.policy_influence_enabled else None,
            "reason": "committed managed memories matched the current query" if results else "",
        }
        gravity_delta = min(0.12, 0.03 * len(results)) if self._config.state_influence_enabled else 0.0
        state_influence = {
            "enabled": self._config.state_influence_enabled,
            "deltas": {"memory_gravity": gravity_delta} if gravity_delta else {},
            "reason": "retrieved managed memories increase memory pull" if gravity_delta else "",
        }
        return {
            "query": query,
            "results": expression_context,
            "expression_context": expression_context,
            "policy_influence": policy_influence,
            "state_influence": state_influence,
            "explanation": {
                "writes": False,
                "committed_memory_count": len(results),
            },
        }

    def update(self, memory_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        proposal = MemoryOperationProposal(operation="update", memory_id=memory_id, patch=patch, reason="manual update")
        return self.commit(operations=[proposal])[0]

    def archive(self, memory_id: int) -> dict[str, Any]:
        proposal = MemoryOperationProposal(operation="archive", memory_id=memory_id, reason="manual archive")
        return self.commit(operations=[proposal])[0]

    def restore(self, memory_id: int) -> dict[str, Any]:
        proposal = MemoryOperationProposal(operation="restore", memory_id=memory_id, reason="manual restore")
        return self.commit(operations=[proposal])[0]

    def get_all(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        where = ["1 = 1"]
        params: list[Any] = []
        status = filters.get("status", "active")
        if status != "all":
            where.append("status = ?")
            params.append(status)
        session_type = filters.get("session_type")
        if session_type:
            where.append("session_type = ?")
            params.append(str(session_type))
        query = str(filters.get("q", "") or "").strip()
        if query:
            where.append("(content LIKE ? OR entities LIKE ? OR topics LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])
        limit = max(1, min(int(filters.get("limit", 100)), 500))
        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT * FROM managed_memories
            WHERE {" AND ".join(where)}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [_memory_row_to_public(row) for row in rows]

    def explain(self, memory_id: int) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM managed_memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(f"managed memory not found: {memory_id}")
        operations = self._conn.execute(
            """
            SELECT * FROM memory_operation_log
            WHERE memory_id = ?
            ORDER BY action_at DESC, id DESC
            """,
            (memory_id,),
        ).fetchall()
        return {
            "memory": _memory_row_to_public(row),
            "operations": [_row_to_dict(item) for item in operations],
            "source_turn_ids": _json_int_list(row["source_turn_ids"]),
        }

    def log_influence(
        self,
        turn_id: int | None,
        query: str,
        influence: dict[str, Any],
        state_snapshot_id: int | None = None,
        policy_action: str | None = None,
    ) -> None:
        memory_ids = [
            item.get("metadata", {}).get("id")
            for item in influence.get("results", [])
            if isinstance(item, dict)
        ]
        self._conn.execute(
            """
            INSERT INTO memory_influence_log (
                session_id, turn_id, query, retrieved_memory_ids,
                expression_context, policy_influence, state_influence,
                state_snapshot_id, policy_action
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._session_id,
                turn_id,
                query,
                json.dumps([mid for mid in memory_ids if mid is not None]),
                json.dumps(influence.get("expression_context", []), ensure_ascii=False),
                json.dumps(influence.get("policy_influence", {}), ensure_ascii=False),
                json.dumps(influence.get("state_influence", {}), ensure_ascii=False),
                state_snapshot_id,
                policy_action,
            ),
        )
        self._conn.commit()

    def _proposal_llm_output(self, messages: list[dict], context: dict[str, Any]) -> str:
        if self._llm_client is None:
            return ""
        system = _load_proposal_prompt(self._prompts_dir)
        payload = {
            "messages": messages[-4:],
            "context": _json_safe(context),
        }
        try:
            with turn_step(
                "memory_proposal.llm",
                metadata={"message_count": len(payload["messages"]), "max_tokens": 800},
            ):
                return self._llm_client.complete(
                    system=system,
                    messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                    max_tokens=800,
                )
        except Exception as exc:
            logger.warning("managed memory proposal LLM failed: %s", exc)
            return ""

    def _commit_one(self, proposal: MemoryOperationProposal) -> dict[str, Any] | None:
        if proposal.operation == "add":
            return self._commit_add(proposal)
        if proposal.operation == "update" and proposal.memory_id is not None:
            return self._commit_update(proposal.memory_id, proposal.patch, proposal)
        if proposal.operation == "supersede" and proposal.memory_id is not None:
            self._set_status(proposal.memory_id, "superseded", proposal)
            add_proposal = MemoryOperationProposal(
                operation="add",
                content=proposal.content,
                reason=proposal.reason,
                source_turn_ids=proposal.source_turn_ids,
                entities=proposal.entities,
                topics=proposal.topics,
                confidence=proposal.confidence,
                scope=proposal.scope,
                metadata={**proposal.metadata, "supersedes": proposal.memory_id},
            )
            return self._commit_add(add_proposal)
        if proposal.operation == "archive" and proposal.memory_id is not None:
            return self._set_status(proposal.memory_id, "archived", proposal)
        if proposal.operation == "restore" and proposal.memory_id is not None:
            return self._set_status(proposal.memory_id, "active", proposal, from_statuses=_RESTORABLE_STATUSES)
        return None

    def _commit_add(self, proposal: MemoryOperationProposal) -> dict[str, Any]:
        embedding, embedding_model = self._embed(proposal.content)
        cursor = self._conn.execute(
            """
            INSERT INTO managed_memories (
                session_id, session_type, scope, memory_kind, content,
                entities, topics, confidence, source_turn_ids, status,
                embedding, embedding_model, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                self._session_id,
                self._session_type,
                proposal.scope,
                str(proposal.metadata.get("memory_kind", "observation")),
                proposal.content,
                json.dumps(proposal.entities, ensure_ascii=False),
                json.dumps(proposal.topics, ensure_ascii=False),
                proposal.confidence,
                json.dumps(proposal.source_turn_ids),
                embedding,
                embedding_model,
                json.dumps(proposal.metadata, ensure_ascii=False),
            ),
        )
        memory_id = int(cursor.lastrowid)
        self._sync_fts(memory_id)
        self._log_operation("add", memory_id, proposal)
        return {"operation": "add", "memory_id": memory_id}

    def _commit_update(
        self,
        memory_id: int,
        patch: dict[str, Any],
        proposal: MemoryOperationProposal,
    ) -> dict[str, Any]:
        existing = self._conn.execute("SELECT * FROM managed_memories WHERE id = ?", (memory_id,)).fetchone()
        if existing is None:
            raise KeyError(f"managed memory not found: {memory_id}")
        allowed = {"content", "entities", "topics", "confidence", "scope", "memory_kind", "metadata"}
        updates: dict[str, Any] = {key: value for key, value in patch.items() if key in allowed}
        if not updates:
            return {"operation": "update", "memory_id": memory_id, "updated": []}
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{key} = ?")
            if key in {"entities", "topics"}:
                params.append(json.dumps(_string_list(value), ensure_ascii=False))
            elif key == "metadata":
                params.append(json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False))
            else:
                params.append(value)
        if "content" in updates:
            embedding, embedding_model = self._embed(str(updates["content"]))
            assignments.extend(["embedding = ?", "embedding_model = ?"])
            params.extend([embedding, embedding_model])
        assignments.append("updated_at = datetime('now')")
        params.append(memory_id)
        self._conn.execute(
            f"UPDATE managed_memories SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        self._sync_fts(memory_id)
        self._log_operation("update", memory_id, proposal)
        return {"operation": "update", "memory_id": memory_id, "updated": sorted(updates)}

    def _set_status(
        self,
        memory_id: int,
        status: str,
        proposal: MemoryOperationProposal,
        from_statuses: set[str] | None = None,
    ) -> dict[str, Any]:
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid managed memory status: {status}")
        row = self._conn.execute("SELECT status FROM managed_memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(f"managed memory not found: {memory_id}")
        if from_statuses is not None and row["status"] not in from_statuses:
            return {"operation": proposal.operation, "memory_id": memory_id, "status": row["status"]}
        self._conn.execute(
            "UPDATE managed_memories SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, memory_id),
        )
        self._log_operation(proposal.operation, memory_id, proposal)
        return {"operation": proposal.operation, "memory_id": memory_id, "status": status}

    def _candidate_rows(self, query: str, filters: dict[str, Any], limit: int) -> list[sqlite3.Row]:
        status = str(filters.get("status", "active"))
        session_type = str(filters.get("session_type", self._session_type))
        params: list[Any] = []
        where = ["session_type = ?"]
        params.append(session_type)
        if status != "all":
            where.append("status = ?")
            params.append(status)
        else:
            where.append("status IN ('active', 'superseded', 'archived', 'hidden')")

        query = query.strip()
        if query:
            fts_rows = self._fts_rows(query, where, params, limit)
            if fts_rows:
                return fts_rows

        params.append(limit)
        return self._conn.execute(
            f"""
            SELECT * FROM managed_memories
            WHERE {" AND ".join(where)}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _fts_rows(
        self,
        query: str,
        where: list[str],
        params: list[Any],
        limit: int,
    ) -> list[sqlite3.Row]:
        match = " OR ".join(_tokens(query))
        if not match:
            return []
        try:
            return self._conn.execute(
                f"""
                SELECT m.*
                FROM managed_memories_fts f
                JOIN managed_memories m ON m.id = f.rowid
                WHERE f.managed_memories_fts MATCH ? AND {" AND ".join("m." + item for item in where)}
                ORDER BY bm25(f), m.updated_at DESC
                LIMIT ?
                """,
                [match, *params, limit],
            ).fetchall()
        except sqlite3.Error:
            return []

    def _sync_fts(self, memory_id: int) -> None:
        row = self._conn.execute("SELECT * FROM managed_memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return
        try:
            self._conn.execute("DELETE FROM managed_memories_fts WHERE rowid = ?", (memory_id,))
            self._conn.execute(
                "INSERT INTO managed_memories_fts(rowid, content, entities, topics) VALUES (?, ?, ?, ?)",
                (memory_id, row["content"], row["entities"], row["topics"]),
            )
        except sqlite3.Error:
            pass

    def _embed(self, text: str) -> tuple[bytes | None, str | None]:
        client = self._embedding_client
        if client is None or not getattr(client, "enabled", False) or not getattr(client, "model", None):
            return None, None
        try:
            with turn_step("embedding.managed_memory_write"):
                return encode_embedding(client.embed(text)), client.model
        except Exception as exc:
            logger.warning("managed memory embedding failed: %s", exc)
            return None, None

    def _query_embedding(self, text: str) -> list[float] | None:
        client = self._embedding_client
        if not text or client is None or not getattr(client, "enabled", False):
            return None
        try:
            with turn_step("embedding.managed_memory_query"):
                return client.embed(text)
        except Exception:
            return None

    def _log_operation(self, action: str, memory_id: int, proposal: MemoryOperationProposal) -> None:
        self._conn.execute(
            """
            INSERT INTO memory_operation_log (
                session_id, action, memory_id, proposal_id,
                source_turn_ids, details
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self._session_id,
                action,
                memory_id,
                proposal.id,
                json.dumps(proposal.source_turn_ids),
                proposal.operation_json(),
            ),
        )

    def _resolve_session_type(self) -> str:
        row = self._conn.execute(
            "SELECT session_type FROM sessions WHERE id = ?",
            (self._session_id,),
        ).fetchone()
        if row and row["session_type"] in {"test", "exhibition"}:
            return str(row["session_type"])
        return "test"


class Mem0Provider(LocalManagedMemoryProvider):
    """
    Optional mem0 backend placeholder.

    The first implementation keeps local persistence and falls back safely when
    mem0ai is not installed. Direct mem0 delegation can be added behind this
    class without changing the MemoryProvider interface.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        try:
            __import__("mem0")
            self.mem0_available = True
        except Exception:
            self.mem0_available = False
            logger.warning("ENTITY_MEMORY_BACKEND=mem0 requested, but mem0ai is unavailable; using local provider.")
        super().__init__(*args, **kwargs)


def build_memory_provider(
    conn: sqlite3.Connection,
    session_id: str,
    llm_client: ClaudeClient | None = None,
    embedding_client: EmbeddingClient | None = None,
    prompts_dir: Path | None = None,
    config: MemoryProviderConfig | None = None,
) -> MemoryProvider:
    cfg = config or MemoryProviderConfig.from_env()
    cls = Mem0Provider if cfg.backend == "mem0" else LocalManagedMemoryProvider
    return cls(conn, session_id, llm_client, embedding_client, prompts_dir, cfg)


def _fallback_proposals(messages: list[dict], source_turn_ids: list[int]) -> list[MemoryOperationProposal]:
    user_text = ""
    for message in reversed(messages):
        if message.get("role") == "user" and str(message.get("content", "")).strip():
            user_text = str(message["content"]).strip()
            break
    if not user_text or len(user_text) < 4:
        return []
    return [MemoryOperationProposal(
        operation="add",
        content=f"Visitor said: {user_text[:500]}",
        reason="deterministic fallback proposal from recent visitor turn",
        source_turn_ids=source_turn_ids,
        entities=_extract_entities(user_text),
        topics=_extract_topics(user_text),
        confidence=0.45,
        metadata={"proposal_source": "fallback", "memory_kind": "observation"},
    )]


def _parse_proposals(raw_output: str, source_turn_ids: list[int]) -> list[MemoryOperationProposal]:
    if not raw_output.strip():
        return []
    data = _extract_json(raw_output)
    if data is None:
        return []
    operations = data.get("operations") if isinstance(data, dict) else data
    if not isinstance(operations, list):
        return []
    proposals: list[MemoryOperationProposal] = []
    for item in operations:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        operation = str(item.get("operation", "add")).strip().lower()
        if operation == "add" and not content:
            continue
        proposals.append(MemoryOperationProposal(
            operation=operation,
            memory_id=item.get("memory_id") if isinstance(item.get("memory_id"), int) else None,
            content=content,
            patch=item.get("patch") if isinstance(item.get("patch"), dict) else {},
            reason=str(item.get("reason", ""))[:500],
            source_turn_ids=_json_int_list(item.get("source_turn_ids")) or source_turn_ids,
            entities=_string_list(item.get("entities")),
            topics=_string_list(item.get("topics")),
            confidence=float(item.get("confidence", 0.5) or 0.5),
            scope=str(item.get("scope", "session")),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        ))
    return proposals


def _coerce_operation(item: MemoryOperationProposal | dict) -> MemoryOperationProposal:
    if isinstance(item, MemoryOperationProposal):
        return item
    return MemoryOperationProposal(
        operation=str(item.get("operation", "add")),
        memory_id=item.get("memory_id") if isinstance(item.get("memory_id"), int) else None,
        content=str(item.get("content", "")),
        patch=item.get("patch") if isinstance(item.get("patch"), dict) else {},
        reason=str(item.get("reason", "")),
        source_turn_ids=_json_int_list(item.get("source_turn_ids")),
        entities=_string_list(item.get("entities")),
        topics=_string_list(item.get("topics")),
        confidence=float(item.get("confidence", 0.5) or 0.5),
        scope=str(item.get("scope", "session")),
        metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    )


def _load_proposal_prompt(prompts_dir: Path | None) -> str:
    if prompts_dir is None:
        return _DEFAULT_PROPOSAL_PROMPT
    path = prompts_dir / "memory_proposal_system.txt"
    if not path.exists():
        return _DEFAULT_PROPOSAL_PROMPT
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except ValueError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def _source_turn_ids(context: dict[str, Any]) -> list[int]:
    for key in ("source_turn_ids", "turn_ids"):
        values = _json_int_list(context.get(key))
        if values:
            return values
    value = context.get("turn_id")
    return [int(value)] if isinstance(value, int) or str(value).isdigit() else []


def _extract_entities(text: str) -> list[str]:
    chunks = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Z][A-Za-z0-9_-]{2,}", text)
    return list(dict.fromkeys(chunks[:8]))


def _extract_topics(text: str) -> list[str]:
    tokens = [token for token in _tokens(text) if len(token) > 1 or re.search(r"[\u4e00-\u9fff]", token)]
    return list(dict.fromkeys(tokens[:12]))


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    return {tok for tok in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", lowered) if tok.strip()}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return _string_list(parsed)
    return _string_list(value)


def _json_int_list(value: Any) -> list[int]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    return [int(item) for item in value if isinstance(item, int) or str(item).isdigit()]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _memory_row_to_public(row: sqlite3.Row) -> dict[str, Any]:
    item = _row_to_dict(row)
    item["entities"] = _json_list(row["entities"])
    item["topics"] = _json_list(row["topics"])
    item["source_turn_ids"] = _json_int_list(row["source_turn_ids"])
    item["metadata"] = _json_dict(row["metadata"])
    item["has_embedding"] = bool(row["embedding"])
    item.pop("embedding", None)
    return item


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_DEFAULT_PROPOSAL_PROMPT = """You extract managed memories for Stranger.
Return JSON only: {"operations":[...]}.
Each operation must be add, update, supersede, archive, or restore.
Prefer add operations for stable visitor behavior, recurring topics, corrected facts, and relation patterns.
Do not include chain-of-thought. Use short reasons.
"""
