from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conscious_entity.audio.types import AudioRuntimeError
from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.interfaces import api
from conscious_entity.interfaces.api_models import AudioDialogRequest


class FakeLoop:
    def __init__(self):
        self.inputs = []

    def run_turn(self, text, source="dialog", input_metadata=None):
        self.inputs.append((text, source, input_metadata))
        return ExpressionOutput(
            text="我记得一点。",
            spoken_text=None,
            delay_ms=100,
            visual_mode="normal",
            raw_prompt="prompt",
        )


class FakeAudioManager:
    def __init__(self):
        self.config = SimpleNamespace(output_format="mp3", disabled_reason=lambda: None)
        self.created = False

    def status(self):
        return {"enabled": True, "provider": "volcengine"}

    def create_tts_stream(self, output):
        self.created = True
        return SimpleNamespace(stream_id="tts_test"), True

    def get_tts_stream(self, stream_id):
        raise AudioRuntimeError("tts_stream_expired", "expired")


class FakeIdentityGating:
    def before_turn(self, *, source, input_mode, text, metadata=None):
        return {
            "runtime_state": "in_dialogue",
            "session_decision": "continue_unidentified",
            "source": source,
            "input_mode": input_mode,
            "text_chars": len(text),
        }


class BrokenIdentityGating:
    def before_turn(self, *, source, input_mode, text, metadata=None):
        raise RuntimeError("gating failed")


def _request(loop=None, audio_manager=None, identity_gating=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        loop=loop or FakeLoop(),
        loop_lock=asyncio.Lock(),
        audio_manager=audio_manager or FakeAudioManager(),
        identity_gating=identity_gating,
    )))


def test_audio_status_delegates_to_manager():
    result = asyncio.run(api.audio_status(_request()))

    assert result["enabled"] is True


def test_audio_dialog_reuses_loop_and_creates_tts_stream():
    loop = FakeLoop()
    manager = FakeAudioManager()

    result = asyncio.run(api.audio_dialog(
        AudioDialogRequest(transcript="  你还记得我吗？ ", audio_session_id="aud"),
        _request(loop=loop, audio_manager=manager),
    ))

    assert loop.inputs == [("你还记得我吗？", "audio_dialog", {
        "input_mode": "voice_transcript",
        "source": "audio_dialog",
        "audio_session_id": "aud",
        "transcript_state": "final",
    })]
    assert manager.created is True
    assert result["tts_stream_id"] == "tts_test"
    assert result["should_speak"] is True


def test_audio_dialog_attaches_identity_session_context_when_available():
    loop = FakeLoop()

    asyncio.run(api.audio_dialog(
        AudioDialogRequest(transcript="  你还记得我吗？ ", audio_session_id="aud"),
        _request(loop=loop, identity_gating=FakeIdentityGating()),
    ))

    metadata = loop.inputs[0][2]
    assert metadata["input_mode"] == "voice_transcript"
    assert metadata["identity_session"]["session_decision"] == "continue_unidentified"
    assert metadata["identity_session"]["runtime_state"] == "in_dialogue"


def test_audio_dialog_continues_when_identity_gating_fails():
    loop = FakeLoop()

    asyncio.run(api.audio_dialog(
        AudioDialogRequest(transcript="继续", audio_session_id="aud"),
        _request(loop=loop, identity_gating=BrokenIdentityGating()),
    ))

    metadata = loop.inputs[0][2]
    assert metadata["identity_session"]["error"] == "identity_gating_failed"
    assert metadata["identity_session"]["session_decision"] == "continue_unidentified"


def test_audio_dialog_rejects_blank_transcript():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.audio_dialog(AudioDialogRequest(transcript=" "), _request()))

    assert exc.value.status_code == 400


def test_tts_http_rejects_unknown_stream_id():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.audio_tts_http_stream("missing", _request()))

    assert exc.value.status_code == 400
    assert exc.value.detail == "tts_stream_expired"
