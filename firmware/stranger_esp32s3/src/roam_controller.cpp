#include "roam_controller.h"

namespace stranger {

RoamController::RoamController(MotorDriver &motors,
                               ChassisController &chassis, ObstacleGate &gate)
    : motors_(motors), chassis_(chassis), gate_(gate) {}

void RoamController::update() {
  if (!enabled_) {
    return;
  }

  if (!motors_.isArmed()) {
    stop();
    lastError_ = "motors_disarmed";
    return;
  }

  const uint32_t now = millis();
  if (now - lastCommandAtMs_ < ROAM_COMMAND_INTERVAL_MS) {
    return;
  }
  lastCommandAtMs_ = now;

  const ObstacleKind state = gate_.state().kind;
  if (state == ObstacleKind::SensorFault) {
    chassis_.drive(0, 0, ROAM_COMMAND_MS);
    mode_ = "sensor_fault_stop";
    lastError_ = "sensor_fault";
    return;
  }

  if (state == ObstacleKind::ObstacleStop) {
    commandForObstacleStop(now);
    return;
  }

  commandForClearOrSlow();
}

bool RoamController::setEnabled(bool enabled) {
  if (!enabled) {
    stop();
    return true;
  }

  if (!motors_.isArmed()) {
    lastError_ = "motors_disarmed";
    return false;
  }

  if (!gate_.enabled()) {
    lastError_ = "avoidance_disabled";
    return false;
  }

  if (gate_.state().kind == ObstacleKind::SensorFault) {
    lastError_ = "sensor_fault";
    return false;
  }

  enabled_ = true;
  escapeBacking_ = true;
  lastCommandAtMs_ = 0;
  escapePhaseStartedAtMs_ = millis();
  mode_ = "starting";
  lastError_ = "none";
  return true;
}

void RoamController::stop() {
  enabled_ = false;
  escapeBacking_ = true;
  mode_ = "stopped";
  chassis_.drive(0, 0, ROAM_COMMAND_MS);
}

bool RoamController::enabled() const { return enabled_; }

const char *RoamController::mode() const { return mode_; }

const char *RoamController::lastError() const { return lastError_; }

void RoamController::commandForObstacleStop(uint32_t now) {
  if (now - escapePhaseStartedAtMs_ >= ROAM_ESCAPE_PHASE_MS) {
    escapeBacking_ = !escapeBacking_;
    escapePhaseStartedAtMs_ = now;
  }

  if (escapeBacking_) {
    if (!chassis_.driveEscape(ROAM_BACK_DUTY, 0, ROAM_COMMAND_MS)) {
      lastError_ = chassis_.lastError();
    } else {
      lastError_ = "none";
    }
    mode_ = "escape_reverse";
    return;
  }

  if (!chassis_.driveEscape(0, escapeTurn(), ROAM_COMMAND_MS)) {
    lastError_ = chassis_.lastError();
  } else {
    lastError_ = "none";
  }
  mode_ = "escape_turn";
}

void RoamController::commandForClearOrSlow() {
  escapeBacking_ = true;
  escapePhaseStartedAtMs_ = millis();

  const ObstacleState &state = gate_.state();
  const int throttle =
      state.kind == ObstacleKind::SlowZone ? ROAM_SLOW_DUTY : ROAM_FORWARD_DUTY;
  const int turn = state.kind == ObstacleKind::SlowZone ? state.suggestedTurn : 0;

  if (!chassis_.drive(throttle, turn, ROAM_COMMAND_MS)) {
    lastError_ = chassis_.lastError();
  } else {
    lastError_ = "none";
  }
  mode_ = state.kind == ObstacleKind::SlowZone ? "slow_forward" : "forward";
}

int RoamController::escapeTurn() const {
  const int suggested = gate_.state().suggestedTurn;
  if (suggested > 0) {
    return ROAM_TURN_DUTY;
  }
  if (suggested < 0) {
    return -ROAM_TURN_DUTY;
  }
  return ROAM_TURN_DUTY;
}

}  // namespace stranger
