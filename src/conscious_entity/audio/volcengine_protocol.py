from __future__ import annotations

import base64
import json
import uuid
from typing import Any

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, SynthesisEvent, TranscriptEvent


class VolcengineProtocol:
    def build_headers(self, config: AudioConfig, *, resource_id: str) -> dict[str, str]:
        headers = {
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }
        if config.api_key:
            headers["X-Api-Key"] = config.api_key
        else:
            if config.app_id:
                headers["X-Api-App-Key"] = config.app_id
            if config.access_token:
                headers["X-Api-Access-Key"] = config.access_token
        return headers

    def build_stt_start_packet(self, config: AudioConfig, *, session_id: str) -> str:
        return json.dumps(
            {
                "type": "start",
                "session_id": session_id,
                "audio": {
                    "format": "pcm_s16le",
                    "rate": config.sample_rate,
                    "bits": 16,
                    "channel": 1,
                },
                "request": {
                    "model_name": "bigmodel",
                    "result_type": "single",
                    "enable_itn": True,
                },
            },
            ensure_ascii=False,
        )

    def build_stt_audio_packet(self, chunk: bytes, *, sequence: int) -> bytes:
        # Volcengine's public examples wrap audio in their binary protocol. Keeping
        # this isolated lets us swap exact packet framing without touching API code.
        return chunk

    def build_stt_final_packet(self, *, session_id: str) -> str:
        return json.dumps({"type": "stop", "session_id": session_id}, ensure_ascii=False)

    def parse_stt_response(self, message: str | bytes, *, session_id: str) -> TranscriptEvent | AudioError | None:
        payload = _decode_json_payload(message)
        if not isinstance(payload, dict):
            return None

        logid = _first(payload, "logid", "log_id", "X-Tt-Logid")
        code = _first(payload, "code", "error_code")
        if code not in {None, 0, "0", "success"} and not _extract_text(payload):
            return AudioError(
                code="stt_protocol_error",
                message=_sanitize(str(_first(payload, "message", "error", default="STT request failed"))),
                logid=logid,
            )

        text = _extract_text(payload)
        if not text:
            return None
        is_final = bool(_first(payload, "is_final", "final", default=False))
        event_type = str(_first(payload, "type", "event", default="")).lower()
        if "final" in event_type or "complete" in event_type:
            is_final = True
        return TranscriptEvent(text=text, is_final=is_final, session_id=session_id, logid=logid)

    def build_tts_request(self, config: AudioConfig, *, text: str, request_id: str) -> str:
        return json.dumps(
            {
                "app": {
                    "appid": config.app_id or "",
                    "token": config.access_token or "",
                    "cluster": config.tts_resource_id,
                },
                "user": {"uid": "conscious_entity"},
                "audio": {
                    "voice_type": config.tts_voice_type,
                    "encoding": config.output_format,
                    "speed_ratio": 1.0,
                    "volume_ratio": 1.0,
                    "pitch_ratio": 1.0,
                },
                "request": {
                    "reqid": request_id,
                    "text": text,
                    "operation": "submit",
                    "with_frontend": 1,
                    "frontend_type": "unitTson",
                },
            },
            ensure_ascii=False,
        )

    def parse_tts_message(self, message: str | bytes) -> SynthesisEvent:
        if isinstance(message, bytes):
            payload = _decode_json_payload(message)
            if not isinstance(payload, dict):
                return SynthesisEvent(audio=message)
        else:
            payload = _decode_json_payload(message)

        if not isinstance(payload, dict):
            return SynthesisEvent(error=AudioError("tts_protocol_error", "Malformed TTS response"))

        logid = _first(payload, "logid", "log_id", "X-Tt-Logid")
        code = _first(payload, "code", "error_code")
        if code not in {None, 0, "0", "success"}:
            return SynthesisEvent(
                error=AudioError(
                    "tts_protocol_error",
                    _sanitize(str(_first(payload, "message", "error", default="TTS request failed"))),
                    logid=logid,
                )
            )

        done = bool(_first(payload, "done", "is_final", default=False))
        event_type = str(_first(payload, "type", "event", default="")).lower()
        if "done" in event_type or "complete" in event_type:
            done = True

        data = _first(payload, "data", "audio", "payload")
        audio = None
        if isinstance(data, str) and data:
            try:
                audio = base64.b64decode(data)
            except Exception:
                audio = data.encode("utf-8")
        return SynthesisEvent(audio=audio, done=done, logid=logid)


def media_type_for_format(output_format: str) -> str:
    if output_format == "ogg_opus":
        return "audio/ogg"
    if output_format == "pcm":
        return "audio/L16"
    return "audio/mpeg"


def _decode_json_payload(message: str | bytes) -> Any:
    if isinstance(message, bytes):
        try:
            text = message.decode("utf-8")
        except UnicodeDecodeError:
            start = message.find(b"{")
            end = message.rfind(b"}")
            if start == -1 or end == -1 or end <= start:
                return None
            text = message[start : end + 1].decode("utf-8", errors="ignore")
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


def _extract_text(payload: dict[str, Any]) -> str:
    for key in ("text", "result_text", "transcript"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    result = payload.get("result")
    if isinstance(result, dict):
        return _extract_text(result)
    payload_msg = payload.get("payload_msg")
    if isinstance(payload_msg, dict):
        return _extract_text(payload_msg)
    results = payload.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            return _extract_text(first)
    return ""


def _first(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def _sanitize(message: str) -> str:
    return message.replace("\n", " ").replace("\r", " ")[:300]
