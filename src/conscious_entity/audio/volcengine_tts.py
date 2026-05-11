from __future__ import annotations

import uuid
import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioRuntimeError, SynthesisEvent
from conscious_entity.audio.volcengine_protocol import (
    EVENT_CONNECTION_STARTED,
    EVENT_SESSION_FINISHED,
    EVENT_SESSION_STARTED,
    VolcengineProtocol,
)
from conscious_entity.telemetry.latency import record_audio_latency


class VolcengineTTSClient:
    def __init__(self, config: AudioConfig, protocol: VolcengineProtocol | None = None) -> None:
        self.config = config
        self.protocol = protocol or VolcengineProtocol()
        self.last_logid: str | None = None

    async def synthesize_stream(self, text_segments: list[str]) -> AsyncIterator[bytes]:
        websockets = _import_websockets()
        headers = self.protocol.build_headers(
            self.config,
            resource_id=self.config.tts_resource_id,
            service="tts",
        )
        session_id = uuid.uuid4().hex
        start = time.perf_counter()
        try:
            async with _connect(websockets, self.config.tts_endpoint, headers) as websocket:
                self.last_logid = _response_header(websocket, "X-Tt-Logid")
                record_audio_latency(
                    "tts.connect",
                    (time.perf_counter() - start) * 1000,
                    metadata={"logid": self.last_logid},
                )
                await websocket.send(self.protocol.build_tts_start_connection())
                await self._expect_event(websocket, {EVENT_CONNECTION_STARTED})
                record_audio_latency(
                    "tts.connection_ready",
                    (time.perf_counter() - start) * 1000,
                    metadata={"logid": self.last_logid},
                )

                await websocket.send(
                    self.protocol.build_tts_start_session(self.config, session_id=session_id)
                )
                await self._expect_event(websocket, {EVENT_SESSION_STARTED})
                record_audio_latency(
                    "tts.session_ready",
                    (time.perf_counter() - start) * 1000,
                    metadata={"session_id": session_id, "logid": self.last_logid},
                )

                for segment in text_segments:
                    await websocket.send(
                        self.protocol.build_tts_task_request(
                            session_id=session_id,
                            text=segment,
                        )
                    )

                await websocket.send(self.protocol.build_tts_finish_session(session_id=session_id))
                async for chunk in self._receive_audio(websocket):
                    yield chunk

                await websocket.send(self.protocol.build_tts_finish_connection())
        except AudioRuntimeError:
            raise
        except Exception as exc:
            record_audio_latency(
                "tts.connect_or_protocol_error",
                (time.perf_counter() - start) * 1000,
                success=False,
                error=exc.__class__.__name__,
            )
            raise AudioRuntimeError("tts_connect_failed", str(exc)) from exc

    async def _receive_audio(self, websocket: Any) -> AsyncIterator[bytes]:
        while True:
            message = await websocket.recv()
            event = self.protocol.parse_tts_message(message)
            self._raise_if_error(event)
            if event.audio:
                yield event.audio
            if event.done or event.event_code == EVENT_SESSION_FINISHED:
                return

    async def _expect_event(self, websocket: Any, event_codes: set[int]) -> SynthesisEvent:
        while True:
            message = await asyncio.wait_for(websocket.recv(), timeout=8.0)
            event = self.protocol.parse_tts_message(message)
            self._raise_if_error(event)
            if event.event_code in event_codes:
                return event

    def _raise_if_error(self, event: SynthesisEvent) -> None:
        if event.logid:
            self.last_logid = event.logid
        if self.last_logid and event.error is not None and event.error.logid is None:
            raise AudioRuntimeError(event.error.code, event.error.message, logid=self.last_logid)
        if event.error is not None:
            raise AudioRuntimeError(
                event.error.code,
                event.error.message,
                logid=event.error.logid,
            )


def _import_websockets() -> Any:
    try:
        import websockets
    except ImportError as exc:
        raise AudioRuntimeError(
            "audio_dependency_missing",
            'websockets is not installed. Install with pip install -e ".[api,audio]".',
        ) from exc
    return websockets


def _connect(websockets: Any, endpoint: str, headers: dict[str, str]) -> Any:
    try:
        return websockets.connect(endpoint, additional_headers=headers, max_size=None)
    except TypeError:
        return websockets.connect(endpoint, extra_headers=headers, max_size=None)


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
