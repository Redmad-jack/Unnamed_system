from __future__ import annotations

import asyncio
from types import SimpleNamespace

from conscious_entity.body.motion import BodyMotionController, MotionIntent, MotionProfile, TrackPolicy
from conscious_entity.body.serial_bridge import BodySerialBridge
from conscious_entity.body.telemetry import BodyTelemetryStore
from conscious_entity.interfaces.api_models import BodyMotionConfigRequest, BodyMotionTestRequest
from conscious_entity.interfaces.api_routes import body_motion_config, body_motion_status, body_motion_test, body_status


def _request():
    store = BodyTelemetryStore()
    bridge = BodySerialBridge(store, dependency_available=False)
    controller = BodyMotionController(
        profiles={
            MotionIntent.HOLD: MotionProfile(MotionIntent.HOLD, TrackPolicy.STRICT_TRACK, 0),
            MotionIntent.NO_MOTION: MotionProfile(MotionIntent.NO_MOTION, TrackPolicy.DISPLAY_ONLY, 0),
        },
        telemetry=store,
        bridge=bridge,
        auto_enabled=False,
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        body_telemetry=store,
        body_bridge=bridge,
        body_motion=controller,
    )))


def test_body_motion_status_and_config_default_off():
    request = _request()

    status = asyncio.run(body_motion_status(request))
    updated = asyncio.run(body_motion_config(BodyMotionConfigRequest(auto_enabled=True), request))

    assert status["auto_enabled"] is False
    assert updated["auto_enabled"] is True


def test_body_status_embeds_runtime_motion_summary():
    request = _request()

    status = asyncio.run(body_status(request))

    assert status["runtime_motion"]["auto_enabled"] is False
    assert status["runtime_motion"]["last_decision"] is None


def test_body_motion_test_only_accepts_known_intent():
    request = _request()

    result = asyncio.run(body_motion_test(BodyMotionTestRequest(intent="NO_MOTION"), request))

    assert result["result"]["status"] == "blocked"
    assert result["result"]["blocker"] == "bridge_disconnected"
