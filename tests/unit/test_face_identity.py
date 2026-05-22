from __future__ import annotations

from conscious_entity.identity import (
    ConfidenceLevel,
    FaceDetectionCandidate,
    FaceIdentityConfig,
    FaceIdentityError,
    FaceIdentityManager,
    FaceSignatureStore,
)


class FakeFaceProvider:
    def __init__(self, candidates):
        self.candidates = candidates

    def dependency_status(self):
        return {"available": True, "missing": []}

    def model_status(self):
        return {
            "provider": "fake",
            "model_name": "fake-face",
            "loaded": True,
            "dependencies": self.dependency_status(),
            "disabled_reason": None,
            "last_error": None,
        }

    def extract(self, _image_bytes):
        return list(self.candidates)


def _candidate(
    *,
    embedding=None,
    bbox=(100, 100, 420, 460),
    score=0.92,
    sharpness=80.0,
    pose=(0.0, 0.0, 0.0),
):
    return FaceDetectionCandidate(
        bbox=bbox,
        detection_score=score,
        embedding=embedding or [1.0, 0.0, 0.0],
        frame_width=1280,
        frame_height=720,
        pose=pose,
        quality_summary={"sharpness": sharpness},
    )


def _manager(tmp_path, candidates):
    config = FaceIdentityConfig(signature_dir=tmp_path, min_sharpness=35.0)
    return FaceIdentityManager(config, provider=FakeFaceProvider(candidates))


def test_fake_provider_capture_returns_redacted_public_payload(tmp_path):
    manager = _manager(tmp_path, [_candidate()])

    outcome = manager.capture_and_match(b"frame")
    public = outcome.to_public_dict()

    assert outcome.accepted is True
    assert public["capture"]["embedding"] == "[redacted]"
    assert public["capture"]["quality_summary"]["sharpness"] == 80.0
    assert public["match_result"]["face"]["metadata"]["face_embedding"] == "[redacted]"


def test_quality_gate_rejects_no_face_multi_face_blur_pose_and_small_face(tmp_path):
    assert _manager(tmp_path / "none", []).capture_and_match(b"frame").reason == "no_face_detected"
    assert _manager(tmp_path / "multi", [_candidate(), _candidate()]).capture_and_match(b"frame").reason == "multiple_faces_detected"
    assert _manager(tmp_path / "blur", [_candidate(sharpness=12.0)]).capture_and_match(b"frame").reason == "face_blurry"
    assert _manager(tmp_path / "pose", [_candidate(pose=(50.0, 0.0, 0.0))]).capture_and_match(b"frame").reason == "face_pose_yaw_too_large"
    assert _manager(tmp_path / "small", [_candidate(bbox=(10, 10, 40, 40))]).capture_and_match(b"frame").reason == "face_too_narrow"


def test_signature_store_writes_reads_and_matches_without_real_database(tmp_path):
    manager = _manager(tmp_path, [_candidate(embedding=[1.0, 0.0, 0.0])])
    outcome = manager.capture_and_match(b"frame")

    reference = manager.enroll_pending("visitor-a")
    records = FaceSignatureStore(tmp_path).list_records()
    matches = FaceSignatureStore(tmp_path).match([0.96, 0.28, 0.0])

    assert outcome.accepted is True
    assert reference.reference.startswith("local://face/")
    assert records[0].visitor_id == "visitor-a"
    assert matches[0].visitor_id == "visitor-a"
    assert matches[0].level == ConfidenceLevel.HIGH


def test_match_score_maps_to_medium_and_low(tmp_path):
    manager = _manager(tmp_path, [_candidate(embedding=[1.0, 0.0])])
    manager.capture_and_match(b"frame")
    manager.enroll_pending("visitor-a")
    store = FaceSignatureStore(tmp_path)

    medium = store.match([0.7, 0.714])[0]
    low = store.match([0.2, 0.98])[0]

    assert medium.level == ConfidenceLevel.MEDIUM
    assert low.level == ConfidenceLevel.LOW


def test_inactive_signature_does_not_match(tmp_path):
    manager = _manager(tmp_path, [_candidate(embedding=[1.0, 0.0])])
    manager.capture_and_match(b"frame")
    reference = manager.enroll_pending("visitor-a")
    manager.deactivate_signature(
        visitor_id="visitor-a",
        signature_id=reference.signature_id,
    )
    store = FaceSignatureStore(tmp_path)

    assert store.status()["signature_count"] == 0
    assert store.status()["inactive_signature_count"] == 1
    assert store.match([1.0, 0.0]) == []


def test_auto_capture_state_uses_in_flight_and_cooldown(tmp_path):
    manager = _manager(tmp_path, [_candidate()])

    started, reason = manager.start_auto_capture()
    blocked, blocked_reason = manager.start_auto_capture()
    manager.finish_auto_capture("accepted")
    cooldown, cooldown_reason = manager.start_auto_capture()

    assert started is True
    assert reason is None
    assert blocked is False
    assert blocked_reason == "capture_in_flight"
    assert cooldown is False
    assert cooldown_reason == "capture_cooldown"
    assert manager.status()["auto_capture"]["cooldown_remaining_seconds"] > 0


def test_enroll_requires_pending_capture(tmp_path):
    manager = _manager(tmp_path, [])

    try:
        manager.enroll_pending("visitor-a")
    except FaceIdentityError as exc:
        assert "No accepted pending" in str(exc)
    else:
        raise AssertionError("expected FaceIdentityError")
