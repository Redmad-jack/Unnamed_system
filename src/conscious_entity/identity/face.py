from __future__ import annotations

import importlib.util
import json
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from conscious_entity.identity.session_gating import (
    ConfidenceLevel,
    IdentityGatingConfig,
    IdentityMatchResult,
    IdentityMatchSignal,
    IdentitySignatureReference,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FaceIdentityError(RuntimeError):
    """Raised when face identity capture or matching cannot continue."""


@dataclass(frozen=True)
class FaceIdentityConfig:
    provider: str = "insightface_arcface"
    model_name: str = "buffalo_l"
    detection_size: tuple[int, int] = (640, 640)
    min_detection_score: float = 0.65
    min_face_width_ratio: float = 0.10
    min_face_height_ratio: float = 0.12
    min_sharpness: float = 12.0
    max_abs_pose_degrees: float = 35.0
    signature_dir: Path = Path("data/signatures/face")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "detection_size": list(self.detection_size),
            "min_detection_score": self.min_detection_score,
            "min_face_width_ratio": self.min_face_width_ratio,
            "min_face_height_ratio": self.min_face_height_ratio,
            "min_sharpness": self.min_sharpness,
            "max_abs_pose_degrees": self.max_abs_pose_degrees,
            "signature_dir": str(self.signature_dir),
        }


@dataclass(frozen=True)
class FaceDetectionCandidate:
    bbox: tuple[int, int, int, int]
    detection_score: float
    embedding: list[float]
    frame_width: int
    frame_height: int
    pose: tuple[float, float, float] | None = None
    quality_summary: dict[str, Any] = field(default_factory=dict)

    def quality(self) -> dict[str, Any]:
        x1, y1, x2, y2 = self.bbox
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        frame_width = max(1, self.frame_width)
        frame_height = max(1, self.frame_height)
        summary = {
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "detection_score": round(float(self.detection_score), 4),
            "face_width_ratio": round(width / frame_width, 4),
            "face_height_ratio": round(height / frame_height, 4),
        }
        if self.pose is not None:
            summary["pose"] = {
                "yaw": round(float(self.pose[0]), 2),
                "pitch": round(float(self.pose[1]), 2),
                "roll": round(float(self.pose[2]), 2),
            }
        summary.update(_public_metadata(self.quality_summary))
        return summary


class FaceProvider(Protocol):
    def dependency_status(self) -> dict[str, Any]:
        ...

    def model_status(self) -> dict[str, Any]:
        ...

    def extract(self, image_bytes: bytes) -> list[FaceDetectionCandidate]:
        ...


@dataclass(frozen=True)
class FaceCapture:
    capture_id: str
    provider: str
    model_name: str
    embedding: list[float]
    quality_summary: dict[str, Any]
    created_at: str = field(default_factory=_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "provider": self.provider,
            "model_name": self.model_name,
            "quality_summary": _public_metadata(self.quality_summary),
            "created_at": self.created_at,
            "embedding": "[redacted]",
        }


@dataclass(frozen=True)
class FaceSignatureRecord:
    signature_id: str
    visitor_id: str
    provider: str
    model_name: str
    reference: str
    embedding: list[float]
    quality_summary: dict[str, Any]
    created_at: str
    status: str = "active"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "visitor_id": self.visitor_id,
            "provider": self.provider,
            "model_name": self.model_name,
            "reference": self.reference,
            "quality_summary": _public_metadata(self.quality_summary),
            "created_at": self.created_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class FaceMatchCandidate:
    visitor_id: str
    signature_id: str
    score: float
    raw_similarity: float
    level: ConfidenceLevel
    reference: str
    quality_summary: dict[str, Any]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "visitor_id": self.visitor_id,
            "signature_id": self.signature_id,
            "score": round(self.score, 4),
            "raw_similarity": round(self.raw_similarity, 4),
            "level": self.level.value,
            "reference": self.reference,
            "quality_summary": _public_metadata(self.quality_summary),
        }


@dataclass(frozen=True)
class FaceCaptureOutcome:
    accepted: bool
    reason: str
    capture: FaceCapture | None = None
    matches: list[FaceMatchCandidate] = field(default_factory=list)
    match_result: IdentityMatchResult | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "capture": self.capture.to_public_dict() if self.capture else None,
            "matches": [item.to_public_dict() for item in self.matches[:5]],
            "match_result": self.match_result.to_public_dict() if self.match_result else None,
        }


class InsightFaceArcFaceProvider:
    def __init__(self, config: FaceIdentityConfig) -> None:
        self._config = config
        self._app: Any | None = None
        self._last_error: str | None = None

    def dependency_status(self) -> dict[str, Any]:
        insightface = importlib.util.find_spec("insightface") is not None
        onnxruntime = importlib.util.find_spec("onnxruntime") is not None
        cv2 = importlib.util.find_spec("cv2") is not None
        numpy = importlib.util.find_spec("numpy") is not None
        missing = []
        if not insightface:
            missing.append("insightface")
        if not onnxruntime:
            missing.append("onnxruntime")
        if not cv2:
            missing.append("opencv-python")
        if not numpy:
            missing.append("numpy")
        return {
            "available": not missing,
            "missing": missing,
            "insightface": insightface,
            "onnxruntime": onnxruntime,
            "opencv": cv2,
            "numpy": numpy,
            "last_error": self._last_error,
        }

    def model_status(self) -> dict[str, Any]:
        deps = self.dependency_status()
        return {
            "provider": self._config.provider,
            "model_name": self._config.model_name,
            "loaded": self._app is not None,
            "dependencies": deps,
            "disabled_reason": None
            if deps["available"]
            else "Missing optional dependencies: " + ", ".join(deps["missing"]),
            "last_error": self._last_error,
        }

    def extract(self, image_bytes: bytes) -> list[FaceDetectionCandidate]:
        if not image_bytes:
            raise FaceIdentityError("No image frame is available for face capture.")
        cv2 = _import_required("cv2", "opencv-python")
        np = _import_required("numpy", "numpy")
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if frame is None:
            raise FaceIdentityError("Could not decode face capture frame.")
        app = self._load_app()
        try:
            faces = app.get(frame)
        except Exception as exc:
            self._last_error = str(exc)
            raise FaceIdentityError(f"InsightFace extraction failed: {exc}") from exc
        height, width = _frame_size(frame)
        candidates: list[FaceDetectionCandidate] = []
        for face in faces:
            bbox = _bbox_tuple(getattr(face, "bbox", None))
            embedding = _embedding_list(getattr(face, "embedding", None))
            if bbox is None or not embedding:
                continue
            quality = {
                "sharpness": _crop_sharpness(cv2, frame, bbox),
            }
            candidates.append(
                FaceDetectionCandidate(
                    bbox=bbox,
                    detection_score=float(getattr(face, "det_score", 0.0) or 0.0),
                    embedding=embedding,
                    frame_width=width,
                    frame_height=height,
                    pose=_pose_tuple(getattr(face, "pose", None)),
                    quality_summary=quality,
                )
            )
        return candidates

    def _load_app(self) -> Any:
        if self._app is not None:
            return self._app
        deps = self.dependency_status()
        if not deps["available"]:
            missing = ", ".join(deps["missing"])
            raise FaceIdentityError(
                f"Face identity optional dependencies are missing: {missing}. "
                'Install with pip install -e ".[api,vision]".'
            )
        try:
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(name=self._config.model_name, providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=self._config.detection_size)
        except Exception as exc:
            self._last_error = str(exc)
            raise FaceIdentityError(f"Could not load InsightFace model: {exc}") from exc
        self._app = app
        self._last_error = None
        return self._app


class FaceSignatureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def status(self) -> dict[str, Any]:
        records = self._all_records()
        active_count = len([record for record in records if record.status == "active"])
        return {
            "path": str(self.root),
            "signature_count": active_count,
            "inactive_signature_count": len(records) - active_count,
        }

    def count(self) -> int:
        return len([record for record in self._all_records() if record.status == "active"])

    def save(self, visitor_id: str, capture: FaceCapture) -> IdentitySignatureReference:
        cleaned = _blank_to_none(visitor_id)
        if cleaned is None:
            raise FaceIdentityError("visitor_id is required for face signature enrollment.")
        np = _import_required("numpy", "numpy")
        self.root.mkdir(parents=True, exist_ok=True)
        signature_id = "face_" + uuid.uuid4().hex
        reference = f"local://face/{signature_id}.npz"
        metadata = {
            "signature_id": signature_id,
            "visitor_id": cleaned,
            "provider": capture.provider,
            "model_name": capture.model_name,
            "reference": reference,
            "quality_summary": _public_metadata(capture.quality_summary),
            "created_at": _now_iso(),
            "status": "active",
        }
        path = self.root / f"{signature_id}.npz"
        np.savez_compressed(
            path,
            embedding=_normalize_embedding(capture.embedding),
            metadata=json.dumps(metadata, ensure_ascii=False),
        )
        return IdentitySignatureReference(
            modality="face",
            signature_id=signature_id,
            provider=capture.provider,
            reference=reference,
            quality_summary=metadata["quality_summary"],
            created_at=metadata["created_at"],
            status="active",
        )

    def list_records(self) -> list[FaceSignatureRecord]:
        return [record for record in self._all_records() if record.status == "active"]

    def deactivate(self, *, visitor_id: str, signature_id: str) -> IdentitySignatureReference:
        cleaned_visitor = _blank_to_none(visitor_id)
        cleaned_signature = _blank_to_none(signature_id)
        if cleaned_visitor is None or cleaned_signature is None:
            raise FaceIdentityError("visitor_id and signature_id are required.")
        path = self.root / f"{cleaned_signature}.npz"
        if not path.exists():
            raise FaceIdentityError("Face signature not found.")
        np = _import_required("numpy", "numpy")
        record = self._load_record(path)
        if record.visitor_id != cleaned_visitor:
            raise FaceIdentityError("Face signature does not belong to visitor.")
        metadata = {
            "signature_id": record.signature_id,
            "visitor_id": record.visitor_id,
            "provider": record.provider,
            "model_name": record.model_name,
            "reference": record.reference,
            "quality_summary": _public_metadata(record.quality_summary),
            "created_at": record.created_at,
            "status": "inactive",
            "updated_at": _now_iso(),
        }
        np.savez_compressed(
            path,
            embedding=_normalize_embedding(record.embedding),
            metadata=json.dumps(metadata, ensure_ascii=False),
        )
        return IdentitySignatureReference(
            modality="face",
            signature_id=record.signature_id,
            provider=record.provider,
            reference=record.reference,
            quality_summary=metadata["quality_summary"],
            created_at=record.created_at,
            status="inactive",
        )

    def _all_records(self) -> list[FaceSignatureRecord]:
        if not self.root.exists():
            return []
        records: list[FaceSignatureRecord] = []
        for path in sorted(self.root.glob("*.npz")):
            try:
                record = self._load_record(path)
            except Exception:
                continue
            records.append(record)
        return records

    def match(
        self,
        embedding: list[float],
        *,
        config: IdentityGatingConfig | None = None,
        limit: int = 5,
    ) -> list[FaceMatchCandidate]:
        effective_config = config or IdentityGatingConfig()
        query = _normalize_embedding(embedding)
        matches: list[FaceMatchCandidate] = []
        for record in self.list_records():
            raw_similarity = _cosine_similarity(query, record.embedding)
            score = _similarity_to_confidence(raw_similarity)
            matches.append(
                FaceMatchCandidate(
                    visitor_id=record.visitor_id,
                    signature_id=record.signature_id,
                    score=score,
                    raw_similarity=raw_similarity,
                    level=effective_config.level_for_score(score),
                    reference=record.reference,
                    quality_summary=record.quality_summary,
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[: max(1, int(limit))]

    def _load_record(self, path: Path) -> FaceSignatureRecord:
        np = _import_required("numpy", "numpy")
        with np.load(path, allow_pickle=False) as data:
            embedding = _embedding_list(data["embedding"])
            raw_metadata = data["metadata"]
            if hasattr(raw_metadata, "item"):
                raw_metadata = raw_metadata.item()
            metadata = json.loads(str(raw_metadata))
        return FaceSignatureRecord(
            signature_id=str(metadata["signature_id"]),
            visitor_id=str(metadata["visitor_id"]),
            provider=str(metadata.get("provider") or "unknown"),
            model_name=str(metadata.get("model_name") or "unknown"),
            reference=str(metadata.get("reference") or f"local://face/{path.name}"),
            embedding=embedding,
            quality_summary=metadata.get("quality_summary")
            if isinstance(metadata.get("quality_summary"), dict)
            else {},
            created_at=str(metadata.get("created_at") or ""),
            status=str(metadata.get("status") or "active"),
        )


class FaceIdentityManager:
    def __init__(
        self,
        config: FaceIdentityConfig,
        *,
        provider: FaceProvider | None = None,
        store: FaceSignatureStore | None = None,
        gating_config: IdentityGatingConfig | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or InsightFaceArcFaceProvider(config)
        self.store = store or FaceSignatureStore(config.signature_dir)
        self.gating_config = gating_config or IdentityGatingConfig()
        self._lock = threading.Lock()
        self._pending_capture: FaceCapture | None = None
        self._last_capture: FaceCaptureOutcome | None = None
        self._last_enrolled: IdentitySignatureReference | None = None
        self._auto_capture_in_flight = False
        self._auto_capture_cooldown_seconds = 6.0
        self._last_auto_capture_started_at: str | None = None
        self._last_auto_capture_finished_at: str | None = None
        self._last_auto_capture_reason: str | None = None

    def status(self) -> dict[str, Any]:
        model = self.provider.model_status()
        with self._lock:
            pending_capture = self._pending_capture
            last_capture = self._last_capture
            last_enrolled = self._last_enrolled
            auto_capture = self._auto_capture_status_locked()
        return {
            "enabled": bool(model.get("dependencies", {}).get("available")),
            "config": self.config.to_public_dict(),
            "model": model,
            "store": self.store.status(),
            "pending_capture": pending_capture.to_public_dict()
            if pending_capture
            else None,
            "last_capture": last_capture.to_public_dict()
            if last_capture
            else None,
            "last_enrolled": last_enrolled.to_public_dict()
            if last_enrolled
            else None,
            "auto_capture": auto_capture,
        }

    def capture_and_match(self, image_bytes: bytes) -> FaceCaptureOutcome:
        try:
            candidates = self.provider.extract(image_bytes)
        except FaceIdentityError as exc:
            outcome = FaceCaptureOutcome(False, str(exc))
            with self._lock:
                self._last_capture = outcome
                self._pending_capture = None
            return outcome
        accepted, reason, candidate = self._select_candidate(candidates)
        if not accepted or candidate is None:
            outcome = FaceCaptureOutcome(False, reason)
            with self._lock:
                self._last_capture = outcome
                self._pending_capture = None
            return outcome

        capture = FaceCapture(
            capture_id="capture_" + uuid.uuid4().hex,
            provider=self.config.provider,
            model_name=self.config.model_name,
            embedding=_normalize_embedding(candidate.embedding),
            quality_summary=candidate.quality(),
        )
        matches = self.store.match(capture.embedding, config=self.gating_config)
        match_result = self._match_result(capture, matches)
        outcome = FaceCaptureOutcome(
            accepted=True,
            reason="accepted",
            capture=capture,
            matches=matches,
            match_result=match_result,
        )
        with self._lock:
            self._pending_capture = capture
            self._last_capture = outcome
        return outcome

    def enroll_pending(self, visitor_id: str) -> IdentitySignatureReference:
        with self._lock:
            pending_capture = self._pending_capture
        if pending_capture is None:
            raise FaceIdentityError("No accepted pending face capture is available for enrollment.")
        return self.enroll_capture(visitor_id, pending_capture)

    def enroll_capture(
        self,
        visitor_id: str,
        capture: FaceCapture | None,
    ) -> IdentitySignatureReference:
        if capture is None:
            raise FaceIdentityError("No accepted face capture is available for enrollment.")
        reference = self.store.save(visitor_id, capture)
        with self._lock:
            self._last_enrolled = reference
            if (
                self._pending_capture is not None
                and self._pending_capture.capture_id == capture.capture_id
            ):
                self._pending_capture = None
        return reference

    def deactivate_signature(self, *, visitor_id: str, signature_id: str) -> IdentitySignatureReference:
        return self.store.deactivate(visitor_id=visitor_id, signature_id=signature_id)

    def start_auto_capture(self) -> tuple[bool, str | None]:
        with self._lock:
            if self._auto_capture_in_flight:
                return False, "capture_in_flight"
            remaining = self._auto_capture_cooldown_remaining_locked()
            if remaining > 0:
                return False, "capture_cooldown"
            self._auto_capture_in_flight = True
            self._last_auto_capture_started_at = _now_iso()
            self._last_auto_capture_reason = "started"
            return True, None

    def finish_auto_capture(self, reason: str) -> None:
        with self._lock:
            self._auto_capture_in_flight = False
            self._last_auto_capture_finished_at = _now_iso()
            self._last_auto_capture_reason = reason

    def _auto_capture_status_locked(self) -> dict[str, Any]:
        return {
            "in_flight": self._auto_capture_in_flight,
            "cooldown_seconds": self._auto_capture_cooldown_seconds,
            "cooldown_remaining_seconds": round(
                self._auto_capture_cooldown_remaining_locked(), 2
            ),
            "last_started_at": self._last_auto_capture_started_at,
            "last_finished_at": self._last_auto_capture_finished_at,
            "last_reason": self._last_auto_capture_reason,
        }

    def _auto_capture_cooldown_remaining_locked(self) -> float:
        if self._last_auto_capture_started_at is None:
            return 0.0
        try:
            started = datetime.fromisoformat(self._last_auto_capture_started_at)
        except ValueError:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        return max(0.0, self._auto_capture_cooldown_seconds - elapsed)

    def _select_candidate(
        self,
        candidates: list[FaceDetectionCandidate],
    ) -> tuple[bool, str, FaceDetectionCandidate | None]:
        if not candidates:
            return False, "no_face_detected", None
        if len(candidates) > 1:
            return False, "multiple_faces_detected", None
        candidate = candidates[0]
        quality = candidate.quality()
        if candidate.detection_score < self.config.min_detection_score:
            return False, "low_detection_score", None
        if quality["face_width_ratio"] < self.config.min_face_width_ratio:
            return False, "face_too_narrow", None
        if quality["face_height_ratio"] < self.config.min_face_height_ratio:
            return False, "face_too_short", None
        sharpness = quality.get("sharpness")
        if isinstance(sharpness, (int, float)) and sharpness < self.config.min_sharpness:
            return False, "face_blurry", None
        pose = quality.get("pose")
        if isinstance(pose, dict):
            for key in ("yaw", "pitch", "roll"):
                value = pose.get(key)
                if isinstance(value, (int, float)) and abs(float(value)) > self.config.max_abs_pose_degrees:
                    return False, f"face_pose_{key}_too_large", None
        try:
            _normalize_embedding(candidate.embedding)
        except FaceIdentityError:
            return False, "invalid_face_embedding", None
        return True, "accepted", candidate

    def _match_result(
        self,
        capture: FaceCapture,
        matches: list[FaceMatchCandidate],
    ) -> IdentityMatchResult:
        top = matches[0] if matches else None
        face_signal = IdentityMatchSignal.build(
            modality="face",
            candidate_visitor_id=top.visitor_id if top and top.score > 0.0 else None,
            score=top.score if top else None,
            quality_status="accepted",
            quality_summary=capture.quality_summary,
            metadata={
                "provider": capture.provider,
                "model_name": capture.model_name,
                "capture_id": capture.capture_id,
                "top_signature_id": top.signature_id if top else None,
                "top_reference": top.reference if top else None,
                "raw_similarity": top.raw_similarity if top else None,
                "face_embedding": "[redacted]",
            },
            config=self.gating_config,
        )
        return IdentityMatchResult.build(
            candidate_visitor_id=face_signal.candidate_visitor_id,
            face=face_signal,
            combined_score=face_signal.score,
            decision_hint="confirm_if_high_confidence",
            metadata={
                "provider": capture.provider,
                "model_name": capture.model_name,
                "match_count": len(matches),
            },
            config=self.gating_config,
        )


def _normalize_embedding(embedding: list[float] | Any) -> list[float]:
    values = _embedding_list(embedding)
    if not values:
        raise FaceIdentityError("Face embedding is empty.")
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0.0:
        raise FaceIdentityError("Face embedding norm is zero.")
    return [float(value) / norm for value in values]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _similarity_to_confidence(raw_similarity: float) -> float:
    return round(max(0.0, min(1.0, float(raw_similarity))), 4)


def _embedding_list(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    while isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, (list, tuple)):
        return []
    return [float(item) for item in value]


def _bbox_tuple(value: Any) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    return tuple(max(0, int(round(float(item)))) for item in value[:4])  # type: ignore[return-value]


def _pose_tuple(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    return (float(value[0]), float(value[1]), float(value[2]))


def _frame_size(frame: Any) -> tuple[int, int]:
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return 1, 1
    return int(shape[0]), int(shape[1])


def _crop_sharpness(cv2: Any, frame: Any, bbox: tuple[int, int, int, int]) -> float | None:
    try:
        x1, y1, x2, y2 = bbox
        crop = frame[y1:y2, x1:x2]
        if getattr(crop, "size", 0) == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
    except Exception:
        return None


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _import_required(module_name: str, package_name: str) -> Any:
    if importlib.util.find_spec(module_name) is None:
        raise FaceIdentityError(
            f"{package_name} is not installed. Install with pip install -e \".[api,vision]\"."
        )
    return __import__(module_name)


def _public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"face_embedding", "voice_embedding", "raw_audio", "raw_image", "face_crop"}:
                result[key] = "[redacted]"
            else:
                result[key] = _public_metadata(item)
        return result
    if isinstance(value, list):
        return [_public_metadata(item) for item in value]
    return value
