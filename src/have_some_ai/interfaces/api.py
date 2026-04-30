from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from conscious_entity.db.connection import get_connection
from conscious_entity.runtime_env import load_project_env, project_root
from have_some_ai.config import default_config_dir, load_have_some_ai_config
from have_some_ai.db import run_migrations
from have_some_ai.models import QueueStatus
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService


def _config_dir() -> Path:
    env = os.getenv("HAVE_SOME_AI_CONFIG_DIR")
    return Path(env) if env else default_config_dir(project_root())


def _db_path() -> Path:
    env = os.getenv("HAVE_SOME_AI_DB_PATH")
    return Path(env) if env else project_root() / "data" / "have_some_ai.db"


def _static_dir() -> Path:
    return Path(__file__).parent / "static"


class ParticipantCreateRequest(BaseModel):
    notes: str | None = None
    safety_flags: dict[str, Any] = Field(default_factory=dict)


class AnswerItem(BaseModel):
    question_id: str
    option_id: str


class AnswersRequest(BaseModel):
    answers: list[AnswerItem]
    assign_immediately: bool = True


class ObservationItem(BaseModel):
    event_type: str
    confidence: float = 1.0
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationsRequest(BaseModel):
    events: list[ObservationItem]


class QueueUpdateRequest(BaseModel):
    status: QueueStatus
    staff_notes: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_project_env()

    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path, check_same_thread=False)
    run_migrations(conn)

    configs = load_have_some_ai_config(_config_dir())
    question_bank = QuestionBank(configs["questions"])
    scoring_engine = ScoringEngine(configs["scoring"], question_bank)
    repository = MealRepository(conn)

    app.state.conn = conn
    app.state.configs = configs
    app.state.service = MealService(repository, question_bank, scoring_engine)
    app.state.db_path = db_path
    app.state.config_dir = _config_dir()

    yield

    conn.close()


app = FastAPI(
    title='Have Some "Ai"',
    version="0.1.0",
    lifespan=lifespan,
)


def _service(request: Request) -> MealService:
    return request.app.state.service


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sqlite3.Error):
        return HTTPException(status_code=500, detail=f"Database error: {exc}")
    return HTTPException(status_code=500, detail=str(exc))


def _model_data(model: BaseModel) -> dict[str, Any]:
    """Support both Pydantic v1 and v2 in local exhibition environments."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.get("/", include_in_schema=False)
async def dashboard():
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/health")
async def health(request: Request):
    try:
        request.app.state.conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "db": db_status,
        "db_path": str(request.app.state.db_path),
        "config_dir": str(request.app.state.config_dir),
    }


@app.get("/api/v1/config")
async def config(request: Request):
    return request.app.state.configs


@app.post("/api/v1/participants")
async def create_participant(body: ParticipantCreateRequest, request: Request):
    try:
        participant = _service(request).create_participant(
            notes=body.notes,
            safety_flags=body.safety_flags,
        )
        return participant.__dict__
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/participants")
async def list_participants(request: Request, limit: int = 50):
    try:
        return _service(request).list_participants(max(1, min(limit, 200)))
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/participants/{participant_id}")
async def participant_detail(participant_id: str, request: Request):
    try:
        return _service(request).participant_detail(participant_id)
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/questionnaire/start")
async def start_questionnaire(participant_id: str, request: Request):
    try:
        return {"questions": _service(request).start_questionnaire(participant_id)}
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/answers")
async def submit_answers(participant_id: str, body: AnswersRequest, request: Request):
    try:
        service = _service(request)
        service.submit_answers(
            participant_id,
            [_model_data(item) for item in body.answers],
        )
        response: dict[str, Any] = {"status": "answers_recorded"}
        if body.assign_immediately:
            assignment = service.assign_food(participant_id)
            response["assignment"] = assignment.__dict__
        return response
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/observations")
async def add_observations(participant_id: str, body: ObservationsRequest, request: Request):
    try:
        _service(request).add_observations(
            participant_id,
            [_model_data(item) for item in body.events],
        )
        return {"status": "observations_recorded"}
    except Exception as exc:
        raise _api_error(exc)


@app.post("/api/v1/participants/{participant_id}/assign")
async def assign_food(participant_id: str, request: Request):
    try:
        assignment = _service(request).assign_food(participant_id)
        return assignment.__dict__
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/staff-queue")
async def staff_queue(request: Request, limit: int = 100):
    try:
        return _service(request).list_staff_queue(max(1, min(limit, 300)))
    except Exception as exc:
        raise _api_error(exc)


@app.patch("/api/v1/staff-queue/{queue_item_id}")
async def update_queue_item(queue_item_id: int, body: QueueUpdateRequest, request: Request):
    try:
        _service(request).update_queue_item(queue_item_id, body.status, body.staff_notes)
        return {"status": "updated"}
    except Exception as exc:
        raise _api_error(exc)


@app.get("/api/v1/export")
async def export_all(request: Request):
    try:
        return _service(request).export_all()
    except Exception as exc:
        raise _api_error(exc)
