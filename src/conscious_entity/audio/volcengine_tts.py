from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioRuntimeError
from conscious_entity.audio.volcengine_protocol import VolcengineProtocol


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
        )
        for segment in text_segments:
            request_id = uuid.uuid4().hex
            try:
                async with _connect(websockets, self.config.tts_endpoint, headers) as websocket:
                    await websocket.send(
                        self.protocol.build_tts_request(
                            self.config,
                            text=segment,
                            request_id=request_id,
                        )
                    )
                    async for chunk in self._receive_audio(websocket):
                        yield chunk
            except AudioRuntimeError:
                raise
            except Exception as exc:
                raise AudioRuntimeError("tts_connect_failed", str(exc)) from exc

    async def _receive_audio(self, websocket: Any) -> AsyncIterator[bytes]:
        while True:
            message = await websocket.recv()
            event = self.protocol.parse_tts_message(message)
            if event.logid:
                self.last_logid = event.logid
            if event.error is not None:
                raise AudioRuntimeError(
                    event.error.code,
                    event.error.message,
                    logid=event.error.logid,
                )
            if event.audio:
                yield event.audio
            if event.done:
                return


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
