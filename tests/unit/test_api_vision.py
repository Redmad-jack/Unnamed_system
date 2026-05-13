from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conscious_entity.interfaces import api
from conscious_entity.vision import VisionConfigurationError


class _FakeVisionManager:
    def __init__(self, *, start_error: Exception | None = None):
        self.start_error = start_error
        self.started = False
        self.stopped = False

    def status(self):
        return {
            "enabled": False,
            "running": self.started and not self.stopped,
            "error": None,
            "disabled_reason": "test disabled",
        }

    def start(self):
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        return self.status()

    def stop(self):
        self.stopped = True
        return self.status()


def _request(manager):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(vision_manager=manager)))


def test_vision_status_returns_disabled_state():
    manager = _FakeVisionManager()

    result = asyncio.run(api.vision_status(_request(manager)))

    assert result["enabled"] is False
    assert result["disabled_reason"] == "test disabled"


def test_vision_start_reports_configuration_error():
    manager = _FakeVisionManager(
        start_error=VisionConfigurationError("ENTITY_VISION_MODEL_PATH is not configured.")
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.vision_start(_request(manager)))

    assert exc.value.status_code == 400
    assert "ENTITY_VISION_MODEL_PATH" in exc.value.detail


def test_vision_stop_delegates_to_manager():
    manager = _FakeVisionManager()

    result = asyncio.run(api.vision_stop(_request(manager)))

    assert manager.stopped is True
    assert result["running"] is False


def test_identity_status_reports_controller_state():
    controller = SimpleNamespace(status=lambda: {"enabled": True, "status": {"runtime_state": "idle"}})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(identity_gating=controller)))

    result = asyncio.run(api.identity_status(request))

    assert result["enabled"] is True
    assert result["status"]["runtime_state"] == "idle"
