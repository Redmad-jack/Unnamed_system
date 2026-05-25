from __future__ import annotations

import asyncio
from types import SimpleNamespace

from conscious_entity.body import BodyTelemetryStore
from conscious_entity.interfaces import api


def test_body_telemetry_tracks_tof_sensors_and_obstacle_state():
    store = BodyTelemetryStore()

    snapshot = store.ingest({
        "type": "tof",
        "tca_0x70": True,
        "sensors": [
            {
                "channel": 0,
                "name": "front_left",
                "present": True,
                "initialized": True,
                "fresh": True,
                "range_valid": True,
                "distance_mm": 420,
                "status": "range valid",
            },
            {
                "channel": 1,
                "name": "front_right",
                "present": True,
                "initialized": True,
                "fresh": True,
                "range_valid": False,
                "distance_mm": None,
                "status": "signal fail",
            },
        ],
    })
    snapshot = store.ingest({
        "type": "obstacle",
        "state": "sensor_fault",
        "avoidance_enabled": True,
        "reason": "front_tof_fault",
    })

    assert snapshot["controller"]["tca_0x70"] is True
    assert snapshot["tof"]["expected_count"] == 4
    assert snapshot["tof"]["present_count"] == 2
    assert snapshot["tof"]["initialized_count"] == 2
    assert snapshot["tof"]["valid_count"] == 1
    assert snapshot["tof"]["sensors"][0]["distance_mm"] == 420
    assert snapshot["tof"]["sensors"][1]["status"] == "signal fail"
    assert snapshot["tof"]["sensors"][2]["status"] == "no update"
    assert snapshot["obstacle"]["state"] == "sensor_fault"


def test_body_telemetry_derives_motion_from_motor_outputs():
    store = BodyTelemetryStore()

    forward = store.ingest({"type": "motor_output", "m1": 80, "m2": 80, "m3": 80, "m4": 80})
    spin = store.ingest({"type": "motor_output", "m1": -90, "m2": 90, "m3": -90, "m4": 90})

    assert forward["motion"]["label"] == "forward"
    assert spin["motion"]["label"] == "spin_left"
    assert spin["motion"]["motor_duties"] == {"m1": -90.0, "m2": 90.0, "m3": -90.0, "m4": 90.0}


def test_body_telemetry_tracks_imu_state():
    store = BodyTelemetryStore()

    snapshot = store.ingest({
        "type": "imu",
        "present": True,
        "initialized": True,
        "fresh": True,
        "state": "ok",
        "age_ms": 12,
        "event_count": 7,
        "reset_count": 1,
        "yaw_deg": 12.5,
        "pitch_deg": -1.25,
        "roll_deg": 3.75,
        "quat": {"real": 0.99, "i": 0.01, "j": 0.02, "k": 0.03},
        "gyro_rad_s": {"x": 0.1, "y": -0.2, "z": 0.3},
        "accel_m_s2": {"x": 0.0, "y": 0.1, "z": 9.8},
        "last_error": "none",
    })

    assert snapshot["controller"]["imu_present"] is True
    assert snapshot["controller"]["imu_initialized"] is True
    assert snapshot["controller"]["imu_fresh"] is True
    assert snapshot["controller"]["imu_state"] == "ok"
    assert snapshot["imu"]["present"] is True
    assert snapshot["imu"]["fresh"] is True
    assert snapshot["imu"]["yaw_deg"] == 12.5
    assert snapshot["imu"]["pitch_deg"] == -1.25
    assert snapshot["imu"]["roll_deg"] == 3.75
    assert snapshot["imu"]["gyro_rad_s"]["z"] == 0.3
    assert snapshot["imu"]["accel_m_s2"]["z"] == 9.8


def test_body_telemetry_tracks_line_sensor_raw_values():
    store = BodyTelemetryStore()

    snapshot = store.ingest({
        "type": "line",
        "enabled": True,
        "calibrated": True,
        "state": "bias_right",
        "reason": "line_right",
        "detected_bits": "001",
        "position": 1850,
        "error": 850,
        "previous_error": 700,
        "correction": 42,
        "last_valid_error": 850,
        "lost_for_ms": 0,
        "reacquire_state": "idle",
        "reacquire_active": False,
        "imu_assist": False,
        "sensors": [
            {"name": "line_left", "pin": 1, "raw": 1420, "confidence": 0.1, "detected": False, "fresh": True, "age_ms": 4},
            {"name": "line_center", "pin": 2, "raw": 3180, "confidence": 0.2, "detected": False, "fresh": True, "age_ms": 4},
            {"name": "line_right", "pin": 14, "raw": 870, "confidence": 0.9, "detected": True, "floor_raw": 3200, "tape_raw": 800, "fresh": True, "age_ms": 4},
        ],
    })

    assert snapshot["controller"]["line_enabled"] is True
    assert snapshot["controller"]["line_calibrated"] is True
    assert snapshot["controller"]["line_state"] == "bias_right"
    assert snapshot["line"]["state"] == "bias_right"
    assert snapshot["line"]["detected_bits"] == "001"
    assert snapshot["line"]["position"] == 1850
    assert snapshot["line"]["error"] == 850
    assert snapshot["line"]["correction"] == 42
    assert snapshot["line"]["expected_count"] == 3
    assert snapshot["line"]["fresh_count"] == 3
    assert snapshot["line"]["sensors"][0]["name"] == "line_left"
    assert snapshot["line"]["sensors"][0]["pin"] == 1
    assert snapshot["line"]["sensors"][1]["raw"] == 3180
    assert snapshot["line"]["sensors"][2]["raw"] == 870
    assert snapshot["line"]["sensors"][2]["confidence"] == 0.9
    assert snapshot["line"]["sensors"][2]["detected"] is True
    assert snapshot["line"]["sensors"][2]["floor_raw"] == 3200


def test_body_telemetry_tracks_motion_result():
    store = BodyTelemetryStore()

    snapshot = store.ingest({
        "type": "motion_result",
        "intent": "expressive",
        "status": "completed",
        "detail": "drive_line_search",
        "line_state": "track_follow",
        "obstacle_state": "clear",
    })

    assert snapshot["motion_result"]["intent"] == "expressive"
    assert snapshot["motion_result"]["status"] == "completed"
    assert snapshot["motion_result"]["line_state"] == "track_follow"


def test_body_telemetry_applies_ack_state_changes():
    store = BodyTelemetryStore()

    armed = store.ingest({"type": "ack", "action": "arm"})
    avoidance_off = store.ingest({"type": "ack", "action": "avoidance", "enabled": False})
    line_off = store.ingest({"type": "ack", "action": "line", "enabled": False})
    calibrated = store.ingest({"type": "ack", "action": "line_calibrate", "target": "tape", "calibrated": True})
    stopped = store.ingest({"type": "ack", "action": "motors_off"})

    assert armed["controller"]["motor_armed"] is True
    assert avoidance_off["controller"]["avoidance_enabled"] is False
    assert line_off["controller"]["line_enabled"] is False
    assert calibrated["controller"]["line_calibrated"] is True
    assert stopped["controller"]["motor_armed"] is False
    assert stopped["controller"]["roam_enabled"] is False


def test_body_telemetry_prefers_live_motor_state_over_stale_status():
    store = BodyTelemetryStore()

    store.ingest({"type": "status", "last_left": 0, "last_right": 0})
    store.ingest({"type": "motor_state", "motor": 1, "duty": 70})
    store.ingest({"type": "motor_state", "motor": 3, "duty": 70})
    store.ingest({"type": "motor_state", "motor": 2, "duty": 70})
    snapshot = store.ingest({"type": "motor_state", "motor": 4, "duty": 70})

    assert snapshot["motion"]["label"] == "forward"


def test_body_status_api_creates_empty_store():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    result = asyncio.run(api.body_status(request))

    assert result["enabled"] is True
    assert result["connected"] is False
    assert result["tof"]["expected_count"] == 4
    assert result["motion"]["label"] == "stopped"


def test_body_telemetry_api_accepts_raw_esp32_payload():
    async def json_body():
        return {
            "type": "status",
            "motor_armed": True,
            "tca_0x70": True,
            "sda": 8,
            "scl": 9,
            "last_left": 60,
            "last_right": -60,
            "avoidance_enabled": False,
            "obstacle_state": "clear",
        }

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()), json=json_body)

    result = asyncio.run(api.body_telemetry_ingest(request))

    assert result["controller"]["motor_armed"] is True
    assert result["controller"]["sda"] == 8
    assert result["motion"]["label"] == "spin_right"
    assert result["obstacle"]["state"] == "clear"


def test_body_bridge_api_uses_existing_bridge():
    class FakeBridge:
        def __init__(self):
            self.commands: list[str] = []
            self.connected = False

        def status(self):
            return {"enabled": True, "connected": self.connected, "port": "/dev/cu.fake"}

        def list_ports(self):
            return [{"device": "/dev/cu.fake", "description": "Fake ESP32", "hwid": "FAKE"}]

        async def connect(self, port, *, baud=115200):
            self.connected = True
            return {"enabled": True, "connected": True, "port": port, "baud": baud}

        async def disconnect(self):
            self.connected = False
            return {"enabled": True, "connected": False, "port": "/dev/cu.fake"}

        async def send_discrete_command(self, command):
            self.commands.append(command)
            return {"enabled": True, "connected": True, "last_command": command}

        async def send_raw_command(self, command):
            self.commands.append(command)
            return {"enabled": True, "connected": True, "last_command": command}

    bridge = FakeBridge()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(body_bridge=bridge)))

    ports = asyncio.run(api.body_ports(request))
    status = asyncio.run(api.body_bridge_status(request))
    command = asyncio.run(api.body_command(SimpleNamespace(command="arm"), request))
    motor = asyncio.run(api.body_motor_test(
        SimpleNamespace(motor=2, duty=80, direction="reverse", duration_ms=800),
        request,
    ))

    assert ports["ports"][0]["device"] == "/dev/cu.fake"
    assert status["connected"] is False
    assert command["last_command"] == "arm"
    assert motor["last_command"] == "motor 2 -80 800"
    assert bridge.commands == ["arm", "motor 2 -80 800"]
