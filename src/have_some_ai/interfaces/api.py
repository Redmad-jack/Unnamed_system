from __future__ import annotations

import asyncio
import os
import sqlite3
import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from conscious_entity.db.connection import get_connection
from conscious_entity.runtime_env import load_project_env, project_root
from have_some_ai.config import default_config_dir, load_have_some_ai_config
from have_some_ai.conversation import ConversationOrchestrator
from have_some_ai.db import run_migrations
from have_some_ai.models import QueueStatus
from have_some_ai.openai_file_stt import OpenAIFileTranscription
from have_some_ai.openai_tts import OpenAITextToSpeech
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService
from have_some_ai.voice import ClaudeRubricInterpreter
from have_some_ai.voice_provider import resolve_voice_provider_config
from have_some_ai.voice_realtime import (
    DOUBAO_TTS_ENDED,
    DoubaoRealtimeVoiceAdapter,
    RealtimeVoiceAdapter,
    RealtimeVoiceEvent,
    build_realtime_system_prompt,
)


def _config_dir() -> Path:
    env = os.getenv("HAVE_SOME_AI_CONFIG_DIR")
    return Path(env) if env else default_config_dir(project_root())


def _db_path() -> Path:
    env = os.getenv("HAVE_SOME_AI_DB_PATH")
    return Path(env) if env else project_root() / "data" / "have_some_ai.db"


def _static_dir() -> Path:
    return Path(__file__).parent / "static"


class ParticipantCreateRequest(BaseModel):
    notes: str | None = None
    safety_flags: dict[str, Any] = Field(default_factory=dict)


class AnswerItem(BaseModel):
    question_id: str
    option_id: str


class AnswersRequest(BaseModel):
    answers: list[AnswerItem]
    assign_immediately: bool = True


class ObservationItem(BaseModel):
    event_type: str
    confidence: float = 1.0
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationsRequest(BaseModel):
    events: list[ObservationItem]


class VoiceAnswerRequest(BaseModel):
    question_id: str
    transcript: str
    detected_language: str | None = None
    stt_confidence: float | None = None
    stt_metadata: dict[str, Any] = Field(default_factory=dict)
    attempt_id: str | None = None
    assign_if_complete: bool = True


class VoiceAudioRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    mime_type: str = Field(..., min_length=1)
    duration_ms: int | None = None
    attempt_id: str = Field(..., min_length=1)
    detected_language: str | None = None
    assign_if_complete: bool = True


class ConversationTurnRequest(BaseModel):
    transcript: str
    include_audio: bool = False


class ConversationAudioRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    mime_type: str = Field(..., min_length=1)
    duration_ms: int | None = None
    attempt_id: str | None = None
    detected_language: str | None = None
    include_audio: bool = True


class QueueUpdateRequest(BaseModel):
    status: QueueStatus
    staff_notes: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_project_env()

    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path, check_same_thread=False)
    run_migrations(conn)

    configs = load_have_some_ai_config(_config_dir())
    question_bank = QuestionBank(configs["questions"])
    scoring_engine = ScoringEngine(configs["scoring"], question_bank)
    repository = MealRepository(conn)
    threshold = float(os.getenv("HAVE_SOME_AI_RUBRIC_CONFIDENCE_THRESHOLD", "0.65"))

    app.state.conn = conn
    app.state.configs = configs
    app.state.service = MealService(
        repository,
        question_bank,
        scoring_engine,
        rubric_interpreter=ClaudeRubricInterpreter(),
        rubric_confidence_threshold=threshold,
    )
    app.state.conversation = ConversationOrchestrator(app.state.service)
    app.state.voice_config = resolve_voice_provider_config()
    app.state.file_stt = OpenAIFileTranscription()
    app.state.tts = OpenAITextToSpeech()
    app.state.realtime_voice_adapter_cls = DoubaoRealtimeVoiceAdapter
    app.state.db_path = db_path
    app.state.config_dir = _config_dir()

    yield

    conn.close()


app = FastAPI(
    title='Have Some "Ai"',
    version="0.1.0",
    lifespan=lifespan,
)

_THANK_YOU_SPEECH_TEXT = "Thank you. 谢谢。"
_REALTIME_PENDING_REPLY_ATTR = "_have_some_ai_pending_reply_text"
_REALTIME_PROVIDER_ASR_ENDED_ATTR = "_have_some_ai_provider_asr_ended"
_REALTIME_LOCAL_TTS_ACTIVE_ATTR = "_have_some_ai_local_tts_active"
_REALTIME_AUTONOMOUS_INTERRUPT_SENT_ATTR = "_have_some_ai_autonomous_interrupt_sent"


def _service(request: Request) -> MealService:
    return request.app.state.service


def _conversation(request: Request) -> ConversationOrchestrator:
    return request.app.state.conversation


def _file_stt(request: Request) -> OpenAIFileTranscription:
    return request.app.state.file_stt


def _tts(request: Request) -> OpenAITextToSpeech:
    return request.app.state.tts


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sqlite3.Error):
        return HTTPException(status_code=500, detail=f"Database error: {exc}")
    return HTTPException(status_code=500, detail=str(exc))


def _model_data(model: BaseModel) -> dict[str, Any]:
    """Support both Pydantic v1 and v2 in local exhibition environments."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.get("/", include_in_schema=False)
async def dashboard():
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/health")
async def health(request: Request):
    try:
        request.app.state.conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "db": db_status,
        "db_path": str(request.app.state.db_path),
        "config_dir": str(request.app.state.config_dir),
    }


@app.get("/api/v1/config")
async def config(request: Request):
    return request.app.state.configs


@app.get("/api/v1/voice-config")
async def voice_config(request: Request):
    return request.app.state.voice_config.public_data()


@app.post("/api/v1/participants")
async def create_participant(body: ParticipantCreateRequest, request: Request):
    try:
        participant = _service(request).create_participant(
            notes=body.notes,
            safety_flags=body.safety_flags,
        )
        return participant.__dict__
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/participants")
async def list_participants(request: Request, limit: int = 50):
    try:
        return _service(request).list_participants(max(1, min(limit, 200)))
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/participants/{participant_id}")
async def participant_detail(participant_id: str, request: Request):
    try:
        return _service(request).participant_detail(participant_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/questionnaire/start")
async def start_questionnaire(participant_id: str, request: Request):
    try:
        return {"questions": _service(request).start_questionnaire(participant_id)}
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/conversation-turn")
async def conversation_turn(
    participant_id: str,
    body: ConversationTurnRequest,
    request: Request,
):
    try:
        response = _conversation(request).conversation_turn(participant_id, body.transcript)
        return _attach_reply_audio(request, response, body.include_audio)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/conversation-audio")
async def conversation_audio(
    participant_id: str,
    body: ConversationAudioRequest,
    request: Request,
):
    try:
        audio = _decode_audio_base64(body.audio_base64)
        transcription = _file_stt(request).transcribe(
            audio,
            mime_type=body.mime_type,
            duration_ms=body.duration_ms,
        )
        metadata = transcription.metadata | {
            "source": "conversation_audio",
        }
        if body.attempt_id:
            metadata["attempt_id"] = body.attempt_id

        response = _conversation(request).conversation_turn(
            participant_id,
            transcription.text,
            detected_language=body.detected_language or transcription.detected_language,
            stt_confidence=transcription.confidence,
            stt_metadata=metadata,
            attempt_id=body.attempt_id,
        )

        return {
            **_attach_reply_audio(request, response, body.include_audio),
            "transcript": transcription.text,
            "detected_language": body.detected_language or transcription.detected_language,
            "stt_confidence": transcription.confidence,
            "stt_metadata": metadata,
        }
    except Exception as exc:
        raise _api_error(exc)


@app.websocket("/api/v1/participants/{participant_id}/conversation-realtime")
async def conversation_realtime(participant_id: str, websocket: WebSocket):
    await websocket.accept()
    adapter: RealtimeVoiceAdapter | None = None
    session_started = False
    try:
        voice_config = websocket.app.state.voice_config
        if not voice_config.conversation_realtime_available:
            await websocket.send_json({
                "type": "error",
                "detail": "doubao realtime unavailable",
            })
            return

        adapter_cls = websocket.app.state.realtime_voice_adapter_cls
        adapter = adapter_cls()
        _disable_realtime_tts_audio(adapter)
        conversation = websocket.app.state.conversation
        await websocket.send_json({
            "type": "state",
            "state": "connected",
            "provider": voice_config.provider,
            "input_audio_format": voice_config.input_audio_format,
            "input_sample_rate": voice_config.input_sample_rate,
            "output_audio_format": voice_config.output_audio_format,
            "output_sample_rate": voice_config.output_sample_rate,
        })

        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type") or "")
            if message_type == "session.start":
                prepare_turn = bool(message.get("prepare_turn", True))
                stream_audio = bool(message.get("stream_audio", True))
                state = (
                    conversation.prepare_realtime_turn(participant_id)
                    if prepare_turn
                    else None
                )
                await adapter.start_session(
                    session_id=_optional_text(message.get("session_id")),
                    system_prompt=build_realtime_system_prompt(state),
                )
                _disable_realtime_tts_audio(adapter)
                session_started = True
                await websocket.send_json({
                    "type": "state",
                    "state": "session.started",
                    "conversation": state,
                })
                if state is not None and state.get("reply_text"):
                    await _say_realtime_text(
                        adapter,
                        str(state["reply_text"]),
                        greeting=True,
                    )
                    if not stream_audio:
                        await _drain_realtime_voice_events(
                            websocket,
                            conversation,
                            adapter,
                            participant_id,
                            timeout_seconds=4.0,
                        )
            elif message_type == "audio.append":
                if not session_started:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "realtime session has not started",
                    })
                    continue
                audio = _decode_audio_base64(str(message.get("audio_base64") or ""))
                await adapter.append_audio(audio)
                await _drain_realtime_voice_events(
                    websocket,
                    conversation,
                    adapter,
                    participant_id,
                    timeout_seconds=0.005,
                    idle_seconds=0.002,
                )
            elif message_type == "audio.end":
                if not session_started:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "realtime session has not started",
                    })
                    continue
                await adapter.end_asr()
                await websocket.send_json({
                    "type": "state",
                    "state": "asr.ended",
                })
                await _drain_realtime_voice_events(
                    websocket,
                    conversation,
                    adapter,
                    participant_id,
                    timeout_seconds=12.0,
                )
            elif message_type == "tts.speak":
                if not session_started:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "realtime session has not started",
                    })
                    continue
                text = str(message.get("text") or "").strip()
                if not text:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "tts text is empty",
                    })
                    continue
                await _say_realtime_text(adapter, text, greeting=True)
                await _drain_realtime_voice_events(
                    websocket,
                    conversation,
                    adapter,
                    participant_id,
                    timeout_seconds=6.0,
                )
            elif message_type == "client.interrupt":
                if not session_started:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "realtime session has not started",
                    })
                    continue
                await adapter.interrupt()
                await websocket.send_json({
                    "type": "state",
                    "state": "client.interrupted",
                })
            elif message_type == "session.stop":
                await websocket.send_json({
                    "type": "state",
                    "state": "session.stopping",
                })
                break
            else:
                await websocket.send_json({
                    "type": "error",
                    "detail": "Unsupported realtime message type",
                })
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await _safe_websocket_send_json(websocket, {
            "type": "error",
            "detail": _safe_websocket_error(exc),
        })
    finally:
        if adapter is not None:
            try:
                await adapter.stop_session()
            except Exception:
                pass
            try:
                await adapter.close()
            except Exception:
                pass


@app.post("/api/v1/participants/{participant_id}/questions/{question_id}/speech")
async def question_speech(participant_id: str, question_id: str, request: Request):
    try:
        speech_text = _service(request).question_speech_text(participant_id, question_id)
        audio = _tts(request).create_speech(speech_text)
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/speech/thanks")
async def thank_you_speech(request: Request):
    try:
        audio = _tts(request).create_speech(_THANK_YOU_SPEECH_TEXT)
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/answers")
async def submit_answers(participant_id: str, body: AnswersRequest, request: Request):
    try:
        service = _service(request)
        service.submit_answers(
            participant_id,
            [_model_data(item) for item in body.answers],
        )
        response: dict[str, Any] = {"status": "answers_recorded"}
        if body.assign_immediately:
            assignment = service.assign_food(participant_id)
            response["assignment"] = assignment.__dict__
        return response
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/observations")
async def add_observations(participant_id: str, body: ObservationsRequest, request: Request):
    try:
        _service(request).add_observations(
            participant_id,
            [_model_data(item) for item in body.events],
        )
        return {"status": "observations_recorded"}
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/voice-answers")
async def submit_voice_answer(participant_id: str, body: VoiceAnswerRequest, request: Request):
    try:
        service = _service(request)
        response = service.submit_voice_answer(
            participant_id,
            question_id=body.question_id,
            transcript=body.transcript,
            detected_language=body.detected_language,
            stt_confidence=body.stt_confidence,
            stt_metadata=body.stt_metadata,
            attempt_id=body.attempt_id,
        )
        return _attach_assignment_if_ready(service, participant_id, response, body.assign_if_complete)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/questions/{question_id}/voice-audio")
async def submit_voice_audio(
    participant_id: str,
    question_id: str,
    body: VoiceAudioRequest,
    request: Request,
):
    try:
        service = _service(request)
        existing = service.voice_attempt_response(participant_id, question_id, body.attempt_id)
        if existing is not None:
            return _attach_assignment_if_ready(
                service,
                participant_id,
                existing,
                body.assign_if_complete,
            )

        audio = _decode_audio_base64(body.audio_base64)
        transcription = _file_stt(request).transcribe(
            audio,
            mime_type=body.mime_type,
            duration_ms=body.duration_ms,
        )
        metadata = transcription.metadata | {
            "attempt_id": body.attempt_id,
            "source": "voice_audio_upload",
        }
        response = service.submit_voice_answer(
            participant_id,
            question_id=question_id,
            transcript=transcription.text,
            detected_language=body.detected_language or transcription.detected_language,
            stt_confidence=transcription.confidence,
            stt_metadata=metadata,
            attempt_id=body.attempt_id,
        )
        return _attach_assignment_if_ready(
            service,
            participant_id,
            response,
            body.assign_if_complete,
        )
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/assign")
async def assign_food(participant_id: str, request: Request):
    try:
        assignment = _service(request).assign_food(participant_id)
        return assignment.__dict__
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/staff-queue")
async def staff_queue(request: Request, limit: int = 100):
    try:
        return _service(request).list_staff_queue(max(1, min(limit, 300)))
    except Exception as exc:
        raise _api_error(exc)


@app.patch("/api/v1/staff-queue/{queue_item_id}")
async def update_queue_item(queue_item_id: int, body: QueueUpdateRequest, request: Request):
    try:
        _service(request).update_queue_item(queue_item_id, body.status, body.staff_notes)
        return {"status": "updated"}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/export")
async def export_all(request: Request):
    try:
        return _service(request).export_all()
    except Exception as exc:
        raise _api_error(exc)


def _decode_audio_base64(audio_base64: str) -> bytes:
    try:
        return base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid audio_base64 payload") from exc


async def _drain_realtime_voice_events(
    websocket: WebSocket,
    conversation: ConversationOrchestrator,
    adapter: RealtimeVoiceAdapter,
    participant_id: str,
    *,
    timeout_seconds: float,
    idle_seconds: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    event_stream = adapter.events()
    saw_audio = False
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        try:
            event = await asyncio.wait_for(
                event_stream.__anext__(),
                timeout=min(idle_seconds if saw_audio else remaining, remaining),
            )
        except (asyncio.TimeoutError, StopAsyncIteration):
            return
        await _handle_realtime_voice_event(
            websocket,
            conversation,
            adapter,
            participant_id,
            event,
        )
        if event.type == "audio.delta" and _realtime_tts_audio_enabled(adapter):
            saw_audio = True


async def _handle_realtime_voice_event(
    websocket: WebSocket,
    conversation: ConversationOrchestrator,
    adapter: RealtimeVoiceAdapter,
    participant_id: str,
    event: RealtimeVoiceEvent,
) -> None:
    if event.type == "audio.delta":
        if not _realtime_tts_audio_enabled(adapter):
            return
        await websocket.send_json({
            "type": "audio.delta",
            "audio_base64": str(event.data.get("audio_base64") or ""),
            "audio_format": event.data.get("audio_format", "pcm_s16le"),
            "sample_rate": int(event.data.get("sample_rate") or 24000),
        })
        return

    if event.type == "transcript.delta":
        await websocket.send_json({
            "type": "transcript.delta",
            "transcript": str(event.data.get("transcript") or ""),
        })
        return

    if event.type == "transcript.final":
        transcript = str(event.data.get("transcript") or "").strip()
        await websocket.send_json({
            "type": "transcript.final",
            "transcript": transcript,
        })
        _disable_realtime_tts_audio(adapter)
        await _interrupt_realtime_autonomous_reply(adapter)
        if not transcript:
            await websocket.send_json({
                "type": "retry",
                "reason": "empty_transcript",
            })
            return
        metadata = _realtime_stt_metadata(event)
        response = conversation.conversation_turn(
            participant_id,
            transcript,
            detected_language=_optional_text(event.data.get("detected_language")),
            stt_confidence=_optional_float(event.data.get("confidence")),
            stt_metadata=metadata,
            attempt_id=_realtime_attempt_id(adapter, event),
        )
        await websocket.send_json({
            "type": "conversation",
            "conversation": response,
        })
        if response.get("next_action") == "repeat_current_question":
            await websocket.send_json({
                "type": "retry",
                "reason": "unclear",
                "conversation": response,
            })
        if response.get("assignment") is not None:
            await websocket.send_json({
                "type": "assignment",
                "assignment": response["assignment"],
            })
        if response.get("reply_text"):
            await _queue_or_speak_realtime_reply(adapter, str(response["reply_text"]))
        return

    if event.type == "speech.started":
        _disable_realtime_tts_audio(adapter)
        _reset_realtime_autonomous_interrupt(adapter)
        setattr(adapter, _REALTIME_PROVIDER_ASR_ENDED_ATTR, False)
        await websocket.send_json({
            "type": "state",
            "state": "provider.asr.started",
            "event": event.data.get("event"),
        })
        return

    if event.type == "speech.ended":
        setattr(adapter, _REALTIME_PROVIDER_ASR_ENDED_ATTR, True)
        await websocket.send_json({
            "type": "state",
            "state": "provider.asr.ended",
            "event": event.data.get("event"),
        })
        await _flush_pending_realtime_reply(adapter)
        return

    if event.type == "error":
        await websocket.send_json({
            "type": "error",
            "detail": _safe_websocket_error_text(str(event.data.get("detail") or "realtime error")),
        })
        return

    if event.type == "chat.delta":
        await _interrupt_realtime_autonomous_reply(adapter)
        return

    await websocket.send_json({
        "type": "state",
        "state": "provider.event",
        "event": event.data.get("event"),
    })
    if event.data.get("event") == DOUBAO_TTS_ENDED:
        _disable_realtime_tts_audio(adapter)


async def _queue_or_speak_realtime_reply(
    adapter: RealtimeVoiceAdapter,
    text: str,
) -> None:
    reply_text = text.strip()
    if not reply_text:
        return
    if bool(getattr(adapter, _REALTIME_PROVIDER_ASR_ENDED_ATTR, False)):
        setattr(adapter, _REALTIME_PENDING_REPLY_ATTR, None)
        await _speak_authorized_realtime_text(adapter, reply_text, greeting=False)
        return
    setattr(adapter, _REALTIME_PENDING_REPLY_ATTR, reply_text)


async def _flush_pending_realtime_reply(adapter: RealtimeVoiceAdapter) -> None:
    pending = _optional_text(getattr(adapter, _REALTIME_PENDING_REPLY_ATTR, None))
    if pending is None:
        return
    setattr(adapter, _REALTIME_PENDING_REPLY_ATTR, None)
    await _interrupt_realtime_autonomous_reply(adapter)
    await _speak_authorized_realtime_text(adapter, pending, greeting=False)


async def _say_realtime_text(
    adapter: RealtimeVoiceAdapter,
    text: str,
    *,
    greeting: bool,
) -> None:
    await _speak_authorized_realtime_text(adapter, text, greeting=greeting)


async def _speak_authorized_realtime_text(
    adapter: RealtimeVoiceAdapter,
    text: str,
    *,
    greeting: bool,
) -> None:
    _enable_realtime_tts_audio(adapter)
    _reset_realtime_autonomous_interrupt(adapter)
    if greeting and hasattr(adapter, "say_hello"):
        try:
            await adapter.say_hello(text)
        except Exception:
            _disable_realtime_tts_audio(adapter)
            raise
        return
    try:
        await adapter.speak_text(text)
    except Exception:
        _disable_realtime_tts_audio(adapter)
        raise


def _enable_realtime_tts_audio(adapter: RealtimeVoiceAdapter) -> None:
    setattr(adapter, _REALTIME_LOCAL_TTS_ACTIVE_ATTR, True)


def _disable_realtime_tts_audio(adapter: RealtimeVoiceAdapter) -> None:
    setattr(adapter, _REALTIME_LOCAL_TTS_ACTIVE_ATTR, False)


def _realtime_tts_audio_enabled(adapter: RealtimeVoiceAdapter) -> bool:
    return bool(getattr(adapter, _REALTIME_LOCAL_TTS_ACTIVE_ATTR, True))


async def _interrupt_realtime_autonomous_reply(adapter: RealtimeVoiceAdapter) -> None:
    if bool(getattr(adapter, _REALTIME_AUTONOMOUS_INTERRUPT_SENT_ATTR, False)):
        return
    setattr(adapter, _REALTIME_AUTONOMOUS_INTERRUPT_SENT_ATTR, True)
    try:
        await adapter.interrupt()
    except Exception:
        return


def _reset_realtime_autonomous_interrupt(adapter: RealtimeVoiceAdapter) -> None:
    setattr(adapter, _REALTIME_AUTONOMOUS_INTERRUPT_SENT_ATTR, False)


def _realtime_stt_metadata(event: RealtimeVoiceEvent) -> dict[str, Any]:
    metadata = {
        "source": "conversation_realtime",
        "provider": "doubao",
    }
    if event.data.get("event") is not None:
        metadata["event"] = event.data["event"]
    provider_metadata = event.data.get("metadata")
    if isinstance(provider_metadata, dict):
        metadata["provider_metadata"] = _scrub_realtime_metadata(provider_metadata)
    return metadata


def _scrub_realtime_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in {"audio", "audio_base64", "payload_audio"}:
                continue
            scrubbed[key_text] = _scrub_realtime_metadata(item)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_realtime_metadata(item) for item in value]
    if isinstance(value, str):
        return _safe_websocket_error_text(value)
    return value


def _realtime_attempt_id(adapter: RealtimeVoiceAdapter, event: RealtimeVoiceEvent) -> str:
    session_id = _optional_text(getattr(adapter, "session_id", None)) or "session"
    event_id = _optional_text(event.data.get("event")) or "final"
    return f"doubao:{session_id}:{event_id}"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _safe_websocket_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        return


def _safe_websocket_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return _safe_websocket_error_text(str(exc))
    return _safe_websocket_error_text(exc.__class__.__name__)


def _safe_websocket_error_text(text: str) -> str:
    sanitized = text
    for secret in (
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_ID"),
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_KEY"),
        os.getenv("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN"),
    ):
        if secret:
            sanitized = sanitized.replace(secret, "[redacted]")
    if len(sanitized) > 500:
        return f"{sanitized[:500]}..."
    return sanitized


def _attach_assignment_if_ready(
    service: MealService,
    participant_id: str,
    response: dict[str, Any],
    assign_if_complete: bool,
) -> dict[str, Any]:
    if assign_if_complete and response["status"] == "accepted":
        try:
            assignment = service.assign_food(participant_id)
        except ValueError:
            assignment = None
        if assignment is not None:
            response["assignment"] = assignment.__dict__
    elif response["status"] == "already_assigned":
        assignment = service.get_assignment_if_exists(participant_id)
        if assignment is not None:
            response["assignment"] = assignment.__dict__
    return response


def _attach_reply_audio(
    request: Request,
    response: dict[str, Any],
    include_audio: bool,
) -> dict[str, Any]:
    payload = {
        **response,
        "reply_audio_base64": None,
        "reply_audio_mime_type": None,
        "reply_audio_provider": None,
    }
    if _uses_doubao_realtime_voice(request):
        if include_audio and response["reply_text"]:
            payload["reply_audio_provider"] = "doubao_realtime"
        return payload
    if include_audio and response["reply_text"]:
        reply_audio = _tts(request).create_speech(response["reply_text"])
        payload["reply_audio_base64"] = base64.b64encode(reply_audio).decode("ascii")
        payload["reply_audio_mime_type"] = "audio/mpeg"
        payload["reply_audio_provider"] = "openai_compatible"
    return payload


def _uses_doubao_realtime_voice(request: Request) -> bool:
    voice_config = request.app.state.voice_config
    return (
        voice_config.provider == "doubao"
        and voice_config.stt_mode == "realtime_dialogue"
        and voice_config.conversation_realtime_available
    )
