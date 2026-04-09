from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LLMCallRecord:
    timestamp: datetime
    model: str
    duration_ms: int
    success: bool
    error: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMStatsTracker:
    """In-memory LLM call statistics. Not persisted to SQLite — developer use only."""

    def __init__(self, max_records: int = 1000) -> None:
        self._records: list[LLMCallRecord] = []
        self._max_records = max_records

    def record(self, rec: LLMCallRecord) -> None:
        self._records.append(rec)
        if len(self._records) > self._max_records:
            self._records.pop(0)

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
        _tracker = LLMStatsTracker()
    return _tracker
