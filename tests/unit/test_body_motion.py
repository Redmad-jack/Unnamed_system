from __future__ import annotations

import asyncio
import time

from conscious_entity.body.motion import (
    BodyMotionController,
    MacroMode,
    MotionIntent,
    MotionProfile,
    MotionStep,
    TrackPolicy,
)
from conscious_entity.body.serial_bridge import BodySerialBridge
from conscious_entity.body.telemetry import BodyTelemetryStore
from conscious_entity.state.state_core import EntityState


class FakeSerial:
    def __init__(self, *, port: str, baudrate: int, timeout: float):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self.writes: list[bytes] = []

    def readline(self) -> bytes:
        time.sleep(0.001)
        return b""

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False


def _profiles() -> dict[MotionIntent, MotionProfile]:
    return {
        MotionIntent.HOLD: MotionProfile(
            intent=MotionIntent.HOLD,
            track_policy=TrackPolicy.STRICT_TRACK,
            cooldown_ms=0,
        ),
        MotionIntent.NO_MOTION: MotionProfile(
            intent=MotionIntent.NO_MOTION,
            track_policy=TrackPolicy.DISPLAY_ONLY,
            cooldown_ms=0,
        ),
        MotionIntent.APPROACH_MICRO: MotionProfile(
            intent=MotionIntent.APPROACH_MICRO,
            track_policy=TrackPolicy.STRICT_TRACK,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=20, turn=0, duration_ms=1),),
            post_check="require_line",
        ),
        MotionIntent.RETREAT_SHORT: MotionProfile(
            intent=MotionIntent.RETREAT_SHORT,
            track_policy=TrackPolicy.STRICT_TRACK,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=-20, turn=0, duration_ms=1),),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.TURN_AWAY: MotionProfile(
            intent=MotionIntent.TURN_AWAY,
            track_policy=TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=0, turn=-20, duration_ms=1),),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.TWIST_SMALL: MotionProfile(
            intent=MotionIntent.TWIST_SMALL,
            track_policy=TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS,
            cooldown_ms=1000,
            steps=(
                MotionStep(throttle=0, turn=-20, duration_ms=1),
                MotionStep(throttle=0, turn=20, duration_ms=1),
            ),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.TWIST_MEDIUM: MotionProfile(
            intent=MotionIntent.TWIST_MEDIUM,
            track_policy=TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=0, turn=25, duration_ms=1),),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.SPIN_ONE_EXPERIMENTAL: MotionProfile(
            intent=MotionIntent.SPIN_ONE_EXPERIMENTAL,
            track_policy=TrackPolicy.DISPLAY_ONLY,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=0, turn=30, duration_ms=1),),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.WITHDRAW: MotionProfile(
            intent=MotionIntent.WITHDRAW,
            track_policy=TrackPolicy.STRICT_TRACK,
            cooldown_ms=1000,
            steps=(MotionStep(throttle=-20, turn=0, duration_ms=1),),
            post_check="require_line_or_reacquire",
        ),
        MotionIntent.REACQUIRE: MotionProfile(
            intent=MotionIntent.REACQUIRE,
            track_policy=TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS,
            cooldown_ms=0,
            command="reacquire start",
        ),
    }


def _controller(*, auto_enabled: bool = False) -> BodyMotionController:
    store = BodyTelemetryStore()
    bridge = BodySerialBridge(store, dependency_available=False)
    return BodyMotionController(
        profiles=_profiles(),
        telemetry=store,
        bridge=bridge,
        auto_enabled=auto_enabled,
        defaults={
            "require_avoidance_enabled": True,
            "require_line_calibrated": True,
            "settle_ms": 0,
        },
    )


def _ready_store(store: BodyTelemetryStore) -> None:
    store.ingest({
        "type": "status",
        "motor_armed": True,
        "avoidance_enabled": True,
        "line_enabled": True,
        "line_calibrated": True,
        "line_state": "track_follow",
    })
    store.ingest({
        "type": "line",
        "enabled": True,
        "calibrated": True,
        "state": "track_follow",
        "reason": "line_centered",
    })
    store.ingest({"type": "obstacle", "state": "clear", "avoidance_enabled": True})


def test_motion_selector_uses_state_and_body_action():
    controller = _controller()

    approach = controller.decide(
        state=EntityState(inquiry=0.7),
        body_action="lean_in",
        macro_mode=MacroMode.SPEECH_INTERACTION,
    )
    confused = controller.decide(
        state=EntityState(confusion=0.72),
        body_action="pause",
        macro_mode=MacroMode.SPEECH_INTERACTION,
    )
    defensive = controller.decide(
        state=EntityState(anger=0.7, inquiry=0.9),
        body_action="lean_in",
        macro_mode=MacroMode.SPEECH_INTERACTION,
    )

    assert approach.intent == MotionIntent.APPROACH_MICRO
    assert approach.blocker == "auto_motion_off"
    assert confused.intent == MotionIntent.TWIST_MEDIUM
    assert defensive.intent == MotionIntent.RETREAT_SHORT


def test_motion_selector_blocks_outside_speech_interaction():
    controller = _controller(auto_enabled=True)

    decision = controller.decide(
        state=EntityState(inquiry=0.9),
        body_action="lean_in",
        macro_mode=MacroMode.NON_SPEECH,
    )

    assert decision.intent == MotionIntent.NO_MOTION
    assert decision.should_execute is False
    assert decision.blocker == "not_in_speech_interaction"


def test_motion_preflight_blocks_when_hardware_not_ready():
    controller = _controller(auto_enabled=True)

    decision = controller.decide(
        state=EntityState(inquiry=0.9),
        body_action="lean_in",
        macro_mode=MacroMode.SPEECH_INTERACTION,
    )
    result = asyncio.run(controller.execute_decision(decision))

    assert result.status == "blocked"
    assert result.blocker == "bridge_disconnected"


def test_motion_execution_sends_expressive_steps_without_disabling_safety_gates():
    store = BodyTelemetryStore()
    fake_holder = {}

    def factory(**kwargs):
        fake = FakeSerial(**kwargs)
        fake_holder["serial"] = fake
        return fake

    bridge = BodySerialBridge(store, serial_factory=factory, dependency_available=True)
    controller = BodyMotionController(
        profiles=_profiles(),
        telemetry=store,
        bridge=bridge,
        auto_enabled=True,
        defaults={
            "require_avoidance_enabled": True,
            "require_line_calibrated": True,
            "settle_ms": 0,
        },
    )

    async def run():
        await bridge.connect("/dev/cu.fake")
        _ready_store(store)
        result = await controller.execute_test("TWIST_SMALL")
        return result

    result = asyncio.run(run())
    writes = fake_holder["serial"].writes

    assert result.status == "completed"
    assert b"expressive 0 -20 1\n" in writes
    assert b"expressive 0 20 1\n" in writes
    assert b"motors off\n" in writes
