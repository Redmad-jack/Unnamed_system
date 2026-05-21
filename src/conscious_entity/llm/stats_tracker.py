from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from conscious_entity.telemetry.latency import JsonlRingStore


_DEFAULT_RECORD_LIMIT = 50


@dataclass
class LLMCallRecord:
    timestamp: datetime
    model: str
    duration_ms: int
    success: bool
    error: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def to_public_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }

    @classmethod
    def from_public_dict(cls, data: dict) -> LLMCallRecord:
        timestamp_value = data.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(str(timestamp_value))
        except (TypeError, ValueError):
            timestamp = datetime.now()
        return cls(
            timestamp=timestamp,
            model=str(data.get("model") or "unknown"),
            duration_ms=int(data.get("duration_ms") or 0),
            success=bool(data.get("success", True)),
            error=data.get("error") if data.get("error") is None else str(data.get("error")),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
        )


class LLMStatsTracker:
    """Process-local LLM call statistics with optional JSONL persistence."""

    def __init__(
        self,
        max_records: int = _DEFAULT_RECORD_LIMIT,
        storage_dir: Path | str | None = None,
    ) -> None:
        self._max_records = max(1, int(max_records))
        self._store = (
            JsonlRingStore(Path(storage_dir) / "llm-latency.jsonl", max_records=self._max_records)
            if storage_dir is not None
            else None
        )
        self._records: list[LLMCallRecord] = [
            LLMCallRecord.from_public_dict(record)
            for record in (self._store.load() if self._store else [])
        ]

    def record(self, rec: LLMCallRecord) -> None:
        self._records.append(rec)
        if len(self._records) > self._max_records:
            self._records.pop(0)
        if self._store is not None:
            self._store.append(rec.to_public_dict())

    def recent(self, n: int = 50) -> list[LLMCallRecord]:
        return list(self._records[-n:])

    def summary(self) -> dict:
        if not self._records:
            return {
                "total_calls": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
            }
        successes = [r for r in self._records if r.success]
        failures = [r for r in self._records if not r.success]
        return {
            "total_calls": len(self._records),
            "success_count": len(successes),
            "failure_count": len(failures),
            "success_rate": round(len(successes) / len(self._records), 4),
            "avg_duration_ms": round(
                sum(r.duration_ms for r in self._records) / len(self._records), 1
            ),
            "total_prompt_tokens": sum(r.prompt_tokens for r in self._records),
            "total_completion_tokens": sum(r.completion_tokens for r in self._records),
        }


# Module-level singleton shared across all ClaudeClient instances in a process.
_tracker: LLMStatsTracker | None = None


def get_tracker() -> LLMStatsTracker:
    global _tracker
    if _tracker is None:
        _tracker = LLMStatsTracker(storage_dir=Path("data/latency_logs"))
    return _tracker


def reset_tracker_for_tests(storage_dir: Path | str | None = None) -> LLMStatsTracker:
    global _tracker
    _tracker = LLMStatsTracker(storage_dir=storage_dir)
    return _tracker
