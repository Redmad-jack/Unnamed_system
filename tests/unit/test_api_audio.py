from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conscious_entity.audio.types import AudioRuntimeError
from conscious_entity.expression.output_model import ExpressionOutput, build_response_plan
from conscious_entity.interfaces import api
from conscious_entity.interfaces.api_models import AudioDialogRequest, DialogRequest


class FakeLoop:
    def __init__(self, *, first_unit="唉。", second_unit="我记得一点。"):
        self.inputs = []
        self.first_unit = first_unit
        self.second_unit = second_unit

    def run_turn(self, text, source="dialog", input_metadata=None, progress_callback=None):
        self.inputs.append((text, source, input_metadata))
        plan = build_response_plan(
            first_unit=self.first_unit,
            second_unit=self.second_unit,
            third_unit="",
            vocal_marker="sigh",
            body_action="pause",
            visual_mode="normal",
        )
        if progress_callback is not None:
            first_plan = build_response_plan(
                first_unit=plan.first_unit,
                second_unit="",
                third_unit="",
                vocal_marker="sigh",
                body_action="pause",
                visual_mode="normal",
            )
            progress_callback({
                "phase": "first_unit",
                "text": plan.first_unit,
                "response_plan": first_plan.to_dict(),
                "events": [],
                "vocal_marker": "sigh",
                "body_action": "pause",
                "visual_mode": "normal",
            })
        return ExpressionOutput(
            text=plan.combined_text,
            spoken_text=plan.combined_text,
            delay_ms=0,
            visual_mode="normal",
            raw_prompt="prompt",
            vocal_marker="sigh",
            body_action="pause",
            response_plan=plan,
        )


class FakeAudioManager:
    def __init__(self):
        self.config = SimpleNamespace(output_format="mp3", disabled_reason=lambda: None)
        self.created = False
        self.created_texts = []

    def status(self):
        return {"enabled": True, "provider": "volcengine"}

    def create_tts_stream(self, output):
        self.created = True
        return SimpleNamespace(stream_id="tts_test"), True

    def create_tts_stream_from_text(self, text, *, source="dialog_output"):
        self.created_texts.append((text, source))
        if not text.strip():
            return None, False
        stream_id = f"tts_progressive_{len(self.created_texts)}"
        return SimpleNamespace(stream_id=stream_id), bool(text.strip())

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


async def _collect_streaming_response(response):
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        chunks.append(str(chunk))
    return [
        json.loads(line)
        for line in "".join(chunks).splitlines()
        if line.strip()
    ]


def test_audio_status_delegates_to_manager():
    result = asyncio.run(api.audio_status(_request()))

    assert result["enabled"] is True


def test_dialog_returns_response_plan():
    result = asyncio.run(api.dialog(
        DialogRequest(text="你记得吗？"),
        _request(),
    ))

    assert result["text"] == "唉。\n我记得一点。"
    assert result["response_plan"]["first_unit"] == "唉。"
    assert result["response_plan"]["second_unit"] == "我记得一点。"
    assert result["response_plan"]["combined_text"] == result["text"]


def test_dialog_progressive_emits_first_before_final():
    response = asyncio.run(api.dialog_progressive(
        DialogRequest(text="你记得吗？"),
        _request(),
    ))
    events = asyncio.run(_collect_streaming_response(response))

    assert [event["phase"] for event in events] == ["first_unit", "final"]
    assert events[0]["text"] == "唉。"
    assert events[0]["response_plan"]["second_unit"] == ""
    assert events[1]["response_plan"]["second_unit"] == "我记得一点。"


def test_dialog_progressive_final_text_is_second_unit_only():
    response = asyncio.run(api.dialog_progressive(
        DialogRequest(text="你记得吗？"),
        _request(),
    ))
    events = asyncio.run(_collect_streaming_response(response))
    final = events[-1]

    assert final["phase"] == "final"
    assert final["text"] == "我记得一点。"
    assert final["text"] != final["response_plan"]["combined_text"]


def test_dialog_progressive_allows_empty_final_text_when_first_unit_completes_turn():
    response = asyncio.run(api.dialog_progressive(
        DialogRequest(text="hi"),
        _request(loop=FakeLoop(first_unit="Hi.", second_unit="")),
    ))
    events = asyncio.run(_collect_streaming_response(response))
    final = events[-1]

    assert [event["phase"] for event in events] == ["first_unit", "final"]
    assert events[0]["text"] == "Hi."
    assert final["phase"] == "final"
    assert final["text"] == ""
    assert final["done"] is True
    assert final["response_plan"]["combined_text"] == "Hi."


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
    assert result["delay_ms"] == 0
    assert result["vocal_marker"] == "sigh"
    assert result["body_action"] == "pause"
    assert result["response_plan"]["combined_text"] == result["output_text"]


def test_audio_progressive_creates_two_tts_streams_from_first_and_second_only():
    loop = FakeLoop()
    manager = FakeAudioManager()

    response = asyncio.run(api.audio_dialog_progressive(
        AudioDialogRequest(transcript="  你还记得我吗？ ", audio_session_id="aud"),
        _request(loop=loop, audio_manager=manager),
    ))
    events = asyncio.run(_collect_streaming_response(response))

    assert [event["phase"] for event in events] == ["first_unit", "final"]
    assert [event["tts_stream_id"] for event in events] == [
        "tts_progressive_1",
        "tts_progressive_2",
    ]
    assert manager.created_texts == [
        ("唉。", "dialog_first_unit"),
        ("我记得一点。", "dialog_second_unit"),
    ]
    assert events[-1]["text"] == "我记得一点。"
    assert events[-1]["response_plan"]["combined_text"] == "唉。\n我记得一点。"


def test_audio_progressive_allows_empty_second_unit_without_tts_stream():
    loop = FakeLoop(first_unit="Hi.", second_unit="")
    manager = FakeAudioManager()

    response = asyncio.run(api.audio_dialog_progressive(
        AudioDialogRequest(transcript="hi", audio_session_id="aud"),
        _request(loop=loop, audio_manager=manager),
    ))
    events = asyncio.run(_collect_streaming_response(response))
    final = events[-1]

    assert [event["phase"] for event in events] == ["first_unit", "final"]
    assert manager.created_texts == [
        ("Hi.", "dialog_first_unit"),
        ("", "dialog_second_unit"),
    ]
    assert final["text"] == ""
    assert final["should_speak"] is False
    assert final["tts_stream_id"] is None
    assert final["done"] is True
    assert final["response_plan"]["combined_text"] == "Hi."


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
