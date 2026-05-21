from __future__ import annotations

from conscious_entity.identity import (
    IdentityMatchResult,
    IdentityMatchSignal,
    RuntimeDialogueState,
    VisitorSessionGatingController,
)
from conscious_entity.perception.event_types import EventType


def test_presence_only_observes_without_session_switch():
    controller = VisitorSessionGatingController(session_id="session-1")

    status = controller.handle_system_event(EventType.USER_ENTERED)

    current = status["status"]
    assert current["runtime_state"] == RuntimeDialogueState.ENCOUNTER_CANDIDATE.value
    assert current["last_decision"] == "observe_only"
    assert current["primary_visitor_id"] is None
    assert status["v1_constraints"]["vision_presence_does_not_create_session"] is True


def test_turn_without_visitor_continues_unidentified():
    controller = VisitorSessionGatingController(session_id="session-1")

    context = controller.before_turn(
        source="audio_dialog",
        input_mode="voice_transcript",
        text="你好",
    )

    assert context["runtime_state"] == "in_dialogue"
    assert context["session_decision"] == "continue_unidentified"
    assert context["identity_status"] == "unidentified"


def test_bound_visitor_turn_continues_current_scope():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-k",
    )

    context = controller.before_turn(
        source="dialog",
        input_mode="text",
        text="你记得我吗",
    )

    assert context["session_decision"] == "continue_current"
    assert context["primary_visitor_id"] == "visitor-k"
    assert context["identity_status"] == "confirmed"


def test_interruption_signal_is_recorded_but_keeps_primary_visitor():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )

    context = controller.before_turn(
        source="audio_dialog",
        input_mode="voice_transcript",
        text="我也想说",
        metadata={"speaker_changed": True},
    )

    assert context["session_decision"] == "interruption_recorded"
    assert context["primary_visitor_id"] == "visitor-a"
    assert context["interruption_count"] == 1


def test_public_status_does_not_expose_raw_biometric_metadata():
    controller = VisitorSessionGatingController(session_id="session-1")
    controller.before_turn(
        source="dialog",
        input_mode="text",
        text="hello",
        metadata={"raw_audio": b"abc", "face_embedding": [0.1, 0.2]},
    )

    event = controller.status()["recent_events"][-1]

    assert "raw_audio" not in event["metadata"]
    assert "face_embedding" not in event["metadata"]


def test_match_score_maps_to_confidence_levels():
    signal = IdentityMatchSignal.build(modality="face", score=0.83)
    result = IdentityMatchResult.build(candidate_visitor_id="visitor-k", face=signal)

    assert signal.level.value == "high"
    assert result.combined_level.value == "high"
    assert result.combined_score == 0.83


def test_high_confidence_match_waits_for_confirmation_by_default():
    controller = VisitorSessionGatingController(session_id="session-1")
    result = IdentityMatchResult.build(
        candidate_visitor_id="visitor-k",
        face=IdentityMatchSignal.build(modality="face", score=0.9),
    )

    context = controller.apply_identity_match(result)

    assert context["session_decision"] == "confirm_candidate"
    assert context["candidate_visitor_id"] == "visitor-k"
    assert context["primary_visitor_id"] is None
    assert context["waiting_for_identity_confirmation"] is True
    assert context["confirmation_state"]["status"] == "pending"


def test_high_confidence_match_can_auto_bind_when_enabled_and_idle():
    controller = VisitorSessionGatingController(session_id="session-1")
    controller.configure_identity(auto_bind_high_confidence=True)
    result = IdentityMatchResult.build(
        candidate_visitor_id="visitor-k",
        voice=IdentityMatchSignal.build(modality="voice", score=0.91),
    )

    context = controller.apply_identity_match(result)

    assert context["session_decision"] == "visitor_bound"
    assert context["primary_visitor_id"] == "visitor-k"
    assert context["candidate_visitor_id"] is None
    assert context["confirmation_state"]["status"] == "accepted"


def test_different_candidate_during_dialogue_records_refuse_switch():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.before_turn(source="dialog", input_mode="text", text="继续")
    result = IdentityMatchResult.build(
        candidate_visitor_id="visitor-b",
        face=IdentityMatchSignal.build(modality="face", score=0.9),
    )

    context = controller.apply_identity_match(result)

    assert context["session_decision"] == "refuse_switch"
    assert context["primary_visitor_id"] == "visitor-a"
    assert context["candidate_visitor_id"] == "visitor-b"
    assert context["interruption_count"] == 1


def test_confirm_candidate_accepts_or_rejects():
    controller = VisitorSessionGatingController(session_id="session-1")
    controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-k",
        face=IdentityMatchSignal.build(modality="face", score=0.9),
    ))

    accepted = controller.confirm_candidate(True)

    assert accepted["session_decision"] == "visitor_bound"
    assert accepted["primary_visitor_id"] == "visitor-k"
    assert accepted["confirmation_state"]["status"] == "accepted"

    controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-q",
        face=IdentityMatchSignal.build(modality="face", score=0.9),
    ))
    rejected = controller.confirm_candidate(False)

    assert rejected["primary_visitor_id"] == "visitor-k"
    assert rejected["candidate_visitor_id"] is None
    assert rejected["confirmation_state"]["status"] == "rejected"
