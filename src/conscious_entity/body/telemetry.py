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

LINE_SENSORS = [
    {"name": "line_left", "pin": 1},
    {"name": "line_center", "pin": 2},
    {"name": "line_right", "pin": 14},
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


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
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


def _default_imu_state() -> dict[str, Any]:
    return {
        "present": False,
        "initialized": False,
        "fresh": False,
        "state": "unknown",
        "status": "unknown",
        "age_ms": None,
        "event_count": 0,
        "reset_count": 0,
        "yaw_deg": None,
        "pitch_deg": None,
        "roll_deg": None,
        "quat": {"real": None, "i": None, "j": None, "k": None},
        "gyro_rad_s": {"x": None, "y": None, "z": None},
        "accel_m_s2": {"x": None, "y": None, "z": None},
        "last_error": None,
        "last_update_ms": None,
    }


def _default_line_sensor(name: str, pin: int) -> dict[str, Any]:
    return {
        "name": name,
        "pin": pin,
        "raw": None,
        "confidence": None,
        "detected": False,
        "floor_raw": None,
        "tape_raw": None,
        "fresh": False,
        "age_ms": None,
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
        self._imu_state: dict[str, Any] = _default_imu_state()
        self._line_state: dict[str, Any] = {}
        self._line_sensors: dict[str, dict[str, Any]] = {
            item["name"]: _default_line_sensor(item["name"], item["pin"])
            for item in LINE_SENSORS
        }
        self._motor_output: dict[str, Any] = {}
        self._last_motion_result: dict[str, Any] | None = None
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
            self._ingest_status_imu_fields(payload, now)
        elif msg_type == "imu":
            self._ingest_imu(payload, now)
        elif msg_type == "line":
            self._ingest_line(payload, now)
        elif msg_type == "motor_state":
            self._ingest_motor_state(payload, now)
        elif msg_type == "motor_output":
            self._motor_output = {**payload, "last_update_ms": now}
        elif msg_type == "motion_result":
            self._last_motion_result = {**payload, "last_update_ms": now}
        elif msg_type == "ack":
            self._last_ack = {**payload, "last_update_ms": now}
            self._ingest_ack_effect(payload, now)
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
        line_sensors = [copy.deepcopy(self._line_sensors[item["name"]]) for item in LINE_SENSORS]
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
                "imu_present": self._status.get("imu_present", self._imu_state.get("present")),
                "imu_initialized": self._status.get("imu_initialized", self._imu_state.get("initialized")),
                "imu_fresh": self._status.get("imu_fresh", self._imu_state.get("fresh")),
                "imu_state": self._status.get("imu_state", self._imu_state.get("state")),
                "line_enabled": self._status.get("line_enabled", self._line_state.get("enabled")),
                "line_calibrated": self._status.get("line_calibrated", self._line_state.get("calibrated")),
                "line_state": self._status.get("line_state", self._line_state.get("state")),
                "line_reacquire_state": self._status.get(
                    "line_reacquire_state",
                    self._line_state.get("reacquire_state"),
                ),
            },
            "motion": self._motion_summary(motor_states),
            "motion_result": copy.deepcopy(self._last_motion_result),
            "obstacle": self._obstacle_summary(),
            "imu": copy.deepcopy(self._imu_state),
            "line": {
                "expected_count": len(LINE_SENSORS),
                "fresh_count": sum(1 for sensor in line_sensors if sensor.get("fresh")),
                **self._line_summary(),
                "sensors": line_sensors,
            },
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

    def _ingest_status_imu_fields(self, payload: dict[str, Any], now: int) -> None:
        if not any(key in payload for key in ("imu_present", "imu_initialized", "imu_fresh", "imu_state")):
            return
        self._imu_state = {
            **self._imu_state,
            "present": bool(payload.get("imu_present", self._imu_state.get("present"))),
            "initialized": bool(payload.get("imu_initialized", self._imu_state.get("initialized"))),
            "fresh": bool(payload.get("imu_fresh", self._imu_state.get("fresh"))),
            "state": str(payload.get("imu_state") or self._imu_state.get("state") or "unknown"),
            "status": str(payload.get("imu_state") or self._imu_state.get("status") or "unknown"),
            "last_update_ms": now,
        }

    def _ingest_ack_effect(self, payload: dict[str, Any], now: int) -> None:
        action = str(payload.get("action") or "").lower()
        if action == "arm":
            self._status.update({"motor_armed": True, "last_update_ms": now})
            return
        if action in {"disarm", "motors_off", "stop"}:
            self._status.update({
                "motor_armed": False,
                "roam_enabled": False,
                "last_update_ms": now,
            })
            return
        if action == "avoidance" and "enabled" in payload:
            enabled = bool(payload.get("enabled"))
            self._status.update({"avoidance_enabled": enabled, "last_update_ms": now})
            if self._obstacle:
                self._obstacle = {**self._obstacle, "avoidance_enabled": enabled, "last_update_ms": now}
            return
        if action == "line" and "enabled" in payload:
            enabled = bool(payload.get("enabled"))
            self._line_state = {**self._line_state, "enabled": enabled, "last_update_ms": now}
            self._status.update({"line_enabled": enabled, "last_update_ms": now})
            return
        if action == "line_calibrate" and "calibrated" in payload:
            calibrated = bool(payload.get("calibrated"))
            self._line_state = {**self._line_state, "calibrated": calibrated, "last_update_ms": now}
            self._status.update({"line_calibrated": calibrated, "last_update_ms": now})
            return
        if action == "reacquire" and "enabled" in payload:
            enabled = bool(payload.get("enabled"))
            self._line_state = {
                **self._line_state,
                "reacquire_active": enabled,
                "reacquire_state": "scanning" if enabled else "idle",
                "last_update_ms": now,
            }
            self._status.update({
                "line_reacquire_state": self._line_state["reacquire_state"],
                "last_update_ms": now,
            })
            return
        if action == "roam" and "enabled" in payload:
            enabled = bool(payload.get("enabled"))
            self._status.update({
                "roam_enabled": enabled,
                "roam_mode": "line_follow" if enabled else "stopped",
                "last_update_ms": now,
            })

    def _ingest_imu(self, payload: dict[str, Any], now: int) -> None:
        state = str(payload.get("state") or payload.get("status") or "unknown")
        quat = payload.get("quat") if isinstance(payload.get("quat"), dict) else {}
        gyro = payload.get("gyro_rad_s") if isinstance(payload.get("gyro_rad_s"), dict) else {}
        accel = payload.get("accel_m_s2") if isinstance(payload.get("accel_m_s2"), dict) else {}
        self._imu_state = {
            **self._imu_state,
            "present": bool(payload.get("present", self._imu_state.get("present"))),
            "initialized": bool(payload.get("initialized", self._imu_state.get("initialized"))),
            "fresh": bool(payload.get("fresh", self._imu_state.get("fresh"))),
            "state": state,
            "status": state,
            "age_ms": _int_or_none(payload.get("age_ms")),
            "event_count": _int_or_none(payload.get("event_count")) or 0,
            "reset_count": _int_or_none(payload.get("reset_count")) or 0,
            "yaw_deg": _float_or_none(payload.get("yaw_deg")),
            "pitch_deg": _float_or_none(payload.get("pitch_deg")),
            "roll_deg": _float_or_none(payload.get("roll_deg")),
            "quat": {
                "real": _float_or_none(quat.get("real")),
                "i": _float_or_none(quat.get("i")),
                "j": _float_or_none(quat.get("j")),
                "k": _float_or_none(quat.get("k")),
            },
            "gyro_rad_s": {
                "x": _float_or_none(gyro.get("x")),
                "y": _float_or_none(gyro.get("y")),
                "z": _float_or_none(gyro.get("z")),
            },
            "accel_m_s2": {
                "x": _float_or_none(accel.get("x")),
                "y": _float_or_none(accel.get("y")),
                "z": _float_or_none(accel.get("z")),
            },
            "last_error": payload.get("last_error"),
            "last_update_ms": now,
        }
        self._status.update({
            "imu_present": self._imu_state["present"],
            "imu_initialized": self._imu_state["initialized"],
            "imu_fresh": self._imu_state["fresh"],
            "imu_state": self._imu_state["state"],
        })

    def _ingest_line(self, payload: dict[str, Any], now: int) -> None:
        self._line_state = {
            **self._line_state,
            "enabled": bool(payload.get("enabled", self._line_state.get("enabled", True))),
            "calibrated": bool(payload.get("calibrated", self._line_state.get("calibrated", False))),
            "state": str(payload.get("state") or self._line_state.get("state") or "unknown"),
            "reason": payload.get("reason", self._line_state.get("reason")),
            "detected_bits": str(payload.get("detected_bits") or self._line_state.get("detected_bits") or "000"),
            "position": _int_or_none(payload.get("position")),
            "error": _int_or_none(payload.get("error")),
            "previous_error": _int_or_none(payload.get("previous_error")),
            "correction": _int_or_none(payload.get("correction")),
            "last_valid_error": _int_or_none(payload.get("last_valid_error")),
            "lost_for_ms": _int_or_none(payload.get("lost_for_ms")),
            "reacquire_state": str(payload.get("reacquire_state") or self._line_state.get("reacquire_state") or "idle"),
            "reacquire_active": bool(payload.get("reacquire_active", self._line_state.get("reacquire_active", False))),
            "imu_assist": bool(payload.get("imu_assist", self._line_state.get("imu_assist", False))),
            "reacquire_start_yaw_deg": _float_or_none(payload.get("reacquire_start_yaw_deg")),
            "last_update_ms": now,
        }
        self._status.update({
            "line_enabled": self._line_state["enabled"],
            "line_calibrated": self._line_state["calibrated"],
            "line_state": self._line_state["state"],
            "line_reacquire_state": self._line_state["reacquire_state"],
        })

        sensors = payload.get("sensors")
        if not isinstance(sensors, list):
            return
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            name = str(sensor.get("name") or "")
            if name not in self._line_sensors:
                continue
            self._line_sensors[name] = {
                **self._line_sensors[name],
                **sensor,
                "pin": _int_or_none(sensor.get("pin")),
                "raw": _int_or_none(sensor.get("raw")),
                "confidence": _float_or_none(sensor.get("confidence")),
                "detected": bool(sensor.get("detected")),
                "floor_raw": _int_or_none(sensor.get("floor_raw")),
                "tape_raw": _int_or_none(sensor.get("tape_raw")),
                "fresh": bool(sensor.get("fresh")),
                "age_ms": _int_or_none(sensor.get("age_ms")),
                "last_update_ms": now,
            }

    def _line_summary(self) -> dict[str, Any]:
        if self._line_state:
            return copy.deepcopy(self._line_state)
        return {
            "enabled": None,
            "calibrated": False,
            "state": "unknown",
            "reason": None,
            "detected_bits": "000",
            "position": None,
            "error": None,
            "previous_error": None,
            "correction": None,
            "last_valid_error": None,
            "lost_for_ms": None,
            "reacquire_state": "idle",
            "reacquire_active": False,
            "imu_assist": False,
            "reacquire_start_yaw_deg": None,
            "last_update_ms": None,
        }

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
