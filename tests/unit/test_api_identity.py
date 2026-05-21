from __future__ import annotations

import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

from conscious_entity.db.migrations import run_migrations
from conscious_entity.identity import VisitorSessionGatingController
from conscious_entity.interfaces import api
from conscious_entity.interfaces import api_routes
from conscious_entity.interfaces.api_models import (
    IdentityConfirmRequest,
    IdentityConfigRequest,
    IdentityMatchRequest,
    IdentityMatchSignalRequest,
)
from conscious_entity.interfaces.api_runtime import _ensure_visitor_profile, _visitor_row_to_public


def _request(conn: sqlite3.Connection, controller: VisitorSessionGatingController):
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
    )))


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("current",))
    conn.commit()
    return conn


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
