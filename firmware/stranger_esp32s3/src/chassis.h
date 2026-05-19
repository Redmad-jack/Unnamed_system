#pragma once

#include <Arduino.h>

#include "motor_driver.h"

namespace stranger {

struct DriveMix {
  int left;
  int right;
  int frontLeft;
  int frontRight;
  int rearLeft;
  int rearRight;
};

class ChassisController {
 public:
  explicit ChassisController(MotorDriver &motors);

  bool drive(int throttle, int turn, int durationMs);
  bool spin(int duty, int durationMs);
  void resetLastMix();
  DriveMix mix(int throttle, int turn) const;
  const DriveMix &lastMix() const;

 private:
  MotorDriver &motors_;
  DriveMix lastMix_ = {0, 0, 0, 0, 0, 0};
};

}  // namespace stranger
