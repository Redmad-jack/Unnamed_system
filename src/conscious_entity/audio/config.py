from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_STT_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
DEFAULT_STT_RESOURCE_ID = "volc.seedasr.sauc.concurrent"
DEFAULT_TTS_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
DEFAULT_TTS_RESOURCE_ID = "seed-tts-2.0"


@dataclass(frozen=True)
class AudioConfig:
    provider: str = "disabled"
    enabled: bool = False
    auth_mode: str = "api_key"
    api_key: str | None = None
    app_id: str | None = None
    access_token: str | None = None
    stt_endpoint: str = DEFAULT_STT_ENDPOINT
    stt_resource_id: str = DEFAULT_STT_RESOURCE_ID
    sample_rate: int = 16000
    chunk_ms: int = 200
    tts_endpoint: str = DEFAULT_TTS_ENDPOINT
    tts_resource_id: str = DEFAULT_TTS_RESOURCE_ID
    tts_voice_type: str | None = None
    output_format: str = "mp3"
    tts_max_segment_bytes: int = 800
    tts_stream_ttl_seconds: int = 120
    max_active_sessions: int = 4
    queue_max_chunks: int = 8
    allow_debug_raw_tts: bool = False

    @classmethod
    def from_env(cls) -> AudioConfig:
        return cls(
            provider=os.getenv("ENTITY_AUDIO_PROVIDER", "disabled").strip().lower() or "disabled",
            enabled=_env_flag("ENTITY_AUDIO_ENABLED", default=False),
            auth_mode=os.getenv("ENTITY_VOLCENGINE_AUTH_MODE", "api_key").strip().lower() or "api_key",
            api_key=_blank_to_none(os.getenv("ENTITY_VOLCENGINE_API_KEY")),
            app_id=_blank_to_none(os.getenv("ENTITY_VOLCENGINE_APP_ID")),
            access_token=_blank_to_none(os.getenv("ENTITY_VOLCENGINE_ACCESS_TOKEN")),
            stt_endpoint=os.getenv("ENTITY_VOLCENGINE_STT_ENDPOINT", DEFAULT_STT_ENDPOINT).strip() or DEFAULT_STT_ENDPOINT,
            stt_resource_id=os.getenv("ENTITY_VOLCENGINE_STT_RESOURCE_ID", DEFAULT_STT_RESOURCE_ID).strip() or DEFAULT_STT_RESOURCE_ID,
            sample_rate=_env_int("ENTITY_AUDIO_SAMPLE_RATE", 16000, minimum=8000, maximum=48000),
            chunk_ms=_env_int("ENTITY_AUDIO_CHUNK_MS", 200, minimum=50, maximum=1000),
            tts_endpoint=os.getenv("ENTITY_VOLCENGINE_TTS_ENDPOINT", DEFAULT_TTS_ENDPOINT).strip() or DEFAULT_TTS_ENDPOINT,
            tts_resource_id=os.getenv("ENTITY_VOLCENGINE_TTS_RESOURCE_ID", DEFAULT_TTS_RESOURCE_ID).strip() or DEFAULT_TTS_RESOURCE_ID,
            tts_voice_type=_blank_to_none(os.getenv("ENTITY_VOLCENGINE_TTS_VOICE_TYPE")),
            output_format=_normalize_output_format(os.getenv("ENTITY_AUDIO_OUTPUT_FORMAT", "mp3")),
            tts_max_segment_bytes=_env_int("ENTITY_AUDIO_TTS_MAX_SEGMENT_BYTES", 800, minimum=80, maximum=8000),
            tts_stream_ttl_seconds=_env_int("ENTITY_AUDIO_TTS_STREAM_TTL_SECONDS", 120, minimum=10, maximum=3600),
            max_active_sessions=_env_int("ENTITY_AUDIO_MAX_ACTIVE_SESSIONS", 4, minimum=1, maximum=32),
            queue_max_chunks=_env_int("ENTITY_AUDIO_QUEUE_MAX_CHUNKS", 8, minimum=1, maximum=256),
            allow_debug_raw_tts=_env_flag("ENTITY_AUDIO_ALLOW_DEBUG_RAW_TTS", default=False),
        )

    def dependency_status(self) -> dict[str, Any]:
        missing = []
        if importlib.util.find_spec("websockets") is None:
            missing.append("websockets")
        return {
            "available": not missing,
            "missing": missing,
            "websockets": "available" if "websockets" not in missing else "missing",
        }

    def credentials_configured(self) -> bool:
        return bool(self.api_key or (self.app_id and self.access_token))

    def disabled_reason(self) -> str | None:
        if not self.enabled or self.provider in {"", "disabled", "none"}:
            return "audio_provider_disabled"
        if self.provider != "volcengine":
            return "unsupported_provider"
        deps = self.dependency_status()
        if not deps["available"]:
            return "audio_dependency_missing"
        if not self.credentials_configured():
            return "missing_volcengine_credentials"
        if not self.stt_resource_id:
            return "missing_stt_resource_id"
        if not self.tts_resource_id:
            return "missing_tts_resource_id"
        if not self.tts_voice_type:
            return "missing_tts_voice_type"
        if self.sample_rate <= 0:
            return "invalid_sample_rate"
        return None

    def to_public_dict(self) -> dict[str, Any]:
        reason = self.disabled_reason()
        return {
            "provider": self.provider,
            "enabled": reason is None,
            "reason": reason,
            "dependencies": self.dependency_status(),
            "auth": {
                "mode": "api_key" if self.api_key else "app_token" if self.app_id and self.access_token else self.auth_mode,
                "api_key": _redact(self.api_key),
                "app_id": _redact(self.app_id),
                "access_token": _redact(self.access_token),
            },
            "stt": {
                "configured": reason is None or reason == "missing_tts_voice_type",
                "endpoint": self.stt_endpoint,
                "resource_id": self.stt_resource_id,
                "sample_rate": self.sample_rate,
                "chunk_ms": self.chunk_ms,
            },
            "tts": {
                "configured": reason is None,
                "endpoint": self.tts_endpoint,
                "resource_id": self.tts_resource_id,
                "voice_type": self.tts_voice_type,
                "output_format": self.output_format,
                "ttl_seconds": self.tts_stream_ttl_seconds,
            },
            "runtime": {
                "max_active_sessions": self.max_active_sessions,
                "queue_max_chunks": self.queue_max_chunks,
                "allow_debug_raw_tts": self.allow_debug_raw_tts,
            },
        }


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _normalize_output_format(value: str | None) -> str:
    cleaned = (value or "mp3").strip().lower()
    if cleaned in {"mp3", "ogg_opus", "pcm"}:
        return cleaned
    if cleaned == "ogg":
        return "ogg_opus"
    return "mp3"


def _redact(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 12:
        return "***"
    return value[:6] + "..." + value[-6:]
