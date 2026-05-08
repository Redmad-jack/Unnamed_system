from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, AudioRuntimeError, TranscriptEvent
from conscious_entity.audio.volcengine_protocol import VolcengineProtocol
from conscious_entity.audio.volcengine_tts import _connect, _import_websockets


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
        )
        try:
            async with _connect(websockets, self.config.stt_endpoint, headers) as websocket:
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
        if event.logid:
            self.last_logid = event.logid
        return event
