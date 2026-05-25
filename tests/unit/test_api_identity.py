from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from conscious_entity.db.migrations import run_migrations
from conscious_entity.identity import (
    FaceDetectionCandidate,
    FaceIdentityConfig,
    FaceIdentityManager,
    VisitorSessionGatingController,
)
from conscious_entity.interfaces import api
from conscious_entity.interfaces import api_runtime
from conscious_entity.interfaces import api_routes
from conscious_entity.interfaces.api_models import (
    FaceCaptureRequest,
    FaceEnrollRequest,
    FaceSignatureDeactivateRequest,
    IdentityConfirmRequest,
    IdentityConfigRequest,
    IdentityMatchRequest,
    IdentityMatchSignalRequest,
)
from conscious_entity.interfaces.api_runtime import _ensure_visitor_profile, _visitor_row_to_public


def _request(
    conn: sqlite3.Connection,
    controller: VisitorSessionGatingController,
    *,
    face_identity_manager=None,
    vision_manager=None,
):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        db_path=":memory:",
        session_id="current",
        visitor_id=None,
        loop_lock=asyncio.Lock(),
        llm_runtime_config=None,
        llm_error=None,
        embedding_runtime_config=None,
        embedding_error=None,
        configs={},
        identity_gating=controller,
        face_identity_manager=face_identity_manager,
        vision_manager=vision_manager,
    )))


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("current",))
    conn.commit()
    return conn


class FakeFaceProvider:
    def __init__(self, candidates):
        self.candidates = candidates

    def dependency_status(self):
        return {"available": True, "missing": []}

    def model_status(self):
        return {
            "provider": "fake",
            "model_name": "fake-face",
            "loaded": True,
            "dependencies": self.dependency_status(),
            "disabled_reason": None,
            "last_error": None,
        }

    def extract(self, _image_bytes):
        return list(self.candidates)


class MissingFaceProvider(FakeFaceProvider):
    def dependency_status(self):
        return {"available": False, "missing": ["insightface"]}

    def model_status(self):
        return {
            "provider": "fake",
            "model_name": "fake-face",
            "loaded": False,
            "dependencies": self.dependency_status(),
            "disabled_reason": "Missing optional dependencies: insightface",
            "last_error": None,
        }


class FakeVisionManager:
    def __init__(self, frame=b"frame"):
        self.frame = frame
        self.activity_marked = False

    def latest_frame_jpeg(self):
        return self.frame

    def mark_activity(self):
        self.activity_marked = True


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
        self.closed = False
        self.turns = []

    def run_turn(self, text, source="dialog", metadata=None, progress_callback=None):
        self.turns.append({"text": text, "source": source, "metadata": metadata or {}})
        self.conn.execute(
            """
            INSERT INTO interaction_log (
                session_id, visitor_id, role, raw_text, event_types,
                policy_action, expression_output
            ) VALUES (?, ?, 'user', ?, '[]', 'respond_openly', ?)
            """,
            (self.session_id, self.visitor_id, text, "ok"),
        )
        self.conn.commit()
        return SimpleNamespace(text="ok")

    def close(self, *, wait_for_background=True):
        self.closed = True


def _face_manager(tmp_path, candidates, provider=None):
    config = FaceIdentityConfig(signature_dir=tmp_path, min_sharpness=35.0)
    return FaceIdentityManager(config, provider=provider or FakeFaceProvider(candidates))


def _candidate(embedding=None, *, bbox=(100, 100, 420, 460), sharpness=80.0):
    return FaceDetectionCandidate(
        bbox=bbox,
        detection_score=0.95,
        embedding=embedding or [1.0, 0.0],
        frame_width=1280,
        frame_height=720,
        quality_summary={"sharpness": sharpness},
    )


def _prepare_dialog_request(
    request,
    monkeypatch,
    tmp_path,
    *,
    visitor_id=None,
):
    request.app.state.loop = FakeLoop(request.app.state.conn, "current", visitor_id=visitor_id)
    request.app.state.prompts_dir = Path(tmp_path)
    monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(api_runtime, "InteractionLoop", FakeLoop)
    return request.app.state.loop


def test_identity_config_defaults_to_no_auto_bind_and_can_update():
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)

    status = asyncio.run(api.identity_status(request))
    updated = asyncio.run(api.identity_config_update(
        IdentityConfigRequest(
            auto_bind_high_confidence=True,
            handoff_after_primary_leave_enabled=False,
        ),
        request,
    ))

    assert status["config"]["auto_bind_high_confidence"] is False
    assert status["config"]["handoff_after_primary_leave_enabled"] is True
    assert status["config"]["primary_leave_grace_seconds"] == 35.0
    assert status["status"]["primary_presence_status"] == "no_primary"
    assert updated["config"]["auto_bind_high_confidence"] is True
    assert updated["config"]["handoff_after_primary_leave_enabled"] is False
    conn.close()


def test_visitor_identity_metadata_merge_preserves_existing_fields():
    conn = _db()

    _ensure_visitor_profile(
        conn,
        "visitor-k",
        metadata={"favorite_color": "blue", "identity": {"schema_version": 1}},
    )
    _ensure_visitor_profile(
        conn,
        "visitor-k",
        metadata={"identity": {"latest_match": {"candidate_visitor_id": "visitor-k"}}},
    )

    row = conn.execute("SELECT * FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    public = _visitor_row_to_public(row)

    assert public["metadata"]["favorite_color"] == "blue"
    assert public["metadata"]["identity"]["schema_version"] == 1
    assert public["metadata"]["identity"]["latest_match"]["candidate_visitor_id"] == "visitor-k"
    conn.close()


def test_identity_match_records_candidate_and_redacted_metadata():
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)

    result = asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignalRequest(
                score=0.9,
                quality_summary={"raw_image": "bytes"},
                metadata={"face_embedding": [0.1, 0.2]},
            ),
        ),
        request,
    ))

    assert result["status"]["candidate_visitor_id"] == "visitor-k"
    assert result["status"]["waiting_for_identity_confirmation"] is True
    row = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        ("visitor-k",),
    ).fetchone()
    metadata = json.loads(row["metadata"])
    face = metadata["identity"]["latest_match"]["face"]
    assert face["quality_summary"]["raw_image"] == "[redacted]"
    assert face["metadata"]["face_embedding"] == "[redacted]"
    conn.close()


def test_identity_confirm_binds_current_session_and_rebuilds_loop(monkeypatch):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)
    rebuilt = {"called": False}
    monkeypatch.setattr(api_routes, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_routes, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(
        api_routes,
        "_rebuild_loop",
        lambda _request, _client, _embedding_client=None: rebuilt.update(called=True),
    )
    asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignalRequest(score=0.9),
        ),
        request,
    ))

    result = asyncio.run(api.identity_confirm(IdentityConfirmRequest(accepted=True), request))

    assert result["status"]["primary_visitor_id"] == "visitor-k"
    assert request.app.state.visitor_id == "visitor-k"
    assert rebuilt["called"] is True
    assert conn.execute(
        "SELECT visitor_id FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["visitor_id"] == "visitor-k"
    conn.close()


def test_primary_leave_handoff_starts_new_unidentified_session(monkeypatch):
    conn = _db()
    conn.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-a", "current"))
    conn.commit()
    controller = VisitorSessionGatingController(
        session_id="current",
        primary_visitor_id="visitor-a",
    )
    request = _request(conn, controller)
    request.app.state.visitor_id = "visitor-a"
    rebuilt = {"called": False}
    saved = {"called": False}
    monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(
        api_runtime,
        "_rebuild_loop",
        lambda _request, _client, _embedding_client=None: rebuilt.update(called=True),
    )
    monkeypatch.setattr(
        api_runtime,
        "_save_initial_state",
        lambda _conn, _session_id, _configs: saved.update(called=True),
    )
    old_last_seen = (datetime.now(timezone.utc) - timedelta(seconds=36)).isoformat()
    controller.update_primary_presence({
        "frame_id": 1,
        "person_present": True,
        "tracks": [{"track_id": 1, "active": True, "last_seen_at": old_last_seen}],
    })
    handoff_context = controller.update_primary_presence({
        "frame_id": 2,
        "person_present": True,
        "tracks": [
            {"track_id": 1, "active": False, "last_seen_at": old_last_seen},
            {"track_id": 2, "active": True, "last_seen_at": datetime.now(timezone.utc).isoformat()},
        ],
    })

    asyncio.run(api_runtime._start_unidentified_session_after_primary_leave(
        request.app,
        handoff_context,
    ))

    new_session_id = request.app.state.session_id
    assert handoff_context["primary_released"] is True
    assert new_session_id != "current"
    assert request.app.state.visitor_id is None
    assert rebuilt["called"] is True
    assert saved["called"] is False
    assert conn.execute(
        "SELECT ended_at FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["ended_at"] is not None
    new_row = conn.execute(
        "SELECT visitor_id, notes FROM sessions WHERE id = ?",
        (new_session_id,),
    ).fetchone()
    assert new_row["visitor_id"] is None
    assert "primary visitor left" in new_row["notes"]
    status = controller.status()["status"]
    assert status["session_id"] == new_session_id
    assert status["primary_visitor_id"] is None
    assert status["last_primary_release"]["reason"] == "primary_track_lost"
    conn.close()


def test_missing_grace_turn_uses_temporary_unscoped_session(monkeypatch, tmp_path):
    conn = _db()
    conn.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-a", "current"))
    conn.commit()
    controller = VisitorSessionGatingController(
        session_id="current",
        primary_visitor_id="visitor-a",
    )
    controller.update_primary_presence({
        "frame_id": 1,
        "person_present": True,
        "tracks": [{
            "track_id": 1,
            "active": True,
            "last_seen_at": (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat(),
        }],
    })
    controller.update_primary_presence({
        "frame_id": 2,
        "person_present": True,
        "tracks": [
            {
                "track_id": 1,
                "active": False,
                "last_seen_at": (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat(),
            },
            {
                "track_id": 2,
                "active": True,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
    })
    manager = _face_manager(tmp_path, [_candidate()])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    request.app.state.visitor_id = "visitor-a"
    request.app.state.loop = FakeLoop(conn, "current", visitor_id="visitor-a")
    request.app.state.prompts_dir = Path(tmp_path)
    monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(api_runtime, "InteractionLoop", FakeLoop)

    asyncio.run(api_runtime._run_dialog_turn(request, "我是B"))

    unscoped_session_id = request.app.state.unscoped_grace_session_id
    unscoped_loop = request.app.state.unscoped_grace_loop

    assert request.app.state.loop.turns == []
    assert request.app.state.session_id == "current"
    assert request.app.state.visitor_id == "visitor-a"
    assert unscoped_session_id != "current"
    assert unscoped_loop.visitor_id is None
    assert unscoped_loop.turns[0]["text"] == "我是B"
    assert "identity_pre_turn_capture" not in unscoped_loop.turns[0]["metadata"]
    assert controller.status()["status"]["visitor_memory_allowed"] is False
    assert conn.execute("SELECT COUNT(*) FROM visitor_profiles").fetchone()[0] == 0
    assert manager.status()["store"]["signature_count"] == 0
    conn.close()


def test_primary_return_archives_temporary_unscoped_session(monkeypatch, tmp_path):
    conn = _db()
    conn.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-a", "current"))
    conn.commit()
    controller = VisitorSessionGatingController(
        session_id="current",
        primary_visitor_id="visitor-a",
    )
    request = _request(conn, controller)
    request.app.state.visitor_id = "visitor-a"
    request.app.state.loop = FakeLoop(conn, "current", visitor_id="visitor-a")
    request.app.state.prompts_dir = Path(tmp_path)
    request.app.state.unscoped_grace_session_id = "unscoped-1"
    request.app.state.unscoped_grace_loop = FakeLoop(conn, "unscoped-1", visitor_id=None)
    conn.execute(
        "INSERT INTO sessions (id, visitor_id, notes) VALUES (?, NULL, ?)",
        ("unscoped-1", "temporary unscoped"),
    )
    conn.commit()

    asyncio.run(api_runtime._archive_unscoped_grace_session_if_needed(
        request.app,
        reason="primary_returned_within_grace",
    ))

    row = conn.execute(
        "SELECT ended_at FROM sessions WHERE id = ?",
        ("unscoped-1",),
    ).fetchone()
    assert row["ended_at"] is not None
    assert request.app.state.session_id == "current"
    assert request.app.state.visitor_id == "visitor-a"
    assert request.app.state.unscoped_grace_session_id is None
    assert request.app.state.unscoped_grace_loop is None
    conn.close()


def test_primary_release_promotes_temporary_unscoped_session(monkeypatch, tmp_path):
    conn = _db()
    conn.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-a", "current"))
    conn.execute(
        "INSERT INTO sessions (id, visitor_id, notes) VALUES (?, NULL, ?)",
        ("unscoped-1", "temporary unscoped"),
    )
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, visitor_id, role, raw_text, event_types,
            policy_action, expression_output
        ) VALUES (?, NULL, 'user', ?, '[]', 'respond_openly', ?)
        """,
        ("unscoped-1", "我是B", "ok"),
    )
    conn.commit()
    controller = VisitorSessionGatingController(
        session_id="current",
        primary_visitor_id="visitor-a",
    )
    request = _request(conn, controller)
    request.app.state.visitor_id = "visitor-a"
    current_loop = FakeLoop(conn, "current", visitor_id="visitor-a")
    pending_loop = FakeLoop(conn, "unscoped-1", visitor_id=None)
    request.app.state.loop = current_loop
    request.app.state.unscoped_grace_session_id = "unscoped-1"
    request.app.state.unscoped_grace_loop = pending_loop
    request.app.state.prompts_dir = Path(tmp_path)
    controller.update_primary_presence({
        "frame_id": 1,
        "person_present": True,
        "tracks": [{
            "track_id": 1,
            "active": True,
            "last_seen_at": (datetime.now(timezone.utc) - timedelta(seconds=36)).isoformat(),
        }],
    })
    released = controller.update_primary_presence({
        "frame_id": 2,
        "person_present": True,
        "tracks": [
            {
                "track_id": 1,
                "active": False,
                "last_seen_at": (datetime.now(timezone.utc) - timedelta(seconds=36)).isoformat(),
            },
            {
                "track_id": 2,
                "active": True,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
    })

    asyncio.run(api_runtime._start_unidentified_session_after_primary_leave(
        request.app,
        released,
    ))

    assert request.app.state.session_id == "unscoped-1"
    assert request.app.state.visitor_id is None
    assert request.app.state.loop is pending_loop
    assert current_loop.closed is True
    assert request.app.state.unscoped_grace_session_id is None
    assert conn.execute(
        "SELECT ended_at FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["ended_at"] is not None
    promoted = conn.execute(
        "SELECT visitor_id, ended_at FROM sessions WHERE id = ?",
        ("unscoped-1",),
    ).fetchone()
    assert promoted["visitor_id"] is None
    assert promoted["ended_at"] is None
    row = conn.execute(
        "SELECT visitor_id, raw_text FROM interaction_log WHERE session_id = ?",
        ("unscoped-1",),
    ).fetchone()
    assert row["visitor_id"] is None
    assert row["raw_text"] == "我是B"
    assert controller.status()["status"]["last_primary_release"]["new_session_id"] == "unscoped-1"
    conn.close()


def test_natural_identity_confirmation_accepts_and_binds(monkeypatch):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", display_name="K")
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)
    rebuilt = {"called": False}
    monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(
        api_runtime,
        "_rebuild_loop",
        lambda _request, _client, _embedding_client=None: rebuilt.update(called=True),
    )
    asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignalRequest(score=0.9),
        ),
        request,
    ))
    metadata: dict = {}

    api_runtime._apply_natural_identity_confirmation_locked(request, "是的，是我", metadata)

    status = controller.status()["status"]
    assert status["primary_visitor_id"] == "visitor-k"
    assert status["visitor_memory_allowed"] is True
    assert status["last_natural_confirmation"]["status"] == "accepted"
    assert request.app.state.visitor_id == "visitor-k"
    assert rebuilt["called"] is True
    conn.close()


def test_natural_identity_confirmation_accepts_explicit_named_phrases(monkeypatch):
    accepted_phrases = ("对，是我", "我是 K")
    for phrase in accepted_phrases:
        conn = _db()
        _ensure_visitor_profile(conn, "visitor-k", display_name="K")
        controller = VisitorSessionGatingController(session_id="current")
        request = _request(conn, controller)
        monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
        monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
        monkeypatch.setattr(api_runtime, "_rebuild_loop", lambda *_args, **_kwargs: None)
        asyncio.run(api.identity_match(
            IdentityMatchRequest(
                candidate_visitor_id="visitor-k",
                face=IdentityMatchSignalRequest(score=0.9),
            ),
            request,
        ))
        metadata: dict = {}

        api_runtime._apply_natural_identity_confirmation_locked(request, phrase, metadata)

        status = controller.status()["status"]
        assert status["primary_visitor_id"] == "visitor-k"
        assert status["last_natural_confirmation"]["status"] == "accepted"
        conn.close()


def test_natural_identity_confirmation_leaves_ambiguous_phrases_unbound(monkeypatch):
    unclear_phrases = ("你是AI吗？", "你是不是在问我是谁？", "我是另一个人")
    for phrase in unclear_phrases:
        conn = _db()
        _ensure_visitor_profile(conn, "visitor-k", display_name="K")
        controller = VisitorSessionGatingController(session_id="current")
        request = _request(conn, controller)
        monkeypatch.setattr(api_runtime, "_active_llm_client", lambda _request: MagicMock())
        monkeypatch.setattr(api_runtime, "_active_embedding_client", lambda _request: None)
        monkeypatch.setattr(api_runtime, "_rebuild_loop", lambda *_args, **_kwargs: None)
        asyncio.run(api.identity_match(
            IdentityMatchRequest(
                candidate_visitor_id="visitor-k",
                face=IdentityMatchSignalRequest(score=0.9),
            ),
            request,
        ))
        metadata: dict = {}

        api_runtime._apply_natural_identity_confirmation_locked(request, phrase, metadata)

        status = controller.status()["status"]
        assert status["primary_visitor_id"] is None
        assert status["candidate_visitor_id"] == "visitor-k"
        assert status["waiting_for_identity_confirmation"] is True
        assert status["last_natural_confirmation"]["status"] == "unclear"
        assert request.app.state.visitor_id is None
        conn.close()


def test_natural_identity_confirmation_rejects_without_binding():
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)
    asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignalRequest(score=0.9),
        ),
        request,
    ))
    metadata: dict = {}

    api_runtime._apply_natural_identity_confirmation_locked(request, "不是，你认错了", metadata)

    status = controller.status()["status"]
    assert status["primary_visitor_id"] is None
    assert status["candidate_visitor_id"] is None
    assert status["last_natural_confirmation"]["status"] == "rejected"
    assert request.app.state.visitor_id is None
    conn.close()


def test_medium_identity_match_sets_candidate_without_profile_update():
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)

    result = asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignalRequest(score=0.7),
        ),
        request,
    ))

    assert result["status"]["candidate_visitor_id"] == "visitor-k"
    assert result["status"]["waiting_for_identity_confirmation"] is True
    assert result["status"]["visitor_memory_allowed"] is False
    assert result["status"]["latest_match"]["candidate_visitor_id"] == "visitor-k"
    row = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        ("visitor-k",),
    ).fetchone()
    assert row is None
    conn.close()


def test_identity_auto_bind_runtime_config_binds_when_idle(monkeypatch):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)
    rebuilt = {"called": False}
    monkeypatch.setattr(api_routes, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api_routes, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(
        api_routes,
        "_rebuild_loop",
        lambda _request, _client, _embedding_client=None: rebuilt.update(called=True),
    )
    asyncio.run(api.identity_config_update(
        IdentityConfigRequest(auto_bind_high_confidence=True),
        request,
    ))

    result = asyncio.run(api.identity_match(
        IdentityMatchRequest(
            candidate_visitor_id="visitor-k",
            voice=IdentityMatchSignalRequest(score=0.91),
        ),
        request,
    ))

    assert result["status"]["primary_visitor_id"] == "visitor-k"
    assert result["status"]["candidate_visitor_id"] is None
    assert request.app.state.visitor_id == "visitor-k"
    assert rebuilt["called"] is True
    conn.close()


def test_face_identity_status_reports_disabled_provider(tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [], provider=MissingFaceProvider([]))
    request = _request(conn, controller, face_identity_manager=manager)

    result = asyncio.run(api.identity_face_status(request))

    assert result["enabled"] is False
    assert "insightface" in result["model"]["disabled_reason"]
    conn.close()


def test_face_capture_matches_existing_signature_and_updates_gating(tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", display_name="K")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-k")
    manager.provider.candidates = [_candidate([0.96, 0.28])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    controller.before_turn(source="dialog", input_mode="text", text="hello")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )

    result = asyncio.run(api.identity_face_capture(request, FaceCaptureRequest()))

    assert result["capture"]["accepted"] is True
    assert result["identity"]["status"]["candidate_visitor_id"] == "visitor-k"
    row = conn.execute("SELECT metadata FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    metadata = json.loads(row["metadata"])
    latest = metadata["identity"]["latest_match"]
    assert latest["candidate_visitor_id"] == "visitor-k"
    assert latest["face"]["metadata"]["face_embedding"] == "[redacted]"
    conn.close()


def test_medium_face_capture_sets_candidate_without_profile_update(tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", display_name="K")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-k")
    manager.provider.candidates = [_candidate([0.7, 0.714])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    controller.before_turn(source="dialog", input_mode="text", text="hello")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )

    result = asyncio.run(api.identity_face_capture(request, FaceCaptureRequest()))

    assert result["capture"]["accepted"] is True
    assert result["capture"]["match_result"]["combined_level"] == "medium"
    assert result["identity"]["status"]["candidate_visitor_id"] == "visitor-k"
    assert result["identity"]["status"]["waiting_for_identity_confirmation"] is True
    assert result["identity"]["status"]["visitor_memory_allowed"] is False
    row = conn.execute("SELECT metadata FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    metadata = json.loads(row["metadata"])
    identity = metadata.get("identity")
    assert not isinstance(identity, dict) or "latest_match" not in identity
    conn.close()


def test_pre_turn_unknown_face_auto_provisions_new_visitor(monkeypatch, tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    old_loop = _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "我是第一次来"))

    visitor_id = request.app.state.visitor_id
    assert visitor_id is not None
    assert visitor_id.startswith("visitor-")
    assert old_loop.closed is True
    assert old_loop.turns == []
    assert request.app.state.loop.visitor_id == visitor_id
    assert request.app.state.loop.turns[0]["text"] == "我是第一次来"
    assert request.app.state.loop.turns[0]["metadata"]["identity_pre_turn_capture"]["action"] == "auto_provisioned"
    assert conn.execute(
        "SELECT visitor_id FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["visitor_id"] == visitor_id
    rows = conn.execute("SELECT id, metadata FROM visitor_profiles").fetchall()
    assert [row["id"] for row in rows] == [visitor_id]
    metadata = json.loads(rows[0]["metadata"])
    identity = metadata["identity"]
    assert identity["auto_provisioned"] is True
    assert identity["provisioned_source"] == "pre_turn"
    assert identity["initial_capture"]["embedding"] == "[redacted]"
    assert len(identity["signatures"]["face"]) == 1
    assert manager.status()["store"]["signature_count"] == 1
    interaction = conn.execute(
        "SELECT visitor_id, raw_text FROM interaction_log WHERE session_id = ?",
        ("current",),
    ).fetchone()
    assert interaction["visitor_id"] == visitor_id
    assert interaction["raw_text"] == "我是第一次来"
    status = controller.status()["status"]
    assert status["primary_visitor_id"] == visitor_id
    assert status["visitor_memory_allowed"] is True
    conn.close()


def test_pre_turn_unknown_face_rejection_keeps_unidentified(monkeypatch, tmp_path):
    cases = [
        (None, FakeVisionManager(frame=None)),
        ([_candidate([1.0, 0.0]), _candidate([0.0, 1.0])], FakeVisionManager()),
        ([
            FaceDetectionCandidate(
                bbox=(100, 100, 420, 460),
                detection_score=0.95,
                embedding=[1.0, 0.0],
                frame_width=1280,
                frame_height=720,
                quality_summary={"sharpness": 10.0},
            )
        ], FakeVisionManager()),
    ]
    for candidates, vision in cases:
        conn = _db()
        controller = VisitorSessionGatingController(session_id="current")
        manager = _face_manager(tmp_path, candidates or [])
        request = _request(
            conn,
            controller,
            face_identity_manager=manager,
            vision_manager=vision,
        )
        old_loop = _prepare_dialog_request(request, monkeypatch, tmp_path)

        asyncio.run(api_runtime._run_dialog_turn(request, "你好"))

        assert request.app.state.visitor_id is None
        assert request.app.state.loop is old_loop
        assert old_loop.visitor_id is None
        assert old_loop.turns[0]["text"] == "你好"
        assert conn.execute("SELECT COUNT(*) FROM visitor_profiles").fetchone()[0] == 0
        assert conn.execute(
            "SELECT visitor_id FROM sessions WHERE id = ?",
            ("current",),
        ).fetchone()["visitor_id"] is None
        conn.close()


def test_pre_turn_known_high_sets_candidate_without_binding_or_memory(monkeypatch, tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", display_name="K")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-k")
    manager.provider.candidates = [_candidate([0.98, 0.2])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    old_loop = _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "你好"))

    assert request.app.state.visitor_id is None
    assert request.app.state.loop is old_loop
    assert old_loop.turns[0]["metadata"]["identity_pre_turn_capture"]["action"] == "candidate_pending"
    turn_identity = old_loop.turns[0]["metadata"]["identity_session"]
    assert turn_identity["candidate_visitor_id"] == "visitor-k"
    assert turn_identity["waiting_for_identity_confirmation"] is True
    assert turn_identity["visitor_memory_allowed"] is False
    assert conn.execute(
        "SELECT visitor_id FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["visitor_id"] is None
    conn.close()


def test_pre_turn_known_medium_sets_candidate_without_binding_or_memory(monkeypatch, tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", display_name="K")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-k")
    manager.provider.candidates = [_candidate([0.7, 0.714])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    old_loop = _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "你好"))

    assert request.app.state.visitor_id is None
    assert request.app.state.loop is old_loop
    turn_identity = old_loop.turns[0]["metadata"]["identity_session"]
    assert turn_identity["candidate_visitor_id"] == "visitor-k"
    assert turn_identity["waiting_for_identity_confirmation"] is True
    assert turn_identity["visitor_memory_allowed"] is False
    row = conn.execute("SELECT metadata FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    metadata = json.loads(row["metadata"])
    assert "latest_match" not in metadata.get("identity", {})
    conn.close()


def test_pre_turn_low_known_match_without_ambiguity_provisions_new_visitor(monkeypatch, tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-old")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-old")
    manager.provider.candidates = [_candidate([0.5, math.sqrt(0.75)])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "我是新人"))

    visitor_id = request.app.state.visitor_id
    assert visitor_id is not None
    assert visitor_id != "visitor-old"
    rows = conn.execute("SELECT id FROM visitor_profiles ORDER BY id").fetchall()
    assert {row["id"] for row in rows} == {"visitor-old", visitor_id}
    assert request.app.state.loop.visitor_id == visitor_id
    assert controller.status()["status"]["primary_visitor_id"] == visitor_id
    conn.close()


def test_pre_turn_low_near_medium_ambiguous_cluster_does_not_provision(monkeypatch, tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-left")
    _ensure_visitor_profile(conn, "visitor-right")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-left")
    manager.provider.candidates = [_candidate([0.0, 1.0, 0.0])]  # type: ignore[attr-defined]
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-right")
    z = math.sqrt(1.0 - (0.58 * 0.58) - (0.56 * 0.56))
    manager.provider.candidates = [_candidate([0.58, 0.56, z])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    old_loop = _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "你好"))

    assert request.app.state.visitor_id is None
    assert request.app.state.loop is old_loop
    assert old_loop.turns[0]["metadata"]["identity_pre_turn_capture"]["action"] == "ignored"
    assert conn.execute("SELECT COUNT(*) FROM visitor_profiles").fetchone()[0] == 2
    assert conn.execute(
        "SELECT visitor_id FROM sessions WHERE id = ?",
        ("current",),
    ).fetchone()["visitor_id"] is None
    assert controller.status()["status"]["candidate_visitor_id"] is None
    conn.close()


def test_pre_turn_auto_provision_and_background_capture_do_not_duplicate(monkeypatch, tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    _prepare_dialog_request(request, monkeypatch, tmp_path)

    asyncio.run(api_runtime._run_dialog_turn(request, "我是新人"))
    visitor_id = request.app.state.visitor_id
    asyncio.run(api_runtime._run_background_face_capture(request.app, b"frame"))

    assert request.app.state.visitor_id == visitor_id
    assert conn.execute("SELECT COUNT(*) FROM visitor_profiles").fetchone()[0] == 1
    assert manager.status()["store"]["signature_count"] == 1
    assert controller.status()["status"]["candidate_visitor_id"] is None
    conn.close()


def test_auto_provision_enrolls_the_capture_that_made_the_routing_decision(monkeypatch, tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    first_face = _candidate(
        [1.0, 0.0],
        bbox=(100, 100, 420, 460),
        sharpness=80.0,
    )
    second_face = _candidate(
        [0.0, 1.0],
        bbox=(20, 30, 220, 300),
        sharpness=95.0,
    )
    manager = _face_manager(tmp_path, [first_face])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )
    _prepare_dialog_request(request, monkeypatch, tmp_path)
    controller.before_turn(source="dialog", input_mode="text", text="我是新人")
    first_outcome = manager.capture_and_match(b"first-frame")

    manager.provider.candidates = [second_face]  # type: ignore[attr-defined]
    manager.capture_and_match(b"second-frame")
    result = api_runtime._apply_face_capture_identity_locked(
        request,
        manager,
        first_outcome,
        source="pre_turn",
    )

    assert result["action"] == "auto_provisioned"
    visitor_id = request.app.state.visitor_id
    assert visitor_id is not None
    row = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        (visitor_id,),
    ).fetchone()
    identity = json.loads(row["metadata"])["identity"]
    signature = identity["signatures"]["face"][0]

    assert identity["initial_capture"]["capture_id"] == first_outcome.capture.capture_id
    assert signature["quality_summary"]["bbox"] == first_outcome.capture.quality_summary["bbox"]
    assert signature["quality_summary"]["bbox"] != second_face.quality()["bbox"]
    assert request.app.state.visitor_id == visitor_id
    assert manager.status()["store"]["signature_count"] == 1
    conn.close()


def test_face_capture_without_frame_returns_api_error(tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    controller.before_turn(source="dialog", input_mode="text", text="hello")
    manager = _face_manager(tmp_path, [_candidate()])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(frame=None),
    )

    try:
        asyncio.run(api.identity_face_capture(request, FaceCaptureRequest()))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
        assert "No vision frame" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("expected HTTPException")
    conn.close()


def test_face_capture_requires_confirmed_dialogue_intent(tmp_path):
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [_candidate()])
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )

    try:
        asyncio.run(api.identity_face_capture(request, FaceCaptureRequest()))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
        assert "confirmed dialogue intent" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("expected HTTPException")
    conn.close()


def test_face_enroll_requires_existing_visitor_and_appends_reference(tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", metadata={"favorite_color": "blue"})
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    request = _request(conn, controller, face_identity_manager=manager)

    result = asyncio.run(api.identity_face_enroll(FaceEnrollRequest(visitor_id="visitor-k"), request))

    assert result["signature"]["reference"].startswith("local://face/")
    row = conn.execute("SELECT metadata FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    metadata = json.loads(row["metadata"])
    face_refs = metadata["identity"]["signatures"]["face"]
    assert metadata["favorite_color"] == "blue"
    assert "embedding" not in face_refs[0]
    assert face_refs[0]["reference"].startswith("local://face/")
    conn.close()


def test_face_signature_deactivate_marks_store_and_metadata_inactive(tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k", metadata={"favorite_color": "blue"})
    controller = VisitorSessionGatingController(session_id="current")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    request = _request(conn, controller, face_identity_manager=manager)
    enrolled = asyncio.run(api.identity_face_enroll(
        FaceEnrollRequest(visitor_id="visitor-k"),
        request,
    ))
    signature_id = enrolled["signature"]["signature_id"]

    result = asyncio.run(api.identity_face_signature_deactivate(
        FaceSignatureDeactivateRequest(
            visitor_id="visitor-k",
            signature_id=signature_id,
        ),
        request,
    ))

    assert result["signature"]["status"] == "inactive"
    assert manager.store.match([1.0, 0.0]) == []
    row = conn.execute("SELECT metadata FROM visitor_profiles WHERE id = ?", ("visitor-k",)).fetchone()
    metadata = json.loads(row["metadata"])
    assert metadata["identity"]["signatures"]["face"][0]["status"] == "inactive"
    conn.close()


def test_background_face_capture_sets_candidate_without_blocking_dialogue(tmp_path):
    conn = _db()
    _ensure_visitor_profile(conn, "visitor-k")
    manager = _face_manager(tmp_path, [_candidate([1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-k")
    manager.provider.candidates = [_candidate([0.98, 0.2])]  # type: ignore[attr-defined]
    controller = VisitorSessionGatingController(session_id="current")
    controller.before_turn(source="dialog", input_mode="text", text="hello")
    request = _request(
        conn,
        controller,
        face_identity_manager=manager,
        vision_manager=FakeVisionManager(),
    )

    async def run_capture():
        api_runtime._maybe_schedule_background_face_capture(request.app)
        await request.app.state.face_auto_capture_task

    asyncio.run(run_capture())

    status = controller.status()["status"]
    assert status["candidate_visitor_id"] == "visitor-k"
    assert status["waiting_for_identity_confirmation"] is True
    assert status["visitor_memory_allowed"] is False
    assert status["capture_in_flight"] is False
    conn.close()
