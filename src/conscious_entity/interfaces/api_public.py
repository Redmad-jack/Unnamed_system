from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import os
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from conscious_entity.audio import AudioRuntimeError
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.interfaces.api_audio import (
    _attach_second_delta_tts_stream,
    _attach_tts_stream,
    _audio_manager,
    _is_websocket_send_after_close,
    _receive_audio_frames,
    _remaining_final_tts_text,
    _send_transcript_events,
)
from conscious_entity.interfaces.api_models import PublicDialogRequest, PublicSessionStartRequest
from conscious_entity.interfaces.api_runtime import (
    _active_embedding_client,
    _active_llm_client,
    _ensure_visitor_profile,
    _save_initial_state,
    _wait_for_turn_future,
)
from conscious_entity.interfaces.api_security import origin_allowed
from conscious_entity.llm.claude_client import ClaudeConfigurationError


public_router = APIRouter(prefix="/api/v1/public")

DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 6
DEFAULT_TEXT_LIMIT = 900
DEFAULT_TURNS_PER_MINUTE = 12
DEFAULT_STT_CONNECTIONS_PER_MINUTE = 6


@dataclass
class PublicSessionHandle:
    session_id: str
    visitor_id: str
    nickname: str
    token: str
    expires_at: float
    conn: Any
    loop: InteractionLoop
    owns_conn: bool
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_seen_at: float = field(default_factory=time.time)
    tts_stream_ids: set[str] = field(default_factory=set)

    def close(self) -> None:
        self.loop.close(wait_for_background=True)
        if self.owns_conn and self.conn is not None:
            self.conn.close()


class PublicSessionManager:
    def __init__(self, app: Any) -> None:
        self._app = app
        self._sessions: dict[str, PublicSessionHandle] = {}
        self._lock = asyncio.Lock()
        self._session_ttl_seconds = _env_int("STRANGER_PUBLIC_SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)
        self._turn_limiter = InMemoryRateLimiter(_env_int("STRANGER_PUBLIC_TURN_LIMIT_PER_MINUTE", DEFAULT_TURNS_PER_MINUTE), 60)
        self._stt_limiter = InMemoryRateLimiter(_env_int("STRANGER_PUBLIC_STT_CONNECTIONS_PER_MINUTE", DEFAULT_STT_CONNECTIONS_PER_MINUTE), 60)

    async def start(self, request: Request, body: PublicSessionStartRequest) -> PublicSessionHandle:
        access_code = os.getenv("STRANGER_PUBLIC_ACCESS_CODE")
        if not access_code:
            raise HTTPException(status_code=503, detail="public access code is not configured")
        if not hmac.compare_digest(str(body.access_code or ""), access_code):
            raise HTTPException(status_code=403, detail="invalid access code")

        nickname = _normalize_nickname(body.nickname)
        visitor_id = _visitor_id_for_nickname(nickname)
        session_id = f"online-{uuid.uuid4().hex}"
        expires_at = time.time() + self._session_ttl_seconds
        token = _sign_session_token({
            "sid": session_id,
            "vid": visitor_id,
            "nick": nickname,
            "exp": int(expires_at),
        })

        async with self._lock:
            await self._cleanup_locked()
            await self._persist_session_locked(session_id, visitor_id, nickname)
            handle = self._build_handle(request, session_id, visitor_id, nickname, token, expires_at)
            self._sessions[session_id] = handle
            return handle

    async def from_request(self, request: Request) -> PublicSessionHandle:
        token = _token_from_request(request)
        if not token:
            raise HTTPException(status_code=401, detail="session token is required")
        payload = _verify_session_token(token)
        return await self._handle_for_payload(request, token, payload)

    async def from_websocket(self, websocket: WebSocket) -> PublicSessionHandle:
        token = websocket.query_params.get("session_token") or _token_from_headers(websocket.headers)
        if not token:
            await websocket.close(code=1008, reason="session token is required")
            raise WebSocketDisconnect(code=1008)
        try:
            payload = _verify_session_token(token)
        except HTTPException:
            await websocket.close(code=1008, reason="invalid session token")
            raise WebSocketDisconnect(code=1008)
        try:
            return await self._handle_for_payload(websocket, token, payload)
        except HTTPException:
            await websocket.close(code=1008, reason="session no longer exists")
            raise WebSocketDisconnect(code=1008)

    async def consume_turn(self, key: str) -> None:
        if not self._turn_limiter.consume(key):
            raise HTTPException(status_code=429, detail="turn rate limit exceeded")

    async def consume_stt(self, key: str) -> bool:
        return self._stt_limiter.consume(key)

    async def stream_allowed(self, request: Request, stream_id: str) -> PublicSessionHandle:
        handle = await self.from_request(request)
        if stream_id not in handle.tts_stream_ids:
            raise HTTPException(status_code=404, detail="tts stream not found for this session")
        return handle

    async def close_all(self) -> None:
        async with self._lock:
            handles = list(self._sessions.values())
            self._sessions.clear()
        for handle in handles:
            handle.close()

    async def _handle_for_payload(self, request_or_websocket: Request | WebSocket, token: str, payload: dict[str, Any]) -> PublicSessionHandle:
        session_id = str(payload.get("sid") or "")
        visitor_id = str(payload.get("vid") or "")
        nickname = str(payload.get("nick") or "")
        if not session_id or not visitor_id:
            raise HTTPException(status_code=401, detail="invalid session token")
        async with self._lock:
            await self._cleanup_locked()
            handle = self._sessions.get(session_id)
            if handle is None:
                row = self._app.state.conn.execute(
                    "SELECT id, visitor_id FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                if row is None or row["visitor_id"] != visitor_id:
                    raise HTTPException(status_code=401, detail="session no longer exists")
                handle = self._build_handle(request_or_websocket, session_id, visitor_id, nickname, token, float(payload["exp"]))
                self._sessions[session_id] = handle
            handle.last_seen_at = time.time()
            return handle

    async def _persist_session_locked(self, session_id: str, visitor_id: str, nickname: str) -> None:
        conn = self._app.state.conn
        _ensure_visitor_profile(
            conn,
            visitor_id,
            display_name=nickname,
            notes="Online public visitor nickname; not an account.",
            metadata={
                "public_online": {
                    "schema_version": 1,
                    "nickname_hash": hashlib.sha256(nickname.casefold().encode("utf-8")).hexdigest()[:16],
                    "identity_mode": "nickname",
                }
            },
        )
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, session_type, visitor_id, notes) VALUES (?, ?, ?, ?)",
            (session_id, "exhibition", visitor_id, "Online public /arts session."),
        )
        _save_initial_state(conn, session_id, self._app.state.configs)
        conn.commit()

    def _build_handle(
        self,
        request_or_websocket: Request | WebSocket,
        session_id: str,
        visitor_id: str,
        nickname: str,
        token: str,
        expires_at: float,
    ) -> PublicSessionHandle:
        db_path = str(self._app.state.db_path)
        owns_conn = db_path != ":memory:"
        conn = self._app.state.conn if not owns_conn else get_connection(db_path, check_same_thread=False)
        run_migrations(conn)
        loop = InteractionLoop(
            conn,
            session_id,
            self._app.state.configs,
            self._app.state.prompts_dir,
            llm_client=_active_llm_client(request_or_websocket),
            embedding_client=_active_embedding_client(request_or_websocket),
            visitor_id=visitor_id,
        )
        return PublicSessionHandle(
            session_id=session_id,
            visitor_id=visitor_id,
            nickname=nickname,
            token=token,
            expires_at=expires_at,
            conn=conn,
            loop=loop,
            owns_conn=owns_conn,
        )

    async def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, handle in self._sessions.items()
            if handle.expires_at <= now or now - handle.last_seen_at > self._session_ttl_seconds
        ]
        for session_id in expired:
            handle = self._sessions.pop(session_id)
            handle.close()


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def consume(self, key: str) -> bool:
        now = time.time()
        events = self._events[key]
        cutoff = now - self.window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True


@public_router.post("/session/start")
async def public_session_start(body: PublicSessionStartRequest, request: Request):
    _assert_request_origin_allowed(request)
    manager = _public_session_manager(request.app)
    try:
        handle = await manager.start(request, body)
    except ClaudeConfigurationError as exc:
        request.app.state.llm_error = str(exc)
        raise HTTPException(status_code=400, detail=str(exc))
    return _public_session_payload(handle, request)


@public_router.get("/state")
async def public_state(request: Request):
    _assert_request_origin_allowed(request)
    handle = await _public_session_manager(request.app).from_request(request)
    return {
        "session_id": handle.session_id,
        "visitor_id": handle.visitor_id,
        "state": handle.loop.current_state.to_dict(),
    }


@public_router.post("/dialog/progressive")
async def public_dialog_progressive(body: PublicDialogRequest, request: Request):
    _assert_request_origin_allowed(request)
    manager = _public_session_manager(request.app)
    handle = await manager.from_request(request)
    text = str(body.text or "").strip()
    text_limit = _env_int("STRANGER_PUBLIC_MAX_INPUT_CHARS", DEFAULT_TEXT_LIMIT)
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > text_limit:
        raise HTTPException(status_code=413, detail="text is too long")
    await manager.consume_turn(f"{_client_host(request)}:{handle.session_id}")
    input_mode = "voice_transcript" if body.input_mode == "voice_transcript" else "text"

    async def stream():
        async with handle.lock:
            async for payload in _run_public_progressive_turn(
                request,
                handle,
                text,
                source="public_dialog_progressive",
                input_mode=input_mode,
            ):
                yield _ndjson(payload)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@public_router.websocket("/audio/stt/stream")
async def public_audio_stt_stream(websocket: WebSocket):
    if not origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008, reason="origin not allowed")
        return
    manager = _public_session_manager(websocket.app)
    handle = await manager.from_websocket(websocket)
    if not await manager.consume_stt(f"{websocket.client.host if websocket.client else 'unknown'}:{handle.session_id}"):
        await websocket.close(code=1008, reason="stt rate limit exceeded")
        return

    await websocket.accept()
    audio_manager = _audio_manager(websocket)
    session_id = ""
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=audio_manager.config.queue_max_chunks
    )
    try:
        start = await websocket.receive_json()
        if start.get("type") != "start":
            await websocket.send_json({"type": "error", "code": "missing_start_message"})
            await websocket.close(code=1008)
            return

        session = audio_manager.create_stt_session(
            sample_rate=int(start.get("sample_rate") or audio_manager.config.sample_rate),
            chunk_ms=int(start.get("chunk_ms") or audio_manager.config.chunk_ms),
            audio_format=str(start.get("format") or "pcm_s16le"),
            channels=int(start.get("channels") or 1),
        )
        session_id = session.session_id
        await websocket.send_json({"type": "stt.start", "session_id": session_id})

        producer = asyncio.create_task(_receive_audio_frames(websocket, audio_queue, audio_manager))
        consumer = asyncio.create_task(_send_transcript_events(websocket, audio_queue, audio_manager, session_id))
        done, _pending = await asyncio.wait({producer, consumer}, return_when=asyncio.FIRST_COMPLETED)
        if producer in done:
            producer.result()
            try:
                await consumer
            except WebSocketDisconnect:
                return
            except RuntimeError as exc:
                if _is_websocket_send_after_close(exc):
                    return
                raise
        else:
            consumer.result()
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
    except WebSocketDisconnect:
        return
    except AudioRuntimeError as exc:
        audio_manager.set_error(exc.code, exc.message, logid=exc.logid)
        await websocket.send_json(
            {
                "type": "error",
                "session_id": session_id or None,
                "code": exc.code,
                "message": exc.message,
                "logid": exc.logid,
            }
        )
        await websocket.close(code=1011)
    finally:
        if session_id:
            audio_manager.finish_stt_session(session_id)


@public_router.get("/audio/tts/stream/{stream_id}")
async def public_audio_tts_stream(stream_id: str, request: Request):
    _assert_request_origin_allowed(request)
    await _public_session_manager(request.app).stream_allowed(request, stream_id)
    manager = _audio_manager(request)
    try:
        manager.get_tts_stream(stream_id)
    except AudioRuntimeError as exc:
        raise HTTPException(status_code=400, detail=exc.code)
    return StreamingResponse(
        manager.stream_tts_bytes(stream_id),
        media_type=manager.media_type(),
    )


async def _run_public_progressive_turn(
    request: Request,
    handle: PublicSessionHandle,
    text: str,
    *,
    source: str,
    input_mode: str,
):
    event_loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    metadata = {
        "source": source,
        "input_mode": input_mode,
        "public_online": True,
        "session_id": handle.session_id,
        "visitor_id": handle.visitor_id,
        "nickname": handle.nickname,
    }
    if input_mode == "voice_transcript":
        metadata.update({
            "transcript_state": "final",
            "audio_session_id": handle.session_id,
        })
    if hasattr(request.app.state, "first_unit_gate_enabled"):
        metadata["first_unit_gate_enabled"] = bool(request.app.state.first_unit_gate_enabled)

    def progress_callback(event: dict[str, Any]) -> None:
        event_loop.call_soon_threadsafe(queue.put_nowait, dict(event))

    future = event_loop.run_in_executor(
        None,
        handle.loop.run_turn,
        text,
        source,
        metadata,
        progress_callback,
    )
    audio_manager = _audio_manager(request)
    second_delta_event_emitted = False
    second_delta_stream_created = False
    second_delta_spoken_texts: list[str] = []

    try:
        while True:
            if future.done() and queue.empty():
                await asyncio.sleep(0)
                if queue.empty():
                    break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            payload = _public_event_payload(event)
            phase = payload.get("phase")
            if phase == "first_unit":
                if str(payload.get("text") or "").strip():
                    _attach_tts_stream(
                        payload,
                        audio_manager,
                        source="dialog_first_unit",
                        latency_name="public_dialog_progressive.first_tts_stream_create",
                        audio_session_id=handle.session_id,
                    )
                    _register_stream(handle, payload)
            elif phase == "second_delta":
                _attach_second_delta_tts_stream(payload, audio_manager, audio_session_id=handle.session_id)
                _register_stream(handle, payload)
                second_delta_event_emitted = True
                if payload.get("tts_stream_id"):
                    second_delta_stream_created = True
                    spoken_text = str(payload.get("text") or "").strip()
                    if spoken_text:
                        second_delta_spoken_texts.append(spoken_text)
            yield payload

        output = await future
        plan = output.response_plan.to_dict() if output.response_plan is not None else None
        final_payload = {
            "phase": "final",
            "text": (
                output.response_plan.second_unit
                if output.response_plan is not None
                else output.text
            ),
            "response_plan": plan,
            "delay_ms": output.delay_ms,
            "visual_mode": output.visual_mode,
            "vocal_marker": output.vocal_marker,
            "body_action": output.body_action,
            "truncated": output.truncated,
            "stop_reason": output.stop_reason,
            "latency_record_id": output.latency_record_id,
            "done": True,
        }
        if second_delta_stream_created:
            remainder = _remaining_final_tts_text(final_payload, second_delta_spoken_texts)
            if remainder:
                _attach_tts_stream(
                    final_payload,
                    audio_manager,
                    source="dialog_second_unit_remainder",
                    latency_name="public_dialog_progressive.second_remainder_tts_stream_create",
                    audio_session_id=handle.session_id,
                    text_override=remainder,
                )
                _register_stream(handle, final_payload)
        elif second_delta_event_emitted or str(final_payload.get("text") or "").strip():
            _attach_tts_stream(
                final_payload,
                audio_manager,
                source="dialog_second_unit",
                latency_name="public_dialog_progressive.second_tts_stream_create",
                audio_session_id=handle.session_id,
            )
            _register_stream(handle, final_payload)
        yield _public_event_payload(final_payload)
    finally:
        await _wait_for_turn_future(future)


def _public_session_manager(app: Any) -> PublicSessionManager:
    manager = getattr(app.state, "public_session_manager", None)
    if manager is None:
        manager = PublicSessionManager(app)
        app.state.public_session_manager = manager
    return manager


def _public_session_payload(handle: PublicSessionHandle, request: Request) -> dict[str, Any]:
    audio_status = _audio_manager(request).status()
    return {
        "session_token": handle.token,
        "session_id": handle.session_id,
        "visitor_id": handle.visitor_id,
        "nickname": handle.nickname,
        "expires_at": int(handle.expires_at),
        "audio": {
            "enabled": bool(audio_status.get("enabled")),
            "provider": audio_status.get("provider"),
            "disabled_reason": audio_status.get("disabled_reason"),
        },
    }


def _public_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "phase",
        "text",
        "index",
        "response_plan",
        "delay_ms",
        "visual_mode",
        "vocal_marker",
        "body_action",
        "truncated",
        "stop_reason",
        "latency_record_id",
        "done",
        "should_speak",
        "tts_stream_id",
        "audio_disabled_reason",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _register_stream(handle: PublicSessionHandle, payload: dict[str, Any]) -> None:
    stream_id = payload.get("tts_stream_id")
    if stream_id:
        handle.tts_stream_ids.add(str(stream_id))


def _assert_request_origin_allowed(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin_allowed(origin):
        raise HTTPException(status_code=403, detail="origin not allowed")


def _normalize_nickname(value: str) -> str:
    nickname = " ".join(str(value or "").strip().split())
    if not nickname:
        raise HTTPException(status_code=400, detail="nickname is required")
    if len(nickname) > 60:
        raise HTTPException(status_code=413, detail="nickname is too long")
    return nickname


def _visitor_id_for_nickname(nickname: str) -> str:
    digest = hashlib.sha256(nickname.casefold().encode("utf-8")).hexdigest()[:18]
    return f"public-{digest}"


def _token_secret() -> str:
    secret = (
        os.getenv("STRANGER_PUBLIC_TOKEN_SECRET")
        or os.getenv("STRANGER_PUBLIC_ACCESS_CODE")
        or os.getenv("OPERATOR_API_KEY")
    )
    if not secret:
        raise HTTPException(status_code=503, detail="public token secret is not configured")
    return secret


def _sign_session_token(payload: dict[str, Any]) -> str:
    encoded = _b64_json(payload)
    signature = hmac.new(_token_secret().encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


def _verify_session_token(token: str) -> dict[str, Any]:
    encoded, sep, signature = str(token or "").partition(".")
    if not sep:
        raise HTTPException(status_code=401, detail="invalid session token")
    expected = hmac.new(_token_secret().encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(expected), signature):
        raise HTTPException(status_code=401, detail="invalid session token")
    try:
        payload = json.loads(_b64_decode(encoded).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid session token") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="session token expired")
    return payload


def _b64_json(payload: dict[str, Any]) -> str:
    return _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _token_from_request(request: Request) -> str | None:
    return (
        request.query_params.get("session_token")
        or _token_from_headers(request.headers)
    )


def _token_from_headers(headers) -> str | None:
    direct = headers.get("X-Session-Token") or headers.get("x-session-token")
    if direct:
        return direct
    auth = headers.get("Authorization") or headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _ndjson(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
