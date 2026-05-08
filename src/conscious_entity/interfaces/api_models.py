from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DialogRequest(BaseModel):
    text: str


class AudioDialogRequest(BaseModel):
    transcript: str
    audio_session_id: Optional[str] = None


class AudioDebugTTSRequest(BaseModel):
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
    messages: list[dict[str, Any]]
    context: dict[str, Any] = Field(default_factory=dict)


class ManagedMemoryCommitRequest(BaseModel):
    proposal_ids: list[int] = Field(default_factory=list)
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ManagedMemoryUpdateRequest(BaseModel):
    patch: dict[str, Any]


class MemoryInfluencePreviewRequest(BaseModel):
    query: str
    context: dict[str, Any] = Field(default_factory=dict)
