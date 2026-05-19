#pragma once

#include <Arduino.h>

#include "chassis.h"
#include "motor_driver.h"
#include "obstacle_gate.h"

namespace stranger {

class RoamController {
 public:
  RoamController(MotorDriver &motors, ChassisController &chassis,
                 ObstacleGate &gate);

  void update();
  bool setEnabled(bool enabled);
  void stop();
  bool enabled() const;
  const char *mode() const;
  const char *lastError() const;

 private:
  void commandForObstacleStop(uint32_t now);
  void commandForClearOrSlow();
  int escapeTurn() const;

  MotorDriver &motors_;
  ChassisController &chassis_;
  ObstacleGate &gate_;
  bool enabled_ = false;
  bool escapeBacking_ = true;
  uint32_t lastCommandAtMs_ = 0;
  uint32_t escapePhaseStartedAtMs_ = 0;
  const char *mode_ = "stopped";
  const char *lastError_ = "none";
};

}  // namespace stranger
