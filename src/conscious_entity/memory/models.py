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
        )
