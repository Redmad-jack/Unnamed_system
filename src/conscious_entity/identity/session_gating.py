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
    CONTINUE_UNSCOPED = "continue_unscoped"
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
    handoff_after_primary_leave_enabled: bool = True
    high_confidence_threshold: float = 0.82
    medium_confidence_threshold: float = 0.62
    candidate_max_turns: int = 2
    candidate_ttl_seconds: float = 90.0
    primary_leave_grace_seconds: float = 35.0

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
            "handoff_after_primary_leave_enabled": self.handoff_after_primary_leave_enabled,
            "high_confidence_threshold": self.high_confidence_threshold,
            "medium_confidence_threshold": self.medium_confidence_threshold,
            "candidate_max_turns": self.candidate_max_turns,
            "candidate_ttl_seconds": self.candidate_ttl_seconds,
            "primary_leave_grace_seconds": self.primary_leave_grace_seconds,
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
    candidate_started_at: str | None = None
    candidate_confirmation_turns: int = 0
    primary_track_id: int | None = None
    primary_track_locked_at: str | None = None
    primary_track_last_seen_at: str | None = None
    primary_presence_status: str = "untracked"
    primary_presence_updated_at: str | None = None
    last_primary_release: dict[str, Any] | None = None
    capture_in_flight: bool = False
    last_capture_rejection: dict[str, Any] | None = None
    last_natural_confirmation: dict[str, Any] | None = None
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
            "candidate_started_at": self.candidate_started_at,
            "candidate_confirmation_turns": self.candidate_confirmation_turns,
            "primary_track_id": self.primary_track_id,
            "primary_track_locked_at": self.primary_track_locked_at,
            "primary_track_last_seen_at": self.primary_track_last_seen_at,
            "primary_presence_status": self.primary_presence_status,
            "primary_presence_updated_at": self.primary_presence_updated_at,
            "last_primary_release": _public_metadata(self.last_primary_release)
            if self.last_primary_release
            else None,
            "visitor_scope_mode": _visitor_scope_mode(
                self.primary_visitor_id,
                self.waiting_for_identity_confirmation,
                self.primary_presence_status,
            ),
            "visitor_memory_allowed": _visitor_memory_allowed(
                self.primary_visitor_id,
                self.primary_presence_status,
            ),
            "capture_in_flight": self.capture_in_flight,
            "last_capture_rejection": _public_metadata(self.last_capture_rejection)
            if self.last_capture_rejection
            else None,
            "last_natural_confirmation": _public_metadata(self.last_natural_confirmation)
            if self.last_natural_confirmation
            else None,
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
            primary_presence_status="untracked" if primary_visitor_id else "no_primary",
        )

    def configure_identity(
        self,
        *,
        auto_bind_high_confidence: bool | None = None,
        handoff_after_primary_leave_enabled: bool | None = None,
        primary_leave_grace_seconds: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._config = IdentityGatingConfig(
                auto_bind_high_confidence=(
                    self._config.auto_bind_high_confidence
                    if auto_bind_high_confidence is None
                    else bool(auto_bind_high_confidence)
                ),
                handoff_after_primary_leave_enabled=(
                    self._config.handoff_after_primary_leave_enabled
                    if handoff_after_primary_leave_enabled is None
                    else bool(handoff_after_primary_leave_enabled)
                ),
                high_confidence_threshold=self._config.high_confidence_threshold,
                medium_confidence_threshold=self._config.medium_confidence_threshold,
                candidate_max_turns=self._config.candidate_max_turns,
                candidate_ttl_seconds=self._config.candidate_ttl_seconds,
                primary_leave_grace_seconds=(
                    self._config.primary_leave_grace_seconds
                    if primary_leave_grace_seconds is None
                    else max(0.0, float(primary_leave_grace_seconds))
                ),
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
            last_primary_release = self._status.last_primary_release
            self._status = IdentitySessionStatus(
                session_id=session_id,
                primary_visitor_id=primary_visitor_id,
                identity_status="confirmed" if primary_visitor_id else "unidentified",
                primary_presence_status="untracked" if primary_visitor_id else "no_primary",
                last_primary_release=last_primary_release,
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
            self._status.candidate_started_at = None
            self._status.candidate_confirmation_turns = 0
            self._status.primary_track_id = None
            self._status.primary_track_locked_at = None
            self._status.primary_track_last_seen_at = None
            self._status.primary_presence_status = "untracked" if visitor_id else "no_primary"
            self._status.primary_presence_updated_at = _now_iso()
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

            previous_visitor_id: str | None = None
            if candidate is None:
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state("none")
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Identity match observed without a visitor candidate."
            elif self._status.primary_visitor_id == candidate:
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
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
                and self._visitor_scope_mode_locked() == "unscoped_grace"
                and result.combined_level == ConfidenceLevel.HIGH
            ):
                previous_visitor_id = self._status.primary_visitor_id
                self._status.runtime_state = RuntimeDialogueState.INTERRUPTED
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
                self._status.identity_status = "primary_missing_grace"
                self._status.waiting_for_identity_confirmation = False
                self._status.interruption_count += 1
                self._status.confirmation_state = _confirmation_state(
                    "interruption_recorded",
                    candidate,
                )
                decision = SessionDecision.REFUSE_SWITCH
                summary = "Different visitor candidate detected while primary is in leave grace; no visitor candidate was opened."
            elif (
                self._status.primary_visitor_id is not None
                and self._status.runtime_state == RuntimeDialogueState.IN_DIALOGUE
                and result.combined_level == ConfidenceLevel.HIGH
            ):
                previous_visitor_id = self._status.primary_visitor_id
                self._status.runtime_state = RuntimeDialogueState.INTERRUPTED
                self._status.candidate_visitor_id = candidate
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
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
                and not self._handoff_release_requires_confirmation_locked()
                and result.decision_hint != "confirm_if_high_confidence"
            ):
                self._status.primary_visitor_id = candidate
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
                self._status.primary_track_id = None
                self._status.primary_track_locked_at = None
                self._status.primary_track_last_seen_at = None
                self._status.primary_presence_status = "untracked"
                self._status.primary_presence_updated_at = _now_iso()
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
                self._status.candidate_started_at = _now_iso()
                self._status.candidate_confirmation_turns = 0
                self._status.identity_status = "candidate"
                self._status.waiting_for_identity_confirmation = True
                self._status.confirmation_state = _confirmation_state(
                    "pending",
                    candidate,
                )
                decision = SessionDecision.CONFIRM_CANDIDATE
                summary = "High-confidence visitor candidate is waiting for non-blocking confirmation."
            elif (
                result.combined_level == ConfidenceLevel.MEDIUM
                and self._status.primary_visitor_id is None
            ):
                self._status.runtime_state = RuntimeDialogueState.IDENTITY_CONFIRMING
                self._status.candidate_visitor_id = candidate
                self._status.candidate_started_at = _now_iso()
                self._status.candidate_confirmation_turns = 0
                self._status.identity_status = "candidate"
                self._status.waiting_for_identity_confirmation = True
                self._status.confirmation_state = _confirmation_state(
                    "pending",
                    candidate,
                )
                decision = SessionDecision.CONFIRM_CANDIDATE
                summary = "Medium-confidence visitor candidate is waiting for non-blocking confirmation."
            elif result.combined_level == ConfidenceLevel.MEDIUM:
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
                self._status.identity_status = (
                    "confirmed" if self._status.primary_visitor_id else "unidentified"
                )
                self._status.waiting_for_identity_confirmation = False
                self._status.confirmation_state = _confirmation_state("none")
                decision = SessionDecision.OBSERVE_ONLY
                summary = "Medium-confidence identity match kept as dashboard diagnostics only."
            else:
                self._status.candidate_visitor_id = None
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
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
                    "previous_visitor_id": previous_visitor_id,
                    "combined_level": result.combined_level.value,
                    "combined_score": result.combined_score,
                    "auto_bind_high_confidence": effective_config.auto_bind_high_confidence,
                    "handoff_after_primary_leave_enabled": effective_config.handoff_after_primary_leave_enabled,
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
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
                self._status.primary_track_id = None
                self._status.primary_track_locked_at = None
                self._status.primary_track_last_seen_at = None
                self._status.primary_presence_status = "untracked"
                self._status.primary_presence_updated_at = _now_iso()
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
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
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

    def record_face_capture_diagnostic(
        self,
        *,
        in_flight: bool | None = None,
        rejection_reason: str | None = None,
        accepted: bool | None = None,
        source: str = "manual",
    ) -> dict[str, Any]:
        with self._lock:
            if in_flight is not None:
                self._status.capture_in_flight = bool(in_flight)
            if rejection_reason:
                self._status.last_capture_rejection = {
                    "reason": rejection_reason,
                    "source": source,
                    "updated_at": _now_iso(),
                }
            elif accepted:
                self._status.last_capture_rejection = None
            self._touch_locked()
            return self._identity_context_locked()

    def record_natural_confirmation(
        self,
        *,
        status: str,
        text: str,
        candidate_visitor_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._status.last_natural_confirmation = {
                "status": status,
                "candidate_visitor_id": candidate_visitor_id or self._status.candidate_visitor_id,
                "text_preview": str(text).strip()[:80],
                "updated_at": _now_iso(),
            }
            self._touch_locked()
            self._append_event_locked(
                "natural_identity_confirmation",
                self._status.last_decision,
                f"Natural identity confirmation parsed as {status}.",
                self._status.last_natural_confirmation,
            )
            return self._identity_context_locked()

    def update_primary_presence(self, tracking_status: dict[str, Any] | None) -> dict[str, Any]:
        with self._lock:
            released_visitor_id = self._update_primary_presence_locked(tracking_status or {})
            context = self._identity_context_locked()
            if released_visitor_id is not None:
                context["primary_released"] = True
                context["released_visitor_id"] = released_visitor_id
            else:
                context["primary_released"] = False
            return context

    def record_primary_release_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            if self._status.last_primary_release is not None:
                self._status.last_primary_release = {
                    **self._status.last_primary_release,
                    "new_session_id": session_id,
                    "updated_at": _now_iso(),
                }
                self._touch_locked()
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
                self._status.candidate_started_at = None
                self._status.candidate_confirmation_turns = 0
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

    def expire_pending_candidate_if_needed(self) -> dict[str, Any]:
        with self._lock:
            self._expire_pending_candidate_if_needed_locked()
            return self._identity_context_locked()

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
            expired = self._expire_pending_candidate_if_needed_locked()
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
            elif self._visitor_scope_mode_locked() == "unscoped_grace":
                self._status.runtime_state = RuntimeDialogueState.INTERRUPTED
                decision = SessionDecision.CONTINUE_UNSCOPED
                summary = "Primary visitor is missing within the leave grace window; this turn must not use visitor-scoped memory."
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
            if (
                not expired
                and self._status.waiting_for_identity_confirmation
                and self._status.candidate_visitor_id
            ):
                self._status.candidate_confirmation_turns += 1
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
            "candidate_started_at": self._status.candidate_started_at,
            "candidate_confirmation_turns": self._status.candidate_confirmation_turns,
            "primary_track_id": self._status.primary_track_id,
            "primary_track_last_seen_at": self._status.primary_track_last_seen_at,
            "primary_presence_status": self._status.primary_presence_status,
            "primary_presence_updated_at": self._status.primary_presence_updated_at,
            "last_primary_release": _public_metadata(self._status.last_primary_release)
            if self._status.last_primary_release
            else None,
            "visitor_scope_mode": self._visitor_scope_mode_locked(),
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
            "visitor_memory_allowed": self._visitor_memory_allowed_locked(),
            "capture_in_flight": self._status.capture_in_flight,
            "last_capture_rejection": _public_metadata(self._status.last_capture_rejection)
            if self._status.last_capture_rejection
            else None,
            "last_natural_confirmation": _public_metadata(self._status.last_natural_confirmation)
            if self._status.last_natural_confirmation
            else None,
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

    def _update_primary_presence_locked(self, tracking_status: dict[str, Any]) -> str | None:
        primary = self._status.primary_visitor_id
        if primary is None:
            self._clear_primary_track_locked("no_primary")
            return None
        if not self._config.handoff_after_primary_leave_enabled:
            self._set_primary_presence_locked("handoff_disabled")
            return None

        frame_id = int(tracking_status.get("frame_id") or 0)
        if frame_id <= 0:
            self._set_primary_presence_locked("untracked")
            return None

        tracks = _public_tracks(tracking_status.get("tracks"))
        active_tracks = [item for item in tracks if item.get("active") is True]
        person_present = bool(tracking_status.get("person_present") or active_tracks)

        if self._status.primary_track_id is None:
            if self._status.primary_presence_status == "ambiguous":
                if not person_present:
                    self._set_primary_presence_locked("untracked")
                    return None
                self._set_primary_presence_locked("ambiguous")
                return None
            if len(active_tracks) == 1:
                self._lock_primary_track_locked(active_tracks[0])
                return None
            if not person_present:
                self._set_primary_presence_locked("untracked")
                return None
            self._set_primary_presence_locked("ambiguous" if len(active_tracks) > 1 else "untracked")
            return None

        primary_track = _find_track(tracks, self._status.primary_track_id)
        if primary_track is not None:
            last_seen = _track_last_seen_iso(primary_track) or self._status.primary_track_last_seen_at
            if last_seen:
                self._status.primary_track_last_seen_at = last_seen
            if primary_track.get("active") is True:
                self._set_primary_presence_locked("present")
                return None
            if self._primary_track_missing_too_long_locked():
                return self._release_primary_visitor_locked("primary_track_lost")
            self._set_primary_presence_locked("missing_grace")
            return None

        if self._primary_track_missing_too_long_locked():
            return self._release_primary_visitor_locked("primary_track_lost")
        self._set_primary_presence_locked("missing_grace")
        return None

    def _lock_primary_track_locked(self, track: dict[str, Any]) -> None:
        track_id = _track_id(track)
        if track_id is None:
            self._set_primary_presence_locked("untracked")
            return
        now = _now_iso()
        self._status.primary_track_id = track_id
        self._status.primary_track_locked_at = self._status.primary_track_locked_at or now
        self._status.primary_track_last_seen_at = _track_last_seen_iso(track) or now
        self._status.primary_presence_status = "present"
        self._status.primary_presence_updated_at = now
        self._touch_locked()
        self._append_event_locked(
            "primary_track_locked",
            SessionDecision.CONTINUE_CURRENT,
            "Primary visitor was locked to the only stable person track.",
            {
                "primary_visitor_id": self._status.primary_visitor_id,
                "primary_track_id": track_id,
            },
        )

    def _release_primary_visitor_locked(self, reason: str) -> str | None:
        released = self._status.primary_visitor_id
        if released is None:
            return None
        now = _now_iso()
        release = {
            "visitor_id": released,
            "reason": reason,
            "primary_track_id": self._status.primary_track_id,
            "primary_track_last_seen_at": self._status.primary_track_last_seen_at,
            "updated_at": now,
        }
        self._status.primary_visitor_id = None
        self._status.candidate_visitor_id = None
        self._status.candidate_started_at = None
        self._status.candidate_confirmation_turns = 0
        self._status.primary_track_id = None
        self._status.primary_track_locked_at = None
        self._status.primary_track_last_seen_at = None
        self._status.primary_presence_status = "left"
        self._status.primary_presence_updated_at = now
        self._status.last_primary_release = release
        self._status.identity_status = "unidentified"
        self._status.waiting_for_identity_confirmation = False
        self._status.confirmation_state = _confirmation_state("none")
        self._status.last_decision = SessionDecision.VISITOR_CLEARED
        self._status.last_event = "primary_visitor_left"
        self._touch_locked()
        self._append_event_locked(
            "primary_visitor_left",
            SessionDecision.VISITOR_CLEARED,
            "Primary visitor left the tracked dialogue window; current visitor was released.",
            release,
        )
        return released

    def _primary_track_missing_too_long_locked(self) -> bool:
        last_seen = _parse_iso_datetime(self._status.primary_track_last_seen_at)
        if last_seen is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last_seen).total_seconds()
        return elapsed >= max(0.0, float(self._config.primary_leave_grace_seconds))

    def _clear_primary_track_locked(self, status: str) -> None:
        self._status.primary_track_id = None
        self._status.primary_track_locked_at = None
        self._status.primary_track_last_seen_at = None
        self._set_primary_presence_locked(status)

    def _set_primary_presence_locked(self, status: str) -> None:
        if self._status.primary_presence_status == status:
            return
        self._status.primary_presence_status = status
        self._status.primary_presence_updated_at = _now_iso()
        self._touch_locked()

    def _visitor_scope_mode_locked(self) -> str:
        return _visitor_scope_mode(
            self._status.primary_visitor_id,
            self._status.waiting_for_identity_confirmation,
            self._status.primary_presence_status,
        )

    def _visitor_memory_allowed_locked(self) -> bool:
        return _visitor_memory_allowed(
            self._status.primary_visitor_id,
            self._status.primary_presence_status,
        )

    def _handoff_release_requires_confirmation_locked(self) -> bool:
        release = self._status.last_primary_release
        if not isinstance(release, dict):
            return False
        new_session_id = release.get("new_session_id")
        return new_session_id is None or new_session_id == self._status.session_id

    def _expire_pending_candidate_if_needed_locked(self) -> bool:
        if (
            not self._status.waiting_for_identity_confirmation
            or not self._status.candidate_visitor_id
        ):
            return False
        candidate = self._status.candidate_visitor_id
        expired = False
        max_turns = max(0, int(self._config.candidate_max_turns))
        if self._status.candidate_confirmation_turns >= max_turns:
            expired = True
        ttl_seconds = float(self._config.candidate_ttl_seconds)
        started_at = _parse_iso_datetime(self._status.candidate_started_at)
        if ttl_seconds <= 0.0:
            expired = True
        elif started_at is not None:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed >= ttl_seconds:
                expired = True
        if not expired:
            return False

        self._status.candidate_visitor_id = None
        self._status.candidate_started_at = None
        self._status.candidate_confirmation_turns = 0
        self._status.identity_status = (
            "confirmed" if self._status.primary_visitor_id else "unidentified"
        )
        self._status.waiting_for_identity_confirmation = False
        self._status.confirmation_state = _confirmation_state("expired", candidate)
        self._status.last_decision = SessionDecision.OBSERVE_ONLY
        self._status.last_event = "candidate_expired"
        self._touch_locked()
        self._append_event_locked(
            "candidate_expired",
            SessionDecision.OBSERVE_ONLY,
            "Pending visitor candidate expired without confirmation.",
            {"candidate_visitor_id": candidate},
        )
        return True

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


def _visitor_scope_mode(
    primary_visitor_id: str | None,
    waiting_for_identity_confirmation: bool,
    primary_presence_status: str,
) -> str:
    if primary_visitor_id:
        if primary_presence_status == "missing_grace":
            return "unscoped_grace"
        return "primary"
    if waiting_for_identity_confirmation:
        return "candidate_pending"
    return "unidentified"


def _visitor_memory_allowed(
    primary_visitor_id: str | None,
    primary_presence_status: str,
) -> bool:
    return bool(primary_visitor_id) and primary_presence_status != "missing_grace"


def _public_tracks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _find_track(tracks: list[dict[str, Any]], track_id: int | None) -> dict[str, Any] | None:
    if track_id is None:
        return None
    for item in tracks:
        if _track_id(item) == track_id:
            return item
    return None


def _track_id(track: dict[str, Any]) -> int | None:
    value = track.get("track_id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _track_last_seen_iso(track: dict[str, Any]) -> str | None:
    value = track.get("last_seen_at")
    if not value:
        return None
    parsed = _parse_iso_datetime(str(value))
    return parsed.isoformat() if parsed else None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
            if key in {"face_embedding", "voice_embedding", "raw_audio", "raw_image", "face_crop"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
