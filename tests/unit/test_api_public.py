from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conscious_entity.audio.types import AudioRuntimeError
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.expression.output_model import ExpressionOutput, build_response_plan
from conscious_entity.interfaces import api_public, api_runtime
from conscious_entity.interfaces.api_models import PublicDialogRequest, PublicSessionStartRequest
from conscious_entity.state.state_core import EntityState


class FakeLoop:
    def __init__(
        self,
        conn,
        session_id,
        _configs=None,
        _prompts_dir=None,
        *,
        visitor_id=None,
        **_kwargs,
    ):
        self.conn = conn
        self.session_id = session_id
        self.visitor_id = visitor_id
        self.current_state = EntityState(inquiry=0.62, care_response=0.34)
        self.closed = False
        self.turns = []

    def run_turn(self, text, source="dialog", metadata=None, progress_callback=None):
        self.turns.append({"text": text, "source": source, "metadata": metadata or {}})
        plan = build_response_plan(
            first_unit="I heard you.",
            second_unit="Stay a little closer.",
            third_unit="",
            vocal_marker="low",
            body_action="pause",
            visual_mode="curious",
        )
        if progress_callback is not None:
            progress_callback({
                "phase": "first_unit",
                "text": plan.first_unit,
                "response_plan": build_response_plan(
                    first_unit=plan.first_unit,
                    second_unit="",
                    third_unit="",
                    vocal_marker="low",
                    body_action="pause",
                    visual_mode="curious",
                ).to_dict(),
                "visual_mode": "curious",
                "vocal_marker": "low",
                "body_action": "pause",
            })
            progress_callback({
                "phase": "second_delta",
                "text": plan.second_unit,
                "index": 0,
                "visual_mode": "curious",
                "vocal_marker": "low",
                "body_action": "pause",
            })
        self.conn.execute(
            """
            INSERT INTO interaction_log (
                session_id, visitor_id, role, raw_text, event_types,
                policy_action, expression_output
            ) VALUES (?, ?, 'user', ?, '[]', 'respond_openly', ?)
            """,
            (self.session_id, self.visitor_id, text, plan.combined_text),
        )
        self.conn.commit()
        return ExpressionOutput(
            text=plan.combined_text,
            spoken_text=plan.combined_text,
            delay_ms=0,
            visual_mode="curious",
            raw_prompt="must not leak",
            vocal_marker="low",
            body_action="pause",
            response_plan=plan,
            latency_record_id="lat_public",
        )

    def close(self, *, wait_for_background=True):
        self.closed = True


class FakeAudioManager:
    def __init__(self):
        self.config = SimpleNamespace(
            output_format="mp3",
            queue_max_chunks=4,
            sample_rate=16000,
            chunk_ms=20,
            disabled_reason=lambda: None,
        )
        self.created_texts = []
        self.active = {}

    def status(self):
        return {"enabled": True, "provider": "fake", "disabled_reason": None}

    def create_tts_stream_from_text(self, text, *, source="dialog_output"):
        self.created_texts.append((text, source))
        if not text.strip():
            return None, False
        stream_id = f"tts_public_{len(self.created_texts)}"
        stream = SimpleNamespace(stream_id=stream_id)
        self.active[stream_id] = stream
        return stream, True

    def get_tts_stream(self, stream_id):
        if stream_id not in self.active:
            raise AudioRuntimeError("tts_stream_expired", "expired")
        return self.active[stream_id]

    async def stream_tts_bytes(self, stream_id):
        self.get_tts_stream(stream_id)
        yield b"audio"

    def media_type(self):
        return "audio/mpeg"


def _db_file(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    conn = get_connection(db_path, check_same_thread=False)
    run_migrations(conn)
    return conn, db_path


def _memory_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


def _request(conn, db_path, tmp_path, *, token=None, origin=None, audio_manager=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["origin"] = origin
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            conn=conn,
            db_path=db_path,
            configs={"entity_profile": {"initial_state": EntityState().to_dict()}},
            prompts_dir=tmp_path,
            llm_runtime_config=None,
            embedding_runtime_config=None,
            audio_manager=audio_manager or FakeAudioManager(),
            first_unit_gate_enabled=False,
        )),
        headers=headers,
        query_params={},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _install_fakes(monkeypatch):
    monkeypatch.setattr(api_public, "InteractionLoop", FakeLoop)
    monkeypatch.setattr(api_public, "_active_llm_client", lambda _request: SimpleNamespace())
    monkeypatch.setattr(api_public, "_active_embedding_client", lambda _request: None)


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


def test_public_access_code_required_and_wrong_code_rejected(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn, db_path = _db_file(tmp_path)
    request = _request(conn, db_path, tmp_path)
    manager = api_public.PublicSessionManager(request.app)
    body = PublicSessionStartRequest(access_code="wrong", nickname="Visitor")

    monkeypatch.setenv("STRANGER_PUBLIC_ACCESS_CODE", "open")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.start(request, body))

    assert exc.value.status_code == 403
    conn.close()


def test_public_nickname_identity_is_deterministic_but_sessions_are_separate(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn, db_path = _db_file(tmp_path)
    request = _request(conn, db_path, tmp_path)
    manager = api_public.PublicSessionManager(request.app)
    monkeypatch.setenv("STRANGER_PUBLIC_ACCESS_CODE", "open")

    first = asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="  Alice  "),
    ))
    second = asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="alice"),
    ))

    assert first.visitor_id == second.visitor_id
    assert first.session_id != second.session_id
    assert first.nickname == "Alice"
    assert second.nickname == "alice"

    rows = conn.execute("SELECT id, visitor_id FROM sessions ORDER BY started_at").fetchall()
    assert {row["id"] for row in rows} == {first.session_id, second.session_id}
    assert {row["visitor_id"] for row in rows} == {first.visitor_id}

    asyncio.run(manager.close_all())
    conn.close()


def test_public_tokens_keep_sessions_and_tts_streams_isolated(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn, db_path = _db_file(tmp_path)
    request = _request(conn, db_path, tmp_path)
    manager = api_public.PublicSessionManager(request.app)
    monkeypatch.setenv("STRANGER_PUBLIC_ACCESS_CODE", "open")

    alice = asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="Alice"),
    ))
    bob = asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="Bob"),
    ))
    alice.tts_stream_ids.add("tts_alice")

    bob_request = _request(conn, db_path, tmp_path, token=bob.token)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.stream_allowed(bob_request, "tts_alice"))

    assert alice.session_id != bob.session_id
    assert alice.visitor_id != bob.visitor_id
    assert exc.value.status_code == 404

    asyncio.run(manager.close_all())
    conn.close()


def test_public_dialog_stream_is_session_scoped_and_redacted(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn, db_path = _db_file(tmp_path)
    audio_manager = FakeAudioManager()
    request = _request(conn, db_path, tmp_path, audio_manager=audio_manager)
    manager = api_public.PublicSessionManager(request.app)
    monkeypatch.setenv("STRANGER_PUBLIC_ACCESS_CODE", "open")

    handle = asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="Alice"),
    ))
    authed_request = _request(conn, db_path, tmp_path, token=handle.token, audio_manager=audio_manager)

    response = asyncio.run(api_public.public_dialog_progressive(
        PublicDialogRequest(text="hello", input_mode="text"),
        authed_request,
    ))
    events = asyncio.run(_collect_streaming_response(response))

    assert [event["phase"] for event in events] == ["first_unit", "second_delta", "final"]
    assert all("raw_prompt" not in event for event in events)
    assert all("memory" not in event for event in events)
    assert any(event.get("tts_stream_id") for event in events)

    row = conn.execute(
        "SELECT session_id, visitor_id, raw_text FROM interaction_log WHERE raw_text = ?",
        ("hello",),
    ).fetchone()
    assert row["session_id"] == handle.session_id
    assert row["visitor_id"] == handle.visitor_id

    asyncio.run(manager.close_all())
    conn.close()


def test_missing_public_session_token_is_rejected(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn, db_path = _db_file(tmp_path)
    request = _request(conn, db_path, tmp_path)
    manager = api_public.PublicSessionManager(request.app)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.from_request(request))

    assert exc.value.status_code == 401
    conn.close()


def test_public_manager_does_not_close_shared_memory_connection(monkeypatch, tmp_path):
    _install_fakes(monkeypatch)
    conn = _memory_db()
    request = _request(conn, ":memory:", tmp_path)
    manager = api_public.PublicSessionManager(request.app)
    monkeypatch.setenv("STRANGER_PUBLIC_ACCESS_CODE", "open")

    asyncio.run(manager.start(
        request,
        PublicSessionStartRequest(access_code="open", nickname="Alice"),
    ))
    asyncio.run(manager.close_all())

    assert conn.execute("SELECT 1").fetchone()[0] == 1
    conn.close()


def test_public_stt_websocket_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("STRANGER_PUBLIC_ALLOWED_ORIGINS", raising=False)
    app = FastAPI()
    app.include_router(api_public.public_router)

    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/public/audio/stt/stream"):
            pass


def test_public_stt_websocket_rejects_wrong_origin(monkeypatch):
    monkeypatch.setenv("STRANGER_PUBLIC_ALLOWED_ORIGINS", "https://allowed.example")
    app = FastAPI()
    app.include_router(api_public.public_router)

    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/v1/public/audio/stt/stream?session_token=bad",
            headers={"origin": "https://blocked.example"},
        ):
            pass


def test_runtime_lifespan_creates_render_db_parent(monkeypatch, tmp_path):
    db_path = tmp_path / "render" / "nested" / "memory.db"
    app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setenv("ENTITY_DB_PATH", str(db_path))
    monkeypatch.setenv("ENTITY_EMBEDDING_MODE", "disabled")
    monkeypatch.setenv("ENTITY_AUDIO_ENABLED", "0")

    async def run_lifespan():
        async with api_runtime.lifespan(app):
            assert db_path.parent.exists()
            assert db_path.exists()

    asyncio.run(run_lifespan())
