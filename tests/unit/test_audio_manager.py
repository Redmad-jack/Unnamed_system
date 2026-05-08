from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.manager import AudioManager
from conscious_entity.audio.types import AudioRuntimeError, utc_now
from conscious_entity.expression.output_model import ExpressionOutput


def _enabled_config(**overrides) -> AudioConfig:
    values = dict(
        provider="volcengine",
        enabled=True,
        api_key="secret",
        tts_voice_type="voice",
    )
    values.update(overrides)
    config = AudioConfig(**values)
    object.__setattr__(config, "dependency_status", lambda: {
        "available": True,
        "missing": [],
        "websockets": "available",
    })
    return config


def _output(text: str) -> ExpressionOutput:
    return ExpressionOutput(
        text=text,
        spoken_text=None,
        delay_ms=0,
        visual_mode="normal",
        raw_prompt="prompt",
    )


def test_disabled_status():
    manager = AudioManager(AudioConfig())

    status = manager.status()

    assert status["enabled"] is False
    assert status["reason"] == "audio_provider_disabled"


def test_create_tts_stream_from_dialog_output():
    manager = AudioManager(_enabled_config())

    stream, should_speak = manager.create_tts_stream(_output("我会说这句话。"))

    assert should_speak is True
    assert stream is not None
    assert stream.stream_id.startswith("tts_")
    assert stream.source == "dialog_output"
    assert manager.status()["tts"]["last_stream_id"] == stream.stream_id


def test_silence_output_creates_no_tts_stream():
    manager = AudioManager(_enabled_config())

    stream, should_speak = manager.create_tts_stream(_output(""))

    assert should_speak is False
    assert stream is None


def test_reject_expired_stream_id():
    manager = AudioManager(_enabled_config())
    stream, _ = manager.create_tts_stream(_output("过期测试。"))
    assert stream is not None
    stream.expires_at = utc_now() - timedelta(seconds=1)

    with pytest.raises(AudioRuntimeError) as exc:
        manager.get_tts_stream(stream.stream_id)

    assert exc.value.code == "tts_stream_expired"


def test_debug_raw_tts_requires_env_flag():
    manager = AudioManager(_enabled_config(allow_debug_raw_tts=False))

    with pytest.raises(AudioRuntimeError) as exc:
        manager.create_debug_tts_stream("debug text")

    assert exc.value.code == "debug_raw_tts_disabled"


def test_stream_tts_bytes_uses_client_and_records_logid():
    class FakeTTSClient:
        last_logid = "log-1"

        async def synthesize_stream(self, segments):
            assert segments == ["我会说。"]
            yield b"audio"

    manager = AudioManager(_enabled_config(), tts_client=FakeTTSClient())
    stream, _ = manager.create_tts_stream(_output("我会说。"))

    chunks = []

    async def collect():
        async for chunk in manager.stream_tts_bytes(stream.stream_id):
            chunks.append(chunk)

    asyncio.run(collect())

    assert chunks == [b"audio"]
    assert manager.last_tts_logid == "log-1"
