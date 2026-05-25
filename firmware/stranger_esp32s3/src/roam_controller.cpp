#include "roam_controller.h"

namespace stranger {

RoamController::RoamController(MotorDriver &motors,
                               ChassisController &chassis, ObstacleGate &gate,
                               LineSensors &lineSensors, ImuMonitor &imu)
    : motors_(motors),
      chassis_(chassis),
      gate_(gate),
      lineSensors_(lineSensors),
      imu_(imu) {}

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
    commandForObstacleStop();
    return;
  }

  if (commandForLineState()) {
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

  if (!lineSensors_.enabled()) {
    lastError_ = "line_disabled";
    return false;
  }

  if (gate_.state().kind == ObstacleKind::SensorFault) {
    lastError_ = "sensor_fault";
    return false;
  }

  if (lineSensors_.state().kind == LineKind::SensorFault) {
    lastError_ = lineSensors_.state().reason;
    return false;
  }

  enabled_ = true;
  lastCommandAtMs_ = 0;
  mode_ = "starting";
  lastError_ = "none";
  return true;
}

void RoamController::stop() {
  enabled_ = false;
  mode_ = "stopped";
  lineSensors_.stopReacquire();
  chassis_.drive(0, 0, ROAM_COMMAND_MS);
}

bool RoamController::enabled() const { return enabled_; }

const char *RoamController::mode() const { return mode_; }

const char *RoamController::lastError() const { return lastError_; }

void RoamController::commandForObstacleStop() {
  lineSensors_.stopReacquire();
  if (!chassis_.drive(0, 0, ROAM_COMMAND_MS)) {
    lastError_ = chassis_.lastError();
  } else {
    lastError_ = "none";
  }
  mode_ = "obstacle_stop";
}

bool RoamController::commandForLineState() {
  const LineKind state = lineSensors_.state().kind;
  if (state == LineKind::SensorFault) {
    if (!chassis_.drive(0, 0, ROAM_COMMAND_MS)) {
      lastError_ = chassis_.lastError();
    } else {
      lastError_ = lineSensors_.state().reason;
    }
    mode_ = "line_sensor_fault_stop";
    return true;
  }

  if (state == LineKind::LineLost || state == LineKind::Reacquire) {
    if (!lineSensors_.reacquiring()) {
      lineSensors_.requestReacquire(imu_.yawDeg(), imu_.yawAvailable());
    }
    if (lineSensors_.reacquireFailed()) {
      if (!chassis_.drive(0, 0, ROAM_COMMAND_MS)) {
        lastError_ = chassis_.lastError();
      } else {
        lastError_ = "line_reacquire_timeout";
      }
      mode_ = "line_lost_stop";
      return true;
    }

    const int turn =
        lineSensors_.reacquireTurnDuty(imu_.yawDeg(), imu_.yawAvailable());
    if (turn == 0) {
      if (!chassis_.drive(0, 0, ROAM_COMMAND_MS)) {
        lastError_ = chassis_.lastError();
      } else {
        lastError_ = "line_reacquire_timeout";
      }
      mode_ = "line_lost_stop";
      return true;
    }

    if (!chassis_.driveLineSearch(0, turn, LINE_REACQUIRE_COMMAND_MS)) {
      lastError_ = chassis_.lastError();
    } else {
      lastError_ = "none";
    }
    mode_ = "reacquire";
    return true;
  }
  return false;
}

void RoamController::commandForClearOrSlow() {
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

}  // namespace stranger
