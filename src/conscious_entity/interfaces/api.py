"""
api.py — FastAPI developer interface for the Conscious Entity system.

Provides REST endpoints for dialog, state inspection, memory queries,
config management, and LLM statistics.

Start with:
    python scripts/start_api.py
    # or directly:
    uvicorn conscious_entity.interfaces.api:app --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeConfigurationError
from conscious_entity.llm.embedding_client import EmbeddingClient, EmbeddingConfigurationError
from conscious_entity.llm.stats_tracker import get_tracker
from conscious_entity.memory.managed import build_memory_provider
from conscious_entity.memory.models import MemoryOperationProposal
from conscious_entity.memory.retrieval import MemoryRetriever
from conscious_entity.memory.vector import encode_embedding
from conscious_entity.runtime_env import load_project_env
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_store import StateStore


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    # api.py is at src/conscious_entity/interfaces/api.py → 4 levels up = project root
    return Path(__file__).parent.parent.parent.parent


def _config_dir() -> Path:
    env = os.getenv("ENTITY_CONFIG_DIR")
    return Path(env) if env else _project_root() / "config"


def _prompts_dir() -> Path:
    return _project_root() / "prompts"


def _db_path() -> Path:
    return Path(os.getenv("ENTITY_DB_PATH", str(_project_root() / "data" / "memory.db")))


def _static_dir() -> Path:
    return Path(__file__).parent / "static"


def _resolve_session_id(conn: sqlite3.Connection) -> str:
    configured = os.getenv("ENTITY_SESSION_ID")
    if configured:
        return configured

    row = conn.execute(
        """
        SELECT id FROM sessions
        ORDER BY
            COALESCE(
                (SELECT MAX(turn_at) FROM interaction_log WHERE session_id = sessions.id),
                (SELECT MAX(recorded_at) FROM state_snapshots WHERE session_id = sessions.id),
                started_at
            ) DESC,
            started_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row:
        return str(row["id"] if isinstance(row, sqlite3.Row) else row[0])
    return "shared"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DialogRequest(BaseModel):
    text: str


class LLMConfigRequest(BaseModel):
    mode: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    auth_token: Optional[str] = None
    base_url: Optional[str] = None
    messages_endpoint: Optional[str] = None
    disable_system_proxy: Optional[bool] = None


class EmbeddingConfigRequest(BaseModel):
    mode: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    endpoint: Optional[str] = None


class EmbeddingTestRequest(BaseModel):
    text: str = "memory retrieval test"


class SessionTypeRequest(BaseModel):
    session_type: str


class MemoryStatusRequest(BaseModel):
    status: str


class ManagedMemoryProposeRequest(BaseModel):
    messages: list[dict]
    context: dict[str, Any] = {}


class ManagedMemoryCommitRequest(BaseModel):
    proposal_ids: list[int] = []
    operations: list[dict[str, Any]] = []


class ManagedMemoryUpdateRequest(BaseModel):
    patch: dict[str, Any]


class MemoryInfluencePreviewRequest(BaseModel):
    query: str
    context: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Lifespan — initialise the loop once on startup, close DB on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_project_env()

    config_dir = _config_dir()
    prompts_dir = _prompts_dir()
    db = _db_path()

    configs = load_all_configs(config_dir)

    conn = get_connection(db, check_same_thread=False)
    run_migrations(conn)

    session_id = _resolve_session_id(conn)
    conn.execute("INSERT OR IGNORE INTO sessions (id) VALUES (?)", (session_id,))
    conn.commit()

    try:
        llm_client = ClaudeClient()
        app.state.llm_error = None
    except ClaudeConfigurationError as exc:
        llm_client = None
        app.state.llm_error = str(exc)

    try:
        embedding_client = EmbeddingClient.from_env()
        app.state.embedding_error = None
    except EmbeddingConfigurationError as exc:
        embedding_client = None
        app.state.embedding_error = str(exc)

    loop = InteractionLoop(
        conn, session_id, configs, prompts_dir,
        llm_client=llm_client,
        embedding_client=embedding_client,
    )

    app.state.loop = loop
    app.state.conn = conn
    app.state.session_id = session_id
    app.state.configs = configs
    app.state.config_dir = config_dir
    app.state.prompts_dir = prompts_dir
    app.state.db_path = db
    app.state.loop_lock = asyncio.Lock()
    app.state.llm_runtime_config = None
    app.state.embedding_runtime_config = None

    yield

    conn.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Conscious Entity — Developer API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_conn(request: Request) -> sqlite3.Connection:
    """Open a separate read-only connection so API queries don't block the loop."""
    conn = sqlite3.connect(str(request.app.state.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _session_type(conn: sqlite3.Connection, session_id: str) -> str:
    row = conn.execute(
        "SELECT session_type FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row:
        value = row["session_type"] if isinstance(row, sqlite3.Row) else row[0]
        if value in {"test", "exhibition"}:
            return str(value)
    return "test"


def _redact(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    if len(v) <= 12:
        return "***"
    return v[:6] + "..." + v[-6:]


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _env_llm_config() -> dict[str, Any]:
    return {
        "model": os.getenv("ENTITY_LLM_MODEL"),
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "auth_token": os.getenv("ANTHROPIC_AUTH_TOKEN"),
        "base_url": os.getenv("ANTHROPIC_BASE_URL"),
        "messages_endpoint": os.getenv("ENTITY_LLM_MESSAGES_ENDPOINT"),
        "disable_system_proxy": _env_flag("ENTITY_LLM_DISABLE_SYSTEM_PROXY"),
    }


def _env_embedding_config() -> dict[str, Any]:
    return {
        "mode": os.getenv("ENTITY_EMBEDDING_MODE", "disabled"),
        "model": os.getenv("ENTITY_EMBEDDING_MODEL"),
        "api_key": os.getenv("ENTITY_EMBEDDING_API_KEY"),
        "base_url": os.getenv("ENTITY_EMBEDDING_BASE_URL"),
        "endpoint": os.getenv("ENTITY_EMBEDDING_ENDPOINT"),
    }


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _llm_mode(settings: dict[str, Any]) -> str:
    if settings.get("mode"):
        return str(settings["mode"])
    if settings.get("messages_endpoint"):
        return "custom_endpoint"
    if settings.get("auth_token"):
        return "supplier"
    if settings.get("api_key"):
        return "official"
    return "unconfigured"


def _public_llm_config(request: Request) -> dict[str, Any]:
    settings = getattr(request.app.state, "llm_runtime_config", None) or _env_llm_config()
    return {
        "mode": _llm_mode(settings),
        "source": "runtime" if getattr(request.app.state, "llm_runtime_config", None) else "env",
        "ANTHROPIC_API_KEY": _redact(settings.get("api_key")),
        "ANTHROPIC_AUTH_TOKEN": _redact(settings.get("auth_token")),
        "ANTHROPIC_BASE_URL": settings.get("base_url"),
        "ENTITY_LLM_MODEL": settings.get("model"),
        "ENTITY_LLM_MESSAGES_ENDPOINT": settings.get("messages_endpoint"),
        "ENTITY_LLM_DISABLE_SYSTEM_PROXY": str(bool(settings.get("disable_system_proxy"))).lower(),
        "error": getattr(request.app.state, "llm_error", None),
    }


def _public_embedding_config(request: Request) -> dict[str, Any]:
    settings = getattr(request.app.state, "embedding_runtime_config", None) or _env_embedding_config()
    return {
        "mode": settings.get("mode") or "disabled",
        "source": "runtime" if getattr(request.app.state, "embedding_runtime_config", None) else "env",
        "ENTITY_EMBEDDING_API_KEY": _redact(settings.get("api_key")),
        "ENTITY_EMBEDDING_BASE_URL": settings.get("base_url"),
        "ENTITY_EMBEDDING_MODEL": settings.get("model"),
        "ENTITY_EMBEDDING_ENDPOINT": settings.get("endpoint"),
        "error": getattr(request.app.state, "embedding_error", None),
    }


def _llm_settings_from_request(
    body: LLMConfigRequest,
    current: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    mode = _blank_to_none(body.mode)
    if mode not in {"official", "supplier", "custom_endpoint"}:
        raise HTTPException(status_code=400, detail="mode must be official, supplier, or custom_endpoint")

    defaults = current or _env_llm_config()
    settings = {
        "mode": mode,
        "model": _blank_to_none(body.model) or defaults.get("model"),
        "api_key": _blank_to_none(body.api_key),
        "auth_token": _blank_to_none(body.auth_token),
        "base_url": _blank_to_none(body.base_url),
        "messages_endpoint": _blank_to_none(body.messages_endpoint),
        "disable_system_proxy": (
            bool(body.disable_system_proxy)
            if body.disable_system_proxy is not None
            else bool(defaults.get("disable_system_proxy"))
        ),
    }

    if mode == "official":
        settings["api_key"] = settings["api_key"] or defaults.get("api_key")
        settings["base_url"] = settings["base_url"] or defaults.get("base_url")
        settings["auth_token"] = None
        settings["messages_endpoint"] = None
    elif mode == "supplier":
        settings["auth_token"] = settings["auth_token"] or defaults.get("auth_token")
        settings["base_url"] = settings["base_url"] or defaults.get("base_url")
        settings["api_key"] = None
        settings["messages_endpoint"] = None
    else:
        settings["api_key"] = settings["api_key"] or defaults.get("api_key")
        settings["auth_token"] = settings["auth_token"] or defaults.get("auth_token")
        settings["base_url"] = settings["base_url"] or defaults.get("base_url")
        settings["messages_endpoint"] = settings["messages_endpoint"] or defaults.get("messages_endpoint")

    return settings


def _client_from_settings(settings: dict[str, Any]) -> ClaudeClient:
    return ClaudeClient(
        model=settings.get("model"),
        api_key=settings.get("api_key"),
        auth_token=settings.get("auth_token"),
        base_url=settings.get("base_url"),
        messages_endpoint=settings.get("messages_endpoint"),
        disable_system_proxy=bool(settings.get("disable_system_proxy")),
        use_env=False,
    )


def _embedding_settings_from_request(
    body: EmbeddingConfigRequest,
    current: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    mode = _blank_to_none(body.mode)
    if mode not in {"disabled", "openai_compatible"}:
        raise HTTPException(status_code=400, detail="mode must be disabled or openai_compatible")

    defaults = current or _env_embedding_config()
    return {
        "mode": mode,
        "model": _blank_to_none(body.model) or defaults.get("model"),
        "api_key": _blank_to_none(body.api_key) or defaults.get("api_key"),
        "base_url": _blank_to_none(body.base_url) or defaults.get("base_url"),
        "endpoint": _blank_to_none(body.endpoint) or defaults.get("endpoint"),
    }


def _embedding_client_from_settings(settings: dict[str, Any]) -> EmbeddingClient:
    return EmbeddingClient(
        mode=settings.get("mode"),
        model=settings.get("model"),
        api_key=settings.get("api_key"),
        base_url=settings.get("base_url"),
        endpoint=settings.get("endpoint"),
        use_env=False,
    )


def _active_llm_client(request: Request) -> ClaudeClient:
    settings = getattr(request.app.state, "llm_runtime_config", None)
    if settings:
        return _client_from_settings(settings)
    return ClaudeClient()


def _active_embedding_client(request: Request) -> EmbeddingClient | None:
    settings = getattr(request.app.state, "embedding_runtime_config", None)
    try:
        if settings:
            return _embedding_client_from_settings(settings)
        return EmbeddingClient.from_env()
    except EmbeddingConfigurationError as exc:
        request.app.state.embedding_error = str(exc)
        return None


def _managed_provider(request: Request, conn: sqlite3.Connection | None = None):
    try:
        llm_client: ClaudeClient | None = _active_llm_client(request)
    except ClaudeConfigurationError:
        llm_client = None
    return build_memory_provider(
        conn or request.app.state.conn,
        request.app.state.session_id,
        llm_client=llm_client,
        embedding_client=_active_embedding_client(request),
        prompts_dir=getattr(request.app.state, "prompts_dir", _prompts_dir()),
    )


def _rebuild_loop(
    request: Request,
    llm_client: Optional[ClaudeClient],
    embedding_client: Optional[EmbeddingClient] = None,
) -> None:
    request.app.state.loop = InteractionLoop(
        request.app.state.conn,
        request.app.state.session_id,
        request.app.state.configs,
        request.app.state.prompts_dir,
        llm_client=llm_client,
        embedding_client=embedding_client,
    )


def _save_initial_state(conn: sqlite3.Connection, session_id: str, configs: dict[str, Any]) -> None:
    state = EntityState.from_dict(configs["entity_profile"]["initial_state"])
    StateStore(conn, session_id).save_snapshot(
        state,
        trigger_event_type="session_reset",
        policy_action="initial_state",
    )


def _conversation_export_payload(
    request: Request,
    limit: int = 1000,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, 5000))
    session_id = session_id or request.app.state.session_id
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM interaction_log
            WHERE session_id = ?
            ORDER BY turn_at ASC, id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    finally:
        conn.close()

    turns: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row)
        turns.append({
            "id": item.get("id"),
            "turn_at": item.get("turn_at"),
            "user_text": item.get("raw_text"),
            "entity_text": item.get("expression_output"),
            "event_types": _parse_json_list(item.get("event_types")),
            "policy_action": item.get("policy_action"),
            "delay_ms": item.get("delay_ms"),
            "visual_mode": item.get("visual_mode"),
            "state_snapshot_id": item.get("state_snapshot_id"),
        })

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "turn_count": len(turns),
        "turns": turns,
    }


def _parse_json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _validate_memory_type(memory_type: str) -> str:
    if memory_type not in {"episodic", "reflective"}:
        raise HTTPException(status_code=400, detail="memory_type must be episodic or reflective")
    return memory_type


def _validate_memory_status(status: str) -> str:
    if status not in {"active", "archived", "hidden"}:
        raise HTTPException(status_code=400, detail="status must be active, archived, or hidden")
    return status


def _curation_table(memory_type: str) -> str:
    return "episodic_memories" if _validate_memory_type(memory_type) == "episodic" else "reflective_summaries"


def _curation_text(row: sqlite3.Row, memory_type: str) -> str:
    if memory_type == "episodic":
        return f"{row['event_type']}: {row['content']}"
    return row["content"]


def _log_curation(
    conn: sqlite3.Connection,
    *,
    action: str,
    memory_type: str,
    memory_id: int,
    source_session_id: Optional[str] = None,
    target_session_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO memory_curation_log (
            action, memory_type, memory_id, source_session_id, target_session_id, details
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            memory_type,
            memory_id,
            source_session_id,
            target_session_id,
            json.dumps(details or {}, ensure_ascii=False),
        ),
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def dashboard():
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(html_path), media_type="text/html")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health(request: Request):
    db_ok = True
    try:
        c = _read_conn(request)
        c.execute("SELECT 1").fetchone()
        c.close()
    except Exception:
        db_ok = False

    llm_error = getattr(request.app.state, "llm_error", None)
    embedding_error = getattr(request.app.state, "embedding_error", None)
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "error",
        "llm": "error: " + llm_error if llm_error else "configured",
        "embedding": "error: " + embedding_error if embedding_error else "configured",
        "session_id": request.app.state.session_id,
        "session_type": _session_type(request.app.state.conn, request.app.state.session_id),
    }


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

@app.post("/api/v1/dialog")
async def dialog(body: DialogRequest, request: Request):
    loop: InteractionLoop = request.app.state.loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Loop not initialised")

    try:
        async with request.app.state.loop_lock:
            output = await asyncio.get_running_loop().run_in_executor(
                None, loop.run_turn, body.text
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "text": output.text,
        "delay_ms": output.delay_ms,
        "visual_mode": output.visual_mode,
        "truncated": output.truncated,
        "stop_reason": output.stop_reason,
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/api/v1/sessions")
async def sessions(request: Request):
    current = request.app.state.session_id
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.started_at,
                s.ended_at,
                s.session_type,
                s.notes,
                (SELECT COUNT(*) FROM interaction_log WHERE session_id = s.id) AS turn_count,
                (SELECT COUNT(*) FROM episodic_memories WHERE session_id = s.id) AS memory_count,
                (SELECT COUNT(*) FROM reflective_summaries WHERE session_id = s.id) AS reflection_count,
                (SELECT MAX(turn_at) FROM interaction_log WHERE session_id = s.id) AS latest_turn_at
            FROM sessions s
            ORDER BY COALESCE(latest_turn_at, s.started_at) DESC, s.started_at DESC
            """
        ).fetchall()
        return [
            {
                **_row_to_dict(row),
                "active": row["id"] == current,
            }
            for row in rows
        ]
    finally:
        conn.close()


@app.post("/api/v1/sessions/reset")
async def sessions_reset(request: Request):
    conn = request.app.state.conn
    old_session_id = request.app.state.session_id
    new_session_id = str(uuid.uuid4())
    current_type = _session_type(conn, old_session_id)

    async with request.app.state.loop_lock:
        try:
            llm_client = _active_llm_client(request)
            embedding_client = _active_embedding_client(request)
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        conn.execute(
            "UPDATE sessions SET ended_at = datetime('now') WHERE id = ? AND ended_at IS NULL",
            (old_session_id,),
        )
        conn.execute(
            "INSERT INTO sessions (id, session_type) VALUES (?, ?)",
            (new_session_id, current_type),
        )
        conn.commit()

        request.app.state.session_id = new_session_id
        _save_initial_state(conn, new_session_id, request.app.state.configs)
        request.app.state.llm_error = None
        _rebuild_loop(request, llm_client, embedding_client)

    return {
        "status": "reset",
        "archived_session_id": old_session_id,
        "session_id": new_session_id,
        "session_type": current_type,
    }


@app.get("/api/v1/sessions/current/type")
async def session_type_current(request: Request):
    return {
        "session_id": request.app.state.session_id,
        "session_type": _session_type(request.app.state.conn, request.app.state.session_id),
    }


@app.post("/api/v1/sessions/current/type")
async def session_type_update(body: SessionTypeRequest, request: Request):
    session_type = _blank_to_none(body.session_type)
    if session_type not in {"test", "exhibition"}:
        raise HTTPException(status_code=400, detail="session_type must be test or exhibition")

    async with request.app.state.loop_lock:
        try:
            llm_client = _active_llm_client(request)
            embedding_client = _active_embedding_client(request)
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        request.app.state.conn.execute(
            "UPDATE sessions SET session_type = ? WHERE id = ?",
            (session_type, request.app.state.session_id),
        )
        request.app.state.conn.commit()
        _rebuild_loop(request, llm_client, embedding_client)

    return {
        "session_id": request.app.state.session_id,
        "session_type": session_type,
    }


@app.get("/api/v1/sessions/{session_id}/conversation")
async def session_conversation(request: Request, session_id: str, limit: int = 1000):
    return _conversation_export_payload(request, limit=limit, session_id=session_id)


@app.get("/api/v1/sessions/{session_id}/memory/episodic")
async def session_memory_episodic(request: Request, session_id: str, limit: int = 100):
    limit = max(1, min(limit, 500))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM episodic_memories
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/sessions/{session_id}/memory/reflective")
async def session_memory_reflective(request: Request, session_id: str):
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM reflective_summaries
            WHERE session_id = ? AND active = 1
            ORDER BY created_at DESC, id DESC
            """,
            (session_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@app.get("/api/v1/state")
async def state_current(request: Request):
    conn = _read_conn(request)
    try:
        row = conn.execute(
            """
            SELECT * FROM state_snapshots
            WHERE session_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (request.app.state.session_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="No state snapshots yet")
        return _row_to_dict(row)
    finally:
        conn.close()


@app.get("/api/v1/state/history")
async def state_history(request: Request, limit: int = 20):
    limit = max(1, min(limit, 200))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM state_snapshots
            WHERE session_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (request.app.state.session_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@app.get("/api/v1/memory/episodic")
async def memory_episodic(request: Request, limit: int = 20):
    limit = max(1, min(limit, 100))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM episodic_memories
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (request.app.state.session_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/memory/reflective")
async def memory_reflective(request: Request):
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM reflective_summaries
            WHERE session_id = ? AND active = 1
            ORDER BY created_at DESC, id DESC
            """,
            (request.app.state.session_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/memory/preview")
async def memory_preview(request: Request, query: str, limit: int = 9):
    limit = max(1, min(limit, 20))
    conn = _read_conn(request)
    try:
        retriever = MemoryRetriever(
            conn,
            request.app.state.session_id,
            embedding_client=_active_embedding_client(request),
        )
        results = retriever.retrieve(query, events=[], limit=limit)
        influence = _managed_provider(request, conn).preview_influence(
            query,
            {"filters": {"session_type": _session_type(conn, request.app.state.session_id)}},
        )
        return {
            "session_id": request.app.state.session_id,
            "session_type": _session_type(conn, request.app.state.session_id),
            "query": query,
            "results": [item.to_public_dict() for item in results],
            "managed_influence": influence,
        }
    finally:
        conn.close()


@app.get("/api/v1/managed-memory")
async def managed_memory_list(
    request: Request,
    status: str = "active",
    session_type: Optional[str] = None,
    q: str = "",
    limit: int = 100,
):
    conn = _read_conn(request)
    try:
        provider = _managed_provider(request, conn)
        return {"rows": provider.get_all({
            "status": status,
            "session_type": session_type,
            "q": q,
            "limit": limit,
        })}
    finally:
        conn.close()


@app.post("/api/v1/managed-memory/proposals")
async def managed_memory_propose(request: Request, body: ManagedMemoryProposeRequest):
    provider = _managed_provider(request)
    proposals = provider.propose(body.messages, body.context)
    return {"proposals": [proposal.to_public_dict() for proposal in proposals]}


@app.get("/api/v1/managed-memory/proposals")
async def managed_memory_proposals(request: Request, status: str = "pending", limit: int = 100):
    limit = max(1, min(limit, 500))
    conn = _read_conn(request)
    try:
        where = ["session_id = ?"]
        params: list[Any] = [request.app.state.session_id]
        if status != "all":
            where.append("status = ?")
            params.append(status)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT * FROM memory_operation_proposals
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        proposals = [MemoryOperationProposal.from_row(row).to_public_dict() for row in rows]
        return {"proposals": proposals}
    finally:
        conn.close()


@app.post("/api/v1/managed-memory/proposals/{proposal_id}/reject")
async def managed_memory_proposal_reject(request: Request, proposal_id: int):
    conn = _read_conn(request)
    try:
        row = conn.execute(
            """
            SELECT id, status FROM memory_operation_proposals
            WHERE id = ? AND session_id = ?
            """,
            (proposal_id, request.app.state.session_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        if row["status"] != "pending":
            return {"proposal_id": proposal_id, "status": row["status"]}
        conn.execute(
            "UPDATE memory_operation_proposals SET status = 'rejected' WHERE id = ?",
            (proposal_id,),
        )
        conn.commit()
        return {"proposal_id": proposal_id, "status": "rejected"}
    finally:
        conn.close()


@app.post("/api/v1/managed-memory/commit")
async def managed_memory_commit(request: Request, body: ManagedMemoryCommitRequest):
    provider = _managed_provider(request)
    operations = [
        MemoryOperationProposal(
            operation=str(item.get("operation", "add")),
            memory_id=item.get("memory_id") if isinstance(item.get("memory_id"), int) else None,
            content=str(item.get("content", "")),
            patch=item.get("patch") if isinstance(item.get("patch"), dict) else {},
            reason=str(item.get("reason", "")),
            source_turn_ids=[
                int(value) for value in item.get("source_turn_ids", [])
                if isinstance(value, int) or str(value).isdigit()
            ],
            entities=[str(value) for value in item.get("entities", []) if str(value).strip()],
            topics=[str(value) for value in item.get("topics", []) if str(value).strip()],
            confidence=float(item.get("confidence", 0.5) or 0.5),
            scope=str(item.get("scope", "session")),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        )
        for item in body.operations
    ]
    return {"committed": provider.commit(proposal_ids=body.proposal_ids, operations=operations)}


@app.post("/api/v1/managed-memory/preview-influence")
async def managed_memory_preview_influence(request: Request, body: MemoryInfluencePreviewRequest):
    conn = _read_conn(request)
    try:
        provider = _managed_provider(request, conn)
        return provider.preview_influence(body.query, body.context)
    finally:
        conn.close()


@app.get("/api/v1/managed-memory/influence-log")
async def managed_memory_influence_log(request: Request, limit: int = 100):
    limit = max(1, min(limit, 500))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM memory_influence_log
            WHERE session_id = ?
            ORDER BY influenced_at DESC, id DESC
            LIMIT ?
            """,
            (request.app.state.session_id, limit),
        ).fetchall()
        return {"rows": [_row_to_dict(row) for row in rows]}
    finally:
        conn.close()


@app.patch("/api/v1/managed-memory/{memory_id}")
async def managed_memory_update(request: Request, memory_id: int, body: ManagedMemoryUpdateRequest):
    return _managed_provider(request).update(memory_id, body.patch)


@app.post("/api/v1/managed-memory/{memory_id}/archive")
async def managed_memory_archive(request: Request, memory_id: int):
    return _managed_provider(request).archive(memory_id)


@app.post("/api/v1/managed-memory/{memory_id}/restore")
async def managed_memory_restore(request: Request, memory_id: int):
    return _managed_provider(request).restore(memory_id)


@app.get("/api/v1/managed-memory/{memory_id}/explain")
async def managed_memory_explain(request: Request, memory_id: int):
    try:
        return _managed_provider(request).explain(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="managed memory not found")


# ---------------------------------------------------------------------------
# Memory Curation
# ---------------------------------------------------------------------------

@app.get("/api/v1/curation/stats")
async def curation_stats(request: Request):
    conn = _read_conn(request)
    try:
        rows: list[dict[str, Any]] = []
        for memory_type, table in (("episodic", "episodic_memories"), ("reflective", "reflective_summaries")):
            table_rows = conn.execute(
                f"""
                SELECT
                    ? AS memory_type,
                    s.session_type,
                    m.memory_status,
                    COUNT(*) AS count,
                    SUM(CASE WHEN m.embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_count
                FROM {table} m
                JOIN sessions s ON s.id = m.session_id
                GROUP BY s.session_type, m.memory_status
                ORDER BY s.session_type, m.memory_status
                """,
                (memory_type,),
            ).fetchall()
            rows.extend(_row_to_dict(row) for row in table_rows)
        return {"rows": rows}
    finally:
        conn.close()


@app.get("/api/v1/curation/memories")
async def curation_memories(
    request: Request,
    session_type: str = "test",
    memory_type: str = "episodic",
    status: str = "active",
    q: str = "",
    limit: int = 50,
):
    if session_type not in {"test", "exhibition"}:
        raise HTTPException(status_code=400, detail="session_type must be test or exhibition")
    if memory_type not in {"episodic", "reflective", "all"}:
        raise HTTPException(status_code=400, detail="memory_type must be episodic, reflective, or all")
    if status not in {"active", "archived", "hidden", "all"}:
        raise HTTPException(status_code=400, detail="status must be active, archived, hidden, or all")

    limit = max(1, min(limit, 200))
    conn = _read_conn(request)
    try:
        rows: list[dict[str, Any]] = []
        if memory_type in {"episodic", "all"}:
            rows.extend(_curation_query_episodic(conn, session_type, status, q, limit))
        if memory_type in {"reflective", "all"}:
            rows.extend(_curation_query_reflective(conn, session_type, status, q, limit))
        rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return {"rows": rows[:limit]}
    finally:
        conn.close()


def _curation_query_episodic(
    conn: sqlite3.Connection,
    session_type: str,
    status: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    where = ["s.session_type = ?"]
    params: list[Any] = [session_type]
    if status != "all":
        where.append("e.memory_status = ?")
        params.append(status)
    if query.strip():
        where.append("(e.content LIKE ? OR e.raw_text LIKE ? OR e.event_type LIKE ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like, like])
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            'episodic' AS memory_type,
            e.id,
            e.session_id,
            s.session_type,
            e.created_at,
            e.event_type,
            e.content,
            e.raw_text,
            e.salience,
            e.memory_status,
            e.embedding_model,
            CASE WHEN e.embedding IS NOT NULL THEN 1 ELSE 0 END AS has_embedding,
            e.curated_from_session_id,
            e.curated_from_memory_id,
            e.curated_at
        FROM episodic_memories e
        JOIN sessions s ON s.id = e.session_id
        WHERE {" AND ".join(where)}
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _curation_query_reflective(
    conn: sqlite3.Connection,
    session_type: str,
    status: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    where = ["s.session_type = ?"]
    params: list[Any] = [session_type]
    if status != "all":
        where.append("r.memory_status = ?")
        params.append(status)
    if query.strip():
        where.append("r.content LIKE ?")
        params.append(f"%{query.strip()}%")
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            'reflective' AS memory_type,
            r.id,
            r.session_id,
            s.session_type,
            r.created_at,
            NULL AS event_type,
            r.content,
            NULL AS raw_text,
            NULL AS salience,
            r.memory_status,
            r.embedding_model,
            CASE WHEN r.embedding IS NOT NULL THEN 1 ELSE 0 END AS has_embedding,
            r.curated_from_session_id,
            r.curated_from_memory_id,
            r.curated_at
        FROM reflective_summaries r
        JOIN sessions s ON s.id = r.session_id
        WHERE {" AND ".join(where)}
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


@app.post("/api/v1/curation/memories/{memory_type}/{memory_id}/status")
async def curation_memory_status(
    request: Request,
    memory_type: str,
    memory_id: int,
    body: MemoryStatusRequest,
):
    memory_type = _validate_memory_type(memory_type)
    status = _validate_memory_status(body.status)
    table = _curation_table(memory_type)
    conn = request.app.state.conn
    row = conn.execute(f"SELECT id, session_id FROM {table} WHERE id = ?", (memory_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="memory not found")

    conn.execute(f"UPDATE {table} SET memory_status = ? WHERE id = ?", (status, memory_id))
    _log_curation(
        conn,
        action=f"set_status:{status}",
        memory_type=memory_type,
        memory_id=memory_id,
        source_session_id=row["session_id"],
    )
    conn.commit()
    return {"status": status, "memory_type": memory_type, "memory_id": memory_id}


@app.post("/api/v1/curation/memories/{memory_type}/{memory_id}/copy-to-exhibition")
async def curation_copy_to_exhibition(request: Request, memory_type: str, memory_id: int):
    memory_type = _validate_memory_type(memory_type)
    source_table = _curation_table(memory_type)
    conn = request.app.state.conn
    source = conn.execute(f"SELECT * FROM {source_table} WHERE id = ?", (memory_id,)).fetchone()
    if source is None:
        raise HTTPException(status_code=404, detail="memory not found")

    target_session_id = "curated-exhibition"
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions (id, session_type, notes)
        VALUES (?, 'exhibition', 'Curated exhibition memory pool')
        """,
        (target_session_id,),
    )

    existing = conn.execute(
        f"""
        SELECT id FROM {source_table}
        WHERE session_id = ? AND curated_from_session_id = ? AND curated_from_memory_id = ?
        LIMIT 1
        """,
        (target_session_id, source["session_id"], source["id"]),
    ).fetchone()
    if existing:
        return {
            "status": "exists",
            "memory_type": memory_type,
            "source_memory_id": memory_id,
            "target_memory_id": existing["id"],
            "target_session_id": target_session_id,
        }

    if memory_type == "episodic":
        metadata = _json_dict(source["metadata"])
        metadata["curation"] = {
            "source_session_id": source["session_id"],
            "source_memory_id": source["id"],
            "source_memory_type": "episodic",
        }
        cursor = conn.execute(
            """
            INSERT INTO episodic_memories (
                session_id, event_type, content, raw_text, salience, state_snapshot_id,
                embedding, embedding_model, reflected, reflection_id, metadata,
                memory_status, curated_from_session_id, curated_from_memory_id, curated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 0, NULL, ?, 'active', ?, ?, datetime('now'))
            """,
            (
                target_session_id,
                source["event_type"],
                source["content"],
                source["raw_text"],
                source["salience"],
                source["embedding"],
                source["embedding_model"],
                json.dumps(metadata, ensure_ascii=False),
                source["session_id"],
                source["id"],
            ),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO reflective_summaries (
                session_id, content, source_event_ids, state_at_reflection,
                embedding, embedding_model, active, memory_status,
                curated_from_session_id, curated_from_memory_id, curated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, datetime('now'))
            """,
            (
                target_session_id,
                source["content"],
                source["source_event_ids"],
                source["state_at_reflection"],
                source["embedding"],
                source["embedding_model"],
                source["session_id"],
                source["id"],
            ),
        )

    target_memory_id = int(cursor.lastrowid)
    _log_curation(
        conn,
        action="copy_to_exhibition",
        memory_type=memory_type,
        memory_id=target_memory_id,
        source_session_id=source["session_id"],
        target_session_id=target_session_id,
        details={"source_memory_id": source["id"]},
    )
    conn.commit()
    return {
        "status": "copied",
        "memory_type": memory_type,
        "source_memory_id": memory_id,
        "target_memory_id": target_memory_id,
        "target_session_id": target_session_id,
    }


@app.post("/api/v1/curation/memories/{memory_type}/{memory_id}/embedding/refresh")
async def curation_refresh_embedding(request: Request, memory_type: str, memory_id: int):
    memory_type = _validate_memory_type(memory_type)
    table = _curation_table(memory_type)
    conn = request.app.state.conn
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (memory_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="memory not found")

    client = _active_embedding_client(request)
    if client is None or not client.enabled or not client.model:
        raise HTTPException(status_code=400, detail="Embedding client is disabled or misconfigured.")

    try:
        embedding = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: client.embed(_curation_text(row, memory_type)),
        )
    except Exception as exc:
        request.app.state.embedding_error = str(exc)
        raise HTTPException(status_code=400, detail=str(exc))

    conn.execute(
        f"UPDATE {table} SET embedding = ?, embedding_model = ? WHERE id = ?",
        (encode_embedding(embedding), client.model, memory_id),
    )
    _log_curation(
        conn,
        action="refresh_embedding",
        memory_type=memory_type,
        memory_id=memory_id,
        source_session_id=row["session_id"],
        details={"model": client.model},
    )
    conn.commit()
    request.app.state.embedding_error = None
    return {
        "status": "refreshed",
        "memory_type": memory_type,
        "memory_id": memory_id,
        "dimension": len(embedding),
        "model": client.model,
    }


# ---------------------------------------------------------------------------
# Interaction log
# ---------------------------------------------------------------------------

@app.get("/api/v1/interaction-log")
async def interaction_log(request: Request, limit: int = 20):
    limit = max(1, min(limit, 200))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            """
            SELECT * FROM interaction_log
            WHERE session_id = ?
            ORDER BY turn_at DESC, id DESC
            LIMIT ?
            """,
            (request.app.state.session_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/conversation/export")
async def conversation_export(
    request: Request,
    limit: int = 1000,
    download: bool = False,
    session_id: Optional[str] = None,
):
    payload = _conversation_export_payload(request, limit=limit, session_id=session_id)
    if not download:
        return payload

    filename = f"conversation-{payload['session_id'][:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.get("/api/v1/config")
async def config_all(request: Request):
    return request.app.state.configs


@app.get("/api/v1/config/llm")
async def config_llm(request: Request):
    return _public_llm_config(request)


@app.post("/api/v1/config/llm")
async def config_llm_update(body: LLMConfigRequest, request: Request):
    current = getattr(request.app.state, "llm_runtime_config", None) or _env_llm_config()
    settings = _llm_settings_from_request(body, current=current)
    async with request.app.state.loop_lock:
        try:
            llm_client = _client_from_settings(settings)
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        request.app.state.llm_runtime_config = settings
        request.app.state.llm_error = None
        _rebuild_loop(request, llm_client, _active_embedding_client(request))

    return _public_llm_config(request)


@app.get("/api/v1/config/embedding")
async def config_embedding(request: Request):
    return _public_embedding_config(request)


@app.post("/api/v1/config/embedding")
async def config_embedding_update(body: EmbeddingConfigRequest, request: Request):
    current = getattr(request.app.state, "embedding_runtime_config", None) or _env_embedding_config()
    settings = _embedding_settings_from_request(body, current=current)

    async with request.app.state.loop_lock:
        try:
            embedding_client = _embedding_client_from_settings(settings)
        except EmbeddingConfigurationError as exc:
            request.app.state.embedding_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        try:
            llm_client = _active_llm_client(request)
            request.app.state.llm_error = None
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        request.app.state.embedding_runtime_config = settings
        request.app.state.embedding_error = None
        _rebuild_loop(request, llm_client, embedding_client)

    return _public_embedding_config(request)


@app.post("/api/v1/config/embedding/test")
async def config_embedding_test(body: EmbeddingTestRequest, request: Request):
    client = _active_embedding_client(request)
    if client is None or not client.enabled:
        raise HTTPException(status_code=400, detail="Embedding client is disabled or misconfigured.")

    text = body.text.strip() or "memory retrieval test"
    start = time.perf_counter()
    try:
        vector = await asyncio.get_running_loop().run_in_executor(None, client.embed, text)
    except Exception as exc:
        request.app.state.embedding_error = str(exc)
        raise HTTPException(status_code=400, detail=str(exc))

    request.app.state.embedding_error = None
    return {
        "status": "ok",
        "dimension": len(vector),
        "model": client.model,
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
    }


@app.post("/api/v1/config/reload")
async def config_reload(request: Request):
    """
    Reload all YAML config files and reinitialise the InteractionLoop.
    Short-term memory (in-memory deque) is reset.
    """
    config_dir = request.app.state.config_dir
    prompts_dir = request.app.state.prompts_dir
    conn = request.app.state.conn
    session_id = request.app.state.session_id

    async with request.app.state.loop_lock:
        try:
            configs = load_all_configs(config_dir)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Config reload failed: {exc}")

        try:
            llm_client = _active_llm_client(request)
            embedding_client = _active_embedding_client(request)
            request.app.state.llm_error = None
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)
            raise HTTPException(status_code=400, detail=str(exc))

        request.app.state.configs = configs
        _rebuild_loop(request, llm_client, embedding_client)

    return {"status": "reloaded", "note": "short-term memory was restored from the current session"}


# ---------------------------------------------------------------------------
# LLM Stats
# ---------------------------------------------------------------------------

@app.get("/api/v1/stats/llm")
async def stats_llm(n: int = 50):
    tracker = get_tracker()
    summary = tracker.summary()
    recent = tracker.recent(n)
    return {
        "summary": summary,
        "recent": [
            {
                "timestamp": r.timestamp.isoformat(),
                "model": r.model,
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error": r.error,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
            }
            for r in recent
        ],
    }
