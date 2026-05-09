from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from typing import Any


ASR_FULL_CLIENT_REQUEST_HEADER = bytes([0x11, 0x10, 0x11, 0x00])
ASR_AUDIO_REQUEST_HEADER = bytes([0x11, 0x20, 0x01, 0x00])
ASR_FINAL_AUDIO_REQUEST_HEADER = bytes([0x11, 0x22, 0x01, 0x00])

ASR_MESSAGE_FULL_SERVER_RESPONSE = 0x9
ASR_MESSAGE_ERROR_RESPONSE = 0xF
ASR_FLAG_POS_SEQUENCE = 0b0001
ASR_FLAG_NEG_SEQUENCE = 0b0011
ASR_SERIALIZATION_JSON = 0x1
ASR_COMPRESSION_GZIP = 0x1


class DoubaoASRProtocolError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        request_id: str | None = None,
        log_id: str | None = None,
        payload: Any = None,
    ) -> None:
        detail = message
        if error_code is not None:
            detail = f"{detail} (error_code={error_code})"
        if request_id:
            detail = f"{detail} (request_id={request_id})"
        if log_id:
            detail = f"{detail} (X-Tt-Logid={log_id})"
        super().__init__(detail)
        self.error_code = error_code
        self.request_id = request_id
        self.log_id = log_id
        self.payload = payload


@dataclass(frozen=True)
class ASRServerResponse:
    message_type: int
    flags: int
    serialization: int
    compression: int
    sequence: int | None = None
    payload: Any = None
    raw_payload: bytes = b""


@dataclass(frozen=True)
class ASRTranscriptEvent:
    type: str
    text: str
    start_time: Any = None
    end_time: Any = None
    definite: bool = False
    key: tuple[Any, Any, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def encode_full_client_request(payload: dict[str, Any]) -> bytes:
    payload_bytes = gzip.compress(json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    return ASR_FULL_CLIENT_REQUEST_HEADER + len(payload_bytes).to_bytes(4, "big") + payload_bytes


def encode_audio_request(audio: bytes, *, final: bool = False) -> bytes:
    payload = gzip.compress(audio or b"")
    header = ASR_FINAL_AUDIO_REQUEST_HEADER if final else ASR_AUDIO_REQUEST_HEADER
    return header + len(payload).to_bytes(4, "big") + payload


def parse_server_response(
    message: bytes,
    *,
    request_id: str | None = None,
    log_id: str | None = None,
) -> ASRServerResponse:
    if len(message) < 8:
        raise DoubaoASRProtocolError(
            "Invalid ASR frame",
            request_id=request_id,
            log_id=log_id,
        )

    header_size_words = message[0] & 0x0F
    message_type = (message[1] >> 4) & 0x0F
    flags = message[1] & 0x0F
    serialization = (message[2] >> 4) & 0x0F
    compression = message[2] & 0x0F
    offset = header_size_words * 4
    sequence: int | None = None

    if offset > len(message):
        raise DoubaoASRProtocolError(
            "Invalid ASR header size",
            request_id=request_id,
            log_id=log_id,
        )

    if message_type == ASR_MESSAGE_ERROR_RESPONSE:
        if offset + 8 > len(message):
            raise DoubaoASRProtocolError(
                "Invalid ASR error frame",
                request_id=request_id,
                log_id=log_id,
            )
        error_code = int.from_bytes(message[offset:offset + 4], "big", signed=True)
        offset += 4
        payload_size = int.from_bytes(message[offset:offset + 4], "big")
        offset += 4
        payload_bytes = message[offset:offset + payload_size]
        payload = _decode_payload(payload_bytes, serialization, compression)
        error_message = _error_message(payload)
        raise DoubaoASRProtocolError(
            error_message,
            error_code=error_code,
            request_id=request_id,
            log_id=log_id,
            payload=payload,
        )

    if message_type != ASR_MESSAGE_FULL_SERVER_RESPONSE:
        return ASRServerResponse(
            message_type=message_type,
            flags=flags,
            serialization=serialization,
            compression=compression,
            raw_payload=message[offset:],
        )

    if flags in {ASR_FLAG_POS_SEQUENCE, ASR_FLAG_NEG_SEQUENCE}:
        if offset + 4 > len(message):
            raise DoubaoASRProtocolError(
                "Invalid ASR sequence frame",
                request_id=request_id,
                log_id=log_id,
            )
        sequence = int.from_bytes(message[offset:offset + 4], "big", signed=True)
        offset += 4

    if offset + 4 > len(message):
        raise DoubaoASRProtocolError(
            "Invalid ASR payload size",
            request_id=request_id,
            log_id=log_id,
        )
    payload_size = int.from_bytes(message[offset:offset + 4], "big")
    offset += 4
    payload_bytes = message[offset:offset + payload_size]
    payload = _decode_payload(payload_bytes, serialization, compression)
    return ASRServerResponse(
        message_type=message_type,
        flags=flags,
        serialization=serialization,
        compression=compression,
        sequence=sequence,
        payload=payload,
        raw_payload=payload_bytes,
    )


def transcript_events_from_payload(
    payload: dict[str, Any],
    *,
    seen_final_keys: set[tuple[Any, Any, str]] | None = None,
) -> list[ASRTranscriptEvent]:
    events: list[ASRTranscriptEvent] = []
    for result in _iter_results(payload):
        text = str(result.get("text") or "").strip()
        if text:
            events.append(ASRTranscriptEvent(
                type="partial",
                text=text,
                metadata={"result": result},
            ))
        utterances = result.get("utterances")
        if not isinstance(utterances, list):
            continue
        for utterance in utterances:
            if not isinstance(utterance, dict) or utterance.get("definite") is not True:
                continue
            utterance_text = str(utterance.get("text") or "").strip()
            if not utterance_text:
                continue
            key = final_utterance_key(utterance)
            if seen_final_keys is not None:
                if key in seen_final_keys:
                    continue
                seen_final_keys.add(key)
            events.append(ASRTranscriptEvent(
                type="final",
                text=utterance_text,
                start_time=utterance.get("start_time"),
                end_time=utterance.get("end_time"),
                definite=True,
                key=key,
                metadata={"utterance": utterance, "result": result},
            ))
    return events


def final_utterance_key(utterance: dict[str, Any]) -> tuple[Any, Any, str]:
    return (
        utterance.get("start_time"),
        utterance.get("end_time"),
        str(utterance.get("text") or "").strip(),
    )


def _iter_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def _decode_payload(payload: bytes, serialization: int, compression: int) -> Any:
    if compression == ASR_COMPRESSION_GZIP:
        payload = gzip.decompress(payload)
    if serialization == ASR_SERIALIZATION_JSON:
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))
    return payload


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(
            payload.get("message")
            or payload.get("error")
            or payload.get("detail")
            or "Doubao ASR error"
        )
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore") or "Doubao ASR error"
    return str(payload or "Doubao ASR error")
