from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from conscious_entity.perception.event_types import EventType


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeDialogueState(str, Enum):
    IDLE = "idle"
    ENCOUNTER_CANDIDATE = "encounter_candidate"
    INTENT_CONFIRMING = "intent_confirming"
    IDENTIFYING = "identifying"
    IDENTITY_CONFIRMING = "identity_confirming"
    IN_DIALOGUE = "in_dialogue"
    INTERRUPTED = "interrupted"
    WATCHING = "watching"
    INTROSPECTING = "introspecting"


class SessionDecision(str, Enum):
    OBSERVE_ONLY = "observe_only"
    CONTINUE_CURRENT = "continue_current"
    CONTINUE_UNIDENTIFIED = "continue_unidentified"
    CONFIRM_CANDIDATE = "confirm_candidate"
    INTERRUPTION_RECORDED = "interruption_recorded"
    REFUSE_SWITCH = "refuse_switch"
    VISITOR_BOUND = "visitor_bound"
    VISITOR_CLEARED = "visitor_cleared"
    SESSION_RESET = "session_reset"


class ConfidenceLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class IdentityGatingConfig:
    auto_bind_high_confidence: bool = False
    high_confidence_threshold: float = 0.82
    medium_confidence_threshold: float = 0.62

    def level_for_score(self, score: float | None) -> ConfidenceLevel:
        if score is None:
            return ConfidenceLevel.NONE
        value = _clamp_score(score)
        if value >= self.high_confidence_threshold:
            return ConfidenceLevel.HIGH
        if value >= self.medium_confidence_threshold:
            return ConfidenceLevel.MEDIUM
        if value > 0.0:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "auto_bind_high_confidence": self.auto_bind_high_confidence,
            "high_confidence_threshold": self.high_confidence_threshold,
            "medium_confidence_threshold": self.medium_confidence_threshold,
        }


@dataclass(frozen=True)
class IdentitySignatureReference:
    modality: str
    signature_id: str
    provider: str
    reference: str
    quality_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    status: str = "active"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "signature_id": self.signature_id,
            "provider": self.provider,
            "reference": self.reference,
            "quality_summary": _public_metadata(self.quality_summary),
            "created_at": self.created_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class IdentityMatchSignal:
    modality: str
    candidate_visitor_id: str | None = None
    score: float | None = None
    level: ConfidenceLevel = ConfidenceLevel.NONE
    quality_status: str = "unknown"
    quality_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        modality: str,
        candidate_visitor_id: str | None = None,
        score: float | None = None,
        level: ConfidenceLevel | str | None = None,
        quality_status: str = "unknown",
        quality_summary: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        config: IdentityGatingConfig | None = None,
    ) -> IdentityMatchSignal:
        effective_config = config or IdentityGatingConfig()
        return cls(
            modality=modality,
            candidate_visitor_id=_blank_to_none(candidate_visitor_id),
            score=_clamp_score(score) if score is not None else None,
            level=_coerce_confidence_level(level)
            if level is not None
            else effective_config.level_for_score(score),
            quality_status=quality_status or "unknown",
            quality_summary=quality_summary or {},
            metadata=metadata or {},
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "candidate_visitor_id": self.candidate_visitor_id,
            "score": self.score,
            "level": self.level.value,
            "quality_status": self.quality_status,
            "quality_summary": _public_metadata(self.quality_summary),
            "metadata": _public_metadata(self.metadata),
        }


@dataclass(frozen=True)
class IdentityMatchResult:
    candidate_visitor_id: str | None = None
    face: IdentityMatchSignal | None = None
    voice: IdentityMatchSignal | None = None
    combined_score: float | None = None
    combined_level: ConfidenceLevel = ConfidenceLevel.NONE
    decision_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        candidate_visitor_id: str | None = None,
        face: IdentityMatchSignal | None = None,
        voice: IdentityMatchSignal | None = None,
        combined_score: float | None = None,
        combined_level: ConfidenceLevel | str | None = None,
        decision_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
        config: IdentityGatingConfig | None = None,
    ) -> IdentityMatchResult:
        effective_config = config or IdentityGatingConfig()
        resolved_candidate = _blank_to_none(candidate_visitor_id)
        if resolved_candidate is None:
            resolved_candidate = _first_present(
                face.candidate_visitor_id if face else None,
                voice.candidate_visitor_id if voice else None,
            )
        resolved_score = _resolve_combined_score(face, voice, combined_score)
        return cls(
            candidate_visitor_id=resolved_candidate,
            face=face,
            voice=voice,
            combined_score=resolved_score,
            combined_level=_coerce_confidence_level(combined_level)
            if combined_level is not None
            else effective_config.level_for_score(resolved_score),
            decision_hint=_blank_to_none(decision_hint),
            metadata=metadata or {},
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "candidate_visitor_id": self.candidate_visitor_id,
            "face": self.face.to_public_dict() if self.face else None,
            "voice": self.voice.to_public_dict() if self.voice else None,
            "combined_score": self.combined_score,
            "combined_level": self.combined_level.value,
            "decision_hint": self.decision_hint,
            "metadata": _public_metadata(self.metadata),
        }


@dataclass(frozen=True)
class IdentityGatingEvent:
    id: str
    timestamp: str
    kind: str
    decision: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "decision": self.decision,
            "summary": self.summary,
            "metadata": _public_metadata(self.metadata),
        }


@dataclass
class IdentitySessionStatus:
    session_id: str
    primary_visitor_id: str | None = None
    candidate_visitor_id: str | None = None
    runtime_state: RuntimeDialogueState = RuntimeDialogueState.IDLE
    encounter_status: str = "none"
    intent_status: str = "unconfirmed"
    identity_status: str = "unidentified"
    face_confidence_level: ConfidenceLevel = ConfidenceLevel.NONE
    voice_confidence_level: ConfidenceLevel = ConfidenceLevel.NONE
    combined_confidence_level: ConfidenceLevel = ConfidenceLevel.NONE
    waiting_for_identity_confirmation: bool = False
    interruption_count: int = 0
    latest_match: dict[str, Any] | None = None
    confirmation_state: dict[str, Any] = field(default_factory=lambda: {
        "status": "none",
        "candidate_visitor_id": None,
        "updated_at": None,
    })
    last_decision: SessionDecision = SessionDecision.OBSERVE_ONLY
    last_event: str | None = None
    updated_at: str = field(default_factory=_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "primary_visitor_id": self.primary_visitor_id,
            "candidate_visitor_id": self.candidate_visitor_id,
            "runtime_state": self.runtime_state.value,
            "encounter_status": self.encounter_status,
            "intent_status": self.intent_status,
            "identity_status": self.identity_status,
            "face_confidence_level": self.face_confidence_level.value,
            "voice_confidence_level": self.voice_confidence_level.value,
            "combined_confidence_level": self.combined_confidence_level.value,
            "waiting_for_identity_confirmation": self.waiting_for_identity_confirmation,
            "interruption_count": self.interruption_count,
            "latest_match": _public_metadata(self.latest_match) if self.latest_match else None,
            "confirmation_state": _public_metadata(self.confirmation_state),
            "last_decision": self.last_decision.value,
            "last_event": self.last_event,
            "updated_at": self.updated_at,
        }


class VisitorSessionGatingController:
    """
    In-memory V1 controller for visitor identity and session routing.

    This controller is deliberately conservative: it observes encounter and
    intent signals, records session decisions, and exposes safe developer
    status. It does not create sessions from vision presence, does not hard
    switch the active visitor during a dialogue, and does not store raw
    biometric material.
    """

    def __init__(
        self,
        *,
        session_id: str,
        primary_visitor_id: str | None = None,
        max_events: int = 120,
    ) -> None:
        self._lock = threading.Lock()
        self._events: deque[IdentityGatingEvent] = deque(maxlen=max_events)
        self._config = IdentityGatingConfig()
        self._status = IdentitySessionStatus(
            session_id=session_id,
            primary_visitor_id=primary_visitor_id,
            identity_status="confirmed" if primary_visitor_id else "unidentified",
        )

    def configure_identity(
        self,
        *,
        auto_bind_high_confidence: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._config = IdentityGatingConfig(
                auto_bind_high_confidence=(
                    self._config.auto_bind_high_confidence
                    if auto_bind_high_confidence is None
                    else bool(auto_bind_high_confidence)
                ),
                high_confidence_threshold=self._config.high_confidence_threshold,
                medium_confidence_threshold=self._config.medium_confidence_threshold,
            )
            self._append_event_locked(
                "identity_config",
                SessionDecision.OBSERVE_ONLY,
                "Identity gating runtime config updated.",
                {"config": self._config.to_public_dict()},
            )
            return self._public_status_locked()

    def configure_session(
        self,
        *,
        session_id: str,
        primary_visitor_id: str | None,
        decision: SessionDecision = SessionDecision.SESSION_RESET,
    ) -> dict[str, Any]:
        with self._lock:
            self._status = IdentitySessionStatus(
                session_id=session_id,
                primary_visitor_id=primary_visitor_id,
                identity_status="confirmed" if primary_visitor_id else "unidentified",
                last_decision=decision,
                last_event="session_configured",
            )
            self._append_event_locked(
                "session_configured",
                decision,
                "Session identity scope configured.",
                {
                    "session_id": session_id,
                    "primary_visitor_id": primary_visitor_id,
                },
            )
            return self._public_status_locked()

    def set_primary_visitor(self, visitor_id: str | None) -> dict[str, Any]:
        decision = (
            SessionDecision.VISITOR_BOUND
            if visitor_id is not None
            else SessionDecision.VISITOR_CLEARED
        )
        with self._lock:
            self._status.primary_visitor_id = visitor_id
            self._status.candidate_visitor_id = None
            self._status.identity_status = "confirmed" if visitor_id else "unidentified"
            self._status.waiting_for_identity_confirmation = False
            self._status.confirmation_state = _confirmation_state("none")
            self._status.last_decision = decision
            self._status.last_event = "visitor_selection"
            self._touch_locked()
            self._append_event_locked(
                "visitor_selection",
                decision,
                "Primary visitor binding changed by developer control.",
                {"primary_visitor_id": visitor_id},
            )
            return self._public_status_locked()

    def apply_identity_match(
        self,
        result: IdentityMatchResult,
        config: IdentityGatingConfig | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            effective_config = config or self._config
            self._config = effective_config
            candidate = result.candidate_visitor_id
            self._status.latest_match = result.to_public_dict()
            self._status.face_confidence_level = (
                result.face.level if result.face else ConfidenceLevel.NONE
            )
            self._status.voice_confidence_level = (
                result.voice.level if result.voice else ConfidenceLevel.NONE
            )
            self._status.combined_confidence_level = result.combined_level

            if candidate is None:
                self._status.candidate_visitor_id = None
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state("none")
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Identity match observed without a visitor candidate."
            elif self._status.primary_visitor_id == candidate:
                self._status.candidate_visitor_id = None
                self._status.identity_status = "confirmed"
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state(
                    "accepted",
                    candidate,
                )
                decision = SessionDecision.CONTINUE_CURRENT
                summary = "Identity match supports the current primary visitor."
            elif (
                self._status.primary_visitor_id is not None
                and self._status.runtime_state == RuntimeDialogueState.IN_DIALOGUE
            ):
                self._status.runtime_state = RuntimeDialogueState.INTERRUPTED
                self._status.candidate_visitor_id = candidate
                self._status.identity_status = "interruption_candidate"
                self._status.waiting_for_identity_confirmation = False
                self._status.interruption_count += 1
                self._status.confirmation_state = _confirmation_state(
                    "interruption_recorded",
                    candidate,
                )
                decision = SessionDecision.REFUSE_SWITCH
                summary = "Different visitor candidate detected during active dialogue; current primary visitor is preserved."
            elif (
                result.combined_level == ConfidenceLevel.HIGH
                and effective_config.auto_bind_high_confidence
                and self._status.primary_visitor_id is None
                and self._status.runtime_state != RuntimeDialogueState.IN_DIALOGUE
            ):
                self._status.primary_visitor_id = candidate
                self._status.candidate_visitor_id = None
                self._status.identity_status = "confirmed"
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state(
                    "accepted",
                    candidate,
                )
                decision = SessionDecision.VISITOR_BOUND
                summary = "High-confidence visitor candidate auto-bound by developer runtime config."
            elif result.combined_level == ConfidenceLevel.HIGH:
                self._status.runtime_state = RuntimeDialogueState.IDENTITY_CONFIRMING
                self._status.candidate_visitor_id = candidate
                self._status.identity_status = "candidate"
                self._status.waiting_for_identity_confirmation = True
                self._status.confirmation_state = _confirmation_state(
                    "pending",
                    candidate,
                )
                decision = SessionDecision.CONFIRM_CANDIDATE
                summary = "High-confidence visitor candidate is waiting for non-blocking confirmation."
            elif result.combined_level == ConfidenceLevel.MEDIUM:
                self._status.candidate_visitor_id = candidate
                self._status.identity_status = "candidate"
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state(
                    "candidate_only",
                    candidate,
                )
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Medium-confidence visitor candidate recorded without confirmation request."
            else:
                self._status.candidate_visitor_id = None
                self._status.identity_status = (
                    "confirmed" if self._status.primary_visitor_id else "unidentified"
                )
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state("none")
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Low-confidence identity match ignored for session routing."

            self._status.last_decision = decision
            self._status.last_event = "identity_match"
            self._touch_locked()
            self._append_event_locked(
                "identity_match",
                decision,
                summary,
                {
                    "candidate_visitor_id": candidate,
                    "combined_level": result.combined_level.value,
                    "combined_score": result.combined_score,
                    "auto_bind_high_confidence": effective_config.auto_bind_high_confidence,
                },
            )
            return self._identity_context_locked()

    def confirm_candidate(self, accepted: bool) -> dict[str, Any]:
        with self._lock:
            candidate = self._status.candidate_visitor_id
            if not candidate:
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Identity confirmation requested without a current candidate."
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state("none")
            elif accepted:
                self._status.primary_visitor_id = candidate
                self._status.candidate_visitor_id = None
                self._status.identity_status = "confirmed"
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state(
                    "accepted",
                    candidate,
                )
                decision = SessionDecision.VISITOR_BOUND
                summary = "Visitor candidate confirmed and bound to the current session."
            else:
                self._status.candidate_visitor_id = None
                self._status.identity_status = (
                    "confirmed" if self._status.primary_visitor_id else "unidentified"
                )
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state(
                    "rejected",
                    candidate,
                )
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Visitor candidate rejected; current session identity was preserved."

            self._status.last_decision = decision
            self._status.last_event = "identity_confirmation"
            self._touch_locked()
            self._append_event_locked(
                "identity_confirmation",
                decision,
                summary,
                {"candidate_visitor_id": candidate, "accepted": bool(accepted)},
            )
            return self._identity_context_locked()

    def handle_system_event(self, event_type: EventType) -> dict[str, Any]:
        with self._lock:
            if event_type == EventType.USER_ENTERED:
                if self._status.runtime_state == RuntimeDialogueState.IN_DIALOGUE:
                    self._status.encounter_status = "presence_during_dialogue"
                    decision = SessionDecision.CONTINUE_CURRENT
                    summary = "Presence detected during an active dialogue; current session is preserved."
                else:
                    self._status.runtime_state = RuntimeDialogueState.ENCOUNTER_CANDIDATE
                    self._status.encounter_status = "presence_detected"
                    self._status.intent_status = "unconfirmed"
                    decision = SessionDecision.OBSERVE_ONLY
                    summary = "Presence detected; waiting for dialogue intent before identity work."
            elif event_type == EventType.LONG_SILENCE_DETECTED:
                self._status.intent_status = "no_response"
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Presence has not produced dialogue intent yet."
            elif event_type == EventType.USER_LEFT:
                self._status.runtime_state = RuntimeDialogueState.IDLE
                self._status.encounter_status = "left"
                self._status.intent_status = "unconfirmed"
                self._status.candidate_visitor_id = None
                self._status.waiting_for_identity_confirmation = False
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Presence left; no session switch was made."
            else:
                decision = SessionDecision.OBSERVE_ONLY
                summary = "System event observed by identity/session gating."

            self._status.last_decision = decision
            self._status.last_event = event_type.value
            self._touch_locked()
            self._append_event_locked(
                "system_event",
                decision,
                summary,
                {"event_type": event_type.value},
            )
            return self._public_status_locked()

    def before_turn(
        self,
        *,
        source: str,
        input_mode: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        with self._lock:
            self._status.intent_status = "confirmed_by_input"
            self._status.encounter_status = (
                self._status.encounter_status
                if self._status.encounter_status != "none"
                else "dialogue_input"
            )

            if _is_interruption_signal(metadata):
                self._status.runtime_state = RuntimeDialogueState.INTERRUPTED
                self._status.interruption_count += 1
                decision = SessionDecision.INTERRUPTION_RECORDED
                summary = "Potential interrupter was recorded; V1 keeps the current primary visitor."
            else:
                self._status.runtime_state = RuntimeDialogueState.IN_DIALOGUE
                if self._status.primary_visitor_id:
                    decision = SessionDecision.CONTINUE_CURRENT
                    summary = "Dialogue continues under the current primary visitor."
                else:
                    decision = SessionDecision.CONTINUE_UNIDENTIFIED
                    summary = "Dialogue continues without a confirmed visitor identity."

            self._status.last_decision = decision
            self._status.last_event = "dialogue_turn"
            self._touch_locked()
            self._append_event_locked(
                "dialogue_turn",
                decision,
                summary,
                {
                    "source": source,
                    "input_mode": input_mode,
                    "input_chars": len(text),
                    "primary_visitor_id": self._status.primary_visitor_id,
                    "interruption_signal": _is_interruption_signal(metadata),
                },
            )
            return self._identity_context_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._public_status_locked()

    def _identity_context_locked(self) -> dict[str, Any]:
        return {
            "session_id": self._status.session_id,
            "runtime_state": self._status.runtime_state.value,
            "encounter_status": self._status.encounter_status,
            "intent_status": self._status.intent_status,
            "identity_status": self._status.identity_status,
            "session_decision": self._status.last_decision.value,
            "primary_visitor_id": self._status.primary_visitor_id,
            "candidate_visitor_id": self._status.candidate_visitor_id,
            "confidence": {
                "face": self._status.face_confidence_level.value,
                "voice": self._status.voice_confidence_level.value,
                "combined": self._status.combined_confidence_level.value,
            },
            "waiting_for_identity_confirmation": self._status.waiting_for_identity_confirmation,
            "interruption_count": self._status.interruption_count,
            "latest_match": _public_metadata(self._status.latest_match)
            if self._status.latest_match
            else None,
            "confirmation_state": _public_metadata(self._status.confirmation_state),
        }

    def _public_status_locked(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "scope": "developer_runtime_observation",
            "config": self._config.to_public_dict(),
            "v1_constraints": {
                "single_primary_visitor_per_session": True,
                "vision_presence_does_not_create_session": True,
                "biometric_raw_data_exposed": False,
                "group_session_enabled": False,
                "wide_angle_identity_input_enabled": False,
            },
            "status": self._status.to_public_dict(),
            "recent_events": [event.to_public_dict() for event in list(self._events)[-12:]],
        }

    def _append_event_locked(
        self,
        kind: str,
        decision: SessionDecision,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(
            IdentityGatingEvent(
                id="identity_" + uuid.uuid4().hex,
                timestamp=_now_iso(),
                kind=kind,
                decision=decision.value,
                summary=summary,
                metadata=metadata or {},
            )
        )

    def _touch_locked(self) -> None:
        self._status.updated_at = _now_iso()


def _is_interruption_signal(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("interruption")
        or metadata.get("interruption_candidate")
        or metadata.get("speaker_changed")
    )


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return _redact_sensitive(metadata)


def _confirmation_state(status: str, candidate_visitor_id: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "candidate_visitor_id": candidate_visitor_id,
        "updated_at": _now_iso(),
    }


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clamp_score(score: float | None) -> float:
    if score is None:
        return 0.0
    return max(0.0, min(1.0, float(score)))


def _coerce_confidence_level(value: ConfidenceLevel | str | None) -> ConfidenceLevel:
    if isinstance(value, ConfidenceLevel):
        return value
    if value is None:
        return ConfidenceLevel.NONE
    try:
        return ConfidenceLevel(str(value))
    except ValueError:
        return ConfidenceLevel.NONE


def _first_present(*values: str | None) -> str | None:
    for value in values:
        cleaned = _blank_to_none(value)
        if cleaned is not None:
            return cleaned
    return None


def _resolve_combined_score(
    face: IdentityMatchSignal | None,
    voice: IdentityMatchSignal | None,
    combined_score: float | None,
) -> float | None:
    if combined_score is not None:
        return _clamp_score(combined_score)
    scores = [
        signal.score
        for signal in (face, voice)
        if signal is not None and signal.score is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"face_embedding", "voice_embedding", "raw_audio", "raw_image"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
