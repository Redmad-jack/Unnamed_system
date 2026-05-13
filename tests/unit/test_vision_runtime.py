from __future__ import annotations

import pytest

from conscious_entity.vision import runtime as vision_runtime
from conscious_entity.perception.event_types import EventType
from conscious_entity.vision import (
    VisionConfig,
    VisionConfigurationError,
    VisionManager,
    VisionPresenceTracker,
)


def test_vision_config_from_env(monkeypatch, tmp_path):
    model = tmp_path / "model.pt"
    model.write_text("placeholder", encoding="utf-8")
    monkeypatch.setenv("ENTITY_VISION_MODEL_PATH", str(model))
    monkeypatch.setenv("ENTITY_VISION_CAMERA_INDEX", "1")
    monkeypatch.setenv("ENTITY_VISION_WIDTH", "640")
    monkeypatch.setenv("ENTITY_VISION_HEIGHT", "480")
    monkeypatch.setenv("ENTITY_VISION_FPS", "12")
    monkeypatch.setenv("ENTITY_VISION_CONFIDENCE", "0.6")
    monkeypatch.setenv("ENTITY_VISION_ENTER_FRAMES", "4")
    monkeypatch.setenv("ENTITY_VISION_LEAVE_SECONDS", "3.5")
    monkeypatch.setenv("ENTITY_VISION_SILENCE_SECONDS", "30")

    config = VisionConfig.from_env()

    assert config.model_path == model
    assert config.camera_index == 1
    assert config.width == 640
    assert config.height == 480
    assert config.fps == 12
    assert config.confidence == 0.6
    assert config.enter_frames == 4
    assert config.leave_seconds == 3.5
    assert config.silence_seconds == 30


def test_presence_tracker_debounces_enter_and_leave():
    tracker = VisionPresenceTracker(
        enter_frames=2,
        leave_seconds=1.0,
        silence_seconds=10.0,
    )

    assert tracker.update(True, now=0.0) == []
    assert tracker.update(True, now=0.1) == [EventType.USER_ENTERED]
    assert tracker.person_present is True
    assert tracker.update(False, now=0.5) == []
    assert tracker.update(False, now=1.2) == [EventType.USER_LEFT]
    assert tracker.person_present is False


def test_presence_tracker_emits_long_silence_once_per_window():
    tracker = VisionPresenceTracker(
        enter_frames=1,
        leave_seconds=1.0,
        silence_seconds=5.0,
    )

    assert tracker.update(True, now=0.0) == [EventType.USER_ENTERED]
    assert tracker.update(True, now=4.9) == []
    assert tracker.update(True, now=5.1) == [EventType.LONG_SILENCE_DETECTED]
    assert tracker.update(True, now=6.0) == []
    assert tracker.update(True, now=9.9) == []
    assert tracker.update(True, now=10.3) == [EventType.LONG_SILENCE_DETECTED]


def test_vision_manager_status_disabled_without_model_path():
    manager = VisionManager(VisionConfig(model_path=None))
    manager._dependency_status = lambda: {"available": True, "missing": []}  # type: ignore[method-assign]

    status = manager.status()

    assert status["enabled"] is False
    assert status["running"] is False
    assert "ENTITY_VISION_MODEL_PATH" in status["disabled_reason"]
    assert status["recognition"]["pipeline_status"] == "disabled"


def test_vision_manager_records_camera_open_failure(monkeypatch, tmp_path):
    model = tmp_path / "model.pt"
    model.write_text("placeholder", encoding="utf-8")

    class FakeCapture:
        def set(self, *_args):
            return None

        def isOpened(self):
            return False

        def release(self):
            return None

    class FakeCv2:
        CAP_PROP_FRAME_WIDTH = 3
        CAP_PROP_FRAME_HEIGHT = 4
        CAP_PROP_FPS = 5

        def VideoCapture(self, _index):
            return FakeCapture()

    manager = VisionManager(VisionConfig(model_path=model, camera_index=7))
    manager._dependency_status = lambda: {"available": True, "missing": []}  # type: ignore[method-assign]
    monkeypatch.setattr(vision_runtime, "_import_required", lambda *_args: FakeCv2())
    monkeypatch.setattr(vision_runtime, "_import_yolo", lambda: lambda _path: object())

    with pytest.raises(VisionConfigurationError):
        manager.start()

    status = manager.status()
    assert status["error"] == "Could not open camera index 7"
    assert status["recognition"]["pipeline_status"] == "error"
    assert status["recognition"]["camera_status"] == "error"
    assert "Camera permission" in status["recognition"]["access_hint"]
