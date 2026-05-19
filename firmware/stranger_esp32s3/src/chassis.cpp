#include "chassis.h"

namespace stranger {

ChassisController::ChassisController(MotorDriver &motors) : motors_(motors) {}

bool ChassisController::drive(int throttle, int turn, int durationMs) {
  const DriveMix requested = mix(throttle, turn);
  const bool applied = motors_.applyWheelDuties(
      requested.frontLeft, requested.frontRight, requested.rearLeft,
      requested.rearRight, durationMs);
  if (applied) {
    lastMix_ = requested;
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

}  // namespace stranger
