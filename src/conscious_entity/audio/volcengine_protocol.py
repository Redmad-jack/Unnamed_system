from __future__ import annotations

import gzip
import json
import struct
import uuid
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, SynthesisEvent, TranscriptEvent


VERSION = 0x1
HEADER_SIZE_WORDS = 0x1

MSG_FULL_CLIENT_REQUEST = 0x1
MSG_AUDIO_ONLY_REQUEST = 0x2
MSG_FULL_SERVER_RESPONSE = 0x9
MSG_AUDIO_ONLY_RESPONSE = 0xB
MSG_ERROR = 0xF

FLAG_NONE = 0x0
FLAG_POS_SEQUENCE = 0x1
FLAG_LAST_NO_SEQUENCE = 0x2
FLAG_LAST_NEG_SEQUENCE = 0x3
FLAG_WITH_EVENT = 0x4

SERIALIZATION_NONE = 0x0
SERIALIZATION_JSON = 0x1

COMPRESSION_NONE = 0x0
COMPRESSION_GZIP = 0x1

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_CONNECTION_FINISHED = 52
EVENT_START_SESSION = 100
EVENT_CANCEL_SESSION = 101
EVENT_FINISH_SESSION = 102
EVENT_SESSION_STARTED = 150
EVENT_SESSION_CANCELED = 151
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TASK_REQUEST = 200
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352

SUCCESS_CODES = {None, 0, "0", 20000000, "20000000", "success", "ok"}


class VolcengineProtocol:
    """Facade for Volcengine V3 ASR and TTS binary protocols."""

    def __init__(self) -> None:
        self.asr = VolcengineASRProtocol()
        self.tts = VolcengineTTSBidirectionalProtocol()

    def build_headers(
        self,
        config: AudioConfig,
        *,
        resource_id: str,
        service: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }
        if service == "asr":
            headers["X-Api-Request-Id"] = uuid.uuid4().hex
            headers["X-Api-Sequence"] = "-1"

        if config.api_key:
            headers["X-Api-Key"] = config.api_key
        else:
            if config.app_id:
                headers["X-Api-App-Key"] = config.app_id
                headers["X-Api-App-Id"] = config.app_id
            if config.access_token:
                headers["X-Api-Access-Key"] = config.access_token
        return headers

    def build_stt_start_packet(self, config: AudioConfig, *, session_id: str) -> bytes:
        return self.asr.build_start_packet(config, session_id=session_id)

    def build_stt_audio_packet(self, chunk: bytes, *, sequence: int, final: bool = False) -> bytes:
        return self.asr.build_audio_packet(chunk, sequence=sequence, final=final)

    def build_stt_final_packet(self, *, session_id: str) -> bytes:
        return self.asr.build_audio_packet(b"", sequence=-1, final=True)

    def parse_stt_response(self, message: str | bytes, *, session_id: str) -> TranscriptEvent | AudioError | None:
        return self.asr.parse_response(message, session_id=session_id)

    def build_tts_start_connection(self) -> bytes:
        return self.tts.build_start_connection()

    def build_tts_finish_connection(self) -> bytes:
        return self.tts.build_finish_connection()

    def build_tts_start_session(self, config: AudioConfig, *, session_id: str) -> bytes:
        return self.tts.build_start_session(config, session_id=session_id)

    def build_tts_finish_session(self, *, session_id: str) -> bytes:
        return self.tts.build_finish_session(session_id=session_id)

    def build_tts_cancel_session(self, *, session_id: str) -> bytes:
        return self.tts.build_cancel_session(session_id=session_id)

    def build_tts_task_request(self, *, session_id: str, text: str) -> bytes:
        return self.tts.build_task_request(session_id=session_id, text=text)

    def build_tts_request(self, config: AudioConfig, *, text: str, request_id: str) -> bytes:
        return self.tts.build_single_text_session(config, session_id=request_id, text=text)

    def parse_tts_message(self, message: str | bytes) -> SynthesisEvent:
        return self.tts.parse_response(message)


class VolcengineASRProtocol:
    def build_start_packet(self, config: AudioConfig, *, session_id: str) -> bytes:
        payload = {
            "user": {
                "uid": "conscious_entity",
                "platform": "python",
            },
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": config.sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "result_type": "single",
                "enable_itn": True,
                "enable_punc": True,
                "enable_nonstream": True,
                "show_utterances": True,
                "end_window_size": 800,
            },
            "session": {
                "id": session_id,
            },
        }
        return _build_sized_frame(
            MSG_FULL_CLIENT_REQUEST,
            FLAG_NONE,
            SERIALIZATION_JSON,
            COMPRESSION_GZIP,
            _json_bytes(payload),
        )

    def build_audio_packet(self, chunk: bytes, *, sequence: int, final: bool = False) -> bytes:
        del sequence
        return _build_sized_frame(
            MSG_AUDIO_ONLY_REQUEST,
            FLAG_LAST_NO_SEQUENCE if final else FLAG_NONE,
            SERIALIZATION_NONE,
            COMPRESSION_GZIP,
            chunk,
        )

    def parse_response(self, message: str | bytes, *, session_id: str) -> TranscriptEvent | AudioError | None:
        if isinstance(message, str):
            return _parse_asr_payload(_decode_json_payload(message), session_id=session_id)

        parsed = _parse_binary_header(message)
        if parsed is None:
            return _parse_asr_payload(_decode_json_payload(message), session_id=session_id)
        message_type, flags, _serialization, compression, offset = parsed

        if message_type == MSG_ERROR:
            return _parse_error_frame(message, offset, code_prefix="stt")
        if message_type != MSG_FULL_SERVER_RESPONSE:
            return None

        if flags in {FLAG_POS_SEQUENCE, FLAG_LAST_NEG_SEQUENCE} and len(message) >= offset + 4:
            offset += 4
        if len(message) < offset + 4:
            return None

        payload_size = _read_u32(message, offset)
        offset += 4
        payload = message[offset : offset + payload_size]
        payload = _decompress(payload, compression)
        result = _decode_json_payload(payload)
        event = _parse_asr_payload(
            result,
            session_id=session_id,
            final_frame=flags in {FLAG_LAST_NO_SEQUENCE, FLAG_LAST_NEG_SEQUENCE},
        )
        return event


class VolcengineTTSBidirectionalProtocol:
    def build_start_connection(self) -> bytes:
        return _build_event_json_frame(EVENT_START_CONNECTION, {})

    def build_finish_connection(self) -> bytes:
        return _build_event_json_frame(EVENT_FINISH_CONNECTION, {})

    def build_start_session(self, config: AudioConfig, *, session_id: str) -> bytes:
        additions = {
            "disable_markdown_filter": True,
            "disable_emoji_filter": False,
        }
        payload = {
            "event": EVENT_START_SESSION,
            "namespace": "BidirectionalTTS",
            "user": {"uid": "conscious_entity"},
            "req_params": {
                "speaker": config.tts_voice_type,
                "audio_params": {
                    "format": config.output_format,
                    "sample_rate": config.tts_sample_rate,
                },
                "additions": json.dumps(additions, ensure_ascii=False),
            },
        }
        return _build_event_json_frame(EVENT_START_SESSION, payload, session_id=session_id)

    def build_finish_session(self, *, session_id: str) -> bytes:
        return _build_event_json_frame(EVENT_FINISH_SESSION, {}, session_id=session_id)

    def build_cancel_session(self, *, session_id: str) -> bytes:
        return _build_event_json_frame(EVENT_CANCEL_SESSION, {}, session_id=session_id)

    def build_task_request(self, *, session_id: str, text: str) -> bytes:
        payload = {
            "event": EVENT_TASK_REQUEST,
            "namespace": "BidirectionalTTS",
            "req_params": {"text": text},
        }
        return _build_event_json_frame(EVENT_TASK_REQUEST, payload, session_id=session_id)

    def build_single_text_session(self, config: AudioConfig, *, session_id: str, text: str) -> bytes:
        return self.build_task_request(session_id=session_id, text=text)

    def parse_response(self, message: str | bytes) -> SynthesisEvent:
        if isinstance(message, str):
            return _parse_tts_json_payload(_decode_json_payload(message))

        parsed = _parse_binary_header(message)
        if parsed is None:
            return _parse_tts_json_payload(_decode_json_payload(message))
        message_type, flags, serialization, compression, offset = parsed

        if message_type == MSG_ERROR:
            error = _parse_error_frame(message, offset, code_prefix="tts")
            return SynthesisEvent(error=error if isinstance(error, AudioError) else None)

        event_code = None
        if flags == FLAG_WITH_EVENT and len(message) >= offset + 4:
            event_code = _read_i32(message, offset)
            offset += 4

        identifier = None
        if flags == FLAG_WITH_EVENT and len(message) >= offset + 8:
            candidate_size = _read_u32(message, offset)
            remaining_after_size = len(message) - (offset + 4)
            if candidate_size <= remaining_after_size - 4:
                offset += 4
                identifier = message[offset : offset + candidate_size].decode("utf-8", errors="ignore")
                offset += candidate_size

        if len(message) < offset + 4:
            return SynthesisEvent(event_code=event_code, session_id=identifier)

        payload_size = _read_u32(message, offset)
        offset += 4
        payload = message[offset : offset + payload_size]
        payload = _decompress(payload, compression)

        if message_type == MSG_AUDIO_ONLY_RESPONSE or event_code == EVENT_TTS_RESPONSE:
            return SynthesisEvent(audio=payload, event_code=event_code, session_id=identifier)

        payload_json = _decode_json_payload(payload)
        if event_code in {EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED}:
            return SynthesisEvent(
                error=AudioError(
                    code="tts_protocol_error",
                    message=_sanitize(_message_from_payload(payload_json, "TTS session failed")),
                ),
                event_code=event_code,
                session_id=identifier,
            )
        if isinstance(payload_json, dict):
            code = _first(payload_json, "status_code", "code", "error_code")
            if code not in SUCCESS_CODES:
                return SynthesisEvent(
                    error=AudioError(
                        code="tts_protocol_error",
                        message=_sanitize(_message_from_payload(payload_json, "TTS request failed")),
                    ),
                    event_code=event_code,
                    session_id=identifier,
                )
            text = _first(payload_json, "text", default=None)
            if text is None:
                res_params = payload_json.get("res_params")
                if isinstance(res_params, dict):
                    text = _first(res_params, "text", default=None)
        else:
            text = None

        return SynthesisEvent(
            done=event_code == EVENT_SESSION_FINISHED,
            event_code=event_code,
            session_id=identifier,
            text=text,
        )


def media_type_for_format(output_format: str) -> str:
    if output_format == "ogg_opus":
        return "audio/ogg"
    if output_format == "pcm":
        return "audio/L16"
    return "audio/mpeg"


def _build_sized_frame(
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
    payload: bytes,
) -> bytes:
    payload = _compress(payload, compression)
    return _header(message_type, flags, serialization, compression) + _u32(len(payload)) + payload


def _build_event_json_frame(event: int, payload: dict[str, Any], *, session_id: str | None = None) -> bytes:
    payload_bytes = _json_bytes(payload)
    header = _header(MSG_FULL_CLIENT_REQUEST, FLAG_WITH_EVENT, SERIALIZATION_JSON, COMPRESSION_NONE)
    frame = bytearray(header)
    frame.extend(_i32(event))
    if session_id is not None:
        session_bytes = session_id.encode("utf-8")
        frame.extend(_u32(len(session_bytes)))
        frame.extend(session_bytes)
    frame.extend(_u32(len(payload_bytes)))
    frame.extend(payload_bytes)
    return bytes(frame)


def _header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes(
        [
            (VERSION << 4) | HEADER_SIZE_WORDS,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0,
        ]
    )


def _parse_binary_header(message: bytes) -> tuple[int, int, int, int, int] | None:
    if len(message) < 4:
        return None
    version = message[0] >> 4
    header_size = message[0] & 0x0F
    if version != VERSION or header_size < HEADER_SIZE_WORDS:
        return None
    offset = header_size * 4
    if len(message) < offset:
        return None
    return message[1] >> 4, message[1] & 0x0F, message[2] >> 4, message[2] & 0x0F, offset


def _parse_error_frame(message: bytes, offset: int, *, code_prefix: str) -> AudioError | None:
    if len(message) < offset + 8:
        return AudioError(f"{code_prefix}_protocol_error", "Malformed error frame")
    error_code = _read_u32(message, offset)
    offset += 4
    payload_size = _read_u32(message, offset)
    offset += 4
    payload = message[offset : offset + payload_size]
    payload_json = _decode_json_payload(payload)
    return AudioError(
        f"{code_prefix}_protocol_error",
        _sanitize(_message_from_payload(payload_json, f"Volcengine error {error_code}")),
    )


def _parse_asr_payload(
    payload: Any,
    *,
    session_id: str,
    final_frame: bool = False,
) -> TranscriptEvent | AudioError | None:
    if not isinstance(payload, dict):
        return None

    logid = _first(payload, "logid", "log_id", "X-Tt-Logid")
    code = _first(payload, "code", "error_code", "status_code")
    text, is_definite = _extract_asr_text(payload)
    if code not in SUCCESS_CODES and not text:
        return AudioError("stt_protocol_error", _sanitize(_message_from_payload(payload, "STT request failed")), logid=logid)
    if not text:
        return None

    event_type = str(_first(payload, "type", "event", default="")).lower()
    is_final = bool(
        final_frame
        or is_definite
        or _first(payload, "is_final", "final", "definite", default=False)
        or "final" in event_type
        or "complete" in event_type
    )
    return TranscriptEvent(text=text, is_final=is_final, session_id=session_id, logid=logid)


def _extract_asr_text(payload: dict[str, Any]) -> tuple[str, bool]:
    result = payload.get("result")
    if isinstance(result, dict):
        utterances = result.get("utterances")
        if isinstance(utterances, list):
            definite_texts = [
                str(item.get("text", ""))
                for item in utterances
                if isinstance(item, dict) and item.get("definite") and item.get("text")
            ]
            if definite_texts:
                return "".join(definite_texts), True
        value = result.get("text")
        if isinstance(value, str):
            return value, False
    if isinstance(result, list):
        texts = []
        definite = False
        for item in result:
            if isinstance(item, dict):
                text, item_definite = _extract_asr_text({"result": item})
                if text:
                    texts.append(text)
                definite = definite or item_definite
        if texts:
            return "".join(texts), definite
    for key in ("text", "result_text", "transcript"):
        value = payload.get(key)
        if isinstance(value, str):
            return value, bool(payload.get("definite"))
    payload_msg = payload.get("payload_msg")
    if isinstance(payload_msg, dict):
        return _extract_asr_text(payload_msg)
    return "", False


def _parse_tts_json_payload(payload: Any) -> SynthesisEvent:
    if not isinstance(payload, dict):
        return SynthesisEvent(error=AudioError("tts_protocol_error", "Malformed TTS response"))

    logid = _first(payload, "logid", "log_id", "X-Tt-Logid")
    code = _first(payload, "code", "error_code", "status_code")
    if code not in SUCCESS_CODES:
        return SynthesisEvent(
            error=AudioError("tts_protocol_error", _sanitize(_message_from_payload(payload, "TTS request failed")), logid=logid)
        )

    done = bool(_first(payload, "done", "is_final", default=False))
    event_type = str(_first(payload, "type", "event", default="")).lower()
    if "done" in event_type or "complete" in event_type:
        done = True

    data = _first(payload, "data", "audio", "payload")
    audio = None
    if isinstance(data, str) and data:
        try:
            import base64

            audio = base64.b64decode(data)
        except Exception:
            audio = data.encode("utf-8")
    return SynthesisEvent(audio=audio, done=done, logid=logid)


def _decode_json_payload(message: str | bytes | bytearray) -> Any:
    if isinstance(message, (bytes, bytearray)):
        try:
            text = bytes(message).decode("utf-8")
        except UnicodeDecodeError:
            start = bytes(message).find(b"{")
            end = bytes(message).rfind(b"}")
            if start == -1 or end == -1 or end <= start:
                return None
            text = bytes(message)[start : end + 1].decode("utf-8", errors="ignore")
    else:
        text = message

    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def _message_from_payload(payload: Any, default: str) -> str:
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return default


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _compress(payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_GZIP:
        return gzip.compress(payload)
    return payload


def _decompress(payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_GZIP and payload:
        return gzip.decompress(payload)
    return payload


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _i32(value: int) -> bytes:
    return struct.pack(">i", value)


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset : offset + 4])[0]


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack(">i", data[offset : offset + 4])[0]


def _first(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def _sanitize(message: str) -> str:
    return message.replace("\n", " ").replace("\r", " ")[:300]
