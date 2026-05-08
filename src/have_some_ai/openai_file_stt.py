from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx


_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "whisper-large-v3"
_MIME_FILENAMES = {
    "audio/webm": "answer.webm",
    "audio/mp4": "answer.mp4",
    "audio/mpeg": "answer.mp3",
    "audio/wav": "answer.wav",
}


@dataclass(frozen=True)
class FileTranscriptionResult:
    text: str
    detected_language: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class OpenAIFileTranscription:
    """OpenAI-compatible file transcription client used by AIHubMix file STT."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or _voice_api_key()
        self._base_url = _voice_base_url(base_url)

    def transcribe(
        self,
        audio: bytes,
        *,
        mime_type: str,
        duration_ms: int | None = None,
    ) -> FileTranscriptionResult:
        if not self._api_key:
            raise ValueError(
                "Missing HAVE_SOME_AI_VOICE_API_KEY or OPENAI_API_KEY "
                "for file transcription"
            )
        if not audio:
            raise ValueError("Audio payload is empty")

        filename = filename_for_mime_type(mime_type)
        normalized_mime = normalize_mime_type(mime_type)
        model = os.getenv("HAVE_SOME_AI_STT_MODEL", _DEFAULT_MODEL)
        language = _stt_language()
        data: dict[str, str] = {
            "model": model,
            "response_format": "json",
            "temperature": "0.2",
        }
        if language:
            data["language"] = language

        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=data,
                files={"file": (filename, audio, normalized_mime)},
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Transcription response must be a JSON object")
        confidence = payload.get("confidence")
        return FileTranscriptionResult(
            text=str(payload.get("text") or payload.get("transcript") or "").strip(),
            detected_language=(
                str(payload.get("language")) if payload.get("language") else language
            ),
            confidence=float(confidence) if confidence is not None else None,
            metadata={
                "provider": os.getenv("HAVE_SOME_AI_VOICE_PROVIDER", "openai-compatible"),
                "stt_mode": "file",
                "stt_model": model,
                "language": language,
                "duration_ms": duration_ms,
                "mime_type": normalized_mime,
                "filename": filename,
                "raw_response": payload,
            },
        )


def normalize_mime_type(mime_type: str) -> str:
    normalized = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized not in _MIME_FILENAMES:
        raise ValueError(f"Unsupported audio MIME type: {mime_type}")
    return normalized


def filename_for_mime_type(mime_type: str) -> str:
    return _MIME_FILENAMES[normalize_mime_type(mime_type)]


def _stt_language() -> str | None:
    value = os.getenv("HAVE_SOME_AI_STT_LANGUAGE")
    return value.strip() if value and value.strip() else None


def _voice_api_key() -> str | None:
    return os.getenv("HAVE_SOME_AI_VOICE_API_KEY") or os.getenv("OPENAI_API_KEY")


def _voice_base_url(base_url: str | None = None) -> str:
    value = (
        base_url
        or os.getenv("HAVE_SOME_AI_VOICE_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or _DEFAULT_BASE_URL
    )
    return value.rstrip("/")
