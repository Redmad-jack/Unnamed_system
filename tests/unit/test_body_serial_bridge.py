from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from conscious_entity.body.protocol import DriveIntent
from conscious_entity.body.serial_bridge import BodySerialBridge
from conscious_entity.body.telemetry import BodyTelemetryStore


class FakeSerial:
    def __init__(self, *, port: str, baudrate: int, timeout: float):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self.writes: list[bytes] = []

    def readline(self) -> bytes:
        time.sleep(0.01)
        return b""

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False


def test_body_serial_bridge_ingests_json_lines_into_telemetry():
    store = BodyTelemetryStore()
    bridge = BodySerialBridge(store, dependency_available=False)

    bridge.ingest_line(
        b'{"type":"tof","tca_0x70":true,"sensors":[{"channel":0,"present":true,"initialized":true,"range_valid":true,"distance_mm":120}]}'
    )
    bridge.ingest_line('{"type":"obstacle","state":"clear","avoidance_enabled":true}')
    bridge.ingest_line('{"type":"imu","present":true,"initialized":true,"fresh":true,"state":"ok","yaw_deg":4.5}')

    status = bridge.status()
    snapshot = store.snapshot()
    assert status["rx_count"] == 3
    assert snapshot["controller"]["tca_0x70"] is True
    assert snapshot["tof"]["sensors"][0]["distance_mm"] == 120
    assert snapshot["obstacle"]["state"] == "clear"
    assert snapshot["imu"]["present"] is True
    assert snapshot["imu"]["yaw_deg"] == 4.5


def test_body_serial_bridge_connects_sends_and_disconnects_with_fake_serial():
    fake_holder = {}

    def factory(**kwargs):
        fake = FakeSerial(**kwargs)
        fake_holder["serial"] = fake
        return fake

    bridge = BodySerialBridge(
        BodyTelemetryStore(),
        serial_factory=factory,
        port_lister=lambda: [SimpleNamespace(device="/dev/cu.fake", description="Fake ESP32", hwid="FAKE")],
        dependency_available=True,
    )

    async def run():
        connected = await bridge.connect("/dev/cu.fake", baud=115200)
        await bridge.send_discrete_command("arm")
        await bridge.send_drive_intent(DriveIntent(throttle=80, turn=0, duration_ms=180))
        disconnected = await bridge.disconnect()
        return connected, disconnected

    connected, disconnected = asyncio.run(run())

    fake = fake_holder["serial"]
    assert connected["connected"] is True
    assert disconnected["connected"] is False
    assert b"arm\n" in fake.writes
    assert b"drive 80 0 180\n" in fake.writes
    assert fake.writes[-1] == b"motors off\n"
