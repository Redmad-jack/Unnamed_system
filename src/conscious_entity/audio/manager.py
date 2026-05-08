from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.speech_text import extract_speakable_text, split_for_tts
from conscious_entity.audio.types import (
    AudioError,
    AudioRuntimeError,
    STTSession,
    TTSStream,
    TranscriptEvent,
    utc_now,
)
from conscious_entity.audio.volcengine_protocol import media_type_for_format
from conscious_entity.audio.volcengine_stt import VolcengineSTTClient
from conscious_entity.audio.volcengine_tts import VolcengineTTSClient
from conscious_entity.expression.output_model import ExpressionOutput


class AudioManager:
    def __init__(
        self,
        config: AudioConfig | None = None,
        *,
        stt_client: Any | None = None,
        tts_client: Any | None = None,
    ) -> None:
        self.config = config or AudioConfig.from_env()
        self._stt_client = stt_client
        self._tts_client = tts_client
        self.active_stt_sessions: dict[str, STTSession] = {}
        self.active_tts_streams: dict[str, TTSStream] = {}
        self.last_partial_transcript: str | None = None
        self.last_final_transcript: str | None = None
        self.last_stt_logid: str | None = None
        self.last_tts_logid: str | None = None
        self.last_stream_id: str | None = None
        self.last_error: AudioError | None = None

    @property
    def enabled(self) -> bool:
        return self.config.disabled_reason() is None

    def status(self) -> dict[str, Any]:
        self._prune_expired_streams()
        public = self.config.to_public_dict()
        public["stt"] = {
            **public["stt"],
            "active_sessions": len(self.active_stt_sessions),
            "last_partial_transcript": self.last_partial_transcript,
            "last_final_transcript": self.last_final_transcript,
            "last_logid": self.last_stt_logid,
            "last_error": self.last_error.to_public_dict() if self.last_error else None,
        }
        public["tts"] = {
            **public["tts"],
            "active_streams": len(self.active_tts_streams),
            "last_stream_id": self.last_stream_id,
            "last_logid": self.last_tts_logid,
            "last_error": self.last_error.to_public_dict() if self.last_error else None,
        }
        return public

    def create_stt_session(
        self,
        *,
        sample_rate: int | None = None,
        chunk_ms: int | None = None,
        audio_format: str = "pcm_s16le",
        channels: int = 1,
    ) -> STTSession:
        self._ensure_enabled("stt_unavailable")
        if len(self.active_stt_sessions) >= self.config.max_active_sessions:
            raise AudioRuntimeError("too_many_audio_sessions", "Too many active audio sessions")
        session = STTSession(
            session_id="aud_" + uuid.uuid4().hex,
            created_at=utc_now(),
            sample_rate=sample_rate or self.config.sample_rate,
            chunk_ms=chunk_ms or self.config.chunk_ms,
            format=audio_format,
            channels=channels,
        )
        self.active_stt_sessions[session.session_id] = session
        return session

    def finish_stt_session(self, session_id: str) -> None:
        self.active_stt_sessions.pop(session_id, None)

    def record_transcript_event(self, event: TranscriptEvent) -> None:
        session = self.active_stt_sessions.get(event.session_id)
        if session is not None:
            session.last_logid = event.logid
            if event.is_final:
                session.final_transcript = event.text
            else:
                session.partial_transcript = event.text
        if event.is_final:
            self.last_final_transcript = event.text
        else:
            self.last_partial_transcript = event.text
        if event.logid:
            self.last_stt_logid = event.logid

    def create_tts_stream(
        self,
        output: ExpressionOutput,
        *,
        source: str = "dialog_output",
    ) -> tuple[TTSStream | None, bool]:
        speakable = extract_speakable_text(
            output,
            max_segment_bytes=self.config.tts_max_segment_bytes,
        )
        if not speakable.should_speak:
            return None, False
        if not self.enabled:
            return None, True
        stream = self._new_tts_stream(speakable.segments, source=source)
        return stream, True

    def create_debug_tts_stream(self, text: str) -> TTSStream:
        if not self.config.allow_debug_raw_tts:
            raise AudioRuntimeError(
                "debug_raw_tts_disabled",
                "Raw text TTS is disabled outside debug preview.",
            )
        self._ensure_enabled("tts_unavailable")
        segments = split_for_tts(
            text,
            max_segment_bytes=self.config.tts_max_segment_bytes,
        )
        if not segments:
            raise AudioRuntimeError("tts_empty_text", "No speakable text.")
        return self._new_tts_stream(segments, source="debug_preview")

    def get_tts_stream(self, stream_id: str) -> TTSStream:
        self._prune_expired_streams()
        stream = self.active_tts_streams.get(stream_id)
        if stream is None:
            raise AudioRuntimeError("tts_stream_expired", "TTS stream is unknown or expired.")
        return stream

    async def stream_tts_bytes(self, stream_id: str) -> AsyncIterator[bytes]:
        self._ensure_enabled("tts_unavailable")
        stream = self.get_tts_stream(stream_id)
        client = self._tts_client or VolcengineTTSClient(self.config)
        try:
            async for chunk in client.synthesize_stream(stream.text_segments):
                yield chunk
            stream.consumed = True
            stream.last_logid = getattr(client, "last_logid", None)
            if stream.last_logid:
                self.last_tts_logid = stream.last_logid
        except AudioRuntimeError as exc:
            self.set_error(exc.code, exc.message, logid=exc.logid)
            raise

    async def stream_stt_events(
        self,
        audio_chunks: AsyncIterator[bytes],
        *,
        session_id: str,
    ) -> AsyncIterator[TranscriptEvent]:
        self._ensure_enabled("stt_unavailable")
        client = self._stt_client or VolcengineSTTClient(self.config)
        try:
            async for event in client.stream_pcm(audio_chunks, session_id=session_id):
                self.record_transcript_event(event)
                yield event
        except AudioRuntimeError as exc:
            self.set_error(exc.code, exc.message, logid=exc.logid)
            raise

    def media_type(self) -> str:
        return media_type_for_format(self.config.output_format)

    def set_error(self, code: str, message: str, *, logid: str | None = None) -> None:
        self.last_error = AudioError(code=code, message=_sanitize(message), logid=logid)

    def clear_error(self) -> None:
        self.last_error = None

    def _new_tts_stream(self, segments: list[str], *, source: str) -> TTSStream:
        now = utc_now()
        stream = TTSStream(
            stream_id="tts_" + uuid.uuid4().hex,
            text_segments=segments,
            output_format=self.config.output_format,
            created_at=now,
            expires_at=now + timedelta(seconds=self.config.tts_stream_ttl_seconds),
            source="debug_preview" if source == "debug_preview" else "dialog_output",
        )
        self.active_tts_streams[stream.stream_id] = stream
        self.last_stream_id = stream.stream_id
        return stream

    def _ensure_enabled(self, code: str) -> None:
        reason = self.config.disabled_reason()
        if reason is not None:
            raise AudioRuntimeError(code, reason)

    def _prune_expired_streams(self) -> None:
        now = utc_now()
        expired = [
            stream_id
            for stream_id, stream in self.active_tts_streams.items()
            if stream.expires_at <= now
        ]
        for stream_id in expired:
            self.active_tts_streams.pop(stream_id, None)


def _sanitize(message: str) -> str:
    return message.replace("\n", " ").replace("\r", " ")[:300]
