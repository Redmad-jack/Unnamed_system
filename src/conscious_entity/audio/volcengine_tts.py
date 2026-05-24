from __future__ import annotations

import uuid
import asyncio
import time
import contextlib
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

    async def open_session(self, *, voice_type: str | None = None) -> VolcengineTTSSession:
        websockets = _import_websockets()
        headers = self.protocol.build_headers(
            self.config,
            resource_id=self.config.tts_resource_id,
            service="tts",
        )
        session_id = uuid.uuid4().hex
        start = time.perf_counter()
        connector = _connect(websockets, self.config.tts_endpoint, headers)
        websocket = None
        try:
            websocket = await connector.__aenter__()
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
                self.protocol.build_tts_start_session(
                    self.config,
                    session_id=session_id,
                    voice_type=voice_type,
                )
            )
            await self._expect_event(websocket, {EVENT_SESSION_STARTED})
            record_audio_latency(
                "tts.session_ready",
                (time.perf_counter() - start) * 1000,
                metadata={"session_id": session_id, "logid": self.last_logid},
            )
            return VolcengineTTSSession(
                client=self,
                connector=connector,
                websocket=websocket,
                session_id=session_id,
            )
        except AudioRuntimeError:
            if websocket is not None:
                await connector.__aexit__(None, None, None)
            raise
        except Exception as exc:
            if websocket is not None:
                await connector.__aexit__(None, None, None)
            record_audio_latency(
                "tts.connect_or_protocol_error",
                (time.perf_counter() - start) * 1000,
                success=False,
                error=exc.__class__.__name__,
            )
            raise AudioRuntimeError("tts_connect_failed", str(exc)) from exc

    async def synthesize_stream(
        self,
        text_segments: list[str],
        *,
        voice_type: str | None = None,
    ) -> AsyncIterator[bytes]:
        session = await self.open_session(voice_type=voice_type)
        try:
            for segment in text_segments:
                await session.send_text(segment)
            await session.finish()
            async for chunk in session.receive_audio():
                yield chunk
        except asyncio.CancelledError:
            await session.interrupt()
            raise
        finally:
            await session.close()

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


class VolcengineTTSSession:
    def __init__(
        self,
        *,
        client: VolcengineTTSClient,
        connector: Any,
        websocket: Any,
        session_id: str,
    ) -> None:
        self.client = client
        self.protocol = client.protocol
        self.websocket = websocket
        self.connector = connector
        self.session_id = session_id
        self.finished = False
        self.interrupted = False
        self.closed = False
        self.connection_finished = False

    async def send_text(self, text: str) -> None:
        if self.finished:
            raise AudioRuntimeError("tts_session_finished", "Cannot send text after finishing TTS session.")
        if self.closed or self.interrupted:
            raise AudioRuntimeError("tts_session_closed", "Cannot send text to a closed TTS session.")
        cleaned = str(text or "").strip()
        if not cleaned:
            return
        await self.websocket.send(
            self.protocol.build_tts_task_request(
                session_id=self.session_id,
                text=cleaned,
            )
        )

    async def finish(self) -> None:
        if self.finished or self.closed:
            return
        self.finished = True
        await self.websocket.send(
            self.protocol.build_tts_finish_session(session_id=self.session_id)
        )

    async def receive_audio(self) -> AsyncIterator[bytes]:
        while True:
            message = await self.websocket.recv()
            event = self.protocol.parse_tts_message(message)
            self.client._raise_if_error(event)
            if event.audio:
                yield event.audio
            if event.done or event.event_code == EVENT_SESSION_FINISHED:
                self.finished = True
                return

    async def interrupt(self) -> None:
        self.interrupted = True
        with contextlib.suppress(Exception):
            await self.websocket.send(
                self.protocol.build_tts_cancel_session(session_id=self.session_id)
            )
        await self.close(send_finish_connection=False)

    async def close(self, *, send_finish_connection: bool = True) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if send_finish_connection and not self.connection_finished and not self.interrupted:
                await self.websocket.send(self.protocol.build_tts_finish_connection())
                self.connection_finished = True
        finally:
            await self.connector.__aexit__(None, None, None)


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
