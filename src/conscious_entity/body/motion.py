from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from conscious_entity.body.protocol import DriveIntent
from conscious_entity.body.serial_bridge import BodySerialBridge
from conscious_entity.body.telemetry import BodyTelemetryStore
from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.state.state_core import EntityState


class MacroMode(str, Enum):
    NON_SPEECH = "NON_SPEECH"
    SPEECH_INTERACTION = "SPEECH_INTERACTION"


class MotionIntent(str, Enum):
    HOLD = "HOLD"
    APPROACH_MICRO = "APPROACH_MICRO"
    RETREAT_SHORT = "RETREAT_SHORT"
    TURN_AWAY = "TURN_AWAY"
    TWIST_SMALL = "TWIST_SMALL"
    TWIST_MEDIUM = "TWIST_MEDIUM"
    SPIN_ONE_EXPERIMENTAL = "SPIN_ONE_EXPERIMENTAL"
    WITHDRAW = "WITHDRAW"
    REACQUIRE = "REACQUIRE"
    NO_MOTION = "NO_MOTION"


class TrackPolicy(str, Enum):
    STRICT_TRACK = "strict_track"
    ALLOW_TRANSIENT_LINE_LOSS = "allow_transient_line_loss"
    DISPLAY_ONLY = "display_only"


@dataclass(frozen=True)
class MotionStep:
    throttle: int = 0
    turn: int = 0
    duration_ms: int = 1


@dataclass(frozen=True)
class MotionProfile:
    intent: MotionIntent
    track_policy: TrackPolicy
    cooldown_ms: int
    steps: tuple[MotionStep, ...] = ()
    post_check: str = "none"
    command: str | None = None
    yaw_target_deg: float | None = None

    @property
    def display_only(self) -> bool:
        return self.track_policy == TrackPolicy.DISPLAY_ONLY


@dataclass(frozen=True)
class MotionDecisionTrace:
    macro_mode: MacroMode
    body_action: str
    intent: MotionIntent
    profile: str
    track_policy: TrackPolicy
    auto_enabled: bool
    should_execute: bool
    blocker: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro_mode": self.macro_mode.value,
            "body_action": self.body_action,
            "intent": self.intent.value,
            "profile": self.profile,
            "track_policy": self.track_policy.value,
            "auto_enabled": self.auto_enabled,
            "should_execute": self.should_execute,
            "blocker": self.blocker,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class MotionExecutionResult:
    intent: MotionIntent
    status: str
    blocker: str | None = None
    detail: str = ""
    started_at_ms: int | None = None
    completed_at_ms: int | None = None
    commands_sent: list[str] = field(default_factory=list)
    line_verify: str | None = None
    yaw_delta_deg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "status": self.status,
            "blocker": self.blocker,
            "detail": self.detail,
            "started_at_ms": self.started_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "commands_sent": list(self.commands_sent),
            "line_verify": self.line_verify,
            "yaw_delta_deg": self.yaw_delta_deg,
        }


class BodyMotionController:
    """Maps expression body hints into bounded body motion attempts."""

    def __init__(
        self,
        *,
        profiles: dict[MotionIntent, MotionProfile],
        telemetry: BodyTelemetryStore,
        bridge: BodySerialBridge,
        auto_enabled: bool = False,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        self.profiles = profiles
        self.telemetry = telemetry
        self.bridge = bridge
        self.auto_enabled = bool(auto_enabled)
        self.defaults = dict(defaults or {})
        self._lock = asyncio.Lock()
        self._last_decision: MotionDecisionTrace | None = None
        self._last_result: MotionExecutionResult | None = None
        self._last_execution_by_intent: dict[MotionIntent, int] = {}
        self._task: asyncio.Task[MotionExecutionResult] | None = None

    @classmethod
    def from_config(
        cls,
        path: Path,
        *,
        telemetry: BodyTelemetryStore,
        bridge: BodySerialBridge,
    ) -> BodyMotionController:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        defaults = dict(data.get("defaults") or {})
        profiles: dict[MotionIntent, MotionProfile] = {}
        for name, raw_profile in (data.get("profiles") or {}).items():
            intent = MotionIntent(str(name))
            raw = dict(raw_profile or {})
            steps = tuple(
                MotionStep(
                    throttle=_clamp_int(step.get("throttle"), -250, 250),
                    turn=_clamp_int(step.get("turn"), -250, 250),
                    duration_ms=_clamp_int(
                        step.get("duration_ms"),
                        1,
                        int(defaults.get("max_step_duration_ms") or 500),
                    ),
                )
                for step in raw.get("steps", []) or []
                if isinstance(step, dict)
            )
            profiles[intent] = MotionProfile(
                intent=intent,
                track_policy=TrackPolicy(str(raw.get("track_policy") or "strict_track")),
                cooldown_ms=_clamp_int(
                    raw.get("cooldown_ms"),
                    0,
                    30 * 60 * 1000,
                    default=int(defaults.get("default_cooldown_ms") or 0),
                ),
                steps=steps,
                post_check=str(raw.get("post_check") or "none"),
                command=(str(raw.get("command")).strip() if raw.get("command") else None),
                yaw_target_deg=_float_or_none(raw.get("yaw_target_deg")),
            )
        return cls(
            profiles=profiles,
            telemetry=telemetry,
            bridge=bridge,
            auto_enabled=bool(defaults.get("auto_enabled", False)),
            defaults=defaults,
        )

    @property
    def in_flight(self) -> bool:
        return self._task is not None and not self._task.done()

    def configure(self, *, auto_enabled: bool | None = None) -> dict[str, Any]:
        if auto_enabled is not None:
            self.auto_enabled = bool(auto_enabled)
        return self.status()

    def decide(
        self,
        *,
        state: EntityState,
        body_action: str,
        macro_mode: MacroMode,
        auto_enabled: bool | None = None,
    ) -> MotionDecisionTrace:
        effective_auto = self.auto_enabled if auto_enabled is None else bool(auto_enabled)
        intent = self._resolve_intent(state, body_action)
        if macro_mode != MacroMode.SPEECH_INTERACTION:
            intent = MotionIntent.NO_MOTION
        profile = self.profiles.get(intent) or self.profiles[MotionIntent.NO_MOTION]
        blocker = None
        should_execute = effective_auto
        if macro_mode != MacroMode.SPEECH_INTERACTION:
            blocker = "not_in_speech_interaction"
            should_execute = False
        elif not effective_auto:
            blocker = "auto_motion_off"
            should_execute = False
        elif intent in {MotionIntent.HOLD, MotionIntent.NO_MOTION}:
            blocker = "hold_no_motor_output"
            should_execute = False
        elif profile.display_only:
            blocker = "display_only_profile"
            should_execute = False
        decision = MotionDecisionTrace(
            macro_mode=macro_mode,
            body_action=body_action,
            intent=intent,
            profile=profile.intent.value,
            track_policy=profile.track_policy,
            auto_enabled=effective_auto,
            should_execute=should_execute,
            blocker=blocker,
            summary=_decision_summary(intent, blocker),
        )
        self._last_decision = decision
        return decision

    def schedule_after_turn(
        self,
        *,
        state: EntityState,
        output: ExpressionOutput,
        macro_mode: MacroMode,
    ) -> MotionDecisionTrace:
        decision = self.decide(
            state=state,
            body_action=output.body_action,
            macro_mode=macro_mode,
        )
        if decision.should_execute and not self.in_flight:
            self._task = asyncio.create_task(self.execute_decision(decision))
        elif decision.should_execute and self.in_flight:
            decision = MotionDecisionTrace(
                macro_mode=decision.macro_mode,
                body_action=decision.body_action,
                intent=decision.intent,
                profile=decision.profile,
                track_policy=decision.track_policy,
                auto_enabled=decision.auto_enabled,
                should_execute=False,
                blocker="motion_in_flight",
                summary=f"{decision.intent.value} selected; another motion is in flight.",
            )
            self._last_decision = decision
        return decision

    async def execute_test(self, intent: str, *, allow_display_only: bool = True) -> MotionExecutionResult:
        motion_intent = MotionIntent(str(intent))
        profile = self.profiles.get(motion_intent)
        if profile is None:
            raise ValueError(f"unknown motion intent: {intent}")
        decision = MotionDecisionTrace(
            macro_mode=MacroMode.SPEECH_INTERACTION,
            body_action="manual_test",
            intent=motion_intent,
            profile=profile.intent.value,
            track_policy=profile.track_policy,
            auto_enabled=self.auto_enabled,
            should_execute=True,
            summary="Manual developer motion test.",
        )
        self._last_decision = decision
        return await self.execute_decision(decision, allow_display_only=allow_display_only)

    async def execute_decision(
        self,
        decision: MotionDecisionTrace,
        *,
        allow_display_only: bool = False,
    ) -> MotionExecutionResult:
        async with self._lock:
            profile = self.profiles.get(decision.intent)
            if profile is None:
                return self._store_result(MotionExecutionResult(
                    intent=decision.intent,
                    status="blocked",
                    blocker="missing_profile",
                    detail="No motion profile exists for this intent.",
                ))

            blocker = self._preflight(profile, allow_display_only=allow_display_only)
            if blocker is not None:
                return self._store_result(MotionExecutionResult(
                    intent=decision.intent,
                    status="blocked",
                    blocker=blocker,
                    detail=f"Motion blocked before execution: {blocker}",
                ))

            started = _now_ms()
            commands: list[str] = []
            start_yaw = _yaw(self.telemetry.snapshot())
            try:
                if profile.command:
                    await self.bridge.send_discrete_command(profile.command)
                    commands.append(profile.command)
                for step in profile.steps:
                    blocker = self._preflight(profile, allow_display_only=allow_display_only, during_step=True)
                    if blocker is not None:
                        await self.bridge.send_stop()
                        return self._store_result(MotionExecutionResult(
                            intent=decision.intent,
                            status="blocked",
                            blocker=blocker,
                            detail=f"Motion blocked during sequence: {blocker}",
                            started_at_ms=started,
                            completed_at_ms=_now_ms(),
                            commands_sent=commands,
                            yaw_delta_deg=_yaw_delta(start_yaw, _yaw(self.telemetry.snapshot())),
                        ))
                    await self.bridge.send_drive_intent(
                        DriveIntent(
                            throttle=step.throttle,
                            turn=step.turn,
                            duration_ms=step.duration_ms,
                            expressive=profile.track_policy == TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS,
                        )
                    )
                    commands.append(_drive_label(step, profile.track_policy))
                    await asyncio.sleep((step.duration_ms + int(self.defaults.get("settle_ms") or 0)) / 1000)
                if profile.steps:
                    await self.bridge.send_stop()
                    commands.append("motors off")
            except Exception as exc:
                return self._store_result(MotionExecutionResult(
                    intent=decision.intent,
                    status="error",
                    blocker="execution_error",
                    detail=str(exc),
                    started_at_ms=started,
                    completed_at_ms=_now_ms(),
                    commands_sent=commands,
                    yaw_delta_deg=_yaw_delta(start_yaw, _yaw(self.telemetry.snapshot())),
                ))

            snapshot = self.telemetry.snapshot()
            line_verify = self._line_verify(snapshot)
            status = "completed"
            detail = "Motion completed."
            if profile.post_check == "require_line" and line_verify != "line_visible":
                status = "blocked"
                detail = "Post-action line verify failed."
            elif profile.post_check == "require_line_or_reacquire" and line_verify != "line_visible":
                status = "reacquiring"
                detail = "Post-action line verify failed; reacquire requested."
                with _suppress_exception():
                    await self.bridge.send_discrete_command("reacquire start")
                    commands.append("reacquire start")

            completed = _now_ms()
            self._last_execution_by_intent[decision.intent] = completed
            return self._store_result(MotionExecutionResult(
                intent=decision.intent,
                status=status,
                detail=detail,
                started_at_ms=started,
                completed_at_ms=completed,
                commands_sent=commands,
                line_verify=line_verify,
                yaw_delta_deg=_yaw_delta(start_yaw, _yaw(snapshot)),
            ))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "auto_enabled": self.auto_enabled,
            "in_flight": self.in_flight,
            "last_decision": self._last_decision.to_dict() if self._last_decision else None,
            "last_result": self._last_result.to_dict() if self._last_result else None,
            "profiles": [
                {
                    "intent": profile.intent.value,
                    "track_policy": profile.track_policy.value,
                    "cooldown_ms": profile.cooldown_ms,
                    "step_count": len(profile.steps),
                    "post_check": profile.post_check,
                    "display_only": profile.display_only,
                }
                for profile in self.profiles.values()
            ],
        }

    def _resolve_intent(self, state: EntityState, body_action: str) -> MotionIntent:
        body_action = str(body_action or "none")
        if state.anger >= 0.60:
            return MotionIntent.RETREAT_SHORT
        if state.fatigue_level >= 0.80 or state.desperation_pressure >= 0.85:
            return MotionIntent.WITHDRAW
        if state.exposure_pressure >= 0.60:
            return MotionIntent.TURN_AWAY
        if state.confusion >= 0.85:
            return MotionIntent.SPIN_ONE_EXPERIMENTAL
        if state.confusion >= 0.70:
            return MotionIntent.TWIST_MEDIUM
        if state.confusion >= 0.50:
            return MotionIntent.TWIST_SMALL
        if body_action in {"lean_in", "circle_back"}:
            if state.anger >= 0.60 or state.fatigue_level >= 0.70 or state.exposure_pressure >= 0.65:
                return MotionIntent.HOLD
            return MotionIntent.APPROACH_MICRO
        if body_action == "step_back":
            return MotionIntent.RETREAT_SHORT
        if body_action == "withdraw":
            return MotionIntent.WITHDRAW
        if body_action == "turn_away_30deg":
            return MotionIntent.TURN_AWAY
        if body_action == "distance_increase":
            return MotionIntent.RETREAT_SHORT
        return MotionIntent.HOLD

    def _preflight(
        self,
        profile: MotionProfile,
        *,
        allow_display_only: bool,
        during_step: bool = False,
    ) -> str | None:
        if profile.display_only and not allow_display_only:
            return "display_only_profile"
        snapshot = self.telemetry.snapshot()
        bridge_status = self.bridge.status()
        controller = snapshot.get("controller", {})
        line = snapshot.get("line", {})
        obstacle = snapshot.get("obstacle", {})

        if not bridge_status.get("connected"):
            return "bridge_disconnected"
        if profile.steps and controller.get("motor_armed") is not True:
            return "motor_disarmed"
        if self.defaults.get("require_avoidance_enabled", True) and controller.get("avoidance_enabled") is not True:
            return "avoidance_off"
        obstacle_state = str(obstacle.get("state") or "unknown")
        if controller.get("avoidance_enabled") is True and obstacle_state in {"sensor_fault", "obstacle_stop"}:
            return obstacle_state
        if self.defaults.get("require_line_calibrated", True):
            if controller.get("line_enabled") is not True and line.get("enabled") is not True:
                return "line_off"
            if controller.get("line_calibrated") is not True and line.get("calibrated") is not True:
                return "line_uncalibrated"
        line_state = str(controller.get("line_state") or line.get("state") or "unknown")
        if profile.track_policy == TrackPolicy.STRICT_TRACK and line_state in {
            "sensor_fault",
            "line_lost",
            "noise",
            "wide",
            "unknown",
        }:
            return f"line_{line_state}"
        now = _now_ms()
        last = self._last_execution_by_intent.get(profile.intent)
        if last is not None and now - last < profile.cooldown_ms:
            return "cooldown"
        return None

    def _line_verify(self, snapshot: dict[str, Any]) -> str:
        line = snapshot.get("line", {})
        state = str(line.get("state") or "unknown")
        if state in {"track_follow", "bias_left", "bias_right"}:
            return "line_visible"
        if state == "reacquire":
            return "reacquiring"
        return state

    def _store_result(self, result: MotionExecutionResult) -> MotionExecutionResult:
        self._last_result = result
        return result


def _clamp_int(value: Any, minimum: int, maximum: int, *, default: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _yaw(snapshot: dict[str, Any]) -> float | None:
    imu = snapshot.get("imu", {})
    if not isinstance(imu, dict):
        return None
    value = imu.get("yaw_deg")
    return _float_or_none(value)


def _yaw_delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    delta = end - start
    while delta > 180:
        delta -= 360
    while delta < -180:
        delta += 360
    return round(delta, 2)


def _drive_label(step: MotionStep, track_policy: TrackPolicy) -> str:
    prefix = "expressive drive" if track_policy == TrackPolicy.ALLOW_TRANSIENT_LINE_LOSS else "drive"
    return f"{prefix} {step.throttle} {step.turn} {step.duration_ms}"


def _decision_summary(intent: MotionIntent, blocker: str | None) -> str:
    if blocker:
        return f"{intent.value} selected; not executing because {blocker}."
    return f"{intent.value} selected for execution."


class _suppress_exception:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return True
