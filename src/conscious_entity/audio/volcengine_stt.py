from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, AudioRuntimeError, TranscriptEvent
from conscious_entity.audio.volcengine_protocol import VolcengineProtocol
from conscious_entity.audio.volcengine_tts import _connect, _import_websockets
from conscious_entity.telemetry.latency import record_audio_latency


class VolcengineSTTClient:
    def __init__(self, config: AudioConfig, protocol: VolcengineProtocol | None = None) -> None:
        self.config = config
        self.protocol = protocol or VolcengineProtocol()
        self.last_logid: str | None = None

    async def stream_pcm(
        self,
        audio_chunks: AsyncIterator[bytes],
        *,
        session_id: str,
    ) -> AsyncIterator[TranscriptEvent]:
        websockets = _import_websockets()
        headers = self.protocol.build_headers(
            self.config,
            resource_id=self.config.stt_resource_id,
            service="asr",
        )
        start = time.perf_counter()
        try:
            async with _connect(websockets, self.config.stt_endpoint, headers) as websocket:
                self.last_logid = _response_header(websocket, "X-Tt-Logid")
                record_audio_latency(
                    "stt.connect",
                    (time.perf_counter() - start) * 1000,
                    metadata={"session_id": session_id, "logid": self.last_logid},
                )
                await websocket.send(
                    self.protocol.build_stt_start_packet(self.config, session_id=session_id)
                )
                sequence = 0
                async for chunk in audio_chunks:
                    sequence += 1
                    await websocket.send(
                        self.protocol.build_stt_audio_packet(chunk, sequence=sequence)
                    )
                    async for event in self._drain_available(websocket, session_id=session_id):
                        yield event
                await websocket.send(self.protocol.build_stt_final_packet(session_id=session_id))
                async for event in self._drain_until_timeout(websocket, session_id=session_id):
                    yield event
        except AudioRuntimeError:
            raise
        except Exception as exc:
            record_audio_latency(
                "stt.connect_or_protocol_error",
                (time.perf_counter() - start) * 1000,
                success=False,
                error=exc.__class__.__name__,
                metadata={"session_id": session_id, "logid": self.last_logid},
            )
            raise AudioRuntimeError("stt_connect_failed", str(exc)) from exc

    async def _drain_available(
        self,
        websocket: Any,
        *,
        session_id: str,
    ) -> AsyncIterator[TranscriptEvent]:
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.01)
            except asyncio.TimeoutError:
                return
            except Exception as exc:
                if _is_normal_websocket_close(exc):
                    return
                raise
            event = self.protocol.parse_stt_response(message, session_id=session_id)
            yielded = self._event_or_raise(event)
            if yielded is not None:
                yield yielded

    async def _drain_until_timeout(
        self,
        websocket: Any,
        *,
        session_id: str,
    ) -> AsyncIterator[TranscriptEvent]:
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                return
            except Exception as exc:
                if _is_normal_websocket_close(exc):
                    return
                raise
            event = self.protocol.parse_stt_response(message, session_id=session_id)
            yielded = self._event_or_raise(event)
            if yielded is not None:
                yield yielded
                if yielded.is_final:
                    return

    def _event_or_raise(
        self,
        event: TranscriptEvent | AudioError | None,
    ) -> TranscriptEvent | None:
        if event is None:
            return None
        if isinstance(event, AudioError):
            raise AudioRuntimeError(event.code, event.message, logid=event.logid)
        if self.last_logid and event.logid is None:
            event = TranscriptEvent(
                text=event.text,
                is_final=event.is_final,
                session_id=event.session_id,
                logid=self.last_logid,
            )
        if event.logid:
            self.last_logid = event.logid
        return event


def _response_header(websocket: Any, name: str) -> str | None:
    headers = getattr(websocket, "response_headers", None)
    if headers is not None:
        value = _headers_get(headers, name)
        if value:
            return value
    response = getattr(websocket, "response", None)
    response_headers = getattr(response, "headers", None)
    if response_headers is not None:
        return _headers_get(response_headers, name)
    return None


def _headers_get(headers: Any, name: str) -> str | None:
    for key in (name, name.lower()):
        try:
            value = headers.get(key)
        except Exception:
            value = None
        if value:
            return str(value)
    return None


def _is_normal_websocket_close(exc: Exception) -> bool:
    return exc.__class__.__name__ == "ConnectionClosedOK"
