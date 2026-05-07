from __future__ import annotations

from conscious_entity.perception.event_types import EventType
from conscious_entity.vision import VisionConfig, VisionManager, VisionPresenceTracker


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
