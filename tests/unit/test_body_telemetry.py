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

    bridge = FakeBridge()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(body_bridge=bridge)))

    ports = asyncio.run(api.body_ports(request))
    status = asyncio.run(api.body_bridge_status(request))
    command = asyncio.run(api.body_command(SimpleNamespace(command="arm"), request))

    assert ports["ports"][0]["device"] == "/dev/cu.fake"
    assert status["connected"] is False
    assert command["last_command"] == "arm"
    assert bridge.commands == ["arm"]
