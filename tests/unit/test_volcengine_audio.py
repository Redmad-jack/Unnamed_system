from __future__ import annotations

import base64
import json

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, TranscriptEvent
from conscious_entity.audio.volcengine_protocol import VolcengineProtocol, media_type_for_format


def test_stt_headers_api_key():
    protocol = VolcengineProtocol()
    config = AudioConfig(api_key="api-secret")

    headers = protocol.build_headers(config, resource_id="stt-resource")

    assert headers["X-Api-Key"] == "api-secret"
    assert headers["X-Api-Resource-Id"] == "stt-resource"
    assert "X-Api-App-Key" not in headers


def test_stt_headers_app_token():
    protocol = VolcengineProtocol()
    config = AudioConfig(app_id="app", access_token="token")

    headers = protocol.build_headers(config, resource_id="stt-resource")

    assert headers["X-Api-App-Key"] == "app"
    assert headers["X-Api-Access-Key"] == "token"


def test_stt_response_parse_partial_and_final():
    protocol = VolcengineProtocol()

    partial = protocol.parse_stt_response(
        json.dumps({"type": "partial", "text": "你还", "logid": "l1"}),
        session_id="aud",
    )
    final = protocol.parse_stt_response(
        json.dumps({"type": "final", "result": {"text": "你还记得我吗？"}, "logid": "l2"}),
        session_id="aud",
    )

    assert isinstance(partial, TranscriptEvent)
    assert partial.is_final is False
    assert partial.text == "你还"
    assert isinstance(final, TranscriptEvent)
    assert final.is_final is True
    assert final.text == "你还记得我吗？"


def test_tts_request_payload_contains_voice_type():
    protocol = VolcengineProtocol()
    config = AudioConfig(
        app_id="app",
        access_token="token",
        tts_resource_id="seed-tts-2.0",
        tts_voice_type="voice",
    )

    payload = json.loads(protocol.build_tts_request(config, text="你好", request_id="req"))

    assert payload["audio"]["voice_type"] == "voice"
    assert payload["request"]["text"] == "你好"
    assert payload["request"]["operation"] == "submit"


def test_tts_parse_audio_chunks_and_error_mapping():
    protocol = VolcengineProtocol()
    encoded = base64.b64encode(b"audio").decode("ascii")

    event = protocol.parse_tts_message(json.dumps({"data": encoded, "done": True, "logid": "l"}))
    error = protocol.parse_tts_message(json.dumps({"code": 401, "message": "bad key", "logid": "e"}))

    assert event.audio == b"audio"
    assert event.done is True
    assert event.logid == "l"
    assert isinstance(error.error, AudioError)
    assert error.error.logid == "e"


def test_media_type_for_format():
    assert media_type_for_format("mp3") == "audio/mpeg"
    assert media_type_for_format("ogg_opus") == "audio/ogg"
    assert media_type_for_format("pcm") == "audio/L16"
