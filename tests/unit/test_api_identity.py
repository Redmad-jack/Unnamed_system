from __future__ import annotations

import asyncio
import json
import sqlite3
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
        identity_gating=controller,
        face_identity_manager=face_identity_manager,
        vision_manager=vision_manager,
    )))


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
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

    def latest_frame_jpeg(self):
        return self.frame


def _face_manager(tmp_path, candidates, provider=None):
    config = FaceIdentityConfig(signature_dir=tmp_path, min_sharpness=35.0)
    return FaceIdentityManager(config, provider=provider or FakeFaceProvider(candidates))


def _candidate(embedding=None):
    return FaceDetectionCandidate(
        bbox=(100, 100, 420, 460),
        detection_score=0.95,
        embedding=embedding or [1.0, 0.0],
        frame_width=1280,
        frame_height=720,
        quality_summary={"sharpness": 80.0},
    )


def test_identity_config_defaults_to_no_auto_bind_and_can_update():
    conn = _db()
    controller = VisitorSessionGatingController(session_id="current")
    request = _request(conn, controller)

    status = asyncio.run(api.identity_status(request))
    updated = asyncio.run(api.identity_config_update(
        IdentityConfigRequest(auto_bind_high_confidence=True),
        request,
    ))

    assert status["config"]["auto_bind_high_confidence"] is False
    assert updated["config"]["auto_bind_high_confidence"] is True
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
