from __future__ import annotations

import asyncio
import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.db.migrations import run_migrations
from conscious_entity.interfaces import api
from conscious_entity.interfaces.api import (
    EmbeddingConfigRequest,
    EmbeddingTestRequest,
    LLMConfigRequest,
    ManagedMemoryCommitRequest,
    ManagedMemoryUpdateRequest,
    MemoryStatusRequest,
    MemoryInfluencePreviewRequest,
    SessionTypeRequest,
    _conversation_export_payload,
    _resolve_session_id,
)


def test_conversation_export_payload_contains_user_and_entity_text(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("session-1",))
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action,
            expression_output, delay_ms, visual_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "session-1",
            "user",
            "你是谁？",
            '["user_spoke", "self_definition_query"]',
            "reject_definition",
            "这个称呼没有停稳。",
            300,
            "normal",
        ),
    )
    conn.commit()
    conn.close()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(db_path=db_path, session_id="session-1")
        )
    )

    payload = _conversation_export_payload(request)

    assert payload["session_id"] == "session-1"
    assert payload["turn_count"] == 1
    assert payload["turns"][0]["user_text"] == "你是谁？"
    assert payload["turns"][0]["entity_text"] == "这个称呼没有停稳。"
    assert payload["turns"][0]["event_types"] == ["user_spoke", "self_definition_query"]


def test_conversation_export_payload_can_select_session(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("current",))
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("archived",))
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action, expression_output
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("current", "user", "current text", "[]", "respond_openly", "current reply"),
    )
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action, expression_output
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("archived", "user", "archived text", "[]", "respond_openly", "archived reply"),
    )
    conn.commit()
    conn.close()

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path=db_path, session_id="current"))
    )

    payload = _conversation_export_payload(request, session_id="archived")

    assert payload["session_id"] == "archived"
    assert payload["turns"][0]["user_text"] == "archived text"


def test_resolve_session_id_uses_latest_existing_session(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTITY_SESSION_ID", raising=False)
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id, started_at) VALUES (?, ?)", ("old", "2026-01-01 00:00:00"))
    conn.execute("INSERT INTO sessions (id, started_at) VALUES (?, ?)", ("new", "2026-01-02 00:00:00"))
    conn.commit()

    assert _resolve_session_id(conn) == "new"
    conn.close()


def test_session_reset_archives_old_session_and_creates_initial_state(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id, session_type) VALUES (?, ?)", ("old-session", "exhibition"))
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action, expression_output
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("old-session", "user", "old text", "[]", "respond_openly", "old reply"),
    )
    conn.commit()

    configs = load_all_configs()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        session_id="old-session",
        configs=configs,
        prompts_dir=api._project_root() / "prompts",
        loop_lock=asyncio.Lock(),
        llm_runtime_config=None,
        llm_error=None,
    )))
    monkeypatch.setattr(api, "_active_llm_client", lambda _request: MagicMock())

    result = asyncio.run(api.sessions_reset(request))

    assert result["archived_session_id"] == "old-session"
    assert result["session_id"] != "old-session"
    old = conn.execute("SELECT ended_at FROM sessions WHERE id = ?", ("old-session",)).fetchone()
    assert old["ended_at"] is not None
    assert conn.execute(
        "SELECT COUNT(*) AS cnt FROM interaction_log WHERE session_id = ?",
        ("old-session",),
    ).fetchone()["cnt"] == 1
    assert conn.execute(
        "SELECT COUNT(*) AS cnt FROM state_snapshots WHERE session_id = ?",
        (result["session_id"],),
    ).fetchone()["cnt"] == 1
    new_session = conn.execute(
        "SELECT session_type FROM sessions WHERE id = ?",
        (result["session_id"],),
    ).fetchone()
    assert new_session["session_type"] == "exhibition"
    conn.close()


def test_session_type_update_rebuilds_loop(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("current",))
    conn.commit()

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        session_id="current",
        loop_lock=asyncio.Lock(),
        llm_runtime_config=None,
        llm_error=None,
        embedding_runtime_config=None,
        embedding_error=None,
    )))
    rebuilt = {"called": False}

    monkeypatch.setattr(api, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api, "_active_embedding_client", lambda _request: None)
    monkeypatch.setattr(
        api,
        "_rebuild_loop",
        lambda _request, _client, _embedding_client=None: rebuilt.update(called=True),
    )

    result = asyncio.run(api.session_type_update(SessionTypeRequest(session_type="exhibition"), request))

    assert result["session_type"] == "exhibition"
    assert rebuilt["called"] is True
    row = conn.execute("SELECT session_type FROM sessions WHERE id = ?", ("current",)).fetchone()
    assert row["session_type"] == "exhibition"
    conn.close()


def test_runtime_llm_config_update_does_not_write_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        loop_lock=asyncio.Lock(),
        llm_runtime_config=None,
        llm_error=None,
    )))
    captured = {}

    def fake_client(settings):
        captured["settings"] = settings
        return MagicMock()

    monkeypatch.setattr(api, "_client_from_settings", fake_client)
    monkeypatch.setattr(api, "_rebuild_loop", lambda _request, _client, _embedding_client=None: None)

    result = asyncio.run(api.config_llm_update(LLMConfigRequest(
        mode="official",
        model="claude-test",
        api_key="runtime-secret-key",
        disable_system_proxy=True,
    ), request))

    assert captured["settings"]["api_key"] == "runtime-secret-key"
    assert request.app.state.llm_runtime_config["model"] == "claude-test"
    assert result["ANTHROPIC_API_KEY"] == "runtim...et-key"
    assert result["source"] == "runtime"
    assert os.environ.get("ANTHROPIC_API_KEY") is None


def test_runtime_embedding_config_update_does_not_write_env(monkeypatch):
    monkeypatch.delenv("ENTITY_EMBEDDING_API_KEY", raising=False)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        loop_lock=asyncio.Lock(),
        embedding_runtime_config=None,
        embedding_error=None,
        llm_runtime_config=None,
        llm_error=None,
    )))
    captured = {}

    def fake_embedding_client(settings):
        captured["settings"] = settings
        return MagicMock(enabled=True, model=settings.get("model"))

    monkeypatch.setattr(api, "_embedding_client_from_settings", fake_embedding_client)
    monkeypatch.setattr(api, "_active_llm_client", lambda _request: MagicMock())
    monkeypatch.setattr(api, "_rebuild_loop", lambda _request, _client, _embedding_client=None: None)

    result = asyncio.run(api.config_embedding_update(EmbeddingConfigRequest(
        mode="openai_compatible",
        model="text-embedding-test",
        api_key="runtime-embedding-secret",
        base_url="https://provider.example/v1",
    ), request))

    assert captured["settings"]["api_key"] == "runtime-embedding-secret"
    assert request.app.state.embedding_runtime_config["model"] == "text-embedding-test"
    assert result["ENTITY_EMBEDDING_API_KEY"] == "runtim...secret"
    assert result["source"] == "runtime"
    assert os.environ.get("ENTITY_EMBEDDING_API_KEY") is None


def test_embedding_test_endpoint_returns_dimension(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        embedding_error=None,
    )))

    class FakeEmbeddingClient:
        enabled = True
        model = "mock-embedding"

        def embed(self, text: str) -> list[float]:
            assert text == "hello"
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr(api, "_active_embedding_client", lambda _request: FakeEmbeddingClient())

    result = asyncio.run(api.config_embedding_test(EmbeddingTestRequest(text="hello"), request))

    assert result["status"] == "ok"
    assert result["dimension"] == 3
    assert result["model"] == "mock-embedding"


def test_embedding_test_endpoint_rejects_disabled(monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        embedding_error=None,
    )))

    class DisabledEmbeddingClient:
        enabled = False
        model = None

    monkeypatch.setattr(api, "_active_embedding_client", lambda _request: DisabledEmbeddingClient())

    try:
        asyncio.run(api.config_embedding_test(EmbeddingTestRequest(text="hello"), request))
    except api.HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("disabled embedding client should fail")


def test_memory_preview_returns_current_session_material(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES (?)", ("current",))
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action, expression_output
        ) VALUES (?, 'user', ?, '[]', 'respond_openly', ?)
        """,
        ("current", "你记住这句话", "我看到了。"),
    )
    conn.commit()
    conn.close()

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        db_path=db_path,
        session_id="current",
    )))

    result = asyncio.run(api.memory_preview(request, query="你记得吗"))

    assert result["session_id"] == "current"
    assert result["results"]
    assert "你记住这句话" in result["results"][0]["content"]
    assert "managed_influence" in result


def test_managed_memory_commit_preview_archive_restore_api(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id, session_type) VALUES (?, ?)", ("current", "test"))
    conn.commit()

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        db_path=db_path,
        session_id="current",
        prompts_dir=api._prompts_dir(),
        embedding_runtime_config=None,
        embedding_error=None,
    )))

    committed = asyncio.run(api.managed_memory_commit(
        request,
        ManagedMemoryCommitRequest(operations=[{
            "operation": "add",
            "content": "Visitor returns to memory continuity questions.",
            "topics": ["memory"],
            "source_turn_ids": [1],
        }]),
    ))
    memory_id = committed["committed"][0]["memory_id"]

    preview = asyncio.run(api.managed_memory_preview_influence(
        request,
        MemoryInfluencePreviewRequest(query="memory", context={}),
    ))
    assert preview["results"]

    asyncio.run(api.managed_memory_archive(request, memory_id))
    rows = asyncio.run(api.managed_memory_list(request, status="active"))
    assert rows["rows"] == []

    asyncio.run(api.managed_memory_restore(request, memory_id))
    explained = asyncio.run(api.managed_memory_explain(request, memory_id))
    assert explained["memory"]["status"] == "active"

    asyncio.run(api.managed_memory_update(
        request,
        memory_id,
        ManagedMemoryUpdateRequest(patch={"topics": ["memory", "continuity"]}),
    ))
    assert conn.execute("SELECT COUNT(*) AS cnt FROM memory_operation_log").fetchone()["cnt"] >= 3
    conn.close()


def test_managed_memory_proposal_reject_prevents_commit(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id, session_type) VALUES (?, ?)", ("current", "test"))
    cursor = conn.execute(
        """
        INSERT INTO memory_operation_proposals (
            session_id, operation_type, operation_json, reason, source_turn_ids, status
        ) VALUES (?, 'add', ?, 'manual test', '[1]', 'pending')
        """,
        ("current", '{"operation":"add","content":"should not commit"}'),
    )
    proposal_id = int(cursor.lastrowid)
    conn.commit()

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        db_path=db_path,
        session_id="current",
        prompts_dir=api._prompts_dir(),
        embedding_runtime_config=None,
        embedding_error=None,
    )))

    rejected = asyncio.run(api.managed_memory_proposal_reject(request, proposal_id))
    assert rejected["status"] == "rejected"

    committed = asyncio.run(api.managed_memory_commit(
        request,
        ManagedMemoryCommitRequest(proposal_ids=[proposal_id]),
    ))
    assert committed["committed"] == []
    assert conn.execute("SELECT COUNT(*) AS cnt FROM managed_memories").fetchone()["cnt"] == 0
    assert conn.execute(
        "SELECT status FROM memory_operation_proposals WHERE id = ?",
        (proposal_id,),
    ).fetchone()["status"] == "rejected"
    conn.close()


def test_curation_can_hide_memory_and_copy_to_exhibition(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id, session_type) VALUES (?, ?)", ("test-session", "test"))
    conn.execute(
        """
        INSERT INTO episodic_memories (
            session_id, event_type, content, raw_text, salience, metadata
        ) VALUES (?, 'memory_continuity_query', ?, ?, 0.8, '{}')
        """,
        ("test-session", "curatable memory", "curatable memory"),
    )
    conn.commit()
    memory_id = conn.execute("SELECT id FROM episodic_memories").fetchone()["id"]

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        conn=conn,
        db_path=db_path,
    )))

    hidden = asyncio.run(api.curation_memory_status(
        request,
        "episodic",
        memory_id,
        MemoryStatusRequest(status="hidden"),
    ))
    assert hidden["status"] == "hidden"
    assert conn.execute(
        "SELECT memory_status FROM episodic_memories WHERE id = ?",
        (memory_id,),
    ).fetchone()["memory_status"] == "hidden"

    copied = asyncio.run(api.curation_copy_to_exhibition(request, "episodic", memory_id))
    assert copied["status"] == "copied"
    target = conn.execute(
        "SELECT session_id, memory_status, curated_from_session_id, curated_from_memory_id FROM episodic_memories WHERE id = ?",
        (copied["target_memory_id"],),
    ).fetchone()
    assert target["session_id"] == "curated-exhibition"
    assert target["memory_status"] == "active"
    assert target["curated_from_session_id"] == "test-session"
    assert target["curated_from_memory_id"] == memory_id
    assert conn.execute(
        "SELECT session_type FROM sessions WHERE id = 'curated-exhibition'"
    ).fetchone()["session_type"] == "exhibition"
    conn.close()
