from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    USER_ENTERED = "user_entered"
    USER_SPOKE = "user_spoke"
    REPEATED_QUESTION_DETECTED = "repeated_question_detected"
    SHUTDOWN_KEYWORD_DETECTED = "shutdown_keyword_detected"
    LONG_SILENCE_DETECTED = "long_silence_detected"
    USER_LEFT = "user_left"
    NEGATIVE_FEEDBACK = "negative_feedback"
    TOPIC_SHIFT = "topic_shift"


@dataclass
class PerceptionEvent:
    event_type: EventType
    raw_text: Optional[str]
    timestamp: datetime
    salience: float  # 0.0–1.0
    metadata: dict = field(default_factory=dict)
