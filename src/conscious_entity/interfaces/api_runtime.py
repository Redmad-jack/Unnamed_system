from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import HTTPException, Request

from conscious_entity.body import BodyMotionController, BodySerialBridge, BodyTelemetryStore
from conscious_entity.body.motion import MacroMode
from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.connection import get_connection
from conscious_entity.db.migrations import run_migrations
from conscious_entity.audio import AudioConfig, AudioManager
from conscious_entity.identity import (
    ConfidenceLevel,
    FaceIdentityError,
    FaceIdentityConfig,
    FaceIdentityManager,
    IdentityGatingConfig,
    IdentityMatchResult,
    IdentitySignatureReference,
    SessionDecision,
    VisitorSessionGatingController,
)
from conscious_entity.interfaces.api_models import EmbeddingConfigRequest, LLMConfigRequest
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeConfigurationError
from conscious_entity.llm.embedding_client import EmbeddingClient, EmbeddingConfigurationError
from conscious_entity.memory.managed import build_memory_provider
from conscious_entity.runtime_env import load_project_env
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_store import StateStore
from conscious_entity.vision import VisionConfig, VisionManager


logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # api_runtime.py is at src/conscious_entity/interfaces/api_runtime.py.
    return Path(__file__).parent.parent.parent.parent


def _config_dir() -> Path:
    env = os.getenv("ENTITY_CONFIG_DIR")
    return Path(env) if env else _project_root() / "config"


def _body_motion_profiles_path() -> Path:
    return _config_dir() / "body_motion_profiles.yaml"


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

    if str(db) != ":memory:":
        db.parent.mkdir(parents=True, exist_ok=True)
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
        visitor_id=_session_visitor_id(conn, session_id),
    )

    app.state.loop = loop
    app.state.conn = conn
    app.state.session_id = session_id
    app.state.visitor_id = _session_visitor_id(conn, session_id)
    app.state.identity_gating = VisitorSessionGatingController(
        session_id=session_id,
        primary_visitor_id=app.state.visitor_id,
    )
    app.state.configs = configs
    app.state.config_dir = config_dir
    app.state.prompts_dir = prompts_dir
    app.state.db_path = db
    app.state.loop_lock = asyncio.Lock()
    app.state.first_unit_gate_enabled = _first_unit_gate_default(configs)
    app.state.llm_runtime_config = None
    app.state.embedding_runtime_config = None
    app.state.vision_manager = VisionManager(VisionConfig.from_env())
    app.state.face_identity_manager = FaceIdentityManager(
        FaceIdentityConfig(signature_dir=_project_root() / "data" / "signatures" / "face")
    )
    app.state.vision_event_task = asyncio.create_task(_vision_event_dispatcher(app))
    app.state.audio_manager = AudioManager(AudioConfig.from_env())
    app.state.body_telemetry = BodyTelemetryStore()
    app.state.body_bridge = BodySerialBridge(app.state.body_telemetry)
    app.state.body_motion = BodyMotionController.from_config(
        _body_motion_profiles_path(),
        telemetry=app.state.body_telemetry,
        bridge=app.state.body_bridge,
    )

    try:
        yield
    finally:
        public_session_manager = getattr(app.state, "public_session_manager", None)
        if public_session_manager is not None:
            await public_session_manager.close_all()
        if getattr(app.state, "body_bridge", None) is not None:
            await app.state.body_bridge.disconnect()
        if getattr(app.state, "loop", None) is not None:
            app.state.loop.close(wait_for_background=True)
        app.state.vision_event_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.vision_event_task
        app.state.vision_manager.stop()
        conn.close()


async def _run_dialog_turn(
    request: Request,
    text: str,
    *,
    source: str = "dialog",
    input_metadata: dict[str, Any] | None = None,
):
    async with request.app.state.loop_lock:
        turn_metadata = dict(input_metadata or {})
        if hasattr(request.app.state, "first_unit_gate_enabled"):
            turn_metadata["first_unit_gate_enabled"] = bool(request.app.state.first_unit_gate_enabled)
        input_mode = str(turn_metadata.get("input_mode") or "text")
        identity_controller = getattr(request.app.state, "identity_gating", None)
        if identity_controller is not None:
            try:
                _apply_natural_identity_confirmation_locked(
                    request,
                    text,
                    turn_metadata,
                )
                turn_metadata["identity_session"] = identity_controller.before_turn(
                    source=source,
                    input_mode=input_mode,
                    text=text,
                    metadata=turn_metadata,
                )
                if hasattr(request.app.state, "conn"):
                    _enrich_identity_context_locked(
                        request.app.state.conn,
                        turn_metadata["identity_session"],
                    )
            except Exception as exc:
                logger.error("Identity/session gating failed; continuing turn: %s", exc)
                turn_metadata["identity_session"] = {
                    "runtime_state": "unknown",
                    "session_decision": "continue_unidentified",
                    "identity_status": "unidentified",
                    "error": "identity_gating_failed",
                }
        use_unscoped_grace = _identity_context_requires_unscoped_grace(
            turn_metadata.get("identity_session")
        )
        if not use_unscoped_grace:
            capture_context = await _run_pre_turn_face_identity_capture_locked(
                request,
                source="pre_turn",
            )
            if capture_context is not None:
                turn_metadata["identity_pre_turn_capture"] = capture_context
                identity_context = capture_context.get("identity_session")
                if (
                    capture_context.get("action") in {"candidate_pending", "auto_provisioned"}
                    and isinstance(identity_context, dict)
                ):
                    turn_metadata["identity_session"] = identity_context
        loop = (
            _ensure_unscoped_grace_loop_locked(request)
            if use_unscoped_grace
            else request.app.state.loop
        )
        if loop is None:
            raise HTTPException(status_code=503, detail="Loop not initialised")
        output = await asyncio.get_running_loop().run_in_executor(
            None,
            loop.run_turn,
            text,
            source,
            turn_metadata,
        )

    manager = getattr(request.app.state, "vision_manager", None)
    if manager is not None:
        manager.mark_activity()
    if not use_unscoped_grace:
        _maybe_schedule_background_face_capture(request.app)
    _maybe_schedule_body_motion(request.app, output, source=source)

    return output


async def _run_dialog_turn_progressive(
    request: Request,
    text: str,
    *,
    source: str = "dialog_progressive",
    input_metadata: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    event_loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async with request.app.state.loop_lock:
        turn_metadata = dict(input_metadata or {})
        if hasattr(request.app.state, "first_unit_gate_enabled"):
            turn_metadata["first_unit_gate_enabled"] = bool(request.app.state.first_unit_gate_enabled)
        input_mode = str(turn_metadata.get("input_mode") or "text")
        identity_controller = getattr(request.app.state, "identity_gating", None)
        if identity_controller is not None:
            try:
                _apply_natural_identity_confirmation_locked(
                    request,
                    text,
                    turn_metadata,
                )
                turn_metadata["identity_session"] = identity_controller.before_turn(
                    source=source,
                    input_mode=input_mode,
                    text=text,
                    metadata=turn_metadata,
                )
                if hasattr(request.app.state, "conn"):
                    _enrich_identity_context_locked(
                        request.app.state.conn,
                        turn_metadata["identity_session"],
                    )
            except Exception as exc:
                logger.error("Identity/session gating failed; continuing turn: %s", exc)
                turn_metadata["identity_session"] = {
                    "runtime_state": "unknown",
                    "session_decision": "continue_unidentified",
                    "identity_status": "unidentified",
                    "error": "identity_gating_failed",
                }
        use_unscoped_grace = _identity_context_requires_unscoped_grace(
            turn_metadata.get("identity_session")
        )
        if not use_unscoped_grace:
            capture_context = await _run_pre_turn_face_identity_capture_locked(
                request,
                source="pre_turn",
            )
            if capture_context is not None:
                turn_metadata["identity_pre_turn_capture"] = capture_context
                identity_context = capture_context.get("identity_session")
                if (
                    capture_context.get("action") in {"candidate_pending", "auto_provisioned"}
                    and isinstance(identity_context, dict)
                ):
                    turn_metadata["identity_session"] = identity_context
        loop = (
            _ensure_unscoped_grace_loop_locked(request)
            if use_unscoped_grace
            else request.app.state.loop
        )
        if loop is None:
            raise HTTPException(status_code=503, detail="Loop not initialised")

        def progress_callback(event: dict[str, Any]) -> None:
            event_loop.call_soon_threadsafe(queue.put_nowait, dict(event))

        future = event_loop.run_in_executor(
            None,
            loop.run_turn,
            text,
            source,
            turn_metadata,
            progress_callback,
        )

        try:
            while True:
                if future.done() and queue.empty():
                    await asyncio.sleep(0)
                    if queue.empty():
                        break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                yield event

            output = await future
            manager = getattr(request.app.state, "vision_manager", None)
            if manager is not None:
                manager.mark_activity()
            if not use_unscoped_grace:
                _maybe_schedule_background_face_capture(request.app)
            motion_decision = _maybe_schedule_body_motion(request.app, output, source=source)
            plan = output.response_plan.to_dict() if output.response_plan is not None else None
            yield {
                "phase": "final",
                "text": (
                    output.response_plan.second_unit
                    if output.response_plan is not None
                    else output.text
                ),
                "response_plan": plan,
                "delay_ms": output.delay_ms,
                "visual_mode": output.visual_mode,
                "vocal_marker": output.vocal_marker,
                "body_action": output.body_action,
                "truncated": output.truncated,
                "stop_reason": output.stop_reason,
                "latency_record_id": output.latency_record_id,
                "motion_decision": motion_decision,
                "done": True,
            }
        finally:
            await _wait_for_turn_future(future)


async def _wait_for_turn_future(future: asyncio.Future) -> None:
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            continue
        except Exception:
            return
    try:
        future.result()
    except Exception:
        return


def _apply_natural_identity_confirmation_locked(
    request: Request,
    text: str,
    turn_metadata: dict[str, Any],
) -> None:
    controller = getattr(request.app.state, "identity_gating", None)
    if controller is None:
        return
    if not hasattr(controller, "status"):
        return
    if hasattr(controller, "expire_pending_candidate_if_needed"):
        controller.expire_pending_candidate_if_needed()
    status_payload = controller.status()
    status = status_payload.get("status") if isinstance(status_payload, dict) else None
    if not isinstance(status, dict) or not status.get("waiting_for_identity_confirmation"):
        return

    candidate = _blank_to_none(status.get("candidate_visitor_id"))
    candidate_display_name = (
        _visitor_display_name(request.app.state.conn, candidate)
        if candidate is not None and hasattr(request.app.state, "conn")
        else None
    )
    decision = _parse_identity_confirmation(
        text,
        candidate_display_name=candidate_display_name,
        candidate_visitor_id=candidate,
    )
    if decision is None:
        context = controller.record_natural_confirmation(
            status="unclear",
            text=text,
            candidate_visitor_id=candidate,
        )
        turn_metadata["identity_natural_confirmation"] = "unclear"
        turn_metadata["identity_session_pending_before_turn"] = context
        return

    accepted = decision == "accepted"
    context = controller.confirm_candidate(accepted)
    controller.record_natural_confirmation(
        status=decision,
        text=text,
        candidate_visitor_id=candidate,
    )
    confirmation = context.get("confirmation_state") or {}
    visitor_id = context.get("primary_visitor_id") or confirmation.get("candidate_visitor_id")
    if visitor_id:
        _update_visitor_identity_metadata(
            request.app.state.conn,
            str(visitor_id),
            {"confirmation_state": confirmation},
        )
        request.app.state.conn.commit()
    if accepted and context.get("primary_visitor_id"):
        _bind_current_visitor_locked(request, str(context["primary_visitor_id"]))
    turn_metadata["identity_natural_confirmation"] = decision
    turn_metadata["identity_session_pending_before_turn"] = context


def _bind_current_visitor_locked(request: Request, visitor_id: str) -> None:
    llm_client = _active_llm_client(request)
    embedding_client = _active_embedding_client(request)
    request.app.state.conn.execute(
        "UPDATE sessions SET visitor_id = ? WHERE id = ?",
        (visitor_id, request.app.state.session_id),
    )
    request.app.state.conn.commit()
    request.app.state.visitor_id = visitor_id
    _rebuild_loop(request, llm_client, embedding_client)


def _identity_context_requires_unscoped_grace(context: Any) -> bool:
    if not isinstance(context, dict):
        return False
    return (
        context.get("session_decision") == SessionDecision.CONTINUE_UNSCOPED.value
        or context.get("visitor_scope_mode") == "unscoped_grace"
    )


def _ensure_unscoped_grace_loop_locked(request: Request) -> Any:
    app = request.app
    loop = getattr(app.state, "unscoped_grace_loop", None)
    session_id = getattr(app.state, "unscoped_grace_session_id", None)
    if loop is not None and session_id:
        return loop

    conn = app.state.conn
    current_session_id = app.state.session_id
    session_id = str(uuid.uuid4())
    current_type = _session_type(conn, current_session_id)
    conn.execute(
        "INSERT INTO sessions (id, session_type, visitor_id, notes) VALUES (?, ?, NULL, ?)",
        (
            session_id,
            current_type,
            "Temporary unscoped session while the primary visitor is in leave grace.",
        ),
    )
    conn.commit()
    if isinstance(getattr(app.state, "configs", None), dict) and "entity_profile" in app.state.configs:
        _save_initial_state(conn, session_id, app.state.configs)

    try:
        llm_client = _active_llm_client(request)
        embedding_client = _active_embedding_client(request)
    except ClaudeConfigurationError as exc:
        app.state.llm_error = str(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    loop = InteractionLoop(
        conn,
        session_id,
        app.state.configs,
        app.state.prompts_dir,
        llm_client=llm_client,
        embedding_client=embedding_client,
        visitor_id=None,
    )
    app.state.unscoped_grace_session_id = session_id
    app.state.unscoped_grace_loop = loop
    return loop


async def _run_pre_turn_face_identity_capture_locked(
    request: Request,
    *,
    source: str,
) -> dict[str, Any] | None:
    app = request.app
    controller = getattr(app.state, "identity_gating", None)
    manager = getattr(app.state, "face_identity_manager", None)
    vision = getattr(app.state, "vision_manager", None)
    if controller is None or manager is None or vision is None:
        return None
    if not _identity_capture_routing_allowed(app):
        return None
    frame = vision.latest_frame_jpeg()
    if frame is None:
        controller.record_face_capture_diagnostic(
            in_flight=False,
            rejection_reason="no_vision_frame",
            source=source,
        )
        return {
            "action": "no_frame",
            "source": source,
            "identity_session": controller.status().get("status", {}),
        }
    outcome = await asyncio.get_running_loop().run_in_executor(
        None,
        manager.capture_and_match,
        frame,
    )
    return _apply_face_capture_identity_locked(
        request,
        manager,
        outcome,
        source=source,
        apply_to_gating=True,
    )


def _apply_face_capture_identity_locked(
    request: Request,
    manager: Any,
    outcome: Any,
    *,
    source: str,
    apply_to_gating: bool = True,
) -> dict[str, Any]:
    controller = getattr(request.app.state, "identity_gating", None)
    if controller is None:
        return {"action": "identity_disabled", "source": source}
    action = "ignored"
    context: dict[str, Any] | None = None
    result = getattr(outcome, "match_result", None)
    routing_allowed = _identity_capture_routing_allowed(request.app)
    if apply_to_gating and getattr(outcome, "accepted", False) and routing_allowed:
        if (
            result is not None
            and result.candidate_visitor_id is not None
            and result.combined_level in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}
        ):
            context = controller.apply_identity_match(result)
            action = "candidate_pending"
            if _identity_match_should_persist(result):
                _update_visitor_identity_metadata(
                    request.app.state.conn,
                    result.candidate_visitor_id,
                    {
                        "latest_match": result.to_public_dict(),
                        "confirmation_state": context.get("confirmation_state", {}),
                    },
                )
                request.app.state.conn.commit()
        elif not _has_ambiguous_known_face_cluster(manager, outcome):
            provisioned = _provision_new_face_visitor_locked(
                request,
                manager,
                outcome,
                source=source,
            )
            if provisioned is not None:
                action = provisioned.get("action", "auto_provisioned")
                context = provisioned.get("identity_session")
    elif apply_to_gating and getattr(outcome, "accepted", False):
        action = "routing_blocked"
    controller.record_face_capture_diagnostic(
        in_flight=False,
        accepted=getattr(outcome, "accepted", False),
        rejection_reason=None if getattr(outcome, "accepted", False) else getattr(outcome, "reason", None),
        source=source,
    )
    if context is None:
        status = controller.status().get("status", {})
        if isinstance(status, dict):
            context = dict(status)
            if hasattr(request.app.state, "conn"):
                _enrich_identity_context_locked(request.app.state.conn, context)
    return {
        "action": action,
        "source": source,
        "capture": outcome.to_public_dict() if hasattr(outcome, "to_public_dict") else None,
        "identity_session": context,
    }


def _provision_new_face_visitor_locked(
    request: Request,
    manager: Any,
    outcome: Any,
    *,
    source: str,
) -> dict[str, Any] | None:
    app = request.app
    if not _new_face_visitor_provision_allowed(app, outcome):
        return None
    try:
        llm_client = _active_llm_client(request)
        embedding_client = _active_embedding_client(request)
    except ClaudeConfigurationError as exc:
        app.state.llm_error = str(exc)
        logger.error("Could not provision new face visitor before loop rebuild: %s", exc)
        return {"action": "provision_failed", "reason": str(exc)}

    conn = app.state.conn
    visitor_id = f"visitor-{uuid.uuid4().hex[:12]}"
    initial_capture = (
        outcome.capture.to_public_dict()
        if getattr(outcome, "capture", None) is not None
        else None
    )
    identity_metadata = {
        "schema_version": 1,
        "auto_provisioned": True,
        "provisioned_source": source,
        "provisioned_at": datetime.now(timezone.utc).isoformat(),
        "initial_capture": initial_capture,
    }
    _ensure_visitor_profile(
        conn,
        visitor_id,
        metadata={"identity": identity_metadata},
    )
    try:
        capture = getattr(outcome, "capture", None)
        if hasattr(manager, "enroll_capture"):
            signature = manager.enroll_capture(visitor_id, capture)
        else:
            signature = manager.enroll_pending(visitor_id)
    except FaceIdentityError as exc:
        _update_visitor_identity_metadata(
            conn,
            visitor_id,
            {
                **identity_metadata,
                "provision_failed": True,
                "provision_failure_reason": str(exc),
            },
        )
        conn.commit()
        logger.error("Could not enroll auto-provisioned face visitor: %s", exc)
        return {"action": "provision_failed", "visitor_id": visitor_id, "reason": str(exc)}

    try:
        _append_visitor_identity_signature(conn, visitor_id, signature)
        cursor = conn.execute(
            "UPDATE sessions SET visitor_id = ? WHERE id = ? AND visitor_id IS NULL",
            (visitor_id, app.state.session_id),
        )
        if cursor.rowcount <= 0:
            raise RuntimeError("current session is no longer unidentified")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        failed_signature = None
        with suppress(Exception):
            failed_signature = manager.deactivate_signature(
                visitor_id=visitor_id,
                signature_id=signature.signature_id,
            )
        failure_patch = {
            **identity_metadata,
            "provision_failed": True,
            "provision_failure_reason": str(exc),
        }
        if failed_signature is not None:
            failure_patch["signatures"] = {
                "face": [failed_signature.to_public_dict()],
            }
        _update_visitor_identity_metadata(
            conn,
            visitor_id,
            failure_patch,
        )
        conn.commit()
        logger.error("Could not bind auto-provisioned face visitor: %s", exc)
        return {"action": "provision_failed", "visitor_id": visitor_id, "reason": str(exc)}

    app.state.visitor_id = visitor_id
    identity_controller = getattr(app.state, "identity_gating", None)
    if identity_controller is not None:
        identity_controller.set_primary_visitor(visitor_id)
    _rebuild_loop(request, llm_client, embedding_client)
    app.state.llm_error = None
    status = identity_controller.status().get("status", {}) if identity_controller else {}
    if isinstance(status, dict) and hasattr(app.state, "conn"):
        _enrich_identity_context_locked(app.state.conn, status)
        status.update({
            "session_decision": SessionDecision.VISITOR_BOUND.value,
            "visitor_scope_mode": "primary",
            "visitor_memory_allowed": True,
        })
    return {
        "action": "auto_provisioned",
        "visitor_id": visitor_id,
        "signature": signature.to_public_dict(),
        "identity_session": status,
    }


def _identity_capture_routing_allowed(app: Any) -> bool:
    controller = getattr(app.state, "identity_gating", None)
    if controller is None:
        return False
    if getattr(app.state, "visitor_id", None) is not None:
        return False
    if _session_visitor_id(app.state.conn, app.state.session_id) is not None:
        return False
    status_payload = controller.status()
    status = status_payload.get("status") if isinstance(status_payload, dict) else None
    if not isinstance(status, dict):
        return False
    if status.get("primary_visitor_id"):
        return False
    if status.get("candidate_visitor_id") or status.get("waiting_for_identity_confirmation"):
        return False
    if status.get("visitor_scope_mode") == "unscoped_grace":
        return False
    return bool(
        status.get("intent_status") == "confirmed_by_input"
        or status.get("runtime_state") in {"in_dialogue", "identity_confirming"}
    )


def _new_face_visitor_provision_allowed(app: Any, outcome: Any) -> bool:
    if not _identity_capture_routing_allowed(app):
        return False
    if not getattr(outcome, "accepted", False):
        return False
    if getattr(outcome, "capture", None) is None:
        return False
    result = getattr(outcome, "match_result", None)
    if (
        result is not None
        and result.candidate_visitor_id is not None
        and result.combined_level in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}
    ):
        return False
    return True


def _has_ambiguous_known_face_cluster(manager: Any, outcome: Any) -> bool:
    matches = [
        item for item in getattr(outcome, "matches", []) or []
        if getattr(item, "visitor_id", None)
    ]
    if len(matches) < 2:
        return False
    config = getattr(manager, "gating_config", None) or IdentityGatingConfig()
    lower = float(config.medium_confidence_threshold) - 0.10
    upper = float(config.medium_confidence_threshold)
    near = [
        item for item in matches
        if lower <= float(getattr(item, "score", 0.0)) < upper
    ]
    if len({str(getattr(item, "visitor_id")) for item in near[:2]}) < 2:
        return False
    first, second = near[0], near[1]
    return abs(float(first.score) - float(second.score)) <= 0.06


def _parse_identity_confirmation(
    text: str,
    *,
    candidate_display_name: str | None = None,
    candidate_visitor_id: str | None = None,
) -> str | None:
    raw = str(text or "").strip().lower()
    compact = _normalize_identity_confirmation_text(raw)
    if not compact:
        return None
    if _is_explicit_identity_rejection(compact):
        return "rejected"
    if _looks_like_identity_question(raw, compact):
        return None
    if _is_explicit_identity_acceptance(
        compact,
        candidate_display_name=candidate_display_name,
        candidate_visitor_id=candidate_visitor_id,
    ):
        return "accepted"
    return None


def _normalize_identity_confirmation_text(text: str) -> str:
    without_punctuation = re.sub(r"[，。！？、,.!?;；:：\"'“”‘’（）()\[\]{}]", " ", text)
    return " ".join(without_punctuation.split())


def _squash_identity_confirmation_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _is_explicit_identity_rejection(compact: str) -> bool:
    reject_exact = {
        "不是",
        "不对",
        "不是我",
        "不是的",
        "不是本人",
        "no",
        "nope",
        "not me",
        "wrong person",
        "you are wrong",
    }
    return compact in reject_exact or "认错" in compact


def _looks_like_identity_question(raw: str, compact: str) -> bool:
    return (
        "?" in raw
        or "？" in raw
        or compact.endswith("吗")
        or "是不是" in compact
    )


def _is_explicit_identity_acceptance(
    compact: str,
    *,
    candidate_display_name: str | None,
    candidate_visitor_id: str | None,
) -> bool:
    squashed = _squash_identity_confirmation_text(compact)
    accept_exact = {
        "是我",
        "是的是我",
        "对是我",
        "对的是我",
        "没错是我",
        "就是我",
        "是本人",
        "是的是本人",
        "yesthatsme",
        "yesthatisme",
        "yesitisme",
        "thatsme",
        "thatstheone",
        "thatisme",
        "itisme",
    }
    if squashed in accept_exact:
        return True
    aliases = _candidate_identity_aliases(candidate_display_name, candidate_visitor_id)
    if not aliases:
        return False
    for prefix in ("我是", "我就是", "iam", "im"):
        if squashed.startswith(prefix) and squashed[len(prefix):] in aliases:
            return True
    return False


def _candidate_identity_aliases(
    candidate_display_name: str | None,
    candidate_visitor_id: str | None,
) -> set[str]:
    aliases: set[str] = set()
    for value in (candidate_display_name, candidate_visitor_id):
        cleaned = _blank_to_none(value)
        if cleaned is None:
            continue
        squashed = _squash_identity_confirmation_text(cleaned.lower())
        if squashed:
            aliases.add(squashed)
        if cleaned.lower().startswith("visitor-"):
            suffix = cleaned[8:]
            suffix_squashed = _squash_identity_confirmation_text(suffix.lower())
            if suffix_squashed:
                aliases.add(suffix_squashed)
    return aliases


def _maybe_schedule_body_motion(app: Any, output: Any, *, source: str) -> dict[str, Any] | None:
    controller = getattr(app.state, "body_motion", None)
    loop = getattr(app.state, "loop", None)
    if controller is None or loop is None:
        return None
    try:
        decision = controller.schedule_after_turn(
            state=loop.current_state,
            output=output,
            macro_mode=MacroMode.SPEECH_INTERACTION,
        )
        payload = decision.to_dict()
        payload["source"] = source
        return payload
    except Exception as exc:
        logger.error("Body motion scheduling failed; continuing turn: %s", exc)
        return {
            "macro_mode": MacroMode.SPEECH_INTERACTION.value,
            "body_action": getattr(output, "body_action", None),
            "intent": "NO_MOTION",
            "profile": "NO_MOTION",
            "track_policy": "display_only",
            "auto_enabled": False,
            "should_execute": False,
            "blocker": "motion_scheduler_error",
            "summary": str(exc),
            "source": source,
        }


def _enrich_identity_context_locked(
    conn: sqlite3.Connection,
    context: dict[str, Any] | None,
) -> None:
    if not isinstance(context, dict):
        return
    context["visitor_memory_allowed"] = (
        bool(context.get("primary_visitor_id"))
        and context.get("visitor_scope_mode") != "unscoped_grace"
    )
    candidate = _blank_to_none(context.get("candidate_visitor_id"))
    if candidate:
        display_name = _visitor_display_name(conn, candidate)
        if display_name:
            context["candidate_display_name"] = display_name
    primary = _blank_to_none(context.get("primary_visitor_id"))
    if primary:
        display_name = _visitor_display_name(conn, primary)
        if display_name:
            context["primary_display_name"] = display_name


def _visitor_display_name(conn: sqlite3.Connection, visitor_id: str) -> str | None:
    row = conn.execute(
        "SELECT display_name FROM visitor_profiles WHERE id = ?",
        (visitor_id,),
    ).fetchone()
    if row is None:
        return None
    value = row["display_name"] if isinstance(row, sqlite3.Row) else row[0]
    return str(value) if value else None


def _maybe_schedule_background_face_capture(app: Any) -> None:
    controller = getattr(app.state, "identity_gating", None)
    manager = getattr(app.state, "face_identity_manager", None)
    vision = getattr(app.state, "vision_manager", None)
    if controller is None or manager is None or vision is None:
        return
    status_payload = controller.status()
    if not _face_auto_capture_allowed(status_payload):
        return
    frame = vision.latest_frame_jpeg()
    if frame is None:
        controller.record_face_capture_diagnostic(
            in_flight=False,
            rejection_reason="no_vision_frame",
            source="auto",
        )
        return
    started, reason = manager.start_auto_capture()
    if not started:
        controller.record_face_capture_diagnostic(
            in_flight=(reason == "capture_in_flight"),
            source="auto",
        )
        return
    controller.record_face_capture_diagnostic(in_flight=True, source="auto")
    app.state.face_auto_capture_task = asyncio.create_task(
        _run_background_face_capture(app, frame)
    )


def _face_auto_capture_allowed(identity_status: dict[str, Any]) -> bool:
    status = identity_status.get("status") if isinstance(identity_status, dict) else None
    if not isinstance(status, dict):
        return False
    if status.get("primary_visitor_id"):
        return False
    if status.get("candidate_visitor_id") or status.get("waiting_for_identity_confirmation"):
        return False
    return (
        status.get("intent_status") == "confirmed_by_input"
        or status.get("runtime_state") in {"in_dialogue", "identity_confirming"}
    )


async def _run_background_face_capture(app: Any, frame: bytes) -> None:
    manager = getattr(app.state, "face_identity_manager", None)
    controller = getattr(app.state, "identity_gating", None)
    if manager is None or controller is None:
        return
    reason = "unknown"
    try:
        outcome = await asyncio.get_running_loop().run_in_executor(
            None,
            manager.capture_and_match,
            frame,
        )
        reason = outcome.reason
        async with app.state.loop_lock:
            _apply_face_capture_identity_locked(
                SimpleNamespace(app=app),
                manager,
                outcome,
                source="auto",
            )
    except Exception as exc:
        reason = str(exc)
        logger.error("Background face capture failed: %s", exc)
        with suppress(Exception):
            controller.record_face_capture_diagnostic(
                in_flight=False,
                rejection_reason=reason,
                source="auto",
            )
    finally:
        with suppress(Exception):
            manager.finish_auto_capture(reason)


async def _vision_event_dispatcher(app: Any) -> None:
    """Forward vision presence events into the existing loop rule path."""
    while True:
        manager = getattr(app.state, "vision_manager", None)
        if manager is not None:
            for event_type in manager.pop_pending_events():
                identity_controller = getattr(app.state, "identity_gating", None)
                if identity_controller is not None:
                    try:
                        identity_controller.handle_system_event(event_type)
                    except Exception as exc:
                        logger.error(
                            "Identity/session gating system event failed; continuing: %s",
                            exc,
                        )
                loop = getattr(app.state, "loop", None)
                if loop is None:
                    continue
                async with app.state.loop_lock:
                    await asyncio.get_running_loop().run_in_executor(
                        None, loop.handle_system_event, event_type
                    )
            identity_controller = getattr(app.state, "identity_gating", None)
            if identity_controller is not None and hasattr(manager, "person_tracking_status"):
                try:
                    handoff_context = identity_controller.update_primary_presence(
                        manager.person_tracking_status()
                    )
                except Exception as exc:
                    logger.error("Primary visitor presence tracking failed; continuing: %s", exc)
                else:
                    if handoff_context.get("primary_released"):
                        await _start_unidentified_session_after_primary_leave(
                            app,
                            handoff_context,
                        )
                    elif (
                        handoff_context.get("visitor_scope_mode") == "primary"
                        and handoff_context.get("primary_presence_status") == "present"
                    ):
                        await _archive_unscoped_grace_session_if_needed(
                            app,
                            reason="primary_returned_within_grace",
                        )
        await asyncio.sleep(0.2)


async def _start_unidentified_session_after_primary_leave(
    app: Any,
    handoff_context: dict[str, Any],
) -> None:
    if not handoff_context.get("primary_released"):
        return
    async with app.state.loop_lock:
        released_visitor_id = handoff_context.get("released_visitor_id")
        if released_visitor_id and getattr(app.state, "visitor_id", None) != released_visitor_id:
            return
        conn = app.state.conn
        old_session_id = app.state.session_id
        old_loop = getattr(app.state, "loop", None)
        pending_session_id = getattr(app.state, "unscoped_grace_session_id", None)
        pending_loop = getattr(app.state, "unscoped_grace_loop", None)
        new_session_id = pending_session_id or str(uuid.uuid4())
        current_type = _session_type(conn, old_session_id)
        request_like = SimpleNamespace(app=app)
        llm_client = None
        embedding_client = None
        if pending_loop is None:
            try:
                llm_client = _active_llm_client(request_like)
                embedding_client = _active_embedding_client(request_like)
            except ClaudeConfigurationError as exc:
                app.state.llm_error = str(exc)
                logger.error("Could not rebuild loop after primary handoff: %s", exc)
                return

        conn.execute(
            "UPDATE sessions SET ended_at = datetime('now') WHERE id = ? AND ended_at IS NULL",
            (old_session_id,),
        )
        if pending_session_id is not None:
            conn.execute(
                """
                UPDATE sessions
                SET visitor_id = NULL,
                    notes = COALESCE(notes || ' ', '') || ?
                WHERE id = ?
                """,
                ("Promoted after primary visitor left the tracked dialogue window.", new_session_id),
            )
        else:
            conn.execute(
                "INSERT INTO sessions (id, session_type, visitor_id, notes) VALUES (?, ?, NULL, ?)",
                (
                    new_session_id,
                    current_type,
                    "Started automatically after primary visitor left the tracked dialogue window.",
                ),
            )
        conn.commit()

        if (
            pending_session_id is None
            and isinstance(getattr(app.state, "configs", None), dict)
            and "entity_profile" in app.state.configs
        ):
            _save_initial_state(conn, new_session_id, app.state.configs)
        app.state.session_id = new_session_id
        app.state.visitor_id = None
        app.state.unscoped_grace_session_id = None
        app.state.unscoped_grace_loop = None
        identity_controller = getattr(app.state, "identity_gating", None)
        if identity_controller is not None:
            identity_controller.configure_session(
                session_id=new_session_id,
                primary_visitor_id=None,
                decision=SessionDecision.VISITOR_CLEARED,
            )
            if hasattr(identity_controller, "record_primary_release_session"):
                identity_controller.record_primary_release_session(new_session_id)
        if pending_loop is not None:
            if old_loop is not None:
                old_loop.close(wait_for_background=True)
            app.state.loop = pending_loop
        else:
            _rebuild_loop(request_like, llm_client, embedding_client)
        app.state.llm_error = None
        logger.info(
            "Primary visitor %s left; started unidentified session %s.",
            released_visitor_id,
            new_session_id,
        )


async def _archive_unscoped_grace_session_if_needed(app: Any, *, reason: str) -> None:
    async with app.state.loop_lock:
        session_id = getattr(app.state, "unscoped_grace_session_id", None)
        if not session_id or session_id == getattr(app.state, "session_id", None):
            return
        loop = getattr(app.state, "unscoped_grace_loop", None)
        app.state.conn.execute(
            """
            UPDATE sessions
            SET ended_at = datetime('now'),
                notes = COALESCE(notes || ' ', '') || ?
            WHERE id = ? AND ended_at IS NULL
            """,
            (f"Archived after {reason}.", session_id),
        )
        app.state.conn.commit()
        if loop is not None:
            loop.close(wait_for_background=True)
        app.state.unscoped_grace_session_id = None
        app.state.unscoped_grace_loop = None


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


def _session_visitor_id(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT visitor_id FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row:
        value = row["visitor_id"] if isinstance(row, sqlite3.Row) else row[0]
        return str(value) if value else None
    return None


def _visitor_row_to_public(row: sqlite3.Row | None, *, active: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None
    item = _row_to_dict(row)
    item["metadata"] = _redact_biometric_metadata(_json_dict(item.get("metadata")))
    item["active"] = active
    return item


def _ensure_visitor_profile(
    conn: sqlite3.Connection,
    visitor_id: str | None = None,
    *,
    display_name: str | None = None,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    cleaned = _blank_to_none(visitor_id) or f"visitor-{uuid.uuid4().hex[:12]}"
    existing = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        (cleaned,),
    ).fetchone()
    existing_metadata = (
        _json_dict(existing["metadata"] if isinstance(existing, sqlite3.Row) else existing[0])
        if existing
        else {}
    )
    merged_metadata = _deep_merge_dicts(existing_metadata, metadata or {})
    conn.execute(
        """
        INSERT INTO visitor_profiles (id, display_name, notes, last_seen_at, metadata)
        VALUES (?, ?, ?, datetime('now'), ?)
        ON CONFLICT(id) DO UPDATE SET
            display_name = COALESCE(excluded.display_name, visitor_profiles.display_name),
            notes = COALESCE(excluded.notes, visitor_profiles.notes),
            last_seen_at = datetime('now'),
            metadata = excluded.metadata
        """,
        (
            cleaned,
            _blank_to_none(display_name),
            _blank_to_none(notes),
            json.dumps(merged_metadata, ensure_ascii=False),
        ),
    )
    return cleaned


def _update_visitor_identity_metadata(
    conn: sqlite3.Connection,
    visitor_id: str,
    identity_patch: dict[str, Any],
) -> None:
    _ensure_visitor_profile(
        conn,
        visitor_id,
        metadata={
            "identity": {
                "schema_version": 1,
                **identity_patch,
            }
        },
    )


def _identity_match_should_persist(result: IdentityMatchResult) -> bool:
    return (
        result.candidate_visitor_id is not None
        and result.combined_level == ConfidenceLevel.HIGH
    )


def _append_visitor_identity_signature(
    conn: sqlite3.Connection,
    visitor_id: str,
    signature: IdentitySignatureReference,
) -> None:
    row = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        (visitor_id,),
    ).fetchone()
    existing_metadata = (
        _json_dict(row["metadata"] if isinstance(row, sqlite3.Row) else row[0])
        if row
        else {}
    )
    identity = existing_metadata.get("identity")
    if not isinstance(identity, dict):
        identity = {}
    signatures = identity.get("signatures")
    if not isinstance(signatures, dict):
        signatures = {}
    modality_items = signatures.get(signature.modality)
    if not isinstance(modality_items, list):
        modality_items = []
    modality_items = [item for item in modality_items if isinstance(item, dict)]
    modality_items.append(signature.to_public_dict())
    signatures[signature.modality] = modality_items
    identity.update({
        "schema_version": 1,
        "signatures": signatures,
    })
    _ensure_visitor_profile(conn, visitor_id, metadata={"identity": identity})


def _deactivate_visitor_identity_signature(
    conn: sqlite3.Connection,
    visitor_id: str,
    signature_id: str,
) -> None:
    row = conn.execute(
        "SELECT metadata FROM visitor_profiles WHERE id = ?",
        (visitor_id,),
    ).fetchone()
    if row is None:
        return
    existing_metadata = _json_dict(row["metadata"] if isinstance(row, sqlite3.Row) else row[0])
    identity = existing_metadata.get("identity")
    if not isinstance(identity, dict):
        return
    signatures = identity.get("signatures")
    if not isinstance(signatures, dict):
        return
    face_items = signatures.get("face")
    if not isinstance(face_items, list):
        return
    updated_items: list[dict[str, Any]] = []
    for item in face_items:
        if not isinstance(item, dict):
            continue
        updated = dict(item)
        if updated.get("signature_id") == signature_id:
            updated["status"] = "inactive"
            updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated_items.append(updated)
    signatures["face"] = updated_items
    identity["signatures"] = signatures
    _ensure_visitor_profile(conn, visitor_id, metadata={"identity": identity})


def _deep_merge_dicts(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _redact_biometric_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"face_embedding", "voice_embedding", "raw_audio", "raw_image", "face_crop"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_biometric_metadata(item)
        return redacted
    if isinstance(value, list):
        return [_redact_biometric_metadata(item) for item in value]
    return value


def _set_current_visitor(
    request: Request,
    visitor_id: str | None,
    *,
    display_name: str | None = None,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    conn = request.app.state.conn
    if visitor_id is None:
        conn.execute(
            "UPDATE sessions SET visitor_id = NULL WHERE id = ?",
            (request.app.state.session_id,),
        )
        conn.commit()
        request.app.state.visitor_id = None
        identity_controller = getattr(request.app.state, "identity_gating", None)
        if identity_controller is not None:
            identity_controller.set_primary_visitor(None)
        return None

    resolved = _ensure_visitor_profile(
        conn,
        visitor_id,
        display_name=display_name,
        notes=notes,
        metadata=metadata,
    )
    conn.execute(
        "UPDATE sessions SET visitor_id = ? WHERE id = ?",
        (resolved, request.app.state.session_id),
    )
    conn.commit()
    request.app.state.visitor_id = resolved
    identity_controller = getattr(request.app.state, "identity_gating", None)
    if identity_controller is not None:
        identity_controller.set_primary_visitor(resolved)
    return resolved


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


def _first_unit_gate_default(configs: dict[str, Any]) -> bool:
    profile = configs.get("entity_profile", {}) if isinstance(configs, dict) else {}
    gate = profile.get("first_unit_speech_gate", {}) if isinstance(profile, dict) else {}
    return bool(gate.get("default_enabled", False)) if isinstance(gate, dict) else False


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
        visitor_id=getattr(request.app.state, "visitor_id", None),
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
        visitor_id=getattr(request.app.state, "visitor_id", None),
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
