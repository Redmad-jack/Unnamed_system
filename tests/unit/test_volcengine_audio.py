from __future__ import annotations

import asyncio
import gzip
import json
import struct

import conscious_entity.audio.volcengine_tts as tts_module
from conscious_entity.audio.config import AudioConfig
from conscious_entity.audio.types import AudioError, TranscriptEvent
from conscious_entity.audio.volcengine_stt import VolcengineSTTClient
from conscious_entity.audio.volcengine_stt import _is_normal_websocket_close
from conscious_entity.audio.volcengine_tts import VolcengineTTSClient
from conscious_entity.audio.volcengine_protocol import (
    COMPRESSION_GZIP,
    COMPRESSION_NONE,
    EVENT_CONNECTION_STARTED,
    EVENT_FINISH_SESSION,
    EVENT_SESSION_STARTED,
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_START_CONNECTION,
    EVENT_START_SESSION,
    EVENT_TASK_REQUEST,
    EVENT_TTS_RESPONSE,
    FLAG_POS_SEQUENCE,
    FLAG_WITH_EVENT,
    MSG_AUDIO_ONLY_RESPONSE,
    MSG_ERROR,
    MSG_FULL_SERVER_RESPONSE,
    SERIALIZATION_JSON,
    SERIALIZATION_NONE,
    VolcengineProtocol,
    media_type_for_format,
)


def test_headers_api_key_and_asr_tracking_headers():
    protocol = VolcengineProtocol()
    config = AudioConfig(api_key="api-secret")

    headers = protocol.build_headers(config, resource_id="stt-resource", service="asr")

    assert headers["X-Api-Key"] == "api-secret"
    assert headers["X-Api-Resource-Id"] == "stt-resource"
    assert headers["X-Api-Sequence"] == "-1"
    assert headers["X-Api-Request-Id"]
    assert "X-Api-App-Key" not in headers


def test_headers_app_token_fallback():
    protocol = VolcengineProtocol()
    config = AudioConfig(app_id="app", access_token="token")

    headers = protocol.build_headers(config, resource_id="tts-resource")

    assert headers["X-Api-App-Key"] == "app"
    assert headers["X-Api-App-Id"] == "app"
    assert headers["X-Api-Access-Key"] == "token"


def test_asr_start_packet_uses_v3_binary_json_gzip_payload():
    protocol = VolcengineProtocol()
    config = AudioConfig(sample_rate=16000)

    packet = protocol.build_stt_start_packet(config, session_id="aud")
    payload = _sized_payload(packet, compression=COMPRESSION_GZIP)

    assert packet[:4] == bytes([0x11, 0x10, 0x11, 0x00])
    assert payload["audio"]["format"] == "pcm"
    assert payload["audio"]["rate"] == 16000
    assert payload["request"]["model_name"] == "bigmodel"
    assert payload["request"]["enable_nonstream"] is True
    assert payload["request"]["show_utterances"] is True


def test_asr_audio_packet_marks_final_frame():
    protocol = VolcengineProtocol()

    normal = protocol.build_stt_audio_packet(b"pcm", sequence=1)
    final = protocol.build_stt_audio_packet(b"", sequence=-1, final=True)

    assert normal[:4] == bytes([0x11, 0x20, 0x01, 0x00])
    assert gzip.decompress(normal[8:]) == b"pcm"
    assert final[:4] == bytes([0x11, 0x22, 0x01, 0x00])


def test_asr_response_parse_partial_and_definite_final():
    protocol = VolcengineProtocol()
    partial_packet = _asr_server_packet({"result": {"text": "你还"}})
    final_packet = _asr_server_packet({
        "result": {
            "text": "你还记得我吗？",
            "utterances": [{"text": "你还记得我吗？", "definite": True}],
        }
    })

    partial = protocol.parse_stt_response(partial_packet, session_id="aud")
    final = protocol.parse_stt_response(final_packet, session_id="aud")

    assert isinstance(partial, TranscriptEvent)
    assert partial.is_final is False
    assert partial.text == "你还"
    assert isinstance(final, TranscriptEvent)
    assert final.is_final is True
    assert final.text == "你还记得我吗？"


def test_asr_error_frame_maps_to_audio_error():
    protocol = VolcengineProtocol()
    packet = _error_packet(MSG_ERROR, {"message": "bad request"}, code=45000001)

    event = protocol.parse_stt_response(packet, session_id="aud")

    assert isinstance(event, AudioError)
    assert event.code == "stt_protocol_error"
    assert "bad request" in event.message


def test_tts_start_connection_and_session_frames():
    protocol = VolcengineProtocol()
    config = AudioConfig(
        tts_voice_type="zh_female_test_bigtts",
        output_format="mp3",
        tts_sample_rate=24000,
    )

    connection = protocol.build_tts_start_connection()
    session = protocol.build_tts_start_session(config, session_id="sess")
    event, session_id, payload = _event_payload(session)

    assert connection[:4] == bytes([0x11, 0x14, 0x10, 0x00])
    assert struct.unpack(">i", connection[4:8])[0] == EVENT_START_CONNECTION
    assert event == EVENT_START_SESSION
    assert session_id == "sess"
    assert payload["namespace"] == "BidirectionalTTS"
    assert payload["req_params"]["speaker"] == "zh_female_test_bigtts"
    assert payload["req_params"]["audio_params"] == {"format": "mp3", "sample_rate": 24000}


def test_tts_task_and_finish_session_frames():
    protocol = VolcengineProtocol()

    task = protocol.build_tts_task_request(session_id="sess", text="你好")
    finish = protocol.build_tts_finish_session(session_id="sess")
    task_event, task_session, task_payload = _event_payload(task)
    finish_event, finish_session, finish_payload = _event_payload(finish)

    assert task_event == EVENT_TASK_REQUEST
    assert task_session == "sess"
    assert task_payload["req_params"]["text"] == "你好"
    assert finish_event == EVENT_FINISH_SESSION
    assert finish_session == "sess"
    assert finish_payload == {}


def test_tts_parse_audio_and_session_finished_frames():
    protocol = VolcengineProtocol()
    audio_frame = _tts_server_frame(
        MSG_AUDIO_ONLY_RESPONSE,
        EVENT_TTS_RESPONSE,
        b"audio",
        serialization=SERIALIZATION_NONE,
    )
    done_frame = _tts_server_frame(
        MSG_FULL_SERVER_RESPONSE,
        EVENT_SESSION_FINISHED,
        {"status_code": 20000000, "message": "ok"},
    )

    audio = protocol.parse_tts_message(audio_frame)
    done = protocol.parse_tts_message(done_frame)

    assert audio.audio == b"audio"
    assert audio.event_code == EVENT_TTS_RESPONSE
    assert done.done is True
    assert done.event_code == EVENT_SESSION_FINISHED


def test_tts_parse_session_failed_frame():
    protocol = VolcengineProtocol()
    failed = _tts_server_frame(
        MSG_FULL_SERVER_RESPONSE,
        EVENT_SESSION_FAILED,
        {"status_code": 45000001, "message": "voice missing"},
    )

    event = protocol.parse_tts_message(failed)

    assert isinstance(event.error, AudioError)
    assert event.error.code == "tts_protocol_error"
    assert "voice missing" in event.error.message


def test_tts_client_runs_bidirectional_session(monkeypatch):
    responses = [
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED, {}),
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED, {}),
        _tts_server_frame(
            MSG_AUDIO_ONLY_RESPONSE,
            EVENT_TTS_RESPONSE,
            b"audio",
            serialization=SERIALIZATION_NONE,
        ),
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_SESSION_FINISHED, {"status_code": 20000000}),
    ]
    fake = _FakeWebSocket(responses)
    monkeypatch.setattr(tts_module, "_import_websockets", lambda: object())
    monkeypatch.setattr(tts_module, "_connect", lambda _websockets, _endpoint, _headers: fake)
    client = VolcengineTTSClient(AudioConfig(api_key="key", tts_voice_type="voice"))

    chunks = asyncio.run(_collect(client.synthesize_stream(["第一句。", "第二句。"])))

    assert chunks == [b"audio"]
    assert client.last_logid == "logid"
    assert len(fake.sent) == 6
    assert struct.unpack(">i", fake.sent[0][4:8])[0] == EVENT_START_CONNECTION
    assert struct.unpack(">i", fake.sent[1][4:8])[0] == EVENT_START_SESSION
    assert struct.unpack(">i", fake.sent[2][4:8])[0] == EVENT_TASK_REQUEST
    assert struct.unpack(">i", fake.sent[3][4:8])[0] == EVENT_TASK_REQUEST
    assert struct.unpack(">i", fake.sent[4][4:8])[0] == EVENT_FINISH_SESSION


def test_tts_client_exposes_incremental_session_api(monkeypatch):
    responses = [
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED, {}),
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED, {}),
        _tts_server_frame(
            MSG_AUDIO_ONLY_RESPONSE,
            EVENT_TTS_RESPONSE,
            b"audio-1",
            serialization=SERIALIZATION_NONE,
        ),
        _tts_server_frame(
            MSG_AUDIO_ONLY_RESPONSE,
            EVENT_TTS_RESPONSE,
            b"audio-2",
            serialization=SERIALIZATION_NONE,
        ),
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_SESSION_FINISHED, {"status_code": 20000000}),
    ]
    fake = _FakeWebSocket(responses)
    monkeypatch.setattr(tts_module, "_import_websockets", lambda: object())
    monkeypatch.setattr(tts_module, "_connect", lambda _websockets, _endpoint, _headers: fake)
    client = VolcengineTTSClient(AudioConfig(api_key="key", tts_voice_type="voice"))

    async def run_session():
        session = await client.open_session()
        try:
            await session.send_text("第一段。")
            await session.send_text("第二段。")
            await session.finish()
            return [chunk async for chunk in session.receive_audio()]
        finally:
            await session.close()

    chunks = asyncio.run(run_session())

    assert chunks == [b"audio-1", b"audio-2"]
    assert len(fake.sent) == 6
    assert struct.unpack(">i", fake.sent[2][4:8])[0] == EVENT_TASK_REQUEST
    assert struct.unpack(">i", fake.sent[3][4:8])[0] == EVENT_TASK_REQUEST
    assert struct.unpack(">i", fake.sent[4][4:8])[0] == EVENT_FINISH_SESSION


def test_tts_session_interrupt_sends_cancel_without_finish_connection(monkeypatch):
    responses = [
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_CONNECTION_STARTED, {}),
        _tts_server_frame(MSG_FULL_SERVER_RESPONSE, EVENT_SESSION_STARTED, {}),
    ]
    fake = _FakeWebSocket(responses)
    monkeypatch.setattr(tts_module, "_import_websockets", lambda: object())
    monkeypatch.setattr(tts_module, "_connect", lambda _websockets, _endpoint, _headers: fake)
    client = VolcengineTTSClient(AudioConfig(api_key="key", tts_voice_type="voice"))

    async def run_session():
        session = await client.open_session()
        await session.send_text("第一段。")
        await session.interrupt()

    asyncio.run(run_session())

    events = [struct.unpack(">i", frame[4:8])[0] for frame in fake.sent]
    assert EVENT_TASK_REQUEST in events
    assert 101 in events
    assert 2 not in events


def test_stt_client_ignores_normal_server_close_after_final_packet():
    client = VolcengineSTTClient(AudioConfig(api_key="key", tts_voice_type="voice"))
    fake = _ClosingWebSocket()

    events = asyncio.run(_collect(client._drain_until_timeout(fake, session_id="aud")))

    assert len(events) == 1
    assert events[0].event_type == "stt.stream_closed"
    assert events[0].reason == "websocket_closed_ok"
    assert events[0].recoverable is True


def test_stt_treats_rst_stream_no_error_as_normal_close():
    exc = RuntimeError(
        "stt_protocol_error: [Server-side generic error] result: rpc error: "
        "code = 13 desc = stream terminated by RST_STREAM with error code: NO_ERROR"
    )

    assert _is_normal_websocket_close(exc) is True


def test_stt_client_surfaces_rst_stream_no_error_as_stream_event():
    client = VolcengineSTTClient(AudioConfig(api_key="key", tts_voice_type="voice"))
    client.last_logid = "logid"
    fake = _RstNoErrorWebSocket()

    events = asyncio.run(_collect(client._drain_available(fake, session_id="aud")))

    assert len(events) == 1
    assert events[0].event_type == "stt.stream_closed"
    assert events[0].reason == "server_rst_stream_no_error"
    assert events[0].message == "STT server ended the streaming RPC with RST_STREAM NO_ERROR."
    assert events[0].recoverable is True
    assert events[0].logid == "logid"


def test_stt_stream_pcm_surfaces_recoverable_close_on_audio_send(monkeypatch):
    fake = _SendClosingWebSocket()
    monkeypatch.setattr("conscious_entity.audio.volcengine_stt._import_websockets", lambda: object())
    monkeypatch.setattr(
        "conscious_entity.audio.volcengine_stt._connect",
        lambda _websockets, _endpoint, _headers: fake,
    )
    client = VolcengineSTTClient(AudioConfig(api_key="key", tts_voice_type="voice"))

    async def audio_chunks():
        yield b"pcm"

    events = asyncio.run(_collect(client.stream_pcm(audio_chunks(), session_id="aud")))

    assert len(events) == 1
    assert events[0].event_type == "stt.stream_closed"
    assert events[0].reason == "server_rst_stream_no_error"
    assert fake.sent


def test_media_type_for_format():
    assert media_type_for_format("mp3") == "audio/mpeg"
    assert media_type_for_format("ogg_opus") == "audio/ogg"
    assert media_type_for_format("pcm") == "audio/L16"


def _sized_payload(packet: bytes, *, compression: int) -> dict:
    payload_size = struct.unpack(">I", packet[4:8])[0]
    payload = packet[8 : 8 + payload_size]
    if compression == COMPRESSION_GZIP:
        payload = gzip.decompress(payload)
    return json.loads(payload.decode("utf-8"))


def _event_payload(packet: bytes) -> tuple[int, str | None, dict]:
    event = struct.unpack(">i", packet[4:8])[0]
    offset = 8
    session_id = None
    if len(packet) > offset + 4:
        possible_session_size = struct.unpack(">I", packet[offset : offset + 4])[0]
        remaining_after_size = len(packet) - (offset + 4)
        if possible_session_size <= remaining_after_size - 4:
            offset += 4
            session_id = packet[offset : offset + possible_session_size].decode("utf-8")
            offset += possible_session_size
    payload_size = struct.unpack(">I", packet[offset : offset + 4])[0]
    offset += 4
    payload = json.loads(packet[offset : offset + payload_size].decode("utf-8"))
    return event, session_id, payload


def _asr_server_packet(payload: dict) -> bytes:
    data = gzip.compress(json.dumps(payload).encode("utf-8"))
    return (
        _header(MSG_FULL_SERVER_RESPONSE, FLAG_POS_SEQUENCE, SERIALIZATION_JSON, COMPRESSION_GZIP)
        + struct.pack(">i", 1)
        + struct.pack(">I", len(data))
        + data
    )


def _tts_server_frame(
    message_type: int,
    event: int,
    payload: dict | bytes,
    *,
    serialization: int = SERIALIZATION_JSON,
) -> bytes:
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload).encode("utf-8")
    else:
        payload_bytes = payload
    session_id = b"sess"
    return (
        _header(message_type, FLAG_WITH_EVENT, serialization, COMPRESSION_NONE)
        + struct.pack(">i", event)
        + struct.pack(">I", len(session_id))
        + session_id
        + struct.pack(">I", len(payload_bytes))
        + payload_bytes
    )


def _error_packet(message_type: int, payload: dict, *, code: int) -> bytes:
    payload_bytes = json.dumps(payload).encode("utf-8")
    return (
        _header(message_type, 0, SERIALIZATION_JSON, COMPRESSION_NONE)
        + struct.pack(">I", code)
        + struct.pack(">I", len(payload_bytes))
        + payload_bytes
    )


def _header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([0x11, (message_type << 4) | flags, (serialization << 4) | compression, 0x00])


async def _collect(iterator):
    return [chunk async for chunk in iterator]


class _FakeWebSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.response_headers = {"X-Tt-Logid": "logid"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        return self.responses.pop(0)


class ConnectionClosedOK(Exception):
    pass


class _ClosingWebSocket:
    async def recv(self):
        raise ConnectionClosedOK("received 1000 OK")


class _RstNoErrorWebSocket:
    async def recv(self):
        raise RuntimeError(
            "stt_protocol_error: [Server-side generic error] result: rpc error: "
            "code = 13 desc = stream terminated by RST_STREAM with error code: NO_ERROR"
        )


class _SendClosingWebSocket(_FakeWebSocket):
    def __init__(self):
        super().__init__([])

    async def send(self, message):
        self.sent.append(message)
        if len(self.sent) > 1:
            raise RuntimeError(
                "stt_protocol_error: [Server-side generic error] result: rpc error: "
                "code = 13 desc = stream terminated by RST_STREAM with error code: NO_ERROR"
            )
