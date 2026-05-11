from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from conscious_entity.audio import AudioManager, AudioRuntimeError
from conscious_entity.interfaces.api_models import AudioDialogRequest
from conscious_entity.interfaces.api_runtime import _run_dialog_turn
from conscious_entity.telemetry.latency import record_audio_latency


audio_router = APIRouter(prefix="/api/v1/audio")


@audio_router.get("/status")
async def audio_status(request: Request):
    return _audio_manager(request).status()


@audio_router.post("/dialog")
async def audio_dialog(body: AudioDialogRequest, request: Request):
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript is required")

    try:
        output = await _run_dialog_turn(request, transcript, source="audio_dialog")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    manager = _audio_manager(request)
    start = time.perf_counter()
    stream, should_speak = manager.create_tts_stream(output)
    record_audio_latency(
        "audio_dialog.tts_stream_create",
        (time.perf_counter() - start) * 1000,
        metadata={
            "should_speak": should_speak,
            "has_stream": stream is not None,
            "audio_session_id": body.audio_session_id,
        },
    )
    disabled_reason = manager.config.disabled_reason() if should_speak and stream is None else None
    return {
        "input_text": transcript,
        "audio_session_id": body.audio_session_id,
        "output_text": output.text,
        "spoken_text": output.spoken_text,
        "delay_ms": output.delay_ms,
        "visual_mode": output.visual_mode,
        "should_speak": should_speak,
        "tts_stream_id": stream.stream_id if stream else None,
        "output_format": manager.config.output_format,
        "audio_disabled_reason": disabled_reason,
    }


@audio_router.get("/tts/stream/{stream_id}")
async def audio_tts_http_stream(stream_id: str, request: Request):
    manager = _audio_manager(request)
    try:
        manager.get_tts_stream(stream_id)
    except AudioRuntimeError as exc:
        raise HTTPException(status_code=400, detail=exc.code)
    return StreamingResponse(
        manager.stream_tts_bytes(stream_id),
        media_type=manager.media_type(),
    )


@audio_router.websocket("/tts/stream")
async def audio_tts_ws_stream(websocket: WebSocket):
    await websocket.accept()
    manager = _audio_manager(websocket)
    try:
        payload = await websocket.receive_json()
        message_type = payload.get("type")
        if message_type == "speak_stream":
            stream_id = str(payload.get("stream_id") or "")
        elif message_type == "debug_speak_text":
            stream = manager.create_debug_tts_stream(str(payload.get("text") or ""))
            stream_id = stream.stream_id
        else:
            await websocket.send_json({"type": "error", "code": "invalid_tts_request"})
            await websocket.close(code=1008)
            return

        stream = manager.get_tts_stream(stream_id)
        await websocket.send_json(
            {
                "type": "tts.start",
                "stream_id": stream.stream_id,
                "format": stream.output_format,
            }
        )
        async for chunk in manager.stream_tts_bytes(stream.stream_id):
            await websocket.send_bytes(chunk)
        await websocket.send_json(
            {
                "type": "tts.done",
                "stream_id": stream.stream_id,
                "logid": stream.last_logid,
            }
        )
    except WebSocketDisconnect:
        return
    except AudioRuntimeError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "code": exc.code,
                "message": exc.message,
                "logid": exc.logid,
            }
        )
        await websocket.close(code=1011)


@audio_router.websocket("/stt/stream")
async def audio_stt_stream(websocket: WebSocket):
    await websocket.accept()
    manager = _audio_manager(websocket)
    session_id = ""
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=manager.config.queue_max_chunks
    )
    try:
        start = await websocket.receive_json()
        if start.get("type") != "start":
            await websocket.send_json({"type": "error", "code": "missing_start_message"})
            await websocket.close(code=1008)
            return

        session = manager.create_stt_session(
            sample_rate=int(start.get("sample_rate") or manager.config.sample_rate),
            chunk_ms=int(start.get("chunk_ms") or manager.config.chunk_ms),
            audio_format=str(start.get("format") or "pcm_s16le"),
            channels=int(start.get("channels") or 1),
        )
        session_id = session.session_id
        await websocket.send_json({"type": "stt.start", "session_id": session_id})

        producer = asyncio.create_task(_receive_audio_frames(websocket, audio_queue, manager))
        consumer = asyncio.create_task(_send_transcript_events(websocket, audio_queue, manager, session_id))
        done, pending = await asyncio.wait(
            {producer, consumer},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if producer in done:
            producer.result()
            await consumer
        else:
            consumer.result()
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
    except WebSocketDisconnect:
        return
    except AudioRuntimeError as exc:
        manager.set_error(exc.code, exc.message, logid=exc.logid)
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
            manager.finish_stt_session(session_id)


async def _receive_audio_frames(
    websocket: WebSocket,
    audio_queue: asyncio.Queue[bytes | None],
    manager: AudioManager,
) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            await _put_stop(audio_queue)
            return
        text = message.get("text")
        if text is not None:
            payload = _parse_json(text)
            if payload.get("type") == "stop":
                await _put_stop(audio_queue)
                return
            continue
        data = message.get("bytes")
        if data:
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                manager.set_error("stt_queue_overflow", "Audio chunk queue overflow.")
                await websocket.send_json({"type": "warning", "code": "stt_queue_overflow"})
            await audio_queue.put(data)


async def _send_transcript_events(
    websocket: WebSocket,
    audio_queue: asyncio.Queue[bytes | None],
    manager: AudioManager,
    session_id: str,
) -> None:
    async for event in manager.stream_stt_events(_audio_chunks(audio_queue), session_id=session_id):
        await websocket.send_json(event.to_public_dict())


async def _audio_chunks(audio_queue: asyncio.Queue[bytes | None]) -> AsyncIterator[bytes]:
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            return
        yield chunk


async def _put_stop(audio_queue: asyncio.Queue[bytes | None]) -> None:
    if audio_queue.full():
        try:
            audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    await audio_queue.put(None)


def _parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _audio_manager(request_or_websocket: Request | WebSocket) -> AudioManager:
    manager = getattr(request_or_websocket.app.state, "audio_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Audio runtime not initialised")
    return manager
