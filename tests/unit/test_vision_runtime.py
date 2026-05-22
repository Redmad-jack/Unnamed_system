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


def test_vision_manager_can_switch_camera_index_without_env(tmp_path):
    model = tmp_path / "model.pt"
    model.write_text("placeholder", encoding="utf-8")
    manager = VisionManager(VisionConfig(model_path=model, camera_index=0))

    status = manager.set_camera_index(2)

    assert manager.config.camera_index == 2
    assert status["config"]["camera_index"] == 2
    assert status["recognition"]["camera_index"] == 2


def test_vision_manager_scans_camera_indices(monkeypatch, tmp_path):
    model = tmp_path / "model.pt"
    model.write_text("placeholder", encoding="utf-8")

    class FakeCapture:
        def __init__(self, index):
            self.index = index

        def set(self, *_args):
            return None

        def get(self, prop):
            return 640 if prop == 3 else 480

        def isOpened(self):
            return self.index == 1

        def read(self):
            return self.index == 1, object()

        def release(self):
            return None

    class FakeCv2:
        CAP_PROP_FRAME_WIDTH = 3
        CAP_PROP_FRAME_HEIGHT = 4
        CAP_PROP_FPS = 5

        def VideoCapture(self, index):
            return FakeCapture(index)

    manager = VisionManager(VisionConfig(model_path=model, camera_index=0))
    monkeypatch.setattr(vision_runtime, "_import_required", lambda *_args: FakeCv2())

    result = manager.scan_cameras(max_index=2)

    assert result["selected_index"] == 0
    assert [item["index"] for item in result["cameras"]] == [0, 1, 2]
    assert result["cameras"][1]["opened"] is True
    assert result["cameras"][1]["frame_readable"] is True


def test_vision_manager_processes_browser_frame(monkeypatch, tmp_path):
    model = tmp_path / "model.pt"
    model.write_text("placeholder", encoding="utf-8")

    class FakeEncoded:
        def tobytes(self):
            return b"annotated-jpeg"

    class FakeCv2:
        IMREAD_COLOR = 1
        IMWRITE_JPEG_QUALITY = 1

        def imdecode(self, _array, _mode):
            return object()

        def imencode(self, _extension, _frame, _params):
            return True, FakeEncoded()

    class FakeNumpy:
        uint8 = object()

        def frombuffer(self, data, dtype=None):
            return data

    class FakeModel:
        def __init__(self, _path):
            pass

        def __call__(self, _frame, verbose=False, conf=0.45):
            return []

    manager = VisionManager(VisionConfig(model_path=model, camera_index=0))
    manager._dependency_status = lambda: {  # type: ignore[method-assign]
        "available": True,
        "missing": [],
        "cv2": True,
        "numpy": True,
        "ultralytics": True,
    }

    def fake_import_required(module_name, _package_name):
        return FakeCv2() if module_name == "cv2" else FakeNumpy()

    monkeypatch.setattr(vision_runtime, "_import_required", fake_import_required)
    monkeypatch.setattr(vision_runtime, "_import_yolo", lambda: FakeModel)

    status = manager.process_image_frame(b"jpeg-bytes", source="browser")

    assert status["frame_id"] == 1
    assert status["recognition"]["pipeline_status"] == "running"
    assert status["recognition"]["camera_status"] == "browser"
    assert status["recognition"]["source"] == "browser"
    metadata, jpeg = manager.stream_snapshot()
    assert metadata["source"] == "browser"
    assert jpeg == b"annotated-jpeg"
    assert manager.latest_frame_jpeg() == b"annotated-jpeg"
