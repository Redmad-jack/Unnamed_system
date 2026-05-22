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


class PresentationLatencyRequest(BaseModel):
    kind: str
    duration_ms: float
    latency_record_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BodyBridgeConnectRequest(BaseModel):
    port: str
    baud: int = 115200


class BodyCommandRequest(BaseModel):
    command: str


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


class VisitorCreateRequest(BaseModel):
    visitor_id: Optional[str] = None
    display_name: Optional[str] = None
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisitorSelectRequest(BaseModel):
    visitor_id: Optional[str] = None


class VisionRuntimeConfigRequest(BaseModel):
    camera_index: int


class IdentityConfigRequest(BaseModel):
    auto_bind_high_confidence: Optional[bool] = None


class IdentityMatchSignalRequest(BaseModel):
    modality: Optional[str] = None
    candidate_visitor_id: Optional[str] = None
    score: Optional[float] = None
    level: Optional[str] = None
    quality_status: str = "unknown"
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityMatchRequest(BaseModel):
    candidate_visitor_id: Optional[str] = None
    face: Optional[IdentityMatchSignalRequest] = None
    voice: Optional[IdentityMatchSignalRequest] = None
    combined_score: Optional[float] = None
    combined_level: Optional[str] = None
    decision_hint: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityConfirmRequest(BaseModel):
    accepted: bool


class FaceCaptureRequest(BaseModel):
    apply_to_gating: bool = True


class FaceEnrollRequest(BaseModel):
    visitor_id: str


class FaceSignatureDeactivateRequest(BaseModel):
    visitor_id: str
    signature_id: str


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
