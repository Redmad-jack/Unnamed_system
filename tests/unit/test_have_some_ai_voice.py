from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.voice import ClaudeRubricInterpreter
from have_some_ai.voice_realtime import (
    DOUBAO_CHAT_TTS_TEXT,
    DOUBAO_CLIENT_INTERRUPT,
    DOUBAO_CONNECTION_STARTED,
    DOUBAO_END_ASR,
    DOUBAO_SAY_HELLO,
    DOUBAO_SESSION_STARTED,
    DOUBAO_START_SESSION,
    DOUBAO_TASK_REQUEST,
    DoubaoProtocol,
    DoubaoRealtimeConfig,
    DoubaoRealtimeVoiceAdapter,
    RealtimeVoiceAdapter,
    build_realtime_system_prompt,
)


class FakeLLM:
    def __init__(self, response: str | list[str]):
        self.responses = [response] if isinstance(response, str) else list(response)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_claude_rubric_interpreter_accepts_direct_a_choice():
    question = _question()
    llm = FakeLLM(
        '{"option_id":"A","confidence":0.95,"reason_zh":"选择A。",'
        '"reason_en":"Chose A.","detected_language":"zh","spoken_choice":"A"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="我选 A",
        detected_language="zh",
    )

    assert result.option_id == "A"
    assert result.confidence == 0.95
    assert result.raw_json["spoken_choice"] == "A"


def test_claude_rubric_interpreter_accepts_direct_b_choice():
    question = _question()
    llm = FakeLLM(
        '{"option_id":"B","confidence":0.93,"reason_zh":"选择B。",'
        '"reason_en":"Chose B.","detected_language":"en","spoken_choice":"B"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="I choose B",
        detected_language="en",
    )

    assert result.option_id == "B"
    assert result.confidence == 0.93
    assert result.raw_json["spoken_choice"] == "B"


def test_claude_rubric_interpreter_keeps_c_as_spoken_choice_but_maps_to_ab():
    question = _question()
    llm = FakeLLM(
        '{"option_id":"A","confidence":0.81,"reason_zh":"自由回答更接近A。",'
        '"reason_en":"The free answer is closer to A.",'
        '"detected_language":"mixed","spoken_choice":"C"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="C，我想说其实我真的会谢谢 AI",
        detected_language="mixed",
    )

    assert result.option_id == "A"
    assert result.raw_json["spoken_choice"] == "C"


def test_claude_rubric_interpreter_allows_low_confidence_for_bare_c():
    question = _question()
    llm = FakeLLM(
        '{"option_id":null,"confidence":0.2,"reason_zh":"只有C，没有具体内容。",'
        '"reason_en":"Only C was spoken, with no content.",'
        '"detected_language":"zh","spoken_choice":"C","status":"unclear"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="其他",
        detected_language="zh",
    )

    assert result.option_id is None
    assert result.confidence < 0.65
    assert result.raw_json["spoken_choice"] == "C"


def test_claude_rubric_interpreter_accepts_unclear_output():
    question = _question()
    llm = FakeLLM(
        '{"option_id":null,"confidence":0.1,"reason_zh":"没太听清。",'
        '"reason_en":"The transcript is unclear.",'
        '"detected_language":"unknown","spoken_choice":"unclear","status":"unclear"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="嗯",
        detected_language="unknown",
    )

    assert result.option_id is None
    assert result.raw_json["status"] == "unclear"


def test_claude_prompt_includes_visible_c_choice():
    question = _question()
    llm = FakeLLM(
        '{"option_id":"A","confidence":0.9,"reason_zh":"",'
        '"reason_en":"","detected_language":"en","spoken_choice":"freeform"}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    interpreter.interpret(question=question, transcript="free answer")

    prompt = llm.calls[0]["messages"][0]["content"]
    assert '"C"' in prompt
    assert "Other. Say anything." in prompt
    assert "scoring_options" in prompt
    assert "compact valid JSON only" in llm.calls[0]["system"]
    assert '"option_id":"A|null"' not in llm.calls[0]["system"]


def test_claude_rubric_interpreter_repairs_malformed_json():
    question = _question()
    llm = FakeLLM([
        (
            '{"status":"accepted","option_id":"A"\n'
            '"confidence":0.86,"reason":"The user has had this experience before."}'
        ),
        (
            '{"status":"accepted","option_id":"A","confidence":0.86,'
            '"reason":"The user has had this experience before.",'
            '"detected_language":"zh","spoken_choice":"freeform"}'
        ),
    ])
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(
        question=question,
        transcript="嗯...有过吧",
        detected_language="zh",
    )

    assert result.option_id == "A"
    assert result.confidence == 0.86
    assert result.raw_json["_json_repaired"] is True
    assert len(llm.calls) == 2
    assert "Do not reinterpret" in llm.calls[1]["system"]


def test_claude_rubric_interpreter_accepts_json_code_fence():
    question = _question()
    llm = FakeLLM(
        '```json\n'
        '{"status":"accepted","option_id":"A","confidence":0.91,'
        '"reason":"The answer is yes.","detected_language":"zh"}\n'
        '```'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(question=question, transcript="有过")

    assert result.option_id == "A"
    assert len(llm.calls) == 1


def test_claude_rubric_interpreter_extracts_balanced_json_from_text():
    question = _question()
    llm = FakeLLM(
        'Here is the mapping:\n'
        '{"status":"accepted","option_id":"A","confidence":0.9,'
        '"reason":"The answer is yes.","detected_language":"zh"}\n'
        'Done.'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(question=question, transcript="有")

    assert result.option_id == "A"
    assert len(llm.calls) == 1


def test_claude_rubric_interpreter_handles_trailing_commas():
    question = _question()
    llm = FakeLLM(
        '{"status":"accepted","option_id":"A","confidence":0.88,'
        '"reason":"The answer is yes.",}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(question=question, transcript="有")

    assert result.option_id == "A"


def test_claude_rubric_interpreter_normalizes_string_null_option():
    question = _question()
    llm = FakeLLM(
        '{"status":"unclear","option_id":"null","confidence":0.2,'
        '"reason":"The answer is too ambiguous."}'
    )
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(question=question, transcript="可能吧")

    assert result.option_id is None
    assert result.raw_json["option_id"] is None
    assert result.raw_json["status"] == "unclear"


def test_claude_rubric_interpreter_returns_unclear_when_repair_fails():
    question = _question()
    llm = FakeLLM(["not json", "still not json"])
    interpreter = ClaudeRubricInterpreter(llm)

    result = interpreter.interpret(question=question, transcript="嗯...有过吧")

    assert result.option_id is None
    assert result.confidence == 0.0
    assert result.raw_json["status"] == "unclear"
    assert "parse_error" in result.raw_json
    assert "repair_error" in result.raw_json


def test_realtime_voice_adapter_placeholder_is_importable():
    adapter = RealtimeVoiceAdapter()

    assert isinstance(adapter, RealtimeVoiceAdapter)


def test_realtime_system_prompt_forbids_autonomous_doubao_decisions():
    prompt = build_realtime_system_prompt({
        "assignment": {"food_code": "soup", "food_label": "Soup"},
    })

    assert "不要自主回答用户问题" in prompt
    assert "不要决定食物" in prompt
    assert "ChatTTSText" in prompt
    assert "food_code" in prompt


def test_doubao_config_uses_fixed_gateway_app_key_by_default(monkeypatch):
    monkeypatch.setenv("HAVE_SOME_AI_DOUBAO_APP_ID", "app-id")
    monkeypatch.delenv("HAVE_SOME_AI_DOUBAO_APP_KEY", raising=False)
    monkeypatch.setenv("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN", "access-token")

    config = DoubaoRealtimeConfig.from_env()

    assert config.app_key == "PlgvMymc7f3tQnJ6"


def test_doubao_start_session_requests_pcm_formats():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1", system_prompt="hello"))

    start_session = _sent_payload(fake_ws, DOUBAO_START_SESSION)
    payload = start_session["payload_msg"]
    assert start_session["session_id"] == "sess-1"
    assert payload["dialog"]["system_role"] == "hello"
    assert "input_mod" not in payload["dialog"]["extra"]
    assert payload["dialog"]["extra"]["model"] == "1.2.1.1"
    assert payload["asr"]["audio_info"] == {
        "format": "pcm_s16le",
        "sample_rate": 16000,
        "channel": 1,
    }
    assert payload["tts"]["audio_config"] == {
        "channel": 1,
        "format": "pcm_s16le",
        "sample_rate": 24000,
    }
    assert payload["tts"]["speaker"] == "zh_female_vv_jupiter_bigtts"


def test_doubao_end_asr_sends_event_400():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1"))
    asyncio.run(adapter.end_asr())

    assert DOUBAO_END_ASR in adapter.sent_event_ids
    end_asr = _sent_payload(fake_ws, DOUBAO_END_ASR)
    assert end_asr["session_id"] == "sess-1"
    assert end_asr["payload_msg"] == {}


def test_doubao_audio_append_sends_task_request_200():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1"))
    asyncio.run(adapter.append_audio(b"pcm"))

    assert DOUBAO_TASK_REQUEST in adapter.sent_event_ids
    audio = _sent_payload(fake_ws, DOUBAO_TASK_REQUEST)
    assert audio["session_id"] == "sess-1"
    assert audio["payload_audio"] == base64.b64encode(b"pcm").decode("ascii")


def test_doubao_interrupt_sends_client_interrupt_515():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1"))
    asyncio.run(adapter.interrupt())

    interrupt = _sent_payload(fake_ws, DOUBAO_CLIENT_INTERRUPT)
    assert interrupt["session_id"] == "sess-1"
    assert interrupt["payload_msg"] == {}


def test_doubao_speak_text_uses_chat_tts_text_500_stream_shape():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1"))
    asyncio.run(adapter.speak_text("你好"))

    tts_frames = _sent_payloads(fake_ws, DOUBAO_CHAT_TTS_TEXT)
    assert len(tts_frames) == 2
    assert tts_frames[0]["session_id"] == "sess-1"
    assert tts_frames[0]["payload_msg"] == {
        "start": True,
        "content": "你好",
        "end": False,
    }
    assert tts_frames[1]["payload_msg"] == {
        "start": False,
        "content": "",
        "end": True,
    }


def test_doubao_say_hello_uses_event_300():
    fake_ws = _FakeWebSocket()
    adapter = DoubaoRealtimeVoiceAdapter(
        _doubao_config(),
        connect=_fake_connect(fake_ws),
    )

    asyncio.run(adapter.start_session(session_id="sess-1"))
    asyncio.run(adapter.say_hello("你好"))

    hello = _sent_payload(fake_ws, DOUBAO_SAY_HELLO)
    assert hello["session_id"] == "sess-1"
    assert hello["payload_msg"] == {"content": "你好"}


def test_doubao_protocol_decodes_transcript_and_pcm_audio_events():
    transcript = DoubaoProtocol.decode(DoubaoProtocol.encode_json(
        451,
        {
            "results": [
                {
                    "text": "我选 A",
                    "is_interim": False,
                },
            ],
        },
        session_id="sess-1",
    ))
    interim = DoubaoProtocol.decode(DoubaoProtocol.encode_json(
        451,
        {
            "results": [
                {
                    "text": "我",
                    "is_interim": True,
                },
            ],
        },
        session_id="sess-1",
    ))
    audio = DoubaoProtocol.decode(DoubaoProtocol.encode_audio(
        352,
        b"pcm-bytes",
        session_id="sess-1",
    ))

    assert transcript.type == "transcript.final"
    assert transcript.data["transcript"] == "我选 A"
    assert interim.type == "transcript.delta"
    assert interim.data["transcript"] == "我"
    assert audio.type == "audio.delta"
    assert audio.data["audio_base64"] == base64.b64encode(b"pcm-bytes").decode("ascii")
    assert audio.data["audio_format"] == "pcm_s16le"
    assert audio.data["sample_rate"] == 24000


def test_doubao_protocol_keeps_legacy_json_transcript_test_compatibility():
    transcript = DoubaoProtocol.decode(json.dumps({
        "event": 451,
        "payload_msg": {
            "transcript": "我选 A",
            "final": True,
        },
    }))
    audio_payload = base64.b64encode(b"pcm-bytes").decode("ascii")
    audio = DoubaoProtocol.decode(json.dumps({
        "event": 500,
        "payload_audio": audio_payload,
    }))

    assert transcript.type == "transcript.final"
    assert transcript.data["transcript"] == "我选 A"
    assert audio.type == "audio.delta"
    assert audio.data["audio_base64"] == audio_payload
    assert audio.data["audio_format"] == "pcm_s16le"
    assert audio.data["sample_rate"] == 24000


def test_doubao_protocol_does_not_treat_non_asr_text_as_transcript():
    event = DoubaoProtocol.decode(DoubaoProtocol.encode_json(
        150,
        {"text": "b7c6cad3-d331-4a90-96a5-28eb75e25a8e"},
        session_id="sess-1",
    ))

    assert event.type == "state"
    assert event.data["event"] == 150


def test_doubao_protocol_decodes_connection_response_session_id():
    frame = DoubaoProtocol.decode_frame(DoubaoProtocol.encode_json(
        DOUBAO_CONNECTION_STARTED,
        {},
        session_id="connect-id",
    ))

    assert frame["event"] == DOUBAO_CONNECTION_STARTED
    assert frame["session_id"] == "connect-id"
    assert frame["payload_msg"] == {}


def test_doubao_protocol_decodes_error_code_before_payload():
    payload = b'{"error":"StartSession failed"}'
    frame_bytes = (
        bytes([0x11, 0xF0, 0x10, 0x00])
        + (42000020).to_bytes(4, "big", signed=True)
        + len(payload).to_bytes(4, "big", signed=True)
        + payload
    )

    frame = DoubaoProtocol.decode_frame(frame_bytes)
    event = DoubaoProtocol.decode(frame_bytes)

    assert frame["message_type"] == 15
    assert frame["error_code"] == 42000020
    assert frame["error"] == "StartSession failed"
    assert event.type == "error"
    assert "StartSession failed" in event.data["detail"]


class _FakeWebSocket:
    def __init__(self):
        self.sent: list[bytes] = []
        self.recv_events: list[bytes] = [
            DoubaoProtocol.encode_json(
                DOUBAO_CONNECTION_STARTED,
                {},
                session_id="fake-connect-id",
            ),
            DoubaoProtocol.encode_json(DOUBAO_SESSION_STARTED, {}, session_id="sess-1"),
        ]

    async def send(self, payload: bytes):
        self.sent.append(payload)

    async def recv(self):
        if self.recv_events:
            return self.recv_events.pop(0)
        raise RuntimeError("no fake events")

    async def close(self):
        return None


def _fake_connect(fake_ws: _FakeWebSocket):
    async def connect(_url, _headers):
        return fake_ws

    return connect


def _doubao_config() -> DoubaoRealtimeConfig:
    return DoubaoRealtimeConfig(
        app_id="app-id",
        app_key="app-key",
        access_token="access-token",
    )


def _sent_payload(fake_ws: _FakeWebSocket, event_id: int) -> dict:
    for payload in fake_ws.sent:
        data = DoubaoProtocol.decode_frame(payload)
        if data["event"] == event_id:
            return data
    raise AssertionError(f"event {event_id} was not sent")


def _sent_payloads(fake_ws: _FakeWebSocket, event_id: int) -> list[dict]:
    return [
        data
        for payload in fake_ws.sent
        if (data := DoubaoProtocol.decode_frame(payload))["event"] == event_id
    ]


def _question():
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"])
    return bank.get_question("m1_thank_ai")
