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
        self._status = IdentitySessionStatus(
            session_id=session_id,
            primary_visitor_id=primary_visitor_id,
            identity_status="confirmed" if primary_visitor_id else "unidentified",
        )

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
        }

    def _public_status_locked(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "scope": "developer_runtime_observation",
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
    redacted: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"face_embedding", "voice_embedding", "raw_audio", "raw_image"}:
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted
