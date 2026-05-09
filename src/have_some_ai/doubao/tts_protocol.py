from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


TTS_START_CONNECTION = 1
TTS_FINISH_CONNECTION = 2
TTS_CONNECTION_STARTED = 50
TTS_CONNECTION_FAILED = 51
TTS_CONNECTION_FINISHED = 52
TTS_START_SESSION = 100
TTS_CANCEL_SESSION = 101
TTS_FINISH_SESSION = 102
TTS_SESSION_STARTED = 150
TTS_SESSION_CANCELED = 151
TTS_SESSION_FINISHED = 152
TTS_SESSION_FAILED = 153
TTS_TASK_REQUEST = 200
TTS_SENTENCE_START = 350
TTS_SENTENCE_END = 351
TTS_RESPONSE = 352

TTS_HEADER_EVENT_JSON = bytes([0x11, 0x14, 0x10, 0x00])
TTS_MESSAGE_FULL_SERVER_RESPONSE = 0x9
TTS_MESSAGE_AUDIO_ONLY_RESPONSE = 0xB
TTS_MESSAGE_ERROR_RESPONSE = 0xF
TTS_FLAG_WITH_EVENT = 0b0100
TTS_SERIALIZATION_JSON = 0x1

TTS_CONNECTION_EVENTS = {
    TTS_CONNECTION_STARTED,
    TTS_CONNECTION_FAILED,
    TTS_CONNECTION_FINISHED,
}
TTS_ERROR_EVENTS = {TTS_CONNECTION_FAILED, TTS_SESSION_FAILED}


class DoubaoTTSProtocolError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        event: int | None = None,
        session_id: str | None = None,
        connection_id: str | None = None,
        log_id: str | None = None,
        error_code: int | None = None,
        payload: Any = None,
    ) -> None:
        detail = message
        if event is not None:
            detail = f"{detail} (event={event})"
        if session_id:
            detail = f"{detail} (session_id={session_id})"
        if connection_id:
            detail = f"{detail} (connection_id={connection_id})"
        if error_code is not None:
            detail = f"{detail} (error_code={error_code})"
        if log_id:
            detail = f"{detail} (X-Tt-Logid={log_id})"
        super().__init__(detail)
        self.event = event
        self.session_id = session_id
        self.connection_id = connection_id
        self.log_id = log_id
        self.error_code = error_code
        self.payload = payload


@dataclass(frozen=True)
class TTSEvent:
    event: int | None
    session_id: str | None = None
    connection_id: str | None = None
    payload: Any = field(default_factory=dict)
    audio: bytes | None = None
    message_type: int | None = None
    flags: int | None = None


def encode_event_payload(
    event: int,
    payload_json: dict[str, Any] | None,
    *,
    session_id: str | None = None,
) -> bytes:
    payload_bytes = json.dumps(
        payload_json or {},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    body = event.to_bytes(4, "big", signed=True)
    if session_id is not None:
        session_bytes = session_id.encode("utf-8")
        body += len(session_bytes).to_bytes(4, "big")
        body += session_bytes
    body += len(payload_bytes).to_bytes(4, "big")
    body += payload_bytes
    return TTS_HEADER_EVENT_JSON + body


def parse_tts_response(message: bytes, *, log_id: str | None = None) -> TTSEvent:
    if len(message) < 12:
        raise DoubaoTTSProtocolError("Invalid TTS frame", log_id=log_id)
    header_size_words = message[0] & 0x0F
    message_type = (message[1] >> 4) & 0x0F
    flags = message[1] & 0x0F
    serialization = (message[2] >> 4) & 0x0F
    offset = header_size_words * 4
    if offset > len(message):
        raise DoubaoTTSProtocolError("Invalid TTS header size", log_id=log_id)

    if message_type == TTS_MESSAGE_ERROR_RESPONSE:
        error_code = _read_int32(message, offset)
        offset += 4
        payload, _offset = _read_payload(message, offset)
        payload_obj = _decode_json_payload(payload)
        raise DoubaoTTSProtocolError(
            _payload_message(payload_obj),
            error_code=error_code,
            log_id=log_id,
            payload=payload_obj,
        )

    event: int | None = None
    if flags & TTS_FLAG_WITH_EVENT:
        event = _read_int32(message, offset)
        offset += 4

    connection_id: str | None = None
    session_id: str | None = None
    if event in TTS_CONNECTION_EVENTS:
        connection_id, offset = _read_string(message, offset)
    else:
        session_id, offset = _read_string(message, offset)

    payload_bytes, offset = _read_payload(message, offset)
    payload: Any = {}
    audio: bytes | None = None
    if event == TTS_RESPONSE or message_type == TTS_MESSAGE_AUDIO_ONLY_RESPONSE:
        audio = payload_bytes
    elif serialization == TTS_SERIALIZATION_JSON:
        payload = _decode_json_payload(payload_bytes)
    elif payload_bytes:
        payload = payload_bytes

    result = TTSEvent(
        event=event,
        session_id=session_id,
        connection_id=connection_id,
        payload=payload,
        audio=audio,
        message_type=message_type,
        flags=flags,
    )
    if event in TTS_ERROR_EVENTS:
        raise DoubaoTTSProtocolError(
            _payload_message(payload),
            event=event,
            session_id=session_id,
            connection_id=connection_id,
            log_id=log_id,
            payload=payload,
        )
    return result


def _read_int32(message: bytes, offset: int) -> int:
    if offset + 4 > len(message):
        raise DoubaoTTSProtocolError("Invalid TTS int32 field")
    return int.from_bytes(message[offset:offset + 4], "big", signed=True)


def _read_string(message: bytes, offset: int) -> tuple[str | None, int]:
    if offset + 4 > len(message):
        return None, offset
    length = int.from_bytes(message[offset:offset + 4], "big")
    offset += 4
    if length == 0:
        return "", offset
    if offset + length > len(message):
        return None, offset
    return message[offset:offset + length].decode("utf-8"), offset + length


def _read_payload(message: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(message):
        return b"", offset
    length = int.from_bytes(message[offset:offset + 4], "big")
    offset += 4
    if length == 0:
        return b"", offset
    if offset + length > len(message):
        raise DoubaoTTSProtocolError("Invalid TTS payload size")
    return message[offset:offset + length], offset + length


def _decode_json_payload(payload: bytes) -> Any:
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return payload.decode("utf-8", errors="ignore")


def _payload_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(
            payload.get("message")
            or payload.get("error")
            or payload.get("detail")
            or "Doubao TTS error"
        )
    return str(payload or "Doubao TTS error")
