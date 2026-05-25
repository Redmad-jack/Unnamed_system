from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

from conscious_entity.body.protocol import (
    BodyProtocolError,
    DriveIntent,
    build_discrete_command,
    build_drive_command,
    build_stop_command,
)
from conscious_entity.body.telemetry import BodyTelemetryStore


DEFAULT_BAUD = 115200


def _now_ms() -> int:
    return int(time.time() * 1000)


def _import_serial_modules() -> tuple[Any | None, Any | None]:
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        return None, None
    return serial, list_ports


class BodySerialBridge:
    """USB serial bridge between the developer API and the ESP32 body controller."""

    def __init__(
        self,
        telemetry: BodyTelemetryStore,
        *,
        serial_factory: Callable[..., Any] | None = None,
        port_lister: Callable[[], list[Any]] | None = None,
        dependency_available: bool | None = None,
    ):
        serial_module, list_ports_module = _import_serial_modules()
        self.telemetry = telemetry
        self._serial_module = serial_module
        self._list_ports_module = list_ports_module
        self._serial_factory = serial_factory
        self._port_lister = port_lister
        self._dependency_available = (
            serial_module is not None if dependency_available is None else dependency_available
        )
        self._serial: Any | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._port: str | None = None
        self._baud: int = DEFAULT_BAUD
        self._rx_count = 0
        self._tx_count = 0
        self._connected_at_ms: int | None = None
        self._last_line: str | None = None
        self._last_json: dict[str, Any] | list[Any] | None = None
        self._last_error: str | None = None
        self._last_event: str = "idle"
        self._last_command: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._dependency_available,
            "dependency": "pyserial" if self._dependency_available else "missing pyserial",
            "connected": self.connected,
            "port": self._port,
            "baud": self._baud,
            "rx_count": self._rx_count,
            "tx_count": self._tx_count,
            "connected_at_ms": self._connected_at_ms,
            "last_line": self._last_line,
            "last_json": self._last_json,
            "last_error": self._last_error,
            "last_event": self._last_event,
            "last_command": self._last_command,
        }

    @property
    def connected(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", True))

    def list_ports(self) -> list[dict[str, Any]]:
        if not self._dependency_available:
            return []
        if self._port_lister is not None:
            ports = self._port_lister()
        elif self._list_ports_module is not None:
            ports = list(self._list_ports_module.comports())
        else:
            return []
        return [
            {
                "device": str(getattr(port, "device", port)),
                "description": str(getattr(port, "description", "") or ""),
                "hwid": str(getattr(port, "hwid", "") or ""),
            }
            for port in ports
        ]

    async def connect(self, port: str, *, baud: int = DEFAULT_BAUD) -> dict[str, Any]:
        if not self._dependency_available:
            raise RuntimeError('pyserial is not installed. Install with pip install -e ".[api,hardware]".')
        port = str(port or "").strip()
        if not port:
            raise ValueError("serial port is required")
        await self.disconnect(send_stop=False)
        factory = self._serial_factory
        if factory is None:
            if self._serial_module is None:
                raise RuntimeError("pyserial is not available")
            factory = self._serial_module.Serial
        self._serial = await asyncio.to_thread(factory, port=port, baudrate=int(baud), timeout=0.1)
        self._port = port
        self._baud = int(baud)
        self._connected_at_ms = _now_ms()
        self._last_error = None
        self._last_event = "connected"
        self._read_task = asyncio.create_task(self._read_loop())
        try:
            await self.send_stop()
            self._last_event = "connected; motors off"
        except Exception as exc:
            self._last_error = f"connect motors off failed: {exc}"
        return self.status()

    async def disconnect(self, *, send_stop: bool = True) -> dict[str, Any]:
        if self.connected and send_stop:
            try:
                await self.send_stop()
            except Exception as exc:
                self._last_error = str(exc)
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None
        if self._serial is not None:
            serial_obj = self._serial
            self._serial = None
            try:
                await asyncio.to_thread(serial_obj.close)
            except Exception as exc:
                self._last_error = str(exc)
        self._last_event = "disconnected"
        return self.status()

    async def send_discrete_command(self, command: str) -> dict[str, Any]:
        normalized = build_discrete_command(command)
        await self.send_raw_command(normalized)
        self._ingest_local_ack(normalized)
        return self.status()

    async def send_drive_intent(self, intent: DriveIntent) -> dict[str, Any]:
        return await self.send_raw_command(build_drive_command(intent))

    async def send_stop(self) -> dict[str, Any]:
        await self.send_raw_command(build_stop_command())
        self._ingest_local_ack(build_stop_command())
        return self.status()

    async def send_raw_command(self, command: str) -> dict[str, Any]:
        if not self.connected or self._serial is None:
            raise RuntimeError("body serial bridge is not connected")
        command = str(command or "").strip()
        if not command:
            raise BodyProtocolError("empty body command")
        payload = f"{command}\n".encode("utf-8")
        async with self._write_lock:
            await asyncio.to_thread(self._serial.write, payload)
            flush = getattr(self._serial, "flush", None)
            if callable(flush):
                await asyncio.to_thread(flush)
            self._tx_count += 1
            self._last_command = command
            self._last_event = f"tx {command}"
        return self.status()

    def _ingest_local_ack(self, command: str) -> None:
        normalized = " ".join(str(command or "").strip().lower().split())
        payload: dict[str, Any] | None = None
        if normalized == "arm":
            payload = {"type": "ack", "action": "arm"}
        elif normalized in {"disarm", "motors off"}:
            payload = {"type": "ack", "action": "motors_off" if normalized == "motors off" else "disarm"}
        elif normalized in {"avoidance on", "avoidance off"}:
            payload = {
                "type": "ack",
                "action": "avoidance",
                "enabled": normalized.endswith(" on"),
            }
        elif normalized in {"line on", "line off"}:
            payload = {
                "type": "ack",
                "action": "line",
                "enabled": normalized.endswith(" on"),
            }
        elif normalized in {"reacquire start", "reacquire stop"}:
            payload = {
                "type": "ack",
                "action": "reacquire",
                "enabled": normalized.endswith(" start"),
            }
        if payload is not None:
            self.telemetry.ingest(payload)

    def ingest_line(self, raw_line: bytes | str) -> dict[str, Any]:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace").strip()
        else:
            line = str(raw_line or "").strip()
        if not line:
            return self.status()
        self._rx_count += 1
        self._last_line = line
        self._last_event = "rx line"
        if line[0] not in "{[":
            return self.status()
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            self._last_error = f"invalid serial JSON: {exc}"
            return self.status()
        self._last_json = payload
        self._last_error = None
        if isinstance(payload, list):
            self.telemetry.ingest_many(payload)
        elif isinstance(payload, dict):
            self.telemetry.ingest(payload)
        return self.status()

    async def _read_loop(self) -> None:
        while self._serial is not None:
            try:
                raw_line = await asyncio.to_thread(self._serial.readline)
            except Exception as exc:
                self._last_error = str(exc)
                self._last_event = "read error"
                break
            if raw_line:
                self.ingest_line(raw_line)
        self._last_event = "read loop stopped"
