from __future__ import annotations

import importlib.util
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conscious_entity.perception.event_types import EventType

_PERSON_CLASS_ID = 0
_DEFAULT_JPEG_QUALITY = 80


class VisionConfigurationError(RuntimeError):
    """Raised when the optional vision runtime is unavailable or misconfigured."""


@dataclass(frozen=True)
class VisionConfig:
    model_path: Path | None = None
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 10
    confidence: float = 0.45
    enter_frames: int = 3
    leave_seconds: float = 2.0
    silence_seconds: float = 45.0

    @classmethod
    def from_env(cls) -> VisionConfig:
        model = _blank_to_none(os.getenv("ENTITY_VISION_MODEL_PATH"))
        return cls(
            model_path=Path(model).expanduser() if model else None,
            camera_index=_env_int("ENTITY_VISION_CAMERA_INDEX", 0, minimum=0),
            width=_env_int("ENTITY_VISION_WIDTH", 1280, minimum=160),
            height=_env_int("ENTITY_VISION_HEIGHT", 720, minimum=120),
            fps=_env_int("ENTITY_VISION_FPS", 10, minimum=1, maximum=30),
            confidence=_env_float("ENTITY_VISION_CONFIDENCE", 0.45, minimum=0.01, maximum=0.99),
            enter_frames=_env_int("ENTITY_VISION_ENTER_FRAMES", 3, minimum=1, maximum=60),
            leave_seconds=_env_float("ENTITY_VISION_LEAVE_SECONDS", 2.0, minimum=0.1, maximum=3600.0),
            silence_seconds=_env_float("ENTITY_VISION_SILENCE_SECONDS", 45.0, minimum=1.0, maximum=86400.0),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "model_path": str(self.model_path) if self.model_path else None,
            "camera_index": self.camera_index,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "confidence": self.confidence,
            "enter_frames": self.enter_frames,
            "leave_seconds": self.leave_seconds,
            "silence_seconds": self.silence_seconds,
        }


@dataclass(frozen=True)
class VisionDetection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]

    def to_public_dict(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        }


@dataclass(frozen=True)
class VisionRuntimeEvent:
    event_type: EventType
    timestamp: datetime
    reason: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
        }


@dataclass
class VisionSnapshot:
    frame_id: int = 0
    timestamp: datetime | None = None
    detections: list[VisionDetection] = field(default_factory=list)
    events: list[VisionRuntimeEvent] = field(default_factory=list)
    jpeg: bytes | None = None

    def metadata(self, config: VisionConfig, running: bool, error: str | None) -> dict[str, Any]:
        return {
            "type": "vision_frame",
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "running": running,
            "error": error,
            "camera": {
                "index": config.camera_index,
                "width": config.width,
                "height": config.height,
                "fps": config.fps,
            },
            "detections": [item.to_public_dict() for item in self.detections],
            "events": [item.to_public_dict() for item in self.events],
        }


class VisionPresenceTracker:
    def __init__(
        self,
        *,
        enter_frames: int,
        leave_seconds: float,
        silence_seconds: float,
    ) -> None:
        self._enter_frames = max(1, int(enter_frames))
        self._leave_seconds = max(0.1, float(leave_seconds))
        self._silence_seconds = max(1.0, float(silence_seconds))
        self._person_present = False
        self._consecutive_present = 0
        self._last_seen_at: float | None = None
        self._last_activity_at: float | None = None
        self._last_silence_event_at: float | None = None

    @property
    def person_present(self) -> bool:
        return self._person_present

    def mark_activity(self, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        self._last_activity_at = current

    def update(self, has_person: bool, now: float | None = None) -> list[EventType]:
        current = time.time() if now is None else float(now)
        events: list[EventType] = []

        if has_person:
            self._last_seen_at = current
            self._consecutive_present += 1
            if not self._person_present and self._consecutive_present >= self._enter_frames:
                self._person_present = True
                self._last_activity_at = current
                self._last_silence_event_at = None
                events.append(EventType.USER_ENTERED)
        else:
            self._consecutive_present = 0
            if (
                self._person_present
                and self._last_seen_at is not None
                and current - self._last_seen_at >= self._leave_seconds
            ):
                self._person_present = False
                self._last_activity_at = current
                self._last_silence_event_at = None
                events.append(EventType.USER_LEFT)

        if self._person_present:
            last_activity = self._last_activity_at if self._last_activity_at is not None else current
            long_enough = current - last_activity >= self._silence_seconds
            repeated = (
                self._last_silence_event_at is not None
                and current - self._last_silence_event_at < self._silence_seconds
            )
            if long_enough and not repeated:
                self._last_silence_event_at = current
                self._last_activity_at = current
                events.append(EventType.LONG_SILENCE_DETECTED)

        return events


class VisionManager:
    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or VisionConfig.from_env()
        self._tracker = VisionPresenceTracker(
            enter_frames=self.config.enter_frames,
            leave_seconds=self.config.leave_seconds,
            silence_seconds=self.config.silence_seconds,
        )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture: Any = None
        self._running = False
        self._error: str | None = None
        self._snapshot = VisionSnapshot()
        self._recent_events: list[VisionRuntimeEvent] = []
        self._pending_events: list[EventType] = []

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def mark_activity(self) -> None:
        self._tracker.mark_activity()

    def status(self) -> dict[str, Any]:
        deps = self._dependency_status()
        model_ok = bool(self.config.model_path and self.config.model_path.exists())
        disabled_reason = None
        if not deps["available"]:
            disabled_reason = "Missing optional dependencies: " + ", ".join(deps["missing"])
        elif self.config.model_path is None:
            disabled_reason = "ENTITY_VISION_MODEL_PATH is not configured"
        elif not model_ok:
            disabled_reason = f"ENTITY_VISION_MODEL_PATH does not exist: {self.config.model_path}"
        with self._lock:
            return {
                "enabled": deps["available"] and model_ok,
                "running": self._running,
                "error": self._error,
                "disabled_reason": disabled_reason,
                "dependencies": deps,
                "model_path": str(self.config.model_path) if self.config.model_path else None,
                "model": {
                    "path": str(self.config.model_path) if self.config.model_path else None,
                    "exists": model_ok,
                },
                "config": self.config.to_public_dict(),
                "frame_id": self._snapshot.frame_id,
                "timestamp": self._snapshot.timestamp.isoformat() if self._snapshot.timestamp else None,
                "detections": [item.to_public_dict() for item in self._snapshot.detections],
                "events": [item.to_public_dict() for item in self._recent_events[-20:]],
                "recent_events": [item.to_public_dict() for item in self._recent_events[-20:]],
                "latest": {
                    "frame_id": self._snapshot.frame_id,
                    "timestamp": self._snapshot.timestamp.isoformat() if self._snapshot.timestamp else None,
                    "detections": [item.to_public_dict() for item in self._snapshot.detections],
                },
            }

    def start(self) -> dict[str, Any]:
        self._ensure_ready()
        if self.running:
            return self.status()
        with self._lock:
            self._error = None
            self._stop_event.clear()

        cv2 = _import_required("cv2", "opencv-python")
        yolo_cls = _import_yolo()
        model = yolo_cls(str(self.config.model_path))
        capture = cv2.VideoCapture(self.config.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        capture.set(cv2.CAP_PROP_FPS, self.config.fps)
        if not capture.isOpened():
            capture.release()
            raise VisionConfigurationError(
                f"Could not open camera index {self.config.camera_index}"
            )

        with self._lock:
            self._capture = capture
            self._running = True
        self._thread = threading.Thread(
            target=self._run_worker,
            args=(cv2, model, capture),
            daemon=True,
            name="vision-yolo-worker",
        )
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._running = False
            self._thread = None
            capture = self._capture
            self._capture = None
        if capture is not None:
            capture.release()
        return self.status()

    def stream_snapshot(self) -> tuple[dict[str, Any], bytes | None]:
        with self._lock:
            metadata = self._snapshot.metadata(self.config, self._running, self._error)
            return metadata, self._snapshot.jpeg

    def pop_pending_events(self) -> list[EventType]:
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()
        return events

    def _ensure_ready(self) -> None:
        deps = self._dependency_status()
        if not deps["available"]:
            missing = ", ".join(deps["missing"])
            raise VisionConfigurationError(
                f"Vision optional dependencies are missing: {missing}. "
                'Install with pip install -e ".[api,vision]".'
            )
        if self.config.model_path is None:
            raise VisionConfigurationError("ENTITY_VISION_MODEL_PATH is not configured.")
        if not self.config.model_path.exists():
            raise VisionConfigurationError(
                f"ENTITY_VISION_MODEL_PATH does not exist: {self.config.model_path}"
            )

    def _run_worker(self, cv2: Any, model: Any, capture: Any) -> None:
        frame_interval = 1.0 / max(1, self.config.fps)
        try:
            while not self._stop_event.is_set():
                started = time.time()
                ok, frame = capture.read()
                if not ok:
                    self._set_error("Camera frame read failed.")
                    time.sleep(frame_interval)
                    continue

                detections = self._detect_people(model, frame)
                self._draw_detections(cv2, frame, detections)
                encoded_ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), _DEFAULT_JPEG_QUALITY],
                )
                jpeg = encoded.tobytes() if encoded_ok else None
                events = self._tracker.update(bool(detections), now=started)
                runtime_events = [
                    VisionRuntimeEvent(event, datetime.now(timezone.utc), "yolo_person_presence")
                    for event in events
                ]
                self._publish_snapshot(detections, runtime_events, jpeg)
                elapsed = time.time() - started
                time.sleep(max(0.0, frame_interval - elapsed))
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            with self._lock:
                self._running = False

    def _detect_people(self, model: Any, frame: Any) -> list[VisionDetection]:
        results = model(frame, verbose=False, conf=self.config.confidence)
        detections: list[VisionDetection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls = _box_scalar(getattr(box, "cls", None))
                if int(cls) != _PERSON_CLASS_ID:
                    continue
                confidence = float(_box_scalar(getattr(box, "conf", None)))
                if confidence < self.config.confidence:
                    continue
                xyxy = getattr(box, "xyxy", None)
                if xyxy is None:
                    continue
                coords = _box_coords(xyxy)
                if coords is None:
                    continue
                detections.append(VisionDetection("person", confidence, coords))
        return detections

    def _draw_detections(self, cv2: Any, frame: Any, detections: list[VisionDetection]) -> None:
        for item in detections:
            x1, y1, x2, y2 = item.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), (92, 124, 250), 2)
            cv2.putText(
                frame,
                f"person {item.confidence:.2f}",
                (x1, max(12, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (92, 124, 250),
                1,
                cv2.LINE_AA,
            )

    def _publish_snapshot(
        self,
        detections: list[VisionDetection],
        events: list[VisionRuntimeEvent],
        jpeg: bytes | None,
    ) -> None:
        with self._lock:
            frame_id = self._snapshot.frame_id + 1
            if events:
                self._recent_events.extend(events)
                self._recent_events = self._recent_events[-100:]
                self._pending_events.extend(event.event_type for event in events)
            self._snapshot = VisionSnapshot(
                frame_id=frame_id,
                timestamp=datetime.now(timezone.utc),
                detections=detections,
                events=events,
                jpeg=jpeg,
            )
            self._error = None

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._error = message

    def _dependency_status(self) -> dict[str, Any]:
        missing: list[str] = []
        cv2_available = importlib.util.find_spec("cv2") is not None
        ultralytics_available = importlib.util.find_spec("ultralytics") is not None
        if not cv2_available:
            missing.append("opencv-python")
        if not ultralytics_available:
            missing.append("ultralytics")
        return {
            "available": not missing,
            "missing": missing,
            "cv2": cv2_available,
            "ultralytics": ultralytics_available,
        }


def _box_scalar(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "item"):
        return float(value.item())
    if hasattr(value, "tolist"):
        listed = value.tolist()
        if isinstance(listed, list):
            while isinstance(listed, list) and listed:
                listed = listed[0]
            return float(listed or 0.0)
    if isinstance(value, (list, tuple)) and value:
        return _box_scalar(value[0])
    return float(value)


def _box_coords(value: Any) -> tuple[int, int, int, int] | None:
    if hasattr(value, "tolist"):
        coords = value.tolist()
    else:
        coords = value
    while isinstance(coords, list) and coords and isinstance(coords[0], list):
        coords = coords[0]
    if not isinstance(coords, (list, tuple)) or len(coords) < 4:
        return None
    return tuple(max(0, int(round(float(item)))) for item in coords[:4])  # type: ignore[return-value]


def _import_required(module_name: str, package_name: str) -> Any:
    if importlib.util.find_spec(module_name) is None:
        raise VisionConfigurationError(
            f"{package_name} is not installed. Install with pip install -e \".[api,vision]\"."
        )
    return __import__(module_name)


def _import_yolo() -> Any:
    if importlib.util.find_spec("ultralytics") is None:
        raise VisionConfigurationError(
            'ultralytics is not installed. Install with pip install -e ".[api,vision]".'
        )
    from ultralytics import YOLO

    return YOLO


def _env_int(name: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    raw = _blank_to_none(os.getenv(name))
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = _blank_to_none(os.getenv(name))
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
