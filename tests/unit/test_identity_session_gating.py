from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conscious_entity.identity import (
    IdentityGatingConfig,
    IdentityMatchResult,
    IdentityMatchSignal,
    RuntimeDialogueState,
    VisitorSessionGatingController,
)
from conscious_entity.perception.event_types import EventType


def _track(
    track_id: int,
    *,
    active: bool = True,
    seconds_ago: float = 0.0,
) -> dict:
    timestamp = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return {
        "track_id": track_id,
        "active": active,
        "last_seen_at": timestamp.isoformat(),
        "bbox": {"x1": 100, "y1": 100, "x2": 420, "y2": 460},
    }


def _tracking_status(*tracks: dict, person_present: bool = True, frame_id: int = 1) -> dict:
    return {
        "frame_id": frame_id,
        "person_present": person_present,
        "tracks": list(tracks),
    }


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
    assert context["candidate_confirmation_turns"] == 0


def test_medium_confidence_match_waits_for_confirmation_without_memory():
    controller = VisitorSessionGatingController(session_id="session-1")
    result = IdentityMatchResult.build(
        candidate_visitor_id="visitor-k",
        face=IdentityMatchSignal.build(modality="face", score=0.7),
    )

    context = controller.apply_identity_match(result)

    assert context["session_decision"] == "confirm_candidate"
    assert context["candidate_visitor_id"] == "visitor-k"
    assert context["primary_visitor_id"] is None
    assert context["waiting_for_identity_confirmation"] is True
    assert context["identity_status"] == "candidate"
    assert context["visitor_memory_allowed"] is False
    assert context["latest_match"]["candidate_visitor_id"] == "visitor-k"
    assert context["latest_match"]["combined_level"] == "medium"


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
    assert controller.status()["config"]["handoff_after_primary_leave_enabled"] is True


def test_primary_track_alive_blocks_different_high_confidence_candidate():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.update_primary_presence(_tracking_status(_track(1)))
    controller.before_turn(source="dialog", input_mode="text", text="继续")
    result = IdentityMatchResult.build(
        candidate_visitor_id="visitor-b",
        face=IdentityMatchSignal.build(modality="face", score=0.92),
    )

    context = controller.apply_identity_match(result)

    assert context["session_decision"] == "refuse_switch"
    assert context["primary_visitor_id"] == "visitor-a"
    assert context["candidate_visitor_id"] == "visitor-b"
    assert context["primary_track_id"] == 1
    assert context["primary_presence_status"] == "present"


def test_primary_track_lost_releases_before_next_candidate_can_bind():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.update_primary_presence(_tracking_status(_track(1, seconds_ago=36.0)))

    released = controller.update_primary_presence(
        _tracking_status(
            _track(1, active=False, seconds_ago=36.0),
            _track(2),
        )
    )

    assert released["primary_released"] is True
    assert released["released_visitor_id"] == "visitor-a"
    assert released["primary_visitor_id"] is None
    assert released["last_primary_release"]["reason"] == "primary_track_lost"

    after_release = controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-b",
        face=IdentityMatchSignal.build(modality="face", score=0.92),
    ))

    assert after_release["session_decision"] == "confirm_candidate"
    assert after_release["candidate_visitor_id"] == "visitor-b"
    assert after_release["primary_visitor_id"] is None
    assert after_release["visitor_memory_allowed"] is False


def test_primary_release_blocks_auto_bind_even_when_debug_switch_is_on():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.configure_identity(auto_bind_high_confidence=True)
    controller.update_primary_presence(_tracking_status(_track(1, seconds_ago=36.0)))
    controller.update_primary_presence(
        _tracking_status(_track(1, active=False, seconds_ago=36.0))
    )
    controller.configure_session(session_id="session-2", primary_visitor_id=None)
    controller.record_primary_release_session("session-2")

    context = controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-b",
        face=IdentityMatchSignal.build(modality="face", score=0.92),
    ))

    assert context["session_decision"] == "confirm_candidate"
    assert context["primary_visitor_id"] is None
    assert context["candidate_visitor_id"] == "visitor-b"
    assert context["waiting_for_identity_confirmation"] is True


def test_primary_track_missing_grace_keeps_primary_but_blocks_visitor_scope():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.update_primary_presence(_tracking_status(_track(1, seconds_ago=20.0)))

    missing = controller.update_primary_presence(
        _tracking_status(
            _track(1, active=False, seconds_ago=20.0),
            _track(2),
        )
    )
    turn = controller.before_turn(source="dialog", input_mode="text", text="我是B")
    match = controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-b",
        face=IdentityMatchSignal.build(modality="face", score=0.92),
    ))

    assert missing["primary_released"] is False
    assert missing["primary_visitor_id"] == "visitor-a"
    assert missing["primary_presence_status"] == "missing_grace"
    assert missing["visitor_scope_mode"] == "unscoped_grace"
    assert missing["visitor_memory_allowed"] is False
    assert turn["session_decision"] == "continue_unscoped"
    assert turn["visitor_memory_allowed"] is False
    assert match["session_decision"] == "refuse_switch"
    assert match["candidate_visitor_id"] is None
    assert match["primary_visitor_id"] == "visitor-a"


def test_primary_track_returns_within_grace_continues_current_visitor():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.update_primary_presence(_tracking_status(_track(1, seconds_ago=20.0)))
    controller.update_primary_presence(
        _tracking_status(_track(1, active=False, seconds_ago=20.0), frame_id=2)
    )

    returned = controller.update_primary_presence(
        _tracking_status(_track(1), frame_id=3)
    )

    assert returned["primary_released"] is False
    assert returned["primary_visitor_id"] == "visitor-a"
    assert returned["primary_presence_status"] == "present"
    assert returned["visitor_scope_mode"] == "primary"
    assert returned["visitor_memory_allowed"] is True


def test_ambiguous_primary_presence_does_not_release_current_visitor():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )

    context = controller.update_primary_presence(
        _tracking_status(_track(1), _track(2))
    )

    assert context["primary_released"] is False
    assert context["primary_visitor_id"] == "visitor-a"
    assert context["primary_track_id"] is None
    assert context["primary_presence_status"] == "ambiguous"

    single_remaining = controller.update_primary_presence(
        _tracking_status(_track(2), frame_id=2)
    )

    assert single_remaining["primary_released"] is False
    assert single_remaining["primary_visitor_id"] == "visitor-a"
    assert single_remaining["primary_track_id"] is None
    assert single_remaining["primary_presence_status"] == "ambiguous"


def test_handoff_disabled_keeps_primary_even_when_scene_is_empty():
    controller = VisitorSessionGatingController(
        session_id="session-1",
        primary_visitor_id="visitor-a",
    )
    controller.configure_identity(handoff_after_primary_leave_enabled=False)

    context = controller.update_primary_presence(
        _tracking_status(person_present=False, frame_id=2)
    )

    assert context["primary_released"] is False
    assert context["primary_visitor_id"] == "visitor-a"
    assert context["primary_presence_status"] == "handoff_disabled"


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


def test_high_confidence_candidate_expires_after_two_unconfirmed_turns():
    controller = VisitorSessionGatingController(session_id="session-1")
    controller.apply_identity_match(IdentityMatchResult.build(
        candidate_visitor_id="visitor-k",
        face=IdentityMatchSignal.build(modality="face", score=0.9),
    ))

    first = controller.before_turn(source="dialog", input_mode="text", text="聊别的")
    second = controller.before_turn(source="dialog", input_mode="text", text="还是聊别的")
    third = controller.before_turn(source="dialog", input_mode="text", text="继续")

    assert first["candidate_visitor_id"] == "visitor-k"
    assert first["waiting_for_identity_confirmation"] is True
    assert first["candidate_confirmation_turns"] == 1
    assert second["candidate_visitor_id"] == "visitor-k"
    assert second["candidate_confirmation_turns"] == 2
    assert third["candidate_visitor_id"] is None
    assert third["waiting_for_identity_confirmation"] is False
    assert third["confirmation_state"]["status"] == "expired"


def test_high_confidence_candidate_expires_after_ttl():
    controller = VisitorSessionGatingController(session_id="session-1")
    controller.apply_identity_match(
        IdentityMatchResult.build(
            candidate_visitor_id="visitor-k",
            face=IdentityMatchSignal.build(modality="face", score=0.9),
            config=IdentityGatingConfig(candidate_ttl_seconds=0.0),
        ),
        config=IdentityGatingConfig(candidate_ttl_seconds=0.0),
    )

    context = controller.before_turn(source="dialog", input_mode="text", text="你好")

    assert context["candidate_visitor_id"] is None
    assert context["waiting_for_identity_confirmation"] is False
    assert context["confirmation_state"]["status"] == "expired"
