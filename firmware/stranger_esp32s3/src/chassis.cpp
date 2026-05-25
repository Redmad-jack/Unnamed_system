#include "chassis.h"

namespace stranger {

ChassisController::ChassisController(MotorDriver &motors) : motors_(motors) {}

void ChassisController::setObstacleGate(ObstacleGate *gate) { gate_ = gate; }

void ChassisController::setLineSensors(LineSensors *lineSensors) {
  lineSensors_ = lineSensors;
}

bool ChassisController::drive(int throttle, int turn, int durationMs) {
  return applyDrive(throttle, turn, durationMs, false, false);
}

bool ChassisController::driveEscape(int throttle, int turn, int durationMs) {
  return applyDrive(throttle, turn, durationMs, true, false);
}

bool ChassisController::driveLineSearch(int throttle, int turn,
                                        int durationMs) {
  return applyDrive(throttle, turn, durationMs, false, true);
}

bool ChassisController::applyDrive(int throttle, int turn, int durationMs,
                                   bool allowEscape, bool allowLineSearch) {
  if ((throttle != 0 || turn != 0) && !motors_.isArmed()) {
    lastError_ = "motors_disarmed";
    return false;
  }

  LineDecision lineDecision;
  lineDecision.throttle = MotorDriver::clampDuty(throttle);
  lineDecision.turn = MotorDriver::clampDuty(turn);
  lineDecision.reason = "no_line_gate";

  if (lineSensors_ != nullptr) {
    lineDecision = lineSensors_->apply(throttle, turn, allowLineSearch);
    if (!lineDecision.allowed) {
      motors_.stopAll();
      resetLastMix();
      lastLineDecision_ = lineDecision;
      lastError_ = lineDecision.reason;
      return false;
    }
  }

  GateDecision decision;
  decision.throttle = lineDecision.throttle;
  decision.turn = lineDecision.turn;
  decision.reason = "no_gate";

  if (gate_ != nullptr) {
    decision =
        gate_->apply(lineDecision.throttle, lineDecision.turn, allowEscape);
    if (!decision.allowed) {
      motors_.stopAll();
      resetLastMix();
      lastLineDecision_ = lineDecision;
      lastGateDecision_ = decision;
      lastError_ = decision.reason;
      return false;
    }
  }

  const DriveMix requested = mix(decision.throttle, decision.turn);
  const bool applied = motors_.applyWheelDuties(
      requested.frontLeft, requested.frontRight, requested.rearLeft,
      requested.rearRight, durationMs);
  if (applied) {
    lastMix_ = requested;
    lastLineDecision_ = lineDecision;
    lastGateDecision_ = decision;
    lastError_ = "none";
  } else {
    lastError_ = motors_.lastError();
  }
  return applied;
}

bool ChassisController::spin(int duty, int durationMs) {
  return drive(0, duty, durationMs);
}

void ChassisController::resetLastMix() { lastMix_ = {0, 0, 0, 0, 0, 0}; }

DriveMix ChassisController::mix(int throttle, int turn) const {
  int left = MotorDriver::clampDuty(throttle + turn);
  int right = MotorDriver::clampDuty(throttle - turn);

  const int rawLeft = throttle + turn;
  const int rawRight = throttle - turn;
  const int maxRaw = max(abs(rawLeft), abs(rawRight));
  if (maxRaw > MOTOR_TEST_MAX_DUTY) {
    left = rawLeft * MOTOR_TEST_MAX_DUTY / maxRaw;
    right = rawRight * MOTOR_TEST_MAX_DUTY / maxRaw;
  }

  return {left, right, left, right, left, right};
}

const DriveMix &ChassisController::lastMix() const { return lastMix_; }

const GateDecision &ChassisController::lastGateDecision() const {
  return lastGateDecision_;
}

const LineDecision &ChassisController::lastLineDecision() const {
  return lastLineDecision_;
}

const char *ChassisController::lastError() const { return lastError_; }

}  // namespace stranger
