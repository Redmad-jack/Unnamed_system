from __future__ import annotations

import json
import os
import sqlite3
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, Request

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.audio import AudioConfig, AudioManager
from conscious_entity.interfaces.api_models import EmbeddingConfigRequest, LLMConfigRequest
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeConfigurationError
from conscious_entity.llm.embedding_client import EmbeddingClient, EmbeddingConfigurationError
from conscious_entity.memory.managed import build_memory_provider
from conscious_entity.runtime_env import load_project_env
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_store import StateStore
from conscious_entity.vision import VisionConfig, VisionManager


def _project_root() -> Path:
    # api_runtime.py is at src/conscious_entity/interfaces/api_runtime.py.
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


@asynccontextmanager
async def lifespan(app: Any):
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
        conn,
        session_id,
        configs,
        prompts_dir,
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
    app.state.vision_manager = VisionManager(VisionConfig.from_env())
    app.state.vision_event_task = asyncio.create_task(_vision_event_dispatcher(app))
    app.state.audio_manager = AudioManager(AudioConfig.from_env())

    try:
        yield
    finally:
        if getattr(app.state, "loop", None) is not None:
            app.state.loop.close(wait_for_background=True)
        app.state.vision_event_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.vision_event_task
        app.state.vision_manager.stop()
        conn.close()


async def _run_dialog_turn(request: Request, text: str, *, source: str = "dialog"):
    loop = request.app.state.loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Loop not initialised")

    async with request.app.state.loop_lock:
        output = await asyncio.get_running_loop().run_in_executor(
            None,
            loop.run_turn,
            text,
            source,
        )

    manager = getattr(request.app.state, "vision_manager", None)
    if manager is not None:
        manager.mark_activity()

    return output


async def _vision_event_dispatcher(app: Any) -> None:
    """Forward vision presence events into the existing loop rule path."""
    while True:
        manager = getattr(app.state, "vision_manager", None)
        if manager is not None:
            for event_type in manager.pop_pending_events():
                loop = getattr(app.state, "loop", None)
                if loop is None:
                    continue
                async with app.state.loop_lock:
                    await asyncio.get_running_loop().run_in_executor(
                        None, loop.handle_system_event, event_type
                    )
        await asyncio.sleep(0.2)


def _read_conn(request: Request) -> sqlite3.Connection:
    """Open a separate read-only connection so API queries don't block the loop."""
    conn = sqlite3.connect(str(request.app.state.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "embedding" in d and isinstance(d["embedding"], bytes):
        d["embedding"] = None
    return d


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
    old_loop = getattr(request.app.state, "loop", None)
    if old_loop is not None:
        old_loop.close(wait_for_background=True)
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
