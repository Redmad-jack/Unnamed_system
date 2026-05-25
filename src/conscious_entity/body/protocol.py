from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TELEOP_DUTY = 80
SLOW_TELEOP_DUTY = 60
FAST_TELEOP_DUTY = 180
MAX_TELEOP_DUTY = 250
DEFAULT_DRIVE_DURATION_MS = 180
MAX_DRIVE_DURATION_MS = 500
DEFAULT_MOTOR_TEST_DUTY = 80
DEFAULT_MOTOR_TEST_DURATION_MS = 800
MAX_MOTOR_TEST_DURATION_MS = 30000

ALLOWED_DISCRETE_COMMANDS = {
    "arm",
    "disarm",
    "motors off",
    "avoidance on",
    "avoidance off",
    "telemetry on",
    "telemetry off",
    "tof",
    "imu",
    "line",
    "line on",
    "line off",
    "line calibrate floor",
    "line calibrate tape",
    "reacquire start",
    "reacquire stop",
    "status",
}


class BodyProtocolError(ValueError):
    """Raised when a requested body command is outside the safe v1 protocol."""


@dataclass(frozen=True)
class DriveIntent:
    throttle: int = 0
    turn: int = 0
    duration_ms: int = DEFAULT_DRIVE_DURATION_MS
    expressive: bool = False


@dataclass(frozen=True)
class MotorTestCommand:
    motor: int
    duty: int = DEFAULT_MOTOR_TEST_DUTY
    direction: str = "forward"
    duration_ms: int = DEFAULT_MOTOR_TEST_DURATION_MS


def build_discrete_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().lower().split())
    if normalized not in ALLOWED_DISCRETE_COMMANDS:
        raise BodyProtocolError(f"unsupported body command: {command}")
    return normalized


def build_motor_test_command(command: MotorTestCommand) -> str:
    motor = _clamp_int(command.motor, 1, 4)
    direction = " ".join(str(command.direction or "").strip().lower().split())
    if direction not in {"forward", "reverse", "stop"}:
        raise BodyProtocolError(f"unsupported motor direction: {command.direction}")

    duty = abs(_clamp_int(command.duty, 0, MAX_TELEOP_DUTY))
    if direction == "reverse":
        duty = -duty
    elif direction == "stop":
        duty = 0

    duration_ms = _clamp_int(command.duration_ms, 1, MAX_MOTOR_TEST_DURATION_MS)
    return f"motor {motor} {duty} {duration_ms}"


def build_drive_command(intent: DriveIntent) -> str:
    throttle = _clamp_int(intent.throttle, -MAX_TELEOP_DUTY, MAX_TELEOP_DUTY)
    turn = _clamp_int(intent.turn, -MAX_TELEOP_DUTY, MAX_TELEOP_DUTY)
    duration_ms = _clamp_int(intent.duration_ms, 1, MAX_DRIVE_DURATION_MS)
    if intent.expressive:
        if throttle != 0:
            raise BodyProtocolError("expressive drive only supports in-place turn steps")
        return f"expressive {throttle} {turn} {duration_ms}"
    return f"drive {throttle} {turn} {duration_ms}"


def build_stop_command() -> str:
    return "motors off"


def drive_intent_from_payload(payload: dict[str, Any]) -> DriveIntent:
    if not isinstance(payload, dict):
        raise BodyProtocolError("teleop payload must be a JSON object")
    return DriveIntent(
        throttle=_int_value(payload.get("throttle")),
        turn=_int_value(payload.get("turn")),
        duration_ms=_int_value(payload.get("duration_ms"), DEFAULT_DRIVE_DURATION_MS),
    )


def _int_value(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        raise BodyProtocolError(f"invalid numeric value: {value}")


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))
