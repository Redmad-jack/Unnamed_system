from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets

from have_some_ai.doubao.tts_protocol import (
    TTSEvent,
    TTS_CANCEL_SESSION,
    TTS_CONNECTION_FINISHED,
    TTS_CONNECTION_STARTED,
    TTS_FINISH_CONNECTION,
    TTS_FINISH_SESSION,
    TTS_RESPONSE,
    TTS_SESSION_CANCELED,
    TTS_SESSION_FINISHED,
    TTS_SESSION_STARTED,
    TTS_START_CONNECTION,
    TTS_START_SESSION,
    TTS_TASK_REQUEST,
    DoubaoTTSProtocolError,
    encode_event_payload,
    parse_tts_response,
)


_DEFAULT_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
_DEFAULT_RESOURCE_ID = "seed-icl-2.0"
_FIXED_SPEAKER = "S_ud9II0522"


@dataclass(frozen=True)
class DoubaoTTSConfig:
    endpoint: str = _DEFAULT_ENDPOINT
    resource_id: str = _DEFAULT_RESOURCE_ID
    api_key: str = ""
    speaker: str = _FIXED_SPEAKER
    audio_format: str = "pcm"
    sample_rate: int = 24000
    speech_rate: int = 0
    loudness_rate: int = 0
    additions: str = "{\"disable_markdown_filter\":true,\"enable_language_detector\":false}"

    @classmethod
    def from_env(cls) -> "DoubaoTTSConfig":
        api_key = os.getenv("DOUBAO_TTS_API_KEY") or os.getenv("DOUBAO_API_KEY") or ""
        return cls(
            endpoint=os.getenv("DOUBAO_TTS_ENDPOINT", _DEFAULT_ENDPOINT),
            resource_id=os.getenv("DOUBAO_TTS_RESOURCE_ID", _DEFAULT_RESOURCE_ID),
            api_key=api_key,
            speaker=_FIXED_SPEAKER,
            audio_format=os.getenv("DOUBAO_TTS_AUDIO_FORMAT", "pcm"),
            sample_rate=_int_env("DOUBAO_TTS_SAMPLE_RATE", 24000),
            speech_rate=_int_env("DOUBAO_TTS_SPEECH_RATE", 0),
            loudness_rate=_int_env("DOUBAO_TTS_LOUDNESS_RATE", 0),
        )

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ValueError("Missing DOUBAO_TTS_API_KEY or DOUBAO_API_KEY")
        return self.api_key

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def headers(self, connect_id: str) -> dict[str, str]:
        return {
            "X-Api-Key": self.require_api_key(),
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": connect_id,
            "X-Control-Require-Usage-Tokens-Return": "text_words",
        }


ConnectFn = Callable[[str, dict[str, str]], Awaitable[Any]]


class DoubaoTTSBidirectionalClient:
    def __init__(
        self,
        config: DoubaoTTSConfig | None = None,
        *,
        uid: str | None = None,
        connect: ConnectFn | None = None,
    ) -> None:
        self.config = config or DoubaoTTSConfig.from_env()
        self.uid = uid or "have-some-ai"
        self.connect_id = str(uuid.uuid4())
        self.provider_log_id: str | None = None
        self.connection_id: str | None = None
        self.current_session_id: str | None = None
        self._connect = connect or _connect_websocket
        self._ws: Any = None
        self._connected = False
        self._session_started = False
        self._session_finishing = False
        self._session_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._ws is not None and self._connected:
            return
        if self._ws is None:
            self._ws = await self._connect(self.config.endpoint, self.headers())
            self.provider_log_id = _websocket_response_header(self._ws, "X-Tt-Logid")
        await self._send(TTS_START_CONNECTION, {}, session_id=None)
        event = await self._wait_for({TTS_CONNECTION_STARTED}, timeout_seconds=8.0)
        self.connection_id = event.connection_id
        self._connected = True

    def headers(self) -> dict[str, str]:
        return self.config.headers(self.connect_id)

    async def synthesize(self, text: str) -> AsyncIterator[TTSEvent]:
        clean_text = text.strip()
        if not clean_text:
            return
        async with self._session_lock:
            await self.connect()
            session_id = str(uuid.uuid4())
            self.current_session_id = session_id
            self._session_started = False
            self._session_finishing = False
            try:
                await self._send(TTS_START_SESSION, self.start_session_payload(), session_id=session_id)
                started = await self._wait_for(
                    {TTS_SESSION_STARTED},
                    timeout_seconds=8.0,
                    session_id=session_id,
                )
                self._session_started = True
                yield started
                await self._send(
                    TTS_TASK_REQUEST,
                    self.task_request_payload(clean_text),
                    session_id=session_id,
                )
                await self._send(TTS_FINISH_SESSION, {}, session_id=session_id)
                self._session_finishing = True
                while True:
                    event = await asyncio.wait_for(self._recv_event(), timeout=30.0)
                    if event.session_id not in {None, session_id}:
                        continue
                    yield event
                    if event.event == TTS_SESSION_FINISHED:
                        return
                    if event.event == TTS_SESSION_CANCELED:
                        return
            finally:
                self.current_session_id = None
                self._session_started = False
                self._session_finishing = False

    def start_session_payload(self) -> dict[str, Any]:
        return {
            "event": TTS_START_SESSION,
            "namespace": "BidirectionalTTS",
            "user": {"uid": self.uid},
            "req_params": {
                "speaker": _FIXED_SPEAKER,
                "audio_params": {
                    "format": self.config.audio_format,
                    "sample_rate": self.config.sample_rate,
                    "speech_rate": self.config.speech_rate,
                    "loudness_rate": self.config.loudness_rate,
                },
                "additions": self.config.additions,
                "text": "",
            },
        }

    def task_request_payload(self, text: str) -> dict[str, Any]:
        return {
            "event": TTS_TASK_REQUEST,
            "namespace": "BidirectionalTTS",
            "user": {"uid": self.uid},
            "req_params": {"text": text},
        }

    async def cancel_current_session(self) -> None:
        session_id = self.current_session_id
        if not session_id or not self._session_started or self._session_finishing:
            return
        await self._send(TTS_CANCEL_SESSION, {}, session_id=session_id)

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            if self.current_session_id and self._session_started and not self._session_finishing:
                await self.cancel_current_session()
            if self._connected:
                await self._send(TTS_FINISH_CONNECTION, {}, session_id=None)
                try:
                    await self._wait_for({TTS_CONNECTION_FINISHED}, timeout_seconds=2.0)
                except Exception:
                    pass
        finally:
            close = getattr(self._ws, "close", None)
            if close is not None:
                await close()
            self._ws = None
            self._connected = False

    async def _send(
        self,
        event: int,
        payload: dict[str, Any] | None,
        *,
        session_id: str | None,
    ) -> None:
        async with self._send_lock:
            await self._ws.send(encode_event_payload(event, payload, session_id=session_id))

    async def _wait_for(
        self,
        events: set[int],
        *,
        timeout_seconds: float,
        session_id: str | None = None,
    ) -> TTSEvent:
        while True:
            event = await asyncio.wait_for(self._recv_event(), timeout=timeout_seconds)
            if session_id is not None and event.session_id not in {None, session_id}:
                continue
            if event.event in events:
                return event

    async def _recv_event(self) -> TTSEvent:
        message = await self._ws.recv()
        return parse_tts_response(message, log_id=self.provider_log_id)


async def _connect_websocket(url: str, headers: dict[str, str]) -> Any:
    try:
        return await websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, max_size=None)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _websocket_response_header(ws: Any, name: str) -> str | None:
    response = getattr(ws, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(ws, "response_headers", None)
    getter = getattr(headers, "get", None) if headers is not None else None
    if getter is None:
        return None
    value = getter(name) or getter(name.lower())
    return str(value) if value else None
