from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.doubao.asr_client import DoubaoASRConfig
from have_some_ai.doubao.asr_protocol import (
    ASR_AUDIO_REQUEST_HEADER,
    ASR_FINAL_AUDIO_REQUEST_HEADER,
    ASR_FULL_CLIENT_REQUEST_HEADER,
    DoubaoASRProtocolError,
    encode_audio_request,
    encode_full_client_request,
    parse_server_response,
    transcript_events_from_payload,
)
from have_some_ai.doubao.tts_bidirectional_client import DoubaoTTSConfig
from have_some_ai.doubao.tts_protocol import (
    TTS_CANCEL_SESSION,
    TTS_CONNECTION_STARTED,
    TTS_FINISH_SESSION,
    TTS_RESPONSE,
    TTS_SENTENCE_END,
    TTS_SENTENCE_START,
    TTS_SESSION_CANCELED,
    TTS_SESSION_FINISHED,
    TTS_SESSION_STARTED,
    TTS_START_CONNECTION,
    TTS_START_SESSION,
    TTS_TASK_REQUEST,
    encode_event_payload,
    parse_tts_response,
)
from have_some_ai.doubao.tts_bidirectional_client import DoubaoTTSBidirectionalClient
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.voice import ClaudeRubricInterpreter


class FakeLLM:
    def __init__(self, response: str | list[str]):
        self.responses = [response] if isinstance(response, str) else list(response)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_claude_rubric_judge_accepts_direct_a_choice():
    llm = FakeLLM(
        '{"label":"A","confidence":0.95,"rationale":"The visitor clearly said A.",'
        '"detected_language":"zh"}'
    )
    result = ClaudeRubricInterpreter(llm).interpret(
        question=_question(),
        transcript="我选 A",
        detected_language="zh",
    )

    assert result.option_id == "A"
    assert result.confidence == 0.95
    assert result.raw_json["label"] == "A"


def test_claude_rubric_judge_accepts_direct_b_choice():
    llm = FakeLLM(
        '{"label":"B","confidence":0.93,"rationale":"The visitor clearly said B.",'
        '"detected_language":"en"}'
    )
    result = ClaudeRubricInterpreter(llm).interpret(
        question=_question(),
        transcript="I choose B",
        detected_language="en",
    )

    assert result.option_id == "B"
    assert result.confidence == 0.93
    assert result.raw_json["label"] == "B"


def test_claude_rubric_judge_accepts_confidence_at_055_threshold():
    llm = FakeLLM(
        '{"label":"A","confidence":0.56,"rationale":"The visitor clearly said A.",'
        '"detected_language":"zh"}'
    )
    result = ClaudeRubricInterpreter(llm).interpret(
        question=_question(),
        transcript="我选 A",
        detected_language="zh",
    )

    assert result.option_id == "A"
    assert result.confidence == 0.56
    assert result.raw_json["status"] == "accepted"


def test_claude_rubric_judge_keeps_c_and_freeform_unclear():
    llm = FakeLLM(
        '{"label":"unclear","confidence":0.2,'
        '"rationale":"The visitor gave a free-form answer instead of choosing A or B.",'
        '"detected_language":"mixed"}'
    )
    result = ClaudeRubricInterpreter(llm).interpret(
        question=_question(),
        transcript="C，我想说其实我真的会谢谢 AI",
        detected_language="mixed",
    )

    assert result.option_id is None
    assert result.raw_json["label"] == "unclear"
    assert result.raw_json["status"] == "unclear"


def test_claude_prompt_forbids_flow_and_food_decisions():
    llm = FakeLLM(
        '{"label":"A","confidence":0.9,"rationale":"The visitor clearly said A."}'
    )
    ClaudeRubricInterpreter(llm).interpret(question=_question(), transcript="A")

    system = llm.calls[0]["system"]
    assert "Do not chat" in system
    assert "score, or assign food" in system
    assert "FormalTurnRouter" in system
    assert '"label":"A"' in system
    assert "Shopkeeper runtime context" not in system

    prompt_payload = json.loads(llm.calls[0]["messages"][0]["content"])
    assert set(prompt_payload["visible_choices"]) == {"A", "B"}
    assert "C" not in prompt_payload["visible_choices"]


def test_claude_rubric_judge_repairs_malformed_json():
    llm = FakeLLM([
        '{"label":"A"\n"confidence":0.86,"rationale":"The visitor clearly said A."}',
        '{"label":"A","confidence":0.86,"rationale":"The visitor clearly said A."}',
    ])
    result = ClaudeRubricInterpreter(llm).interpret(
        question=_question(),
        transcript="A",
    )

    assert result.option_id == "A"
    assert result.raw_json["_json_repaired"] is True
    assert len(llm.calls) == 2


def test_asr_full_client_request_frame_uses_gzip_json_size():
    payload = {
        "user": {"uid": "tester"},
        "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {"model_name": "bigmodel", "enable_nonstream": True},
    }
    frame = encode_full_client_request(payload)

    assert frame[:4] == ASR_FULL_CLIENT_REQUEST_HEADER
    payload_size = int.from_bytes(frame[4:8], "big")
    compressed = frame[8:]
    assert payload_size == len(compressed)
    assert json.loads(gzip.decompress(compressed).decode("utf-8")) == payload


def test_asr_regular_audio_frame_uses_no_sequence_and_gzip_audio():
    frame = encode_audio_request(b"pcm")

    assert frame[:4] == ASR_AUDIO_REQUEST_HEADER
    payload_size = int.from_bytes(frame[4:8], "big")
    assert payload_size == len(frame[8:])
    assert gzip.decompress(frame[8:]) == b"pcm"


def test_asr_final_audio_frame_uses_no_sequence_and_last_packet_flag():
    frame = encode_audio_request(b"", final=True)

    assert frame[:4] == ASR_FINAL_AUDIO_REQUEST_HEADER
    assert gzip.decompress(frame[8:]) == b""


def test_asr_response_parser_decodes_sequence_and_gzip_json():
    body = {"result": {"text": "我", "utterances": []}}
    frame = _asr_server_json_frame(body, sequence=7)

    response = parse_server_response(frame)

    assert response.sequence == 7
    assert response.payload == body


def test_asr_response_parser_decodes_error_frame():
    payload = b'{"message":"bad gzip"}'
    frame = bytes([0x11, 0xF0, 0x10, 0x00])
    frame += (42000001).to_bytes(4, "big", signed=True)
    frame += len(payload).to_bytes(4, "big")
    frame += payload

    with pytest.raises(DoubaoASRProtocolError, match="bad gzip"):
        parse_server_response(frame, request_id="req-1", log_id="log-1")


def test_asr_transcript_events_handle_result_dict_list_missing_and_dedupe():
    seen: set[tuple[object, object, str]] = set()
    dict_payload = {
        "result": {
            "text": "partial",
            "utterances": [
                {"text": "我选 A", "start_time": 1, "end_time": 2, "definite": True},
                {"text": "还没定", "start_time": 2, "end_time": 3, "definite": False},
            ],
        }
    }
    list_payload = {
        "result": [
            {
                "text": "full text",
                "utterances": [
                    {"text": "我选 A", "start_time": 1, "end_time": 2, "definite": True},
                    {"text": "我选 B", "start_time": 3, "end_time": 4, "definite": True},
                ],
            }
        ]
    }

    first = transcript_events_from_payload(dict_payload, seen_final_keys=seen)
    second = transcript_events_from_payload(list_payload, seen_final_keys=seen)
    missing = transcript_events_from_payload({"status": "ok"}, seen_final_keys=seen)

    assert [event.type for event in first] == ["partial", "final"]
    assert first[1].text == "我选 A"
    assert [event.text for event in second if event.type == "final"] == ["我选 B"]
    assert missing == []


def test_asr_config_defaults_to_bigmodel_async_and_duration_resource(monkeypatch):
    monkeypatch.setenv("DOUBAO_ASR_API_KEY", "asr-key")

    config = DoubaoASRConfig.from_env()

    assert config.endpoint.endswith("/sauc/bigmodel_async")
    assert config.resource_id == "volc.seedasr.sauc.duration"
    assert config.enable_nonstream is True
    assert config.sample_rate == 16000


def test_tts_start_connection_frame_shape():
    frame = encode_event_payload(TTS_START_CONNECTION, {})

    assert frame[:4] == bytes([0x11, 0x14, 0x10, 0x00])
    assert int.from_bytes(frame[4:8], "big", signed=True) == 1
    payload_size = int.from_bytes(frame[8:12], "big")
    assert frame[12:12 + payload_size] == b"{}"


def test_tts_start_session_payload_fixes_speaker_and_resource_id():
    client = DoubaoTTSBidirectionalClient(DoubaoTTSConfig(api_key="tts-key"))
    payload = client.start_session_payload()
    frame = encode_event_payload(TTS_START_SESSION, payload, session_id="session-long-id")

    offset = 8
    session_len = int.from_bytes(frame[offset:offset + 4], "big")
    offset += 4
    assert session_len == len("session-long-id".encode("utf-8"))
    assert DoubaoTTSConfig(api_key="tts-key").resource_id == "seed-icl-2.0"
    assert payload["req_params"]["speaker"] == "S_ud9II0522"
    assert payload["req_params"]["audio_params"]["format"] == "pcm"
    assert payload["req_params"]["audio_params"]["sample_rate"] == 24000
    assert payload["req_params"]["text"] == ""


def test_tts_headers_use_new_console_api_key_auth():
    client = DoubaoTTSBidirectionalClient(DoubaoTTSConfig(api_key="tenant-api-key"))

    headers = client.headers()

    assert headers["X-Api-Key"] == "tenant-api-key"
    assert headers["X-Api-Resource-Id"] == "seed-icl-2.0"
    assert headers["X-Api-Connect-Id"] == client.connect_id
    assert "X-Api-App-Id" not in headers
    assert "X-Api-App-Key" not in headers
    assert "X-Api-Access-Key" not in headers


def test_tts_task_request_puts_text_in_req_params():
    client = DoubaoTTSBidirectionalClient(DoubaoTTSConfig(api_key="tts-key"))
    payload = client.task_request_payload("你好")
    frame = encode_event_payload(TTS_TASK_REQUEST, payload, session_id="sess")

    assert int.from_bytes(frame[4:8], "big", signed=True) == 200
    assert payload["req_params"]["text"] == "你好"


def test_tts_finish_and_cancel_session_payloads_are_empty():
    finish = encode_event_payload(TTS_FINISH_SESSION, {}, session_id="sess")
    cancel = encode_event_payload(TTS_CANCEL_SESSION, {}, session_id="sess")

    assert int.from_bytes(finish[4:8], "big", signed=True) == 102
    assert finish[-2:] == b"{}"
    assert int.from_bytes(cancel[4:8], "big", signed=True) == 101
    assert cancel[-2:] == b"{}"


def test_tts_response_parser_handles_state_and_audio_events():
    events = [
        parse_tts_response(_tts_server_json(TTS_CONNECTION_STARTED, {}, connection_id="conn")),
        parse_tts_response(_tts_server_json(TTS_SESSION_STARTED, {}, session_id="sess")),
        parse_tts_response(_tts_server_json(TTS_SENTENCE_START, {"text": "你"}, session_id="sess")),
        parse_tts_response(_tts_server_json(TTS_SENTENCE_END, {"text": "你"}, session_id="sess")),
        parse_tts_response(_tts_server_audio(TTS_RESPONSE, b"pcm", session_id="sess")),
        parse_tts_response(_tts_server_json(TTS_SESSION_CANCELED, {}, session_id="sess")),
        parse_tts_response(_tts_server_json(TTS_SESSION_FINISHED, {"usage": {}}, session_id="sess")),
    ]

    assert [event.event for event in events] == [50, 150, 350, 351, 352, 151, 152]
    assert events[0].connection_id == "conn"
    assert events[4].audio == b"pcm"


def _asr_server_json_frame(payload: dict, *, sequence: int | None = None) -> bytes:
    compressed = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    flags = 0b0001 if sequence is not None else 0b0000
    frame = bytes([0x11, (0x9 << 4) | flags, 0x11, 0x00])
    if sequence is not None:
        frame += sequence.to_bytes(4, "big", signed=True)
    frame += len(compressed).to_bytes(4, "big")
    frame += compressed
    return frame


def _tts_server_json(
    event: int,
    payload: dict,
    *,
    connection_id: str | None = None,
    session_id: str | None = None,
) -> bytes:
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    body = event.to_bytes(4, "big", signed=True)
    identity = connection_id if connection_id is not None else session_id or ""
    identity_bytes = identity.encode("utf-8")
    body += len(identity_bytes).to_bytes(4, "big")
    body += identity_bytes
    body += len(payload_bytes).to_bytes(4, "big")
    body += payload_bytes
    return bytes([0x11, 0x94, 0x10, 0x00]) + body


def _tts_server_audio(event: int, payload: bytes, *, session_id: str) -> bytes:
    session_bytes = session_id.encode("utf-8")
    body = event.to_bytes(4, "big", signed=True)
    body += len(session_bytes).to_bytes(4, "big")
    body += session_bytes
    body += len(payload).to_bytes(4, "big")
    body += payload
    return bytes([0x11, 0xB4, 0x00, 0x00]) + body


def _question():
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"])
    return bank.get_question("m1_thank_ai")
