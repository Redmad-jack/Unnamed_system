from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from conscious_entity.core.config_loader import load_all_configs
from conscious_entity.interfaces.api_models import (
    DialogRequest,
    EmbeddingConfigRequest,
    EmbeddingTestRequest,
    LLMConfigRequest,
    ManagedMemoryCommitRequest,
    ManagedMemoryProposeRequest,
    ManagedMemoryUpdateRequest,
    MemoryInfluencePreviewRequest,
    MemoryStatusRequest,
    SessionTypeRequest,
)
from conscious_entity.interfaces.api_runtime import (
    _active_embedding_client,
    _active_llm_client,
    _blank_to_none,
    _client_from_settings,
    _conversation_export_payload,
    _curation_query_episodic,
    _curation_query_reflective,
    _curation_table,
    _curation_text,
    _embedding_client_from_settings,
    _embedding_settings_from_request,
    _env_embedding_config,
    _env_llm_config,
    _json_dict,
    _llm_settings_from_request,
    _log_curation,
    _managed_provider,
    _public_embedding_config,
    _public_llm_config,
    _read_conn,
    _rebuild_loop,
    _row_to_dict,
    _save_initial_state,
    _session_type,
    _static_dir,
    _validate_memory_status,
    _validate_memory_type,
)
from conscious_entity.llm.claude_client import ClaudeConfigurationError
from conscious_entity.llm.embedding_client import EmbeddingConfigurationError
from conscious_entity.llm.stats_tracker import get_tracker
from conscious_entity.memory.models import MemoryOperationProposal
from conscious_entity.memory.retrieval import MemoryRetriever
from conscious_entity.memory.vector import encode_embedding
from conscious_entity.vision import VisionConfigurationError


router = APIRouter()


@router.get("/", include_in_schema=False)
async def dashboard():
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(html_path), media_type="text/html")


@router.get("/visitor", include_in_schema=False)
async def visitor_surface():
    html_path = _static_dir() / "visitor.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Visitor surface not found")
    return FileResponse(str(html_path), media_type="text/html")


@router.get("/health")
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


@router.post("/api/v1/dialog")
async def dialog(body: DialogRequest, request: Request):
    loop = request.app.state.loop
    if loop is None:
        raise HTTPException(status_code=503, detail="Loop not initialised")

    try:
        async with request.app.state.loop_lock:
            output = await asyncio.get_running_loop().run_in_executor(
                None, loop.run_turn, body.text
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    manager = getattr(request.app.state, "vision_manager", None)
    if manager is not None:
        manager.mark_activity()

    return {
        "text": output.text,
        "delay_ms": output.delay_ms,
        "visual_mode": output.visual_mode,
        "truncated": output.truncated,
        "stop_reason": output.stop_reason,
    }


@router.get("/api/v1/vision/status")
async def vision_status(request: Request):
    manager = getattr(request.app.state, "vision_manager", None)
    if manager is None:
        return {"enabled": False, "running": False, "error": "Vision runtime not initialised"}
    return manager.status()


@router.post("/api/v1/vision/start")
async def vision_start(request: Request):
    manager = getattr(request.app.state, "vision_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Vision runtime not initialised")
    try:
        return manager.start()
    except VisionConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/v1/vision/stop")
async def vision_stop(request: Request):
    manager = getattr(request.app.state, "vision_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Vision runtime not initialised")
    manager.stop()
    return manager.status()


@router.websocket("/api/v1/vision/stream")
async def vision_stream(websocket: WebSocket):
    await websocket.accept()
    manager = getattr(websocket.app.state, "vision_manager", None)
    if manager is None:
        await websocket.send_json({"type": "error", "error": "Vision runtime not initialised"})
        await websocket.close(code=1011)
        return

    try:
        while True:
            metadata, jpeg = manager.stream_snapshot()
            await websocket.send_json(metadata)
            if jpeg is not None:
                await websocket.send_bytes(jpeg)
            await asyncio.sleep(1 / max(1, manager.config.fps))
    except WebSocketDisconnect:
        return


@router.get("/api/v1/sessions")
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


@router.post("/api/v1/sessions/reset")
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


@router.get("/api/v1/sessions/current/type")
async def session_type_current(request: Request):
    return {
        "session_id": request.app.state.session_id,
        "session_type": _session_type(request.app.state.conn, request.app.state.session_id),
    }


@router.post("/api/v1/sessions/current/type")
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


@router.get("/api/v1/sessions/{session_id}/conversation")
async def session_conversation(request: Request, session_id: str, limit: int = 1000):
    return _conversation_export_payload(request, limit=limit, session_id=session_id)


@router.get("/api/v1/sessions/{session_id}/memory/episodic")
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


@router.get("/api/v1/sessions/{session_id}/memory/reflective")
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


@router.get("/api/v1/state")
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


@router.get("/api/v1/state/history")
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


@router.get("/api/v1/memory/episodic")
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


@router.get("/api/v1/memory/reflective")
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


@router.get("/api/v1/memory/preview")
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


@router.get("/api/v1/managed-memory")
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


@router.post("/api/v1/managed-memory/proposals")
async def managed_memory_propose(request: Request, body: ManagedMemoryProposeRequest):
    provider = _managed_provider(request)
    proposals = provider.propose(body.messages, body.context)
    return {"proposals": [proposal.to_public_dict() for proposal in proposals]}


@router.get("/api/v1/managed-memory/proposals")
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


@router.post("/api/v1/managed-memory/proposals/{proposal_id}/reject")
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


@router.post("/api/v1/managed-memory/commit")
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


@router.post("/api/v1/managed-memory/preview-influence")
async def managed_memory_preview_influence(request: Request, body: MemoryInfluencePreviewRequest):
    conn = _read_conn(request)
    try:
        provider = _managed_provider(request, conn)
        return provider.preview_influence(body.query, body.context)
    finally:
        conn.close()


@router.get("/api/v1/managed-memory/influence-log")
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


@router.patch("/api/v1/managed-memory/{memory_id}")
async def managed_memory_update(request: Request, memory_id: int, body: ManagedMemoryUpdateRequest):
    return _managed_provider(request).update(memory_id, body.patch)


@router.post("/api/v1/managed-memory/{memory_id}/archive")
async def managed_memory_archive(request: Request, memory_id: int):
    return _managed_provider(request).archive(memory_id)


@router.post("/api/v1/managed-memory/{memory_id}/restore")
async def managed_memory_restore(request: Request, memory_id: int):
    return _managed_provider(request).restore(memory_id)


@router.get("/api/v1/managed-memory/{memory_id}/explain")
async def managed_memory_explain(request: Request, memory_id: int):
    try:
        return _managed_provider(request).explain(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="managed memory not found")


@router.get("/api/v1/curation/stats")
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


@router.get("/api/v1/curation/memories")
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


@router.post("/api/v1/curation/memories/{memory_type}/{memory_id}/status")
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


@router.post("/api/v1/curation/memories/{memory_type}/{memory_id}/copy-to-exhibition")
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


@router.post("/api/v1/curation/memories/{memory_type}/{memory_id}/embedding/refresh")
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


@router.get("/api/v1/interaction-log")
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


@router.get("/api/v1/conversation/export")
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


@router.get("/api/v1/config")
async def config_all(request: Request):
    return request.app.state.configs


@router.get("/api/v1/config/llm")
async def config_llm(request: Request):
    return _public_llm_config(request)


@router.post("/api/v1/config/llm")
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


@router.get("/api/v1/config/embedding")
async def config_embedding(request: Request):
    return _public_embedding_config(request)


@router.post("/api/v1/config/embedding")
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


@router.post("/api/v1/config/embedding/test")
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


@router.post("/api/v1/config/reload")
async def config_reload(request: Request):
    """
    Reload all YAML config files and reinitialise the InteractionLoop.
    Short-term memory (in-memory deque) is reset.
    """
    config_dir = request.app.state.config_dir
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
        request.app.state.conn = conn
        request.app.state.session_id = session_id
        _rebuild_loop(request, llm_client, embedding_client)

    return {"status": "reloaded", "note": "short-term memory was restored from the current session"}


@router.get("/api/v1/stats/llm")
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
