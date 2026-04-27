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
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeConfigurationError
from conscious_entity.llm.stats_tracker import get_tracker
from conscious_entity.runtime_env import load_project_env
from conscious_entity.shopkeeper.models import TurnInput


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


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DialogRequest(BaseModel):
    text: str = ""
    asr_text: Optional[str] = None
    visual_tags: list[str] = Field(default_factory=list)
    retrieved_context: list[str] = Field(default_factory=list)
    microphone: Optional[dict[str, Any]] = None


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

    session_id = str(uuid.uuid4())
    conn.execute("INSERT OR IGNORE INTO sessions (id) VALUES (?)", (session_id,))
    conn.commit()

    try:
        llm_client = ClaudeClient()
        app.state.llm_error = None
    except ClaudeConfigurationError as exc:
        llm_client = None
        app.state.llm_error = str(exc)

    loop = InteractionLoop(
        conn, session_id, configs, prompts_dir,
        llm_client=llm_client,
    )

    app.state.loop = loop
    app.state.conn = conn
    app.state.session_id = session_id
    app.state.configs = configs
    app.state.config_dir = config_dir
    app.state.prompts_dir = prompts_dir
    app.state.db_path = db
    app.state.loop_lock = asyncio.Lock()

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


def _turn_input_from_dialog(body: DialogRequest) -> TurnInput:
    return TurnInput(
        text=body.text,
        asr_text=body.asr_text,
        visual_tags=body.visual_tags,
        retrieved_context=body.retrieved_context,
        microphone=body.microphone,
    )


def _dialog_response(output, shop_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": output.text,
        "delay_ms": output.delay_ms,
        "visual_mode": output.visual_mode,
        "truncated": output.truncated,
        "stop_reason": output.stop_reason,
        "turn": output.turn,
        "shop_state": shop_state,
        "language": output.turn.get("language") if output.turn else shop_state["language"],
        "scene": output.turn.get("scene") if output.turn else shop_state["current_scene"],
        "action": output.turn.get("action") if output.turn else "none",
        "selected_soup": shop_state["selected_soup"],
        "order_status": shop_state["order_status"],
    }


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
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "error",
        "llm": "error: " + llm_error if llm_error else "configured",
        "session_id": request.app.state.session_id,
    }


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

@app.post("/api/v1/dialog")
async def dialog(body: DialogRequest, request: Request):
    loop: InteractionLoop = request.app.state.loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Loop not initialised")

    turn_input = _turn_input_from_dialog(body)
    if not turn_input.effective_text and not turn_input.visual_tags:
        raise HTTPException(status_code=400, detail="text, asr_text, or visual_tags is required")

    try:
        async with request.app.state.loop_lock:
            output = await asyncio.get_running_loop().run_in_executor(
                None, loop.run_turn, turn_input
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return _dialog_response(output, loop.current_shop_state.to_dict())


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@app.get("/api/v1/state")
async def state_current(request: Request):
    conn = _read_conn(request)
    try:
        row = conn.execute(
            "SELECT * FROM state_snapshots ORDER BY recorded_at DESC LIMIT 1"
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
            "SELECT * FROM state_snapshots ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
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
            "SELECT * FROM episodic_memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/v1/memory/reflective")
async def memory_reflective(request: Request):
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            "SELECT * FROM reflective_summaries WHERE active = 1 ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Interaction log
# ---------------------------------------------------------------------------

@app.get("/api/v1/interaction-log")
async def interaction_log(request: Request, limit: int = 20):
    limit = max(1, min(limit, 200))
    conn = _read_conn(request)
    try:
        rows = conn.execute(
            "SELECT * FROM interaction_log ORDER BY turn_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.get("/api/v1/config")
async def config_all(request: Request):
    return request.app.state.configs


@app.get("/api/v1/config/llm")
async def config_llm(request: Request):
    import os

    def _redact(v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if len(v) <= 12:
            return "***"
        return v[:6] + "..." + v[-6:]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    model = os.getenv("ENTITY_LLM_MODEL")
    endpoint = os.getenv("ENTITY_LLM_MESSAGES_ENDPOINT")
    disable_proxy = os.getenv("ENTITY_LLM_DISABLE_SYSTEM_PROXY")

    if endpoint:
        mode = "custom_endpoint"
    elif auth_token:
        mode = "supplier"
    elif api_key:
        mode = "official"
    else:
        mode = "unconfigured"

    return {
        "mode": mode,
        "ANTHROPIC_API_KEY": _redact(api_key),
        "ANTHROPIC_AUTH_TOKEN": _redact(auth_token),
        "ANTHROPIC_BASE_URL": base_url,
        "ENTITY_LLM_MODEL": model,
        "ENTITY_LLM_MESSAGES_ENDPOINT": endpoint,
        "ENTITY_LLM_DISABLE_SYSTEM_PROXY": disable_proxy,
        "error": getattr(request.app.state, "llm_error", None),
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

        llm_client: Optional[ClaudeClient] = None
        try:
            llm_client = ClaudeClient()
            request.app.state.llm_error = None
        except ClaudeConfigurationError as exc:
            request.app.state.llm_error = str(exc)

        loop = InteractionLoop(conn, session_id, configs, prompts_dir, llm_client=llm_client)
        request.app.state.loop = loop
        request.app.state.configs = configs

    return {"status": "reloaded", "note": "short-term memory was reset"}


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
