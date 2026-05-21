#include "obstacle_gate.h"

#include "motor_driver.h"

namespace stranger {

ObstacleGate::ObstacleGate(TofScanner &tof) : tof_(tof) {}

void ObstacleGate::update() {
  state_.avoidanceEnabled = enabled_;
  state_.updatedAtMs = millis();
  state_.frontLeftOk = usableFrontSample(0, state_.frontLeftMm);
  state_.frontRightOk = usableFrontSample(1, state_.frontRightMm);
  state_.suggestedTurn = 0;

  if (!state_.frontLeftOk || !state_.frontRightOk) {
    state_.kind = ObstacleKind::SensorFault;
    state_.frontMinMm = 0;
    state_.reason = "front_tof_fault";
    return;
  }

  state_.frontMinMm = min(state_.frontLeftMm, state_.frontRightMm);
  state_.suggestedTurn =
      computeSuggestedTurn(state_.frontLeftMm, state_.frontRightMm);

  if (state_.frontMinMm < TOF_HARD_STOP_MM) {
    state_.kind = ObstacleKind::ObstacleStop;
    state_.reason = "front_hard_stop";
    return;
  }

  if (state_.frontMinMm < TOF_SLOW_ZONE_MM) {
    state_.kind = ObstacleKind::SlowZone;
    state_.reason = "front_slow_zone";
    return;
  }

  state_.kind = ObstacleKind::Clear;
  state_.suggestedTurn = 0;
  state_.reason = "clear";
}

GateDecision ObstacleGate::apply(int throttle, int turn,
                                 bool allowEscape) const {
  GateDecision decision;
  decision.throttle = MotorDriver::clampDuty(throttle);
  decision.turn = MotorDriver::clampDuty(turn);
  decision.state = state_.kind;
  decision.reason = state_.reason;

  if (!enabled_) {
    decision.reason = "avoidance_disabled";
    return decision;
  }

  if (state_.kind == ObstacleKind::SensorFault) {
    if (decision.throttle == 0 && decision.turn == 0) {
      decision.reason = "sensor_fault_stop";
      return decision;
    }
    decision.allowed = false;
    decision.adjusted = true;
    decision.throttle = 0;
    decision.turn = 0;
    decision.reason = "sensor_fault";
    return decision;
  }

  if (state_.kind == ObstacleKind::ObstacleStop) {
    if (decision.throttle == 0 && decision.turn == 0) {
      decision.reason = "obstacle_stop";
      return decision;
    }
    if (allowEscape && decision.throttle <= 0) {
      decision.reason = "obstacle_escape";
      return decision;
    }
    decision.allowed = false;
    decision.adjusted = true;
    decision.throttle = 0;
    decision.turn = 0;
    decision.reason = "obstacle_stop";
    return decision;
  }

  if (state_.kind == ObstacleKind::SlowZone && decision.throttle > 0) {
    if (decision.throttle > OBSTACLE_SLOW_MAX_DUTY) {
      decision.throttle = OBSTACLE_SLOW_MAX_DUTY;
      decision.adjusted = true;
    }
    if (state_.suggestedTurn != 0) {
      decision.turn = MotorDriver::clampDuty(decision.turn +
                                             state_.suggestedTurn);
      decision.adjusted = true;
    }
    decision.reason = decision.adjusted ? "slow_zone_adjusted" : "slow_zone";
    return decision;
  }

  decision.reason = "clear";
  return decision;
}

void ObstacleGate::setEnabled(bool enabled) { enabled_ = enabled; }

bool ObstacleGate::enabled() const { return enabled_; }

const ObstacleState &ObstacleGate::state() const { return state_; }

const char *ObstacleGate::stateName() const { return stateName(state_.kind); }

const char *ObstacleGate::stateName(ObstacleKind kind) const {
  switch (kind) {
    case ObstacleKind::Clear:
      return "clear";
    case ObstacleKind::SlowZone:
      return "slow_zone";
    case ObstacleKind::ObstacleStop:
      return "obstacle_stop";
    case ObstacleKind::SensorFault:
      return "sensor_fault";
  }
  return "unknown";
}

void ObstacleGate::printState(Stream &out) const {
  out.printf(
      "{\"type\":\"obstacle\",\"uptime_ms\":%lu,\"state\":\"%s\","
      "\"avoidance_enabled\":%s,\"front_left_ok\":%s,"
      "\"front_right_ok\":%s,\"front_left_mm\":",
      static_cast<unsigned long>(millis()), stateName(),
      enabled_ ? "true" : "false", state_.frontLeftOk ? "true" : "false",
      state_.frontRightOk ? "true" : "false");
  if (state_.frontLeftOk) {
    out.print(state_.frontLeftMm);
  } else {
    out.print("null");
  }
  out.print(",\"front_right_mm\":");
  if (state_.frontRightOk) {
    out.print(state_.frontRightMm);
  } else {
    out.print("null");
  }
  out.printf(",\"front_min_mm\":");
  if (state_.frontLeftOk && state_.frontRightOk) {
    out.print(state_.frontMinMm);
  } else {
    out.print("null");
  }
  out.printf(",\"suggested_turn\":%d,\"reason\":\"%s\"}\n",
             state_.suggestedTurn, state_.reason);
}

bool ObstacleGate::usableFrontSample(uint8_t index,
                                     uint16_t &distanceMm) const {
  const TofSample &s = tof_.sample(index);
  if (!s.present || !s.initialized || s.timeout || !tof_.sampleFresh(index)) {
    return false;
  }

  if (s.rangeStatus == VL53L1X::OutOfBoundsFail) {
    distanceMm = TOF_CLEAR_DISTANCE_MM;
    return true;
  }

  if (!s.rangeValid) {
    return false;
  }

  distanceMm = s.distanceMm;
  return true;
}

int ObstacleGate::computeSuggestedTurn(uint16_t frontLeftMm,
                                       uint16_t frontRightMm) const {
  const int delta = static_cast<int>(frontRightMm) - frontLeftMm;
  if (abs(delta) < OBSTACLE_BIAS_DIFF_MM) {
    return 0;
  }
  return delta > 0 ? OBSTACLE_TURN_BIAS_DUTY : -OBSTACLE_TURN_BIAS_DUTY;
}

}  // namespace stranger
