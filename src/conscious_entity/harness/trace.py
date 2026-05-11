from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarnessLayer(str, Enum):
    INPUT = "input"
    STATE = "state"
    MEMORY = "memory"
    POLICY = "policy"
    PROMPT = "prompt"
    GENERATION = "generation"
    OUTPUT = "output"
    PRESENTATION = "presentation"


HARNESS_LAYERS: tuple[HarnessLayer, ...] = (
    HarnessLayer.INPUT,
    HarnessLayer.STATE,
    HarnessLayer.MEMORY,
    HarnessLayer.POLICY,
    HarnessLayer.PROMPT,
    HarnessLayer.GENERATION,
    HarnessLayer.OUTPUT,
    HarnessLayer.PRESENTATION,
)


@dataclass(frozen=True)
class HarnessLayerTrace:
    layer: HarnessLayer
    status: str
    summary: str
    rule_ids: list[str] = field(default_factory=list)
    decision: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.value,
            "status": self.status,
            "summary": self.summary,
            "rule_ids": list(self.rule_ids),
            "decision": self.decision,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class HarnessTrace:
    trace_id: str
    session_id: str
    source: str
    started_at: str
    completed_at: str
    success: bool
    error: str | None
    metadata: dict[str, Any]
    layers: list[HarnessLayerTrace]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "source": self.source,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "layers": [layer.to_public_dict() for layer in self.layers],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        latest_by_layer: dict[str, dict[str, Any]] = {}
        for item in self.layers:
            latest_by_layer[item.layer.value] = item.to_public_dict()
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "success": self.success,
            "layer_count": len(self.layers),
            "layers": latest_by_layer,
        }


class HarnessTraceRecorder:
    def __init__(
        self,
        *,
        session_id: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = "harness_" + uuid.uuid4().hex
        self.session_id = session_id
        self.source = source
        self.started_at = _now_iso()
        self.metadata = metadata or {}
        self._layers: list[HarnessLayerTrace] = []

    def record(
        self,
        layer: HarnessLayer,
        *,
        status: str,
        summary: str,
        rule_ids: list[str] | None = None,
        decision: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._layers.append(
            HarnessLayerTrace(
                layer=layer,
                status=status,
                summary=summary,
                rule_ids=list(rule_ids or []),
                decision=decision,
                metadata=metadata or {},
            )
        )

    def finish(self, *, success: bool, error: str | None = None) -> HarnessTrace:
        return HarnessTrace(
            trace_id=self.trace_id,
            session_id=self.session_id,
            source=self.source,
            started_at=self.started_at,
            completed_at=_now_iso(),
            success=success,
            error=error,
            metadata=self.metadata,
            layers=list(self._layers),
        )


class HarnessTraceStore:
    def __init__(self, max_records: int = 300) -> None:
        self._records: deque[HarnessTrace] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    def record(self, trace: HarnessTrace) -> None:
        with self._lock:
            self._records.append(trace)

    def recent(self, limit: int = 20) -> list[HarnessTrace]:
        bounded = max(1, min(int(limit), 100))
        with self._lock:
            return list(self._records)[-bounded:]

    def latest(self) -> HarnessTrace | None:
        with self._lock:
            return self._records[-1] if self._records else None

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def status(self) -> dict[str, Any]:
        latest = self.latest()
        return {
            "enabled": True,
            "storage": "process_memory_ring_buffer",
            "layers": [layer.value for layer in HARNESS_LAYERS],
            "recent_count": len(self.recent(100)),
            "latest": latest.to_public_dict() if latest else None,
        }


_store: HarnessTraceStore | None = None


def get_harness_trace_store() -> HarnessTraceStore:
    global _store
    if _store is None:
        _store = HarnessTraceStore()
    return _store
