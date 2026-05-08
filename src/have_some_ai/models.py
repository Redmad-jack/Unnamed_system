from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ParticipantStatus(str, Enum):
    WAITING = "waiting"
    OBSERVING = "observing"
    QUESTIONING = "questioning"
    SCORING = "scoring"
    ASSIGNED = "assigned"
    SERVED = "served"
    CANCELLED = "cancelled"


class QueueStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    SERVED = "served"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Option:
    id: str
    text: str
    text_zh: str | None
    scores: dict[str, float]


@dataclass(frozen=True)
class Question:
    id: str
    module_id: str
    module_label: str
    text: str
    text_zh: str | None
    options: list[Option]


@dataclass(frozen=True)
class Participant:
    id: str
    public_code: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    notes: str | None = None
    safety_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DrawnQuestion:
    participant_id: str
    module_id: str
    question: Question
    drawn_at: str | None = None


@dataclass(frozen=True)
class Answer:
    participant_id: str
    question_id: str
    option_id: str
    answered_at: str | None = None


@dataclass(frozen=True)
class VoiceAnswerInterpretation:
    participant_id: str
    question_id: str
    transcript: str
    detected_language: str | None
    stt_confidence: float | None
    stt_metadata: dict[str, Any] = field(default_factory=dict)
    attempt_id: str | None = None
    inferred_option_id: str | None = None
    llm_confidence: float | None = None
    reason_zh: str | None = None
    reason_en: str | None = None
    raw_llm_json: dict[str, Any] = field(default_factory=dict)
    status: str = "failed"
    interpretation_id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class ObservationEvent:
    participant_id: str
    event_type: str
    confidence: float = 1.0
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime | None = None


@dataclass(frozen=True)
class Assignment:
    participant_id: str
    food_code: str
    food_label: str
    ai_trace_score: float
    relational_score: float
    rationale: dict[str, Any]
    assignment_id: int | None = None
    assigned_at: str | None = None
