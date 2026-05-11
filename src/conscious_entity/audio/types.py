from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AudioError:
    code: str
    message: str
    logid: str | None = None
    timestamp: datetime = field(default_factory=utc_now)

    def to_public_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "logid": self.logid,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool
    session_id: str
    logid: str | None = None

    @property
    def event_type(self) -> str:
        return "transcript.final" if self.is_final else "transcript.partial"

    def to_public_dict(self) -> dict:
        return {
            "type": self.event_type,
            "session_id": self.session_id,
            "text": self.text,
            "is_final": self.is_final,
            "logid": self.logid,
        }


@dataclass(frozen=True)
class SynthesisEvent:
    audio: bytes | None = None
    done: bool = False
    logid: str | None = None
    error: AudioError | None = None
    event_code: int | None = None
    session_id: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class SpeakableText:
    should_speak: bool
    segments: list[str]
    raw_text: str
    normalized_text: str


@dataclass
class STTSession:
    session_id: str
    created_at: datetime
    sample_rate: int
    chunk_ms: int
    format: str = "pcm_s16le"
    channels: int = 1
    partial_transcript: str | None = None
    final_transcript: str | None = None
    last_logid: str | None = None

    def to_public_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "sample_rate": self.sample_rate,
            "chunk_ms": self.chunk_ms,
            "format": self.format,
            "channels": self.channels,
            "partial_transcript": self.partial_transcript,
            "final_transcript": self.final_transcript,
            "last_logid": self.last_logid,
        }


@dataclass
class TTSStream:
    stream_id: str
    text_segments: list[str]
    output_format: str
    created_at: datetime
    expires_at: datetime
    source: Literal["dialog_output", "debug_preview"]
    consumed: bool = False
    last_logid: str | None = None

    def to_public_dict(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "source": self.source,
            "output_format": self.output_format,
            "consumed": self.consumed,
            "last_logid": self.last_logid,
        }


class AudioConfigurationError(RuntimeError):
    pass


class AudioRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, logid: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.logid = logid
