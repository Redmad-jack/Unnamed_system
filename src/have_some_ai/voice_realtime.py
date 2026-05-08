from __future__ import annotations

import base64
import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import websockets


DOUBAO_START_CONNECTION = 1
DOUBAO_FINISH_CONNECTION = 2
DOUBAO_START_SESSION = 100
DOUBAO_FINISH_SESSION = 102
DOUBAO_TASK_REQUEST = 200
DOUBAO_SAY_HELLO = 300
DOUBAO_END_ASR = 400
DOUBAO_CHAT_TTS_TEXT = 500
DOUBAO_CHAT_TEXT_QUERY = 501
DOUBAO_CLIENT_INTERRUPT = 515

DOUBAO_CONNECTION_STARTED = 50
DOUBAO_CONNECTION_FAILED = 51
DOUBAO_CONNECTION_ENDED = 52
DOUBAO_SESSION_STARTED = 150
DOUBAO_SESSION_FINISHED = 152
DOUBAO_SESSION_FAILED = 153
DOUBAO_TTS_SENTENCE_START = 350
DOUBAO_TTS_SENTENCE_END = 351
DOUBAO_TTS_RESPONSE = 352
DOUBAO_TTS_ENDED = 359
DOUBAO_ASR_INFO = 450
DOUBAO_ASR_RESPONSE = 451
DOUBAO_ASR_ENDED = 459
DOUBAO_CHAT_RESPONSE = 550
DOUBAO_CHAT_TEXT_QUERY_CONFIRMED = 553
DOUBAO_CHAT_ENDED = 559
DOUBAO_DIALOG_COMMON_ERROR = 599

_PROTOCOL_VERSION = 0b0001
_HEADER_SIZE = 0b0001
_FULL_CLIENT_REQUEST = 0b0001
_AUDIO_ONLY_CLIENT_REQUEST = 0b0010
_FULL_SERVER_RESPONSE = 0b1001
_AUDIO_ONLY_SERVER_RESPONSE = 0b1011
_ERROR_RESPONSE = 0b1111
_FLAG_WITH_EVENT = 0b0100
_NO_SERIALIZATION = 0b0000
_JSON_SERIALIZATION = 0b0001
_NO_COMPRESSION = 0b0000

_DEFAULT_WS_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
_DEFAULT_RESOURCE_ID = "volc.speech.dialog"
_DEFAULT_DOUBAO_APP_KEY = "PlgvMymc7f3tQnJ6"
_DEFAULT_DOUBAO_MODEL = "1.2.1.1"
_DEFAULT_DOUBAO_SPEAKER = "zh_female_vv_jupiter_bigtts"
_CLIENT_CONNECTION_EVENT_IDS = {DOUBAO_START_CONNECTION, DOUBAO_FINISH_CONNECTION}
_SERVER_ERROR_EVENTS = {
    DOUBAO_CONNECTION_FAILED,
    DOUBAO_SESSION_FAILED,
    DOUBAO_DIALOG_COMMON_ERROR,
}


@dataclass(frozen=True)
class RealtimeVoiceEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class RealtimeVoiceAdapter:
    async def connect(self) -> None:
        raise NotImplementedError

    async def start_session(
        self,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def append_audio(self, audio: bytes) -> None:
        raise NotImplementedError

    async def end_asr(self) -> None:
        raise NotImplementedError

    async def speak_text(self, text: str) -> None:
        raise NotImplementedError

    async def say_hello(self, text: str) -> None:
        await self.speak_text(text)

    async def interrupt(self) -> None:
        return None

    async def stop_session(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def events(self) -> AsyncIterator[RealtimeVoiceEvent]:
        if False:
            yield RealtimeVoiceEvent("noop")


@dataclass(frozen=True)
class DoubaoRealtimeConfig:
    app_id: str
    app_key: str
    access_token: str
    resource_id: str = _DEFAULT_RESOURCE_ID
    ws_url: str = _DEFAULT_WS_URL
    input_audio_format: str = "pcm_s16le"
    input_sample_rate: int = 16000
    output_audio_format: str = "pcm_s16le"
    output_sample_rate: int = 24000
    dialog_model: str = _DEFAULT_DOUBAO_MODEL
    speaker: str = _DEFAULT_DOUBAO_SPEAKER
    bot_name: str = "Have Some Ai"
    speaking_style: str = "用简短、温和、带一点展览店主感的中文或英文回答。"

    @classmethod
    def from_env(cls) -> "DoubaoRealtimeConfig":
        app_id = _required_env("HAVE_SOME_AI_DOUBAO_APP_ID")
        app_key = os.getenv("HAVE_SOME_AI_DOUBAO_APP_KEY", _DEFAULT_DOUBAO_APP_KEY)
        access_token = _required_env("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN")
        return cls(
            app_id=app_id,
            app_key=app_key,
            access_token=access_token,
            resource_id=os.getenv("HAVE_SOME_AI_DOUBAO_RESOURCE_ID", _DEFAULT_RESOURCE_ID),
            ws_url=os.getenv("HAVE_SOME_AI_DOUBAO_WS_URL", _DEFAULT_WS_URL),
            input_sample_rate=_int_env("HAVE_SOME_AI_DOUBAO_SAMPLE_RATE", 16000),
            output_sample_rate=_int_env("HAVE_SOME_AI_DOUBAO_OUTPUT_SAMPLE_RATE", 24000),
            dialog_model=os.getenv("HAVE_SOME_AI_DOUBAO_MODEL", _DEFAULT_DOUBAO_MODEL),
            speaker=os.getenv("HAVE_SOME_AI_DOUBAO_SPEAKER", _DEFAULT_DOUBAO_SPEAKER),
            bot_name=os.getenv("HAVE_SOME_AI_DOUBAO_BOT_NAME", "Have Some Ai"),
            speaking_style=os.getenv(
                "HAVE_SOME_AI_DOUBAO_SPEAKING_STYLE",
                "用简短、温和、带一点展览店主感的中文或英文回答。",
            ),
        )

    def headers(self, connect_id: str) -> dict[str, str]:
        return {
            "X-Api-App-ID": self.app_id,
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": connect_id,
        }


class DoubaoProtocol:
    """Volcengine WebSocket V3 frame codec for Doubao realtime events.

    The adapter keeps event ids explicit so tests and logs can verify that
    frontend audio frames are mapped to TaskRequest 200; manual stop can still
    send EndASR 400, while the normal mic path uses provider server VAD.
    """

    @staticmethod
    def encode_json(
        event_id: int,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> bytes:
        body = payload or {}
        return DoubaoProtocol._encode_frame(
            event_id=event_id,
            payload=json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            serialization=_JSON_SERIALIZATION,
            session_id=session_id or _event_session_id(event_id, body),
            message_type=_FULL_CLIENT_REQUEST,
        )

    @staticmethod
    def encode_audio(event_id: int, audio: bytes, session_id: str | None = None) -> bytes:
        return DoubaoProtocol._encode_frame(
            event_id=event_id,
            payload=audio,
            serialization=_NO_SERIALIZATION,
            session_id=session_id,
            message_type=_AUDIO_ONLY_CLIENT_REQUEST,
        )

    @staticmethod
    def decode_frame(message: bytes | str) -> dict[str, Any]:
        if isinstance(message, str):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return {"raw": message}
            return payload if isinstance(payload, dict) else {"raw": payload}
        if message.lstrip().startswith(b"{"):
            try:
                payload = json.loads(message.decode("utf-8"))
            except json.JSONDecodeError:
                return {"raw": message.decode("utf-8", errors="ignore")}
            return payload if isinstance(payload, dict) else {"raw": payload}
        if len(message) < 8:
            return {"error": "Invalid Doubao V3 frame"}

        header_size = message[0] & 0x0F
        message_type = (message[1] >> 4) & 0x0F
        flags = message[1] & 0x0F
        serialization = (message[2] >> 4) & 0x0F
        compression = message[2] & 0x0F
        offset = header_size * 4
        event_id: int | None = None
        session_id: str | None = None
        error_code: int | None = None

        if message_type == _ERROR_RESPONSE and (
            flags == 0b1111 or _payload_fits(message, offset + 4)
        ):
            if offset + 4 <= len(message):
                error_code = int.from_bytes(message[offset:offset + 4], "big", signed=True)
                offset += 4

        should_read_event = bool(flags & _FLAG_WITH_EVENT)
        if message_type == _ERROR_RESPONSE and _payload_fits(message, offset):
            should_read_event = False

        if should_read_event:
            if offset + 4 > len(message):
                return {"error": "Invalid Doubao V3 event frame"}
            event_id = int.from_bytes(message[offset:offset + 4], "big", signed=True)
            offset += 4
            if event_id not in _CLIENT_CONNECTION_EVENT_IDS:
                parsed_session, parsed_offset = _try_read_content(message, offset)
                if parsed_session is not None:
                    session_id = parsed_session
                    offset = parsed_offset

        payload = b""
        if offset + 4 <= len(message):
            payload_size = int.from_bytes(message[offset:offset + 4], "big", signed=True)
            offset += 4
            if payload_size >= 0 and offset + payload_size <= len(message):
                payload = message[offset:offset + payload_size]

        frame: dict[str, Any] = {
            "event": event_id,
            "session_id": session_id,
            "message_type": message_type,
            "flags": flags,
            "serialization": serialization,
            "compression": compression,
        }
        if error_code is not None:
            frame["error_code"] = error_code
        if message_type == _ERROR_RESPONSE:
            error_text = payload.decode("utf-8", errors="ignore")
            try:
                parsed_error = json.loads(error_text) if error_text else {}
            except json.JSONDecodeError:
                parsed_error = {}
            if isinstance(parsed_error, dict):
                frame["payload_msg"] = parsed_error
                frame["error"] = (
                    parsed_error.get("error")
                    or parsed_error.get("message")
                    or error_text
                    or "Doubao realtime error"
                )
            else:
                frame["error"] = error_text or "Doubao realtime error"
        elif message_type in {_AUDIO_ONLY_SERVER_RESPONSE, _AUDIO_ONLY_CLIENT_REQUEST}:
            frame["payload_audio"] = base64.b64encode(payload).decode("ascii")
        elif serialization == _JSON_SERIALIZATION and payload:
            try:
                frame["payload_msg"] = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                frame["payload_msg"] = payload.decode("utf-8", errors="ignore")
        elif payload:
            frame["payload_msg"] = payload.decode("utf-8", errors="ignore")
        return frame

    @staticmethod
    def _encode_frame(
        *,
        event_id: int,
        payload: bytes,
        serialization: int,
        session_id: str | None,
        message_type: int,
    ) -> bytes:
        header = bytes([
            (_PROTOCOL_VERSION << 4) | _HEADER_SIZE,
            (message_type << 4) | _FLAG_WITH_EVENT,
            (serialization << 4) | _NO_COMPRESSION,
            0x00,
        ])
        optional = event_id.to_bytes(4, "big", signed=True)
        if session_id:
            session_bytes = session_id.encode("utf-8")
            optional += len(session_bytes).to_bytes(4, "big", signed=True)
            optional += session_bytes
        return (
            header
            + optional
            + len(payload).to_bytes(4, "big", signed=True)
            + payload
        )

    @staticmethod
    def encode_json_debug(event_id: int, payload: dict[str, Any] | None = None) -> bytes:
        return json.dumps(
            {
                "event": event_id,
                "payload_msg": payload or {},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def encode_audio_debug(event_id: int, audio: bytes) -> bytes:
        return json.dumps(
            {
                "event": event_id,
                "payload_audio": base64.b64encode(audio).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def decode(message: bytes | str) -> RealtimeVoiceEvent:
        payload = DoubaoProtocol.decode_frame(message)
        event_id = payload.get("event")
        body = _payload_body(payload)
        if payload.get("payload_audio"):
            return RealtimeVoiceEvent("audio.delta", {
                "audio_base64": str(payload["payload_audio"]),
                "event": event_id,
                "audio_format": "pcm_s16le",
                "sample_rate": 24000,
            })
        if event_id == DOUBAO_ASR_RESPONSE:
            transcript, is_interim = _extract_asr_response(body)
            if transcript:
                return RealtimeVoiceEvent(
                    "transcript.delta" if is_interim else "transcript.final",
                    {
                        "transcript": transcript,
                        "event": event_id,
                        "metadata": body,
                    },
                )
        if event_id == DOUBAO_ASR_INFO:
            return RealtimeVoiceEvent("speech.started", {
                "event": event_id,
                "metadata": body,
            })
        if event_id == DOUBAO_ASR_ENDED:
            return RealtimeVoiceEvent("speech.ended", {
                "event": event_id,
                "metadata": body,
            })
        if event_id == DOUBAO_CHAT_RESPONSE:
            return RealtimeVoiceEvent("chat.delta", {
                "event": event_id,
                "content": str(body.get("content") or ""),
                "metadata": body,
            })
        if "audio" in body:
            return RealtimeVoiceEvent("audio.delta", {
                "audio_base64": str(body.get("audio") or ""),
                "event": event_id,
                "audio_format": body.get("audio_format", "pcm_s16le"),
                "sample_rate": int(body.get("sample_rate") or 24000),
            })
        if event_id is None:
            transcript = body.get("transcript") or body.get("text") or body.get("asr_text")
            if transcript:
                final = bool(body.get("final") or body.get("is_final") or body.get("completed"))
                return RealtimeVoiceEvent(
                    "transcript.final" if final else "transcript.delta",
                    {
                        "transcript": str(transcript),
                        "event": event_id,
                        "metadata": body,
                    },
                )
        if (
            payload.get("error")
            or event_id in _SERVER_ERROR_EVENTS
            or body.get("error")
            or body.get("message")
            or body.get("code") not in {None, 0, "0"}
        ):
            error_body = dict(body)
            if payload.get("error"):
                error_body["error"] = payload["error"]
            return RealtimeVoiceEvent("error", {
                "event": event_id,
                "detail": _safe_error(error_body),
            })
        return RealtimeVoiceEvent("state", {
            "event": event_id,
            "metadata": body,
        })


ConnectFn = Callable[[str, dict[str, str]], Awaitable[Any]]


class DoubaoRealtimeVoiceAdapter(RealtimeVoiceAdapter):
    def __init__(
        self,
        config: DoubaoRealtimeConfig | None = None,
        *,
        connect: ConnectFn | None = None,
    ) -> None:
        self.config = config or DoubaoRealtimeConfig.from_env()
        self.connect_id = str(uuid.uuid4())
        self.session_id: str | None = None
        self.provider_log_id: str | None = None
        self.sent_event_ids: list[int] = []
        self._connect = connect or _connect_websocket
        self._ws: Any = None
        self._connection_started = False
        self._session_started = False

    async def connect(self) -> None:
        if self._ws is not None:
            return
        self._ws = await self._connect(
            self.config.ws_url,
            self.config.headers(self.connect_id),
        )
        self.provider_log_id = _websocket_response_header(self._ws, "X-Tt-Logid")
        await self._send_json(DOUBAO_START_CONNECTION, {})
        await self._wait_for_provider_event(
            success_events={DOUBAO_CONNECTION_STARTED},
            timeout_seconds=5.0,
        )
        self._connection_started = True

    async def start_session(
        self,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        await self.connect()
        self.session_id = session_id or str(uuid.uuid4())
        await self._send_json(
            DOUBAO_START_SESSION,
            build_doubao_start_session_payload(
                self.config,
                system_prompt=system_prompt,
                input_mod=None,
            ),
            session_id=self.session_id,
        )
        await self._wait_for_provider_event(
            success_events={DOUBAO_SESSION_STARTED},
            timeout_seconds=8.0,
        )
        self._session_started = True

    async def append_audio(self, audio: bytes) -> None:
        if not audio:
            return
        await self.connect()
        await self._send_audio(DOUBAO_TASK_REQUEST, audio)

    async def end_asr(self) -> None:
        await self.connect()
        await self._send_json(DOUBAO_END_ASR, {}, session_id=self.session_id)

    async def speak_text(self, text: str) -> None:
        if not text.strip():
            return
        await self.connect()
        await self._send_json(DOUBAO_CHAT_TTS_TEXT, {
            "start": True,
            "content": text,
            "end": False,
        }, session_id=self.session_id)
        await self._send_json(DOUBAO_CHAT_TTS_TEXT, {
            "start": False,
            "content": "",
            "end": True,
        }, session_id=self.session_id)

    async def say_hello(self, text: str) -> None:
        if not text.strip():
            return
        await self.connect()
        await self._send_json(DOUBAO_SAY_HELLO, {
            "content": text,
        }, session_id=self.session_id)

    async def interrupt(self) -> None:
        await self.connect()
        await self._send_json(DOUBAO_CLIENT_INTERRUPT, {}, session_id=self.session_id)

    async def stop_session(self) -> None:
        if self._ws is None:
            return
        await self._send_json(DOUBAO_FINISH_SESSION, {}, session_id=self.session_id)

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._send_json(DOUBAO_FINISH_CONNECTION, {})
        finally:
            close = getattr(self._ws, "close", None)
            if close is not None:
                await close()
            self._ws = None

    async def events(self) -> AsyncIterator[RealtimeVoiceEvent]:
        await self.connect()
        while self._ws is not None:
            try:
                message = await self._ws.recv()
            except Exception as exc:
                yield RealtimeVoiceEvent("error", {"detail": _safe_error({"error": str(exc)})})
                return
            yield DoubaoProtocol.decode(message)

    async def _send_json(
        self,
        event_id: int,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> None:
        self.sent_event_ids.append(event_id)
        await self._send(DoubaoProtocol.encode_json(event_id, payload, session_id=session_id))

    async def _send_audio(self, event_id: int, audio: bytes) -> None:
        self.sent_event_ids.append(event_id)
        await self._send(DoubaoProtocol.encode_audio(event_id, audio, self.session_id))

    async def _send(self, payload: bytes) -> None:
        await self.connect()
        await self._ws.send(payload)

    async def _wait_for_provider_event(
        self,
        *,
        success_events: set[int],
        timeout_seconds: float,
    ) -> RealtimeVoiceEvent:
        if self._ws is None:
            await self.connect()
        while True:
            try:
                message = await asyncio.wait_for(self._ws.recv(), timeout=timeout_seconds)
            except Exception as exc:
                raise RuntimeError(_safe_error({"error": str(exc)})) from exc
            event = DoubaoProtocol.decode(message)
            event_id = event.data.get("event")
            if event.type == "error":
                raise RuntimeError(self._with_provider_log_id(
                    str(event.data.get("detail") or "Doubao realtime error")
                ))
            if event_id in success_events:
                return event

    def _with_provider_log_id(self, detail: str) -> str:
        if not self.provider_log_id or "logid" in detail.lower():
            return detail
        return f"{detail} (X-Tt-Logid={self.provider_log_id})"


async def _connect_websocket(url: str, headers: dict[str, str]) -> Any:
    try:
        return await websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, max_size=None)


def build_realtime_system_prompt(initial_state: dict[str, Any] | None = None) -> str:
    state = initial_state or {}
    return (
        "你是 Have Some Ai 的店主声音。你只负责自然对话、实时转写和朗读。"
        "不要自主回答用户问题，不要主动追问，不要临时加问题。"
        "不要决定 A/B 选项，不要决定食物，不要推荐或发明菜单，不要输出评分 JSON。"
        "每次用户说完后，只产出 transcript；下一句店主回复必须等待后端用 ChatTTSText 或 SayHello 明确下发。"
        "如果 state 里有 assignment，只能承认该系统结果，不能改写成别的食物。"
        f"\nstate={json.dumps(state, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_doubao_start_session_payload(
    config: DoubaoRealtimeConfig,
    *,
    system_prompt: str | None = None,
    input_mod: str | None = None,
    include_model: bool = True,
    include_audio_info: bool = True,
    include_audio_config: bool = True,
    include_empty_extras: bool = True,
) -> dict[str, Any]:
    dialog_extra: dict[str, Any] = {}
    if input_mod:
        dialog_extra["input_mod"] = input_mod
    if include_model:
        dialog_extra["model"] = config.dialog_model

    dialog: dict[str, Any] = {
        "bot_name": config.bot_name,
        "system_role": system_prompt or "",
        "speaking_style": config.speaking_style,
        "extra": dialog_extra,
    }
    asr: dict[str, Any] = {}
    if include_audio_info:
        asr["audio_info"] = {
            "format": config.input_audio_format,
            "sample_rate": config.input_sample_rate,
            "channel": 1,
        }
    if include_empty_extras:
        asr["extra"] = {}

    tts: dict[str, Any] = {
        "speaker": config.speaker,
    }
    if include_audio_config:
        tts["audio_config"] = {
            "channel": 1,
            "format": config.output_audio_format,
            "sample_rate": config.output_sample_rate,
        }
    if include_empty_extras:
        tts["extra"] = {}

    return {
        "dialog": dialog,
        "asr": asr,
        "tts": tts,
    }


def _event_session_id(event_id: int, payload: dict[str, Any]) -> str | None:
    if event_id in _CLIENT_CONNECTION_EVENT_IDS:
        return None
    session_id = payload.get("session_id")
    return str(session_id) if session_id else None


def _extract_asr_response(body: dict[str, Any]) -> tuple[str, bool]:
    results = body.get("results")
    if isinstance(results, list):
        texts: list[str] = []
        interim = False
        for item in results:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if text:
                texts.append(str(text))
            interim = interim or bool(item.get("is_interim"))
        return " ".join(text.strip() for text in texts if text and text.strip()).strip(), interim
    text = body.get("text") or body.get("transcript") or body.get("asr_text")
    if not text:
        return "", False
    return str(text).strip(), bool(body.get("is_interim"))


def _try_read_content(message: bytes, offset: int) -> tuple[str | None, int]:
    if offset + 4 > len(message):
        return None, offset
    content_size = int.from_bytes(message[offset:offset + 4], "big", signed=True)
    content_offset = offset + 4
    if content_size < 0 or content_offset + content_size > len(message):
        return None, offset
    try:
        return message[content_offset:content_offset + content_size].decode("utf-8"), (
            content_offset + content_size
        )
    except UnicodeDecodeError:
        return None, offset


def _payload_fits(message: bytes, offset: int) -> bool:
    if offset + 4 > len(message):
        return False
    payload_size = int.from_bytes(message[offset:offset + 4], "big", signed=True)
    return payload_size >= 0 and offset + 4 + payload_size <= len(message)


def _payload_body(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("payload_msg")
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return {"text": body}
        return parsed if isinstance(parsed, dict) else {"text": body}
    if isinstance(body, dict):
        return body
    return payload


def _safe_error(payload: dict[str, Any]) -> str:
    text = str(payload.get("error") or payload.get("message") or payload.get("detail") or payload)
    for key in (
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_ID"),
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_KEY"),
        os.getenv("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN"),
    ):
        if key:
            text = text.replace(key, "[redacted]")
    if len(text) > 500:
        return f"{text[:500]}..."
    return text


def _websocket_response_header(ws: Any, name: str) -> str | None:
    response = getattr(ws, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(ws, "response_headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    value = getter(name) or getter(name.lower())
    return str(value) if value else None


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing {name} for Doubao realtime voice")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
