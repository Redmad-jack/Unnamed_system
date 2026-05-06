from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from conscious_entity.perception.event_types import EventType
from conscious_entity.state.state_core import EntityState


@dataclass
class ShortTermEntry:
    role: str  # "user" or "entity"
    content: str
    timestamp: datetime
    event_type: Optional[EventType] = None


@dataclass
class EpisodicMemory:
    session_id: str
    event_type: str
    content: str
    salience: float
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    raw_text: Optional[str] = None
    state_snapshot_id: Optional[int] = None
    reflected: bool = False
    reflection_id: Optional[int] = None
    metadata: dict = field(default_factory=dict)
    embedding: Optional[bytes] = None
    embedding_model: Optional[str] = None

    def metadata_json(self) -> str:
        return json.dumps(self.metadata)

    @classmethod
    def from_row(cls, row) -> EpisodicMemory:
        d = dict(row)
        return cls(
            id=d["id"],
            session_id=d["session_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            event_type=d["event_type"],
            content=d["content"],
            raw_text=d.get("raw_text"),
            salience=d["salience"],
            state_snapshot_id=d.get("state_snapshot_id"),
            reflected=bool(d["reflected"]),
            reflection_id=d.get("reflection_id"),
            metadata=json.loads(d["metadata"]) if d.get("metadata") else {},
            embedding=d.get("embedding"),
            embedding_model=d.get("embedding_model"),
        )


@dataclass
class ReflectiveSummary:
    session_id: str
    content: str
    source_event_ids: list[int]
    state_at_reflection: EntityState
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    active: bool = True
    embedding: Optional[bytes] = None
    embedding_model: Optional[str] = None

    def source_event_ids_json(self) -> str:
        return json.dumps(self.source_event_ids)

    def state_json(self) -> str:
        return json.dumps(self.state_at_reflection.to_dict())

    @classmethod
    def from_row(cls, row) -> ReflectiveSummary:
        d = dict(row)
        return cls(
            id=d["id"],
            session_id=d["session_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            content=d["content"],
            source_event_ids=json.loads(d["source_event_ids"]),
            state_at_reflection=EntityState.from_dict(json.loads(d["state_at_reflection"])),
            active=bool(d["active"]),
            embedding=d.get("embedding"),
            embedding_model=d.get("embedding_model"),
        )


@dataclass
class RetrievedMemory:
    memory_type: str  # "recent", "episodic", or "reflective"
    content: str
    timestamp: Optional[datetime] = None
    score: float = 0.0
    similarity: Optional[float] = None
    source: str = "deterministic"
    metadata: dict = field(default_factory=dict)

    def to_public_dict(self) -> dict:
        return {
            "memory_type": self.memory_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "score": round(self.score, 4),
            "similarity": round(self.similarity, 4) if self.similarity is not None else None,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class MemoryOperationProposal:
    operation: str
    content: str = ""
    memory_id: Optional[int] = None
    patch: dict = field(default_factory=dict)
    reason: str = ""
    source_turn_ids: list[int] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    confidence: float = 0.5
    scope: str = "session"
    metadata: dict = field(default_factory=dict)
    id: Optional[int] = None
    session_id: Optional[str] = None
    created_at: Optional[datetime] = None
    status: str = "pending"
    raw_llm_output: Optional[str] = None

    def operation_json(self) -> str:
        return json.dumps({
            "operation": self.operation,
            "memory_id": self.memory_id,
            "content": self.content,
            "patch": self.patch,
            "reason": self.reason,
            "source_turn_ids": self.source_turn_ids,
            "entities": self.entities,
            "topics": self.topics,
            "confidence": self.confidence,
            "scope": self.scope,
            "metadata": self.metadata,
        }, ensure_ascii=False)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "operation": self.operation,
            "memory_id": self.memory_id,
            "content": self.content,
            "patch": self.patch,
            "reason": self.reason,
            "source_turn_ids": self.source_turn_ids,
            "entities": self.entities,
            "topics": self.topics,
            "confidence": round(float(self.confidence), 4),
            "scope": self.scope,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row) -> MemoryOperationProposal:
        d = dict(row)
        operation = json.loads(d["operation_json"]) if d.get("operation_json") else {}
        return cls(
            id=d["id"],
            session_id=d["session_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            status=d["status"],
            raw_llm_output=d.get("raw_llm_output"),
            operation=str(operation.get("operation", d.get("operation_type") or "add")),
            memory_id=operation.get("memory_id"),
            content=str(operation.get("content", "")),
            patch=operation.get("patch") if isinstance(operation.get("patch"), dict) else {},
            reason=str(operation.get("reason", d.get("reason") or "")),
            source_turn_ids=[
                int(value) for value in operation.get("source_turn_ids", [])
                if isinstance(value, int) or str(value).isdigit()
            ],
            entities=_string_list(operation.get("entities")),
            topics=_string_list(operation.get("topics")),
            confidence=float(operation.get("confidence", 0.5) or 0.5),
            scope=str(operation.get("scope", "session")),
            metadata=operation.get("metadata") if isinstance(operation.get("metadata"), dict) else {},
        )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
