from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_DEFAULT_RECORD_LIMIT = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _default_latency_log_dir() -> Path:
    return Path("data/latency_logs")


class JsonlRingStore:
    def __init__(self, path: Path | str, *, max_records: int = _DEFAULT_RECORD_LIMIT) -> None:
        self.path = Path(path)
        self.max_records = max(1, int(max_records))
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.warning("Skipping corrupt latency log line in %s", self.path)
                    continue
                if isinstance(value, dict):
                    records.append(value)
        except OSError as exc:
            logger.warning("Failed to read latency log %s: %s", self.path, exc)
            return []
        return records[-self.max_records :]

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            records = self.load()
            records.append(record)
            records = records[-self.max_records :]
            self._write(records)

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        )
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.path)


@dataclass
class LatencyStep:
    name: str
    duration_ms: float
    blocking: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "blocking": self.blocking,
            "metadata": self.metadata,
        }

    @classmethod
    def from_public_dict(cls, data: dict[str, Any]) -> LatencyStep:
        return cls(
            name=str(data.get("name") or ""),
            duration_ms=float(data.get("duration_ms") or 0.0),
            blocking=bool(data.get("blocking", True)),
            metadata=_dict_or_empty(data.get("metadata")),
        )


@dataclass
class TurnLatencyRecord:
    record_id: str
    source: str
    timestamp: str
    total_ms: float
    success: bool
    error: str | None
    metadata: dict[str, Any]
    steps: list[LatencyStep]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "total_ms": self.total_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "steps": [step.to_public_dict() for step in self.steps],
        }

    @classmethod
    def from_public_dict(cls, data: dict[str, Any]) -> TurnLatencyRecord:
        return cls(
            record_id=str(data.get("record_id") or "turn_" + uuid.uuid4().hex),
            source=str(data.get("source") or "unknown"),
            timestamp=str(data.get("timestamp") or _now_iso()),
            total_ms=float(data.get("total_ms") or 0.0),
            success=bool(data.get("success", True)),
            error=data.get("error") if data.get("error") is None else str(data.get("error")),
            metadata=_dict_or_empty(data.get("metadata")),
            steps=[
                LatencyStep.from_public_dict(step)
                for step in data.get("steps", [])
                if isinstance(step, dict)
            ],
        )


@dataclass
class AudioLatencyRecord:
    record_id: str
    kind: str
    timestamp: str
    duration_ms: float
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_public_dict(cls, data: dict[str, Any]) -> AudioLatencyRecord:
        return cls(
            record_id=str(data.get("record_id") or "audio_" + uuid.uuid4().hex),
            kind=str(data.get("kind") or "unknown"),
            timestamp=str(data.get("timestamp") or _now_iso()),
            duration_ms=float(data.get("duration_ms") or 0.0),
            success=bool(data.get("success", True)),
            error=data.get("error") if data.get("error") is None else str(data.get("error")),
            metadata=_dict_or_empty(data.get("metadata")),
        )


@dataclass
class PresentationLatencyRecord:
    record_id: str
    kind: str
    timestamp: str
    duration_ms: float
    latency_record_id: str | None = None
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "latency_record_id": self.latency_record_id,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_public_dict(cls, data: dict[str, Any]) -> PresentationLatencyRecord:
        latency_record_id = data.get("latency_record_id")
        return cls(
            record_id=str(data.get("record_id") or "presentation_" + uuid.uuid4().hex),
            kind=str(data.get("kind") or "unknown"),
            timestamp=str(data.get("timestamp") or _now_iso()),
            duration_ms=float(data.get("duration_ms") or 0.0),
            latency_record_id=None if latency_record_id is None else str(latency_record_id),
            success=bool(data.get("success", True)),
            error=data.get("error") if data.get("error") is None else str(data.get("error")),
            metadata=_dict_or_empty(data.get("metadata")),
        )


class TurnLatencyRecorder:
    def __init__(self, source: str, metadata: dict[str, Any] | None = None) -> None:
        self.record_id = "turn_" + uuid.uuid4().hex
        self.source = source
        self.timestamp = _now_iso()
        self.metadata = metadata or {}
        self._start = time.perf_counter()
        self._steps: list[LatencyStep] = []

    @contextlib.contextmanager
    def step(
        self,
        name: str,
        *,
        blocking: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.add_step(name, _duration_ms(start), blocking=blocking, metadata=metadata)

    def add_step(
        self,
        name: str,
        duration_ms: float,
        *,
        blocking: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._steps.append(
            LatencyStep(
                name=name,
                duration_ms=round(float(duration_ms), 2),
                blocking=blocking,
                metadata=metadata or {},
            )
        )

    def finish(self, *, success: bool = True, error: str | None = None) -> TurnLatencyRecord:
        return TurnLatencyRecord(
            record_id=self.record_id,
            source=self.source,
            timestamp=self.timestamp,
            total_ms=_duration_ms(self._start),
            success=success,
            error=error,
            metadata=self.metadata,
            steps=list(self._steps),
        )


class LatencyTracker:
    def __init__(
        self,
        max_turn_records: int = _DEFAULT_RECORD_LIMIT,
        max_audio_records: int = _DEFAULT_RECORD_LIMIT,
        max_presentation_records: int = _DEFAULT_RECORD_LIMIT,
        storage_dir: Path | str | None = None,
    ) -> None:
        self._max_turn_records = max(1, int(max_turn_records))
        self._max_audio_records = max(1, int(max_audio_records))
        self._max_presentation_records = max(1, int(max_presentation_records))
        self._lock = threading.Lock()
        self._turn_store = (
            JsonlRingStore(Path(storage_dir) / "turn-latency.jsonl", max_records=self._max_turn_records)
            if storage_dir is not None
            else None
        )
        self._audio_store = (
            JsonlRingStore(Path(storage_dir) / "audio-latency.jsonl", max_records=self._max_audio_records)
            if storage_dir is not None
            else None
        )
        self._presentation_store = (
            JsonlRingStore(
                Path(storage_dir) / "presentation-latency.jsonl",
                max_records=self._max_presentation_records,
            )
            if storage_dir is not None
            else None
        )
        self._turn_records: list[TurnLatencyRecord] = [
            TurnLatencyRecord.from_public_dict(record)
            for record in (self._turn_store.load() if self._turn_store else [])
        ]
        self._audio_records: list[AudioLatencyRecord] = [
            AudioLatencyRecord.from_public_dict(record)
            for record in (self._audio_store.load() if self._audio_store else [])
        ]
        self._presentation_records: list[PresentationLatencyRecord] = [
            PresentationLatencyRecord.from_public_dict(record)
            for record in (self._presentation_store.load() if self._presentation_store else [])
        ]

    def record_turn(self, record: TurnLatencyRecord) -> None:
        with self._lock:
            self._turn_records.append(record)
            if len(self._turn_records) > self._max_turn_records:
                self._turn_records.pop(0)
        if self._turn_store is not None:
            self._turn_store.append(record.to_public_dict())

    def record_audio(self, record: AudioLatencyRecord) -> None:
        with self._lock:
            self._audio_records.append(record)
            if len(self._audio_records) > self._max_audio_records:
                self._audio_records.pop(0)
        if self._audio_store is not None:
            self._audio_store.append(record.to_public_dict())

    def record_presentation(self, record: PresentationLatencyRecord) -> None:
        with self._lock:
            self._presentation_records.append(record)
            if len(self._presentation_records) > self._max_presentation_records:
                self._presentation_records.pop(0)
        if self._presentation_store is not None:
            self._presentation_store.append(record.to_public_dict())

    def recent_turns(self, n: int = 20) -> list[TurnLatencyRecord]:
        with self._lock:
            return list(self._turn_records[-max(1, min(int(n), 100)):])

    def recent_audio(self, n: int = 50) -> list[AudioLatencyRecord]:
        with self._lock:
            return list(self._audio_records[-max(1, min(int(n), 200)):])

    def recent_presentation(self, n: int = 50) -> list[PresentationLatencyRecord]:
        with self._lock:
            return list(self._presentation_records[-max(1, min(int(n), 200)):])

    def turn_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._turn_records)
        return _turn_summary(records)

    def audio_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._audio_records)
        return _audio_summary(records)

    def presentation_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._presentation_records)
        return _presentation_summary(records)


_tracker: LatencyTracker | None = None
_active_turn: contextvars.ContextVar[TurnLatencyRecorder | None] = contextvars.ContextVar(
    "active_turn_latency_recorder",
    default=None,
)


def get_latency_tracker() -> LatencyTracker:
    global _tracker
    if _tracker is None:
        _tracker = LatencyTracker(storage_dir=_default_latency_log_dir())
    return _tracker


def reset_latency_tracker_for_tests(storage_dir: Path | str | None = None) -> LatencyTracker:
    global _tracker
    _tracker = LatencyTracker(storage_dir=storage_dir)
    return _tracker


def current_turn_recorder() -> TurnLatencyRecorder | None:
    return _active_turn.get()


@contextlib.contextmanager
def activate_turn_recorder(recorder: TurnLatencyRecorder) -> Iterator[None]:
    token = _active_turn.set(recorder)
    try:
        yield
    finally:
        _active_turn.reset(token)


@contextlib.contextmanager
def turn_step(
    name: str,
    *,
    blocking: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    recorder = current_turn_recorder()
    if recorder is None:
        yield
        return
    with recorder.step(name, blocking=blocking, metadata=metadata):
        yield


def record_audio_latency(
    kind: str,
    duration_ms: float,
    *,
    success: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    get_latency_tracker().record_audio(
        AudioLatencyRecord(
            record_id="audio_" + uuid.uuid4().hex,
            kind=kind,
            timestamp=_now_iso(),
            duration_ms=round(float(duration_ms), 2),
            success=success,
            error=error,
            metadata=metadata or {},
        )
    )


def record_presentation_latency(
    kind: str,
    duration_ms: float,
    *,
    latency_record_id: str | None = None,
    success: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PresentationLatencyRecord:
    record = PresentationLatencyRecord(
        record_id="presentation_" + uuid.uuid4().hex,
        kind=kind,
        timestamp=_now_iso(),
        duration_ms=round(float(duration_ms), 2),
        latency_record_id=latency_record_id,
        success=success,
        error=error,
        metadata=metadata or {},
    )
    get_latency_tracker().record_presentation(record)
    return record


def _turn_summary(records: list[TurnLatencyRecord]) -> dict[str, Any]:
    if not records:
        return {
            "total_turns": 0,
            "success_count": 0,
            "failure_count": 0,
            "avg_total_ms": 0.0,
            "p95_total_ms": 0.0,
            "steps": {},
        }
    totals = [record.total_ms for record in records]
    step_values: dict[str, list[float]] = {}
    for record in records:
        for step in record.steps:
            step_values.setdefault(step.name, []).append(step.duration_ms)
    return {
        "total_turns": len(records),
        "success_count": sum(1 for record in records if record.success),
        "failure_count": sum(1 for record in records if not record.success),
        "avg_total_ms": round(statistics.fmean(totals), 2),
        "p95_total_ms": _p95(totals),
        "steps": {
            name: {
                "count": len(values),
                "avg_ms": round(statistics.fmean(values), 2),
                "p95_ms": _p95(values),
            }
            for name, values in sorted(step_values.items())
        },
    }


def _audio_summary(records: list[AudioLatencyRecord]) -> dict[str, Any]:
    if not records:
        return {"total_records": 0, "kinds": {}}
    grouped: dict[str, list[AudioLatencyRecord]] = {}
    for record in records:
        grouped.setdefault(record.kind, []).append(record)
    return {
        "total_records": len(records),
        "kinds": {
            kind: {
                "count": len(items),
                "success_count": sum(1 for item in items if item.success),
                "failure_count": sum(1 for item in items if not item.success),
                "avg_ms": round(statistics.fmean(item.duration_ms for item in items), 2),
                "p95_ms": _p95([item.duration_ms for item in items]),
            }
            for kind, items in sorted(grouped.items())
        },
    }


def _presentation_summary(records: list[PresentationLatencyRecord]) -> dict[str, Any]:
    if not records:
        return {"total_records": 0, "kinds": {}}
    grouped: dict[str, list[PresentationLatencyRecord]] = {}
    for record in records:
        grouped.setdefault(record.kind, []).append(record)
    return {
        "total_records": len(records),
        "kinds": {
            kind: {
                "count": len(items),
                "success_count": sum(1 for item in items if item.success),
                "failure_count": sum(1 for item in items if not item.success),
                "avg_ms": round(statistics.fmean(item.duration_ms for item in items), 2),
                "p95_ms": _p95([item.duration_ms for item in items]),
            }
            for kind, items in sorted(grouped.items())
        },
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return round(ordered[index], 2)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
