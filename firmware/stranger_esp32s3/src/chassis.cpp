#include "chassis.h"

namespace stranger {

ChassisController::ChassisController(MotorDriver &motors) : motors_(motors) {}

void ChassisController::setObstacleGate(ObstacleGate *gate) { gate_ = gate; }

bool ChassisController::drive(int throttle, int turn, int durationMs) {
  return applyDrive(throttle, turn, durationMs, false);
}

bool ChassisController::driveEscape(int throttle, int turn, int durationMs) {
  return applyDrive(throttle, turn, durationMs, true);
}

bool ChassisController::applyDrive(int throttle, int turn, int durationMs,
                                   bool allowEscape) {
  if ((throttle != 0 || turn != 0) && !motors_.isArmed()) {
    lastError_ = "motors_disarmed";
    return false;
  }

  GateDecision decision;
  decision.throttle = MotorDriver::clampDuty(throttle);
  decision.turn = MotorDriver::clampDuty(turn);
  decision.reason = "no_gate";

  if (gate_ != nullptr) {
    decision = gate_->apply(throttle, turn, allowEscape);
    if (!decision.allowed) {
      motors_.stopAll();
      resetLastMix();
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

const char *ChassisController::lastError() const { return lastError_; }

}  // namespace stranger
