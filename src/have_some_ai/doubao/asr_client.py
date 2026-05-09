from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets

from have_some_ai.doubao.asr_protocol import (
    ASRTranscriptEvent,
    encode_audio_request,
    encode_full_client_request,
    parse_server_response,
    transcript_events_from_payload,
)


_DEFAULT_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
_DEFAULT_RESOURCE_ID = "volc.seedasr.sauc.duration"


@dataclass(frozen=True)
class DoubaoASRConfig:
    endpoint: str = _DEFAULT_ENDPOINT
    resource_id: str = _DEFAULT_RESOURCE_ID
    api_key: str = ""
    enable_nonstream: bool = True
    end_window_size_ms: int = 800
    force_to_speech_time_ms: int = 1000
    result_type: str = "single"
    audio_format: str = "pcm"
    sample_rate: int = 16000
    bits: int = 16
    channels: int = 1

    @classmethod
    def from_env(cls) -> "DoubaoASRConfig":
        api_key = os.getenv("DOUBAO_ASR_API_KEY") or os.getenv("DOUBAO_API_KEY") or ""
        return cls(
            endpoint=os.getenv("DOUBAO_ASR_ENDPOINT", _DEFAULT_ENDPOINT),
            resource_id=os.getenv("DOUBAO_ASR_RESOURCE_ID", _DEFAULT_RESOURCE_ID),
            api_key=api_key,
            enable_nonstream=_env_flag("DOUBAO_ASR_ENABLE_NONSTREAM", True),
            end_window_size_ms=_int_env("DOUBAO_ASR_END_WINDOW_SIZE_MS", 800),
            force_to_speech_time_ms=_int_env("DOUBAO_ASR_FORCE_TO_SPEECH_TIME_MS", 1000),
            result_type=os.getenv("DOUBAO_ASR_RESULT_TYPE", "single"),
            audio_format=os.getenv("DOUBAO_ASR_AUDIO_FORMAT", "pcm"),
            sample_rate=16000,
            bits=16,
            channels=_int_env("DOUBAO_ASR_CHANNELS", 1),
        )

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ValueError("Missing DOUBAO_ASR_API_KEY or DOUBAO_API_KEY")
        return self.api_key


ConnectFn = Callable[[str, dict[str, str]], Awaitable[Any]]


class DoubaoASRClient:
    def __init__(
        self,
        config: DoubaoASRConfig | None = None,
        *,
        uid: str | None = None,
        connect: ConnectFn | None = None,
    ) -> None:
        self.config = config or DoubaoASRConfig.from_env()
        self.uid = uid or "have-some-ai"
        self.request_id = str(uuid.uuid4())
        self.connect_id = str(uuid.uuid4())
        self.provider_log_id: str | None = None
        self._connect = connect or _connect_websocket
        self._ws: Any = None
        self._finished = False
        self._closed = False
        self._connected_event = asyncio.Event()
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._seen_final_keys: set[tuple[Any, Any, str]] = set()

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._ws is not None:
                return
            self._ws = await self._connect(self.config.endpoint, self.headers())
            self.provider_log_id = _websocket_response_header(self._ws, "X-Tt-Logid")
            await self._ws.send(encode_full_client_request(self.full_request_payload()))
            self._connected_event.set()

    def headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.config.require_api_key(),
            "X-Api-Resource-Id": self.config.resource_id,
            "X-Api-Request-Id": self.request_id,
            "X-Api-Sequence": "-1",
            "X-Api-Connect-Id": self.connect_id,
        }

    def full_request_payload(self) -> dict[str, Any]:
        return {
            "user": {"uid": self.uid},
            "audio": {
                "format": self.config.audio_format,
                "codec": "raw",
                "rate": self.config.sample_rate,
                "bits": self.config.bits,
                "channel": self.config.channels,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_nonstream": self.config.enable_nonstream,
                "show_utterances": True,
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
                "result_type": self.config.result_type,
                "end_window_size": self.config.end_window_size_ms,
                "force_to_speech_time": self.config.force_to_speech_time_ms,
            },
        }

    async def append_audio(self, audio: bytes) -> None:
        if not audio or self._finished:
            return
        await self.connect()
        async with self._send_lock:
            await self._ws.send(encode_audio_request(audio))

    async def finish(self, audio: bytes = b"") -> None:
        if self._finished:
            return
        if self._ws is None and not audio:
            self._finished = True
            self._connected_event.set()
            return
        await self.connect()
        self._finished = True
        async with self._send_lock:
            await self._ws.send(encode_audio_request(audio, final=True))

    async def events(self) -> AsyncIterator[ASRTranscriptEvent]:
        while self._ws is None:
            if self._closed or self._finished:
                return
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
        while self._ws is not None:
            message = await self._ws.recv()
            response = parse_server_response(
                message,
                request_id=self.request_id,
                log_id=self.provider_log_id,
            )
            if isinstance(response.payload, dict):
                for event in transcript_events_from_payload(
                    response.payload,
                    seen_final_keys=self._seen_final_keys,
                ):
                    yield event

    async def close(self) -> None:
        self._closed = True
        self._connected_event.set()
        if self._ws is None:
            return
        close = getattr(self._ws, "close", None)
        if close is not None:
            await close()
        self._ws = None


async def _connect_websocket(url: str, headers: dict[str, str]) -> Any:
    try:
        return await websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, max_size=None)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
