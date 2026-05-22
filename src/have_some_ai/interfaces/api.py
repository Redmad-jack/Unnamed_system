from __future__ import annotations

import asyncio
import os
import sqlite3
import base64
import binascii
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, StrictBool

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - Pydantic v1 fallback.
    ConfigDict = None

from conscious_entity.db.connection import get_connection
from conscious_entity.runtime_env import load_project_env, project_root
from have_some_ai import __version__ as HAVE_SOME_AI_VERSION
from have_some_ai.chat import ShopkeeperReplyService
from have_some_ai.config import default_config_dir, load_have_some_ai_config
from have_some_ai.conversation import ConversationOrchestrator
from have_some_ai.db import run_migrations
from have_some_ai.doubao.asr_client import DoubaoASRClient
from have_some_ai.doubao.asr_protocol import ASRTranscriptEvent
from have_some_ai.doubao.tts_bidirectional_client import DoubaoTTSBidirectionalClient
from have_some_ai.doubao.tts_protocol import (
    TTS_RESPONSE,
    TTS_SENTENCE_END,
    TTS_SENTENCE_START,
    TTS_SESSION_CANCELED,
    TTS_SESSION_FINISHED,
    TTSEvent,
)
from have_some_ai.models import QueueStatus
from have_some_ai.openai_file_stt import OpenAIFileTranscription
from have_some_ai.openai_tts import OpenAITextToSpeech
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService
from have_some_ai.voice import ClaudeRubricInterpreter
from have_some_ai.voice_provider import resolve_voice_provider_config


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


class DisplayStateUpdateRequest(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    display_text: str | None = None
    food_name: str | None = None
    food_subtitle: str | None = None
    robot_active: StrictBool | None = None
    avatar_greeting: StrictBool | None = None
    avatar_system_speaking: StrictBool | None = None
    avatar_audience_speaking: StrictBool | None = None

    if ConfigDict is None:  # pragma: no cover - Pydantic v1 fallback.
        class Config:
            extra = "forbid"


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
    threshold = float(os.getenv("HAVE_SOME_AI_RUBRIC_CONFIDENCE_THRESHOLD", "0.55"))

    app.state.conn = conn
    app.state.configs = configs
    app.state.service = MealService(
        repository,
        question_bank,
        scoring_engine,
        rubric_interpreter=ClaudeRubricInterpreter(),
        rubric_confidence_threshold=threshold,
    )
    app.state.conversation = ConversationOrchestrator(
        app.state.service,
        reply_service=ShopkeeperReplyService(enable_llm=True),
    )
    app.state.voice_config = resolve_voice_provider_config()
    app.state.file_stt = OpenAIFileTranscription()
    app.state.tts = OpenAITextToSpeech()
    app.state.doubao_asr_client_cls = DoubaoASRClient
    app.state.doubao_tts_client_cls = DoubaoTTSBidirectionalClient
    app.state.db_path = db_path
    app.state.config_dir = _config_dir()
    app.state.display_state = _initial_display_state()

    yield

    conn.close()


app = FastAPI(
    title='Have Some "Ai"',
    version=HAVE_SOME_AI_VERSION,
    lifespan=lifespan,
)

_THANK_YOU_SPEECH_TEXT = "Thank you. 谢谢。"
_ASR_TARGET_CHUNK_BYTES = 16000 * 2 // 5
_DISPLAY_MODES = {"idle", "question", "robot_speaking", "result", "error"}
_DISPLAY_TEXT_LIMIT = 800
_DISPLAY_FOOD_NAME_LIMIT = 80
_DISPLAY_FOOD_SUBTITLE_LIMIT = 160


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


def _model_fields_set(model: BaseModel) -> set[str]:
    fields = getattr(model, "model_fields_set", None)
    if fields is not None:
        return set(fields)
    return set(getattr(model, "__fields_set__", set()))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial_display_state() -> dict[str, Any]:
    return {
        "mode": "idle",
        "display_text": "",
        "food_name": None,
        "food_subtitle": None,
        "robot_active": False,
        "avatar_greeting": False,
        "avatar_system_speaking": False,
        "avatar_audience_speaking": False,
        "updated_at": _utc_iso(),
    }


def _truncate_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _display_state(request: Request) -> dict[str, Any]:
    state = getattr(request.app.state, "display_state", None)
    if state is None:
        state = _initial_display_state()
        request.app.state.display_state = state
    return state


@app.get("/", include_in_schema=False)
async def dashboard():
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/display", include_in_schema=False)
async def display_page():
    html_path = _static_dir() / "display.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Display page not found")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/particle-display", include_in_schema=False)
async def particle_display_page():
    html_path = _static_dir() / "particle-display.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Particle display page not found")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/display-assets/{filename}", include_in_schema=False)
async def display_asset(filename: str):
    allowed_assets = {"avatar-film-texture.png", "avatar-film-overlay.png", "amhand.png"}
    if filename not in allowed_assets:
        raise HTTPException(status_code=404, detail="Display asset not found")
    asset_path = _static_dir() / "assets" / filename
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Display asset not found")
    return FileResponse(str(asset_path), media_type="image/png")


@app.get("/particle-display-assets/{asset_path:path}", include_in_schema=False)
async def particle_display_asset(asset_path: str):
    allowed_assets = {
        "particle-display.css",
        "particle-display.js",
        "vendor/three.module.js",
    }
    if asset_path not in allowed_assets:
        raise HTTPException(status_code=404, detail="Particle display asset not found")
    file_path = _static_dir() / asset_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Particle display asset not found")
    return FileResponse(str(file_path))


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


@app.get("/api/v1/display-state")
async def get_display_state(request: Request):
    return dict(_display_state(request))


@app.post("/api/v1/display-state")
async def update_display_state(body: DisplayStateUpdateRequest, request: Request):
    fields = _model_fields_set(body)
    if "mode" in fields:
        if body.mode not in _DISPLAY_MODES:
            raise HTTPException(status_code=400, detail="Invalid display mode")
    if "display_text" in fields and body.display_text is None:
        raise HTTPException(status_code=400, detail="display_text must be a string")
    if "robot_active" in fields and body.robot_active is None:
        raise HTTPException(status_code=400, detail="robot_active must be a boolean")
    for field in ("avatar_greeting", "avatar_system_speaking", "avatar_audience_speaking"):
        if field in fields and getattr(body, field) is None:
            raise HTTPException(status_code=400, detail=f"{field} must be a boolean")

    state = _display_state(request)
    if "mode" in fields:
        state["mode"] = body.mode
    if "display_text" in fields:
        state["display_text"] = _truncate_text(body.display_text, _DISPLAY_TEXT_LIMIT) or ""
    if "food_name" in fields:
        state["food_name"] = _truncate_text(body.food_name, _DISPLAY_FOOD_NAME_LIMIT)
    if "food_subtitle" in fields:
        state["food_subtitle"] = _truncate_text(body.food_subtitle, _DISPLAY_FOOD_SUBTITLE_LIMIT)
    if "robot_active" in fields:
        state["robot_active"] = bool(body.robot_active)
    if "avatar_greeting" in fields:
        state["avatar_greeting"] = bool(body.avatar_greeting)
    if "avatar_system_speaking" in fields:
        state["avatar_system_speaking"] = bool(body.avatar_system_speaking)
    if "avatar_audience_speaking" in fields:
        state["avatar_audience_speaking"] = bool(body.avatar_audience_speaking)
    state["updated_at"] = _utc_iso()
    return dict(state)


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


@app.websocket("/api/v1/participants/{participant_id}/conversation-stream")
async def conversation_stream(participant_id: str, websocket: WebSocket):
    await websocket.accept()
    voice_config = websocket.app.state.voice_config
    if not voice_config.conversation_stream_available:
        await websocket.send_json({
            "type": "error",
            "message": "doubao stream unavailable",
            "provider": "app",
        })
        return

    conversation = websocket.app.state.conversation
    asr_client = websocket.app.state.doubao_asr_client_cls(uid=participant_id)
    tts_client = websocket.app.state.doubao_tts_client_cls(uid=participant_id)
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=24)
    final_queue: asyncio.Queue[ASRTranscriptEvent | None] = asyncio.Queue(maxsize=8)
    mic_muted = asyncio.Event()
    session_done = asyncio.Event()
    tts_tasks: set[asyncio.Task] = set()

    await websocket.send_json({
        "type": "state",
        "state": "connected",
        "provider": voice_config.provider,
        "input_audio_format": voice_config.input_audio_format,
        "input_sample_rate": voice_config.input_sample_rate,
    })
    await websocket.send_json({
        "type": "audio.output_config",
        "format": voice_config.output_audio_format or "pcm_s16le",
        "sample_rate": voice_config.output_sample_rate or 24000,
        "channels": 1,
    })

    async def client_receiver() -> None:
        while not session_done.is_set():
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                session_done.set()
                await _queue_audio_final(audio_queue)
                return
            if "bytes" in message and message["bytes"] is not None:
                if not mic_muted.is_set():
                    await _queue_audio_chunk(audio_queue, message["bytes"])
                continue
            if "text" not in message or message["text"] is None:
                continue
            try:
                payload = _json_loads(message["text"])
            except ValueError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Unsupported WebSocket text payload",
                    "provider": "app",
                })
                continue
            message_type = str(payload.get("type") or "")
            if message_type == "session.start":
                state = await _handle_stream_session_start(
                    websocket,
                    conversation,
                    participant_id,
                    payload,
                )
                if state is not None and state.get("reply_text"):
                    mic_muted.set()
                    task = asyncio.create_task(
                        _stream_tts_text(websocket, tts_client, str(state["reply_text"]), mic_muted)
                    )
                    tts_tasks.add(task)
                    task.add_done_callback(tts_tasks.discard)
            elif message_type == "audio.append":
                if not mic_muted.is_set():
                    await _queue_audio_chunk(
                        audio_queue,
                        _decode_audio_base64(str(payload.get("audio_base64") or "")),
                    )
            elif message_type in {"audio.end", "session.cancel"}:
                session_done.set()
                await _queue_audio_final(audio_queue)
                return
            elif message_type == "barge_in":
                await websocket.send_json({"type": "tts.canceling"})
                await tts_client.cancel_current_session()
            elif message_type == "tts.speak":
                text = str(payload.get("text") or "").strip()
                if text:
                    mic_muted.set()
                    task = asyncio.create_task(_stream_tts_text(websocket, tts_client, text, mic_muted))
                    tts_tasks.add(task)
                    task.add_done_callback(tts_tasks.discard)
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Unsupported stream message type",
                    "provider": "app",
                })

    async def asr_sender() -> None:
        buffer = b""
        try:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    await asr_client.finish(buffer)
                    return
                buffer += chunk
                while len(buffer) >= _ASR_TARGET_CHUNK_BYTES:
                    await asr_client.append_audio(buffer[:_ASR_TARGET_CHUNK_BYTES])
                    buffer = buffer[_ASR_TARGET_CHUNK_BYTES:]
        finally:
            session_done.set()

    async def asr_receiver() -> None:
        async for event in asr_client.events():
            if event.type == "partial":
                await websocket.send_json({"type": "asr.partial", "text": event.text})
            elif event.type == "final":
                await websocket.send_json({
                    "type": "asr.final",
                    "text": event.text,
                    "start_time": event.start_time,
                    "end_time": event.end_time,
                })
                await final_queue.put(event)
            if session_done.is_set():
                return

    async def orchestrator_worker() -> None:
        while not session_done.is_set():
            event = await final_queue.get()
            if event is None:
                return
            response = conversation.conversation_turn(
                participant_id,
                event.text,
                stt_metadata={
                    "source": "conversation_stream",
                    "provider": "doubao_asr",
                    "asr_request_id": getattr(asr_client, "request_id", None),
                    "asr_connect_id": getattr(asr_client, "connect_id", None),
                    "asr_log_id": getattr(asr_client, "provider_log_id", None),
                    "utterance": event.metadata.get("utterance"),
                },
                attempt_id=_stream_attempt_id(asr_client, event),
            )
            await _send_stream_conversation_events(websocket, response)
            if response.get("reply_text"):
                await _stream_tts_text(websocket, tts_client, str(response["reply_text"]), mic_muted)
            if response.get("next_action") == "end_session" or response.get("participant_deleted"):
                session_done.set()
                await _queue_audio_final(audio_queue)
                await final_queue.put(None)
                return

    tasks: list[asyncio.Task] = []
    try:
        tasks = [
            asyncio.create_task(client_receiver()),
            asyncio.create_task(asr_sender()),
            asyncio.create_task(asr_receiver()),
            asyncio.create_task(orchestrator_worker()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
        await session_done.wait()
    except WebSocketDisconnect:
        session_done.set()
    except Exception as exc:
        await _safe_websocket_send_json(websocket, {
            "type": "error",
            "message": _safe_websocket_error(exc),
            "provider": "app",
        })
    finally:
        session_done.set()
        await _queue_audio_final(audio_queue)
        await final_queue.put(None)
        for task in tasks:
            task.cancel()
        for task in tts_tasks:
            task.cancel()
        try:
            await asr_client.finish()
        except Exception:
            pass
        try:
            await asr_client.close()
        except Exception:
            pass
        try:
            await tts_client.close()
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


async def _handle_stream_session_start(
    websocket: WebSocket,
    conversation: ConversationOrchestrator,
    participant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    prepare_turn = bool(payload.get("prepare_turn", True))
    state = conversation.prepare_stream_turn(participant_id) if prepare_turn else None
    await websocket.send_json({
        "type": "state",
        "state": "session.started",
        "conversation": state,
    })
    if state is not None:
        await _send_stream_conversation_events(websocket, state)
    return state


async def _stream_tts_text(
    websocket: WebSocket,
    tts_client: DoubaoTTSBidirectionalClient,
    text: str,
    mic_muted: asyncio.Event,
) -> None:
    clean_text = text.strip()
    if not clean_text:
        return
    mic_muted.set()
    await websocket.send_json({"type": "mic.muted_for_tts", "text": clean_text})
    try:
        async for event in tts_client.synthesize(clean_text):
            await _forward_tts_event(websocket, event)
            if event.audio:
                await websocket.send_bytes(event.audio)
            if event.event in {TTS_SESSION_FINISHED, TTS_SESSION_CANCELED}:
                break
    except Exception as exc:
        await _safe_websocket_send_json(websocket, {
            "type": "tts.error",
            "message": _safe_websocket_error(exc),
            "provider": "doubao_tts",
        })
    finally:
        mic_muted.clear()
        await _safe_websocket_send_json(websocket, {"type": "mic.resumed_after_tts"})


async def _forward_tts_event(websocket: WebSocket, event: TTSEvent) -> None:
    if event.event == TTS_RESPONSE:
        return
    payload = {
        "type": "tts.event",
        "event": event.event,
        "session_id": event.session_id,
        "connection_id": event.connection_id,
    }
    if event.event in {TTS_SENTENCE_START, TTS_SENTENCE_END, TTS_SESSION_FINISHED, TTS_SESSION_CANCELED}:
        payload["payload"] = event.payload
    await websocket.send_json(payload)


async def _send_stream_conversation_events(
    websocket: WebSocket,
    response: dict[str, Any],
) -> None:
    await websocket.send_json({
        "type": "conversation",
        "conversation": response,
    })
    if response.get("current_question_text"):
        await websocket.send_json({
            "type": "question",
            "index": int(response.get("answered_count") or 0) + 1,
            "text": response["current_question_text"],
        })
    interpretation = response.get("interpretation")
    if isinstance(interpretation, dict):
        if interpretation.get("choice") or interpretation.get("source") == "judge":
            label = interpretation.get("choice") or "unclear"
            await websocket.send_json({
                "type": "judge",
                "label": label,
                "confidence": interpretation.get("confidence"),
            })
    if response.get("assignment") is not None:
        await websocket.send_json({
            "type": "score",
            "food_allocation": response["assignment"],
        })


async def _queue_audio_chunk(queue: asyncio.Queue[bytes | None], chunk: bytes) -> None:
    if not chunk:
        return
    try:
        queue.put_nowait(chunk)
    except asyncio.QueueFull:
        await queue.get()
        queue.put_nowait(chunk)


async def _queue_audio_final(queue: asyncio.Queue[bytes | None]) -> None:
    try:
        queue.put_nowait(None)
    except asyncio.QueueFull:
        await queue.get()
        queue.put_nowait(None)


def _stream_attempt_id(asr_client: DoubaoASRClient, event: ASRTranscriptEvent) -> str:
    key = event.key or (event.start_time, event.end_time, event.text)
    return f"doubao-asr:{getattr(asr_client, 'request_id', 'request')}:{key[0]}:{key[1]}:{hash(key[2])}"


def _json_loads(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON WebSocket payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON WebSocket payload")
    return payload


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
        os.getenv("DOUBAO_API_KEY"),
        os.getenv("DOUBAO_ASR_API_KEY"),
        os.getenv("DOUBAO_TTS_API_KEY"),
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
    if _uses_doubao_stream_voice(request):
        if include_audio and response["reply_text"]:
            payload["reply_audio_provider"] = "doubao_stream"
        return payload
    if include_audio and response["reply_text"]:
        reply_audio = _tts(request).create_speech(response["reply_text"])
        payload["reply_audio_base64"] = base64.b64encode(reply_audio).decode("ascii")
        payload["reply_audio_mime_type"] = "audio/mpeg"
        payload["reply_audio_provider"] = "openai_compatible"
    return payload


def _uses_doubao_stream_voice(request: Request) -> bool:
    voice_config = request.app.state.voice_config
    return (
        voice_config.provider == "doubao"
        and voice_config.stt_mode == "asr_tts_stream"
        and voice_config.conversation_stream_available
    )
