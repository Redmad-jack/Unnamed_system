"""
api.py — FastAPI developer interface for the Conscious Entity system.

This module keeps the public ASGI entrypoint stable:

    uvicorn conscious_entity.interfaces.api:app --reload

The implementation is split into:
    api_models.py   — request models
    api_runtime.py  — lifespan, runtime config, DB helpers
    api_routes.py   — HTTP route handlers
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from conscious_entity.interfaces.api_audio import (
    audio_dialog,
    audio_router,
    audio_status,
    audio_stt_stream,
    audio_tts_http_stream,
    audio_tts_ws_stream,
)
from conscious_entity.interfaces.api_models import (
    AudioDebugTTSRequest,
    AudioDialogRequest,
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
from conscious_entity.interfaces.api_routes import (
    config_all,
    config_embedding,
    config_embedding_test,
    config_embedding_update,
    config_llm,
    config_llm_update,
    config_reload,
    conversation_export,
    curation_copy_to_exhibition,
    curation_memories,
    curation_memory_status,
    curation_refresh_embedding,
    curation_stats,
    dashboard,
    dialog,
    health,
    harness_status,
    harness_trace_recent,
    interaction_log,
    managed_memory_archive,
    managed_memory_commit,
    managed_memory_explain,
    managed_memory_influence_log,
    managed_memory_list,
    managed_memory_preview_influence,
    managed_memory_proposal_reject,
    managed_memory_proposals,
    managed_memory_propose,
    managed_memory_restore,
    managed_memory_update,
    memory_episodic,
    memory_preview,
    memory_reflective,
    router,
    session_conversation,
    session_memory_episodic,
    session_memory_reflective,
    session_type_current,
    session_type_update,
    sessions,
    sessions_reset,
    state_current,
    state_history,
    stats_audio_latency,
    stats_latency,
    stats_llm,
    visitor_surface,
    vision_start,
    vision_status,
    vision_stop,
    vision_stream,
)
from conscious_entity.interfaces.api_runtime import (
    _active_embedding_client,
    _active_llm_client,
    _blank_to_none,
    _client_from_settings,
    _config_dir,
    _conversation_export_payload,
    _curation_query_episodic,
    _curation_query_reflective,
    _curation_table,
    _curation_text,
    _db_path,
    _embedding_client_from_settings,
    _embedding_settings_from_request,
    _env_embedding_config,
    _env_flag,
    _env_llm_config,
    _json_dict,
    _llm_mode,
    _llm_settings_from_request,
    _log_curation,
    _managed_provider,
    _project_root,
    _prompts_dir,
    _public_embedding_config,
    _public_llm_config,
    _read_conn,
    _rebuild_loop,
    _redact,
    _resolve_session_id,
    _row_to_dict,
    _save_initial_state,
    _session_type,
    _static_dir,
    _validate_memory_status,
    _validate_memory_type,
    lifespan,
)


app = FastAPI(
    title="Conscious Entity — Developer API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(audio_router)
app.mount("/static", StaticFiles(directory=str(_static_dir())), name="static")
