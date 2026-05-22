from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TELEOP_DUTY = 80
SLOW_TELEOP_DUTY = 60
FAST_TELEOP_DUTY = 180
MAX_TELEOP_DUTY = 250
DEFAULT_DRIVE_DURATION_MS = 180
MAX_DRIVE_DURATION_MS = 500

ALLOWED_DISCRETE_COMMANDS = {
    "arm",
    "motors off",
    "avoidance on",
    "avoidance off",
    "telemetry on",
    "telemetry off",
    "tof",
    "status",
}


class BodyProtocolError(ValueError):
    """Raised when a requested body command is outside the safe v1 protocol."""


@dataclass(frozen=True)
class DriveIntent:
    throttle: int = 0
    turn: int = 0
    duration_ms: int = DEFAULT_DRIVE_DURATION_MS


def build_discrete_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().lower().split())
    if normalized not in ALLOWED_DISCRETE_COMMANDS:
        raise BodyProtocolError(f"unsupported body command: {command}")
    return normalized


def build_drive_command(intent: DriveIntent) -> str:
    throttle = _clamp_int(intent.throttle, -MAX_TELEOP_DUTY, MAX_TELEOP_DUTY)
    turn = _clamp_int(intent.turn, -MAX_TELEOP_DUTY, MAX_TELEOP_DUTY)
    duration_ms = _clamp_int(intent.duration_ms, 1, MAX_DRIVE_DURATION_MS)
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
