from __future__ import annotations

import pytest

from conscious_entity.body.protocol import (
    BodyProtocolError,
    DriveIntent,
    build_discrete_command,
    build_drive_command,
    build_stop_command,
    drive_intent_from_payload,
)


def test_body_protocol_builds_drive_command_from_teleop_intent():
    assert build_drive_command(DriveIntent(throttle=80, turn=0, duration_ms=180)) == "drive 80 0 180"
    assert build_drive_command(DriveIntent(throttle=-80, turn=60, duration_ms=180)) == "drive -80 60 180"


def test_body_protocol_clamps_drive_intent():
    command = build_drive_command(DriveIntent(throttle=999, turn=-999, duration_ms=5000))

    assert command == "drive 250 -250 500"


def test_body_protocol_allows_only_discrete_debug_commands():
    assert build_discrete_command("  Avoidance   OFF ") == "avoidance off"
    assert build_discrete_command(" imu ") == "imu"
    assert build_stop_command() == "motors off"

    with pytest.raises(BodyProtocolError):
        build_discrete_command("motor 1 250 30000")


def test_body_protocol_parses_json_teleop_payload():
    intent = drive_intent_from_payload({"throttle": "180", "turn": -60, "duration_ms": "120"})

    assert intent == DriveIntent(throttle=180, turn=-60, duration_ms=120)


def test_body_protocol_rejects_invalid_teleop_payload():
    with pytest.raises(BodyProtocolError):
        drive_intent_from_payload({"throttle": "fast"})
