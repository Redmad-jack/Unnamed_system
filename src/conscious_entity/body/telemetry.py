from __future__ import annotations

import copy
import time
from typing import Any


TOF_CHANNELS = [
    {"channel": 0, "name": "front_left"},
    {"channel": 1, "name": "front_right"},
    {"channel": 2, "name": "left"},
    {"channel": 3, "name": "right"},
]

MOTOR_POSITIONS = {
    1: "front_left",
    2: "front_right",
    3: "rear_left",
    4: "rear_right",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_tof_sensor(channel: int, name: str) -> dict[str, Any]:
    return {
        "channel": channel,
        "name": name,
        "present": False,
        "initialized": False,
        "fresh": False,
        "range_valid": False,
        "timeout": False,
        "distance_mm": None,
        "age_ms": None,
        "status": "no update",
        "last_update_ms": None,
    }


def _default_motor_state(motor: int) -> dict[str, Any]:
    return {
        "motor": motor,
        "name": f"M{motor}",
        "position": MOTOR_POSITIONS[motor],
        "duty": 0,
        "pwm_pin": None,
        "dir_pin": None,
        "invert": False,
        "last_update_ms": None,
    }


class BodyTelemetryStore:
    """Small in-process cache for ESP32 body telemetry."""

    def __init__(self, *, stale_after_ms: int = 5000):
        self.stale_after_ms = stale_after_ms
        self._last_packet_ms: int | None = None
        self._last_packet: dict[str, Any] | None = None
        self._status: dict[str, Any] = {}
        self._obstacle: dict[str, Any] = {}
        self._motor_output: dict[str, Any] = {}
        self._last_ack: dict[str, Any] | None = None
        self._last_error: dict[str, Any] | None = None
        self._tof_sensors: dict[int, dict[str, Any]] = {
            item["channel"]: _default_tof_sensor(item["channel"], item["name"])
            for item in TOF_CHANNELS
        }
        self._motor_states: dict[int, dict[str, Any]] = {
            motor: _default_motor_state(motor)
            for motor in MOTOR_POSITIONS
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("body telemetry payload must be a JSON object")

        now = _now_ms()
        payload = copy.deepcopy(payload)
        msg_type = str(payload.get("type") or "unknown")
        self._last_packet_ms = now
        self._last_packet = payload

        if msg_type == "tof":
            self._ingest_tof(payload, now)
        elif msg_type in {"obstacle", "safety"}:
            self._ingest_obstacle(payload, now)
        elif msg_type == "status":
            self._status = {**self._status, **payload, "last_update_ms": now}
        elif msg_type == "motor_state":
            self._ingest_motor_state(payload, now)
        elif msg_type == "motor_output":
            self._motor_output = {**payload, "last_update_ms": now}
        elif msg_type == "ack":
            self._last_ack = {**payload, "last_update_ms": now}
        elif msg_type == "error":
            self._last_error = {**payload, "last_update_ms": now}

        return self.snapshot()

    def ingest_many(self, payloads: list[dict[str, Any]]) -> dict[str, Any]:
        for payload in payloads:
            self.ingest(payload)
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        now = _now_ms()
        last_age = None if self._last_packet_ms is None else max(0, now - self._last_packet_ms)
        telemetry_fresh = last_age is not None and last_age <= self.stale_after_ms
        tof_sensors = [copy.deepcopy(self._tof_sensors[item["channel"]]) for item in TOF_CHANNELS]
        motor_states = [copy.deepcopy(self._motor_states[motor]) for motor in sorted(self._motor_states)]
        tca_connected = self._tca_connected()
        return {
            "enabled": True,
            "connected": telemetry_fresh,
            "telemetry_fresh": telemetry_fresh,
            "last_packet_age_ms": last_age,
            "last_packet_type": self._last_packet.get("type") if self._last_packet else None,
            "controller": {
                "name": "ESP32-S3 lower body controller",
                "tca_0x70": tca_connected,
                "sda": self._status.get("sda"),
                "scl": self._status.get("scl"),
                "motor_armed": self._status.get("motor_armed"),
                "avoidance_enabled": self._status.get("avoidance_enabled"),
                "roam_enabled": self._status.get("roam_enabled"),
                "roam_mode": self._status.get("roam_mode"),
            },
            "motion": self._motion_summary(motor_states),
            "obstacle": self._obstacle_summary(),
            "tof": {
                "tca_0x70": tca_connected,
                "expected_count": len(TOF_CHANNELS),
                "present_count": sum(1 for sensor in tof_sensors if sensor.get("present")),
                "initialized_count": sum(1 for sensor in tof_sensors if sensor.get("initialized")),
                "valid_count": sum(1 for sensor in tof_sensors if sensor.get("range_valid")),
                "sensors": tof_sensors,
            },
            "motors": motor_states,
            "last_ack": copy.deepcopy(self._last_ack),
            "last_error": copy.deepcopy(self._last_error),
        }

    def _tca_connected(self) -> bool | None:
        if "tca_0x70" in self._status:
            return bool(self._status.get("tca_0x70"))
        if self._last_packet and "tca_0x70" in self._last_packet:
            return bool(self._last_packet.get("tca_0x70"))
        return None

    def _ingest_tof(self, payload: dict[str, Any], now: int) -> None:
        if "tca_0x70" in payload:
            self._status["tca_0x70"] = bool(payload.get("tca_0x70"))
        sensors = payload.get("sensors")
        if isinstance(sensors, list):
            for sensor in sensors:
                if not isinstance(sensor, dict):
                    continue
                channel = _int_or_none(sensor.get("channel"))
                if channel not in self._tof_sensors:
                    continue
                self._tof_sensors[channel] = {
                    **self._tof_sensors[channel],
                    **sensor,
                    "last_update_ms": now,
                }
            return

        flat_keys = {
            "front_left_mm": 0,
            "front_right_mm": 1,
            "left_mm": 2,
            "right_mm": 3,
        }
        for key, channel in flat_keys.items():
            if key not in payload:
                continue
            distance = _int_or_none(payload.get(key))
            self._tof_sensors[channel] = {
                **self._tof_sensors[channel],
                "present": distance is not None,
                "initialized": distance is not None,
                "fresh": True,
                "range_valid": distance is not None,
                "distance_mm": distance,
                "age_ms": 0,
                "status": "range valid" if distance is not None else "no update",
                "last_update_ms": now,
            }

    def _ingest_obstacle(self, payload: dict[str, Any], now: int) -> None:
        normalized = {**payload, "last_update_ms": now}
        if "state" not in normalized and "safety_state" in normalized:
            normalized["state"] = normalized["safety_state"]
        self._obstacle = normalized

    def _ingest_motor_state(self, payload: dict[str, Any], now: int) -> None:
        motor = _int_or_none(payload.get("motor"))
        if motor not in self._motor_states:
            return
        self._motor_states[motor] = {
            **self._motor_states[motor],
            **payload,
            "last_update_ms": now,
        }

    def _obstacle_summary(self) -> dict[str, Any]:
        if self._obstacle:
            return copy.deepcopy(self._obstacle)
        state = self._status.get("obstacle_state")
        return {
            "type": "obstacle",
            "state": state or "unknown",
            "avoidance_enabled": self._status.get("avoidance_enabled"),
            "reason": None,
            "last_update_ms": self._status.get("last_update_ms"),
        }

    def _motion_summary(self, motor_states: list[dict[str, Any]]) -> dict[str, Any]:
        duties = {int(item["motor"]): _num(item.get("duty")) for item in motor_states}
        if self._motor_output:
            for motor in range(1, 5):
                key = f"m{motor}"
                if key in self._motor_output:
                    duties[motor] = _num(self._motor_output.get(key))

        has_motor_output = any(abs(value) > 1.0 for value in duties.values()) or bool(self._motor_output)
        left = None if has_motor_output else self._status.get("last_left")
        right = None if has_motor_output else self._status.get("last_right")
        if left is None:
            left = (duties[1] + duties[3]) / 2
        if right is None:
            right = (duties[2] + duties[4]) / 2

        left = _num(left)
        right = _num(right)
        label, detail = self._motion_label(left, right)
        if self._status.get("roam_enabled"):
            label = "roaming"
            detail = str(self._status.get("roam_mode") or detail)

        return {
            "label": label,
            "detail": detail,
            "left_duty": left,
            "right_duty": right,
            "motor_duties": {f"m{motor}": duties[motor] for motor in range(1, 5)},
            "clipped": bool(self._motor_output.get("clipped")) if self._motor_output else False,
            "source": "motor_output" if self._motor_output else "status",
        }

    def _motion_label(self, left: float, right: float) -> tuple[str, str]:
        deadband = 1.0
        if abs(left) <= deadband and abs(right) <= deadband:
            return "stopped", "all motor output is zero"
        if left > deadband and right > deadband:
            if abs(left - right) <= 8:
                return "forward", "left and right sides forward"
            return ("turning_left" if left < right else "turning_right", "forward arc")
        if left < -deadband and right < -deadband:
            if abs(left - right) <= 8:
                return "reverse", "left and right sides reverse"
            return ("reverse_left" if abs(left) < abs(right) else "reverse_right", "reverse arc")
        if left < -deadband and right > deadband:
            return "spin_left", "left reverse, right forward"
        if left > deadband and right < -deadband:
            return "spin_right", "left forward, right reverse"
        return "mixed", "asymmetric wheel output"
