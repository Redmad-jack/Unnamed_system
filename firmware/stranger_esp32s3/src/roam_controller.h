#pragma once

#include <Arduino.h>

#include "chassis.h"
#include "imu_monitor.h"
#include "line_sensors.h"
#include "motor_driver.h"
#include "obstacle_gate.h"

namespace stranger {

class RoamController {
 public:
  RoamController(MotorDriver &motors, ChassisController &chassis,
                 ObstacleGate &gate, LineSensors &lineSensors,
                 ImuMonitor &imu);

  void update();
  bool setEnabled(bool enabled);
  void stop();
  bool enabled() const;
  const char *mode() const;
  const char *lastError() const;

 private:
  void commandForObstacleStop();
  bool commandForLineState();
  void commandForClearOrSlow();

  MotorDriver &motors_;
  ChassisController &chassis_;
  ObstacleGate &gate_;
  LineSensors &lineSensors_;
  ImuMonitor &imu_;
  bool enabled_ = false;
  uint32_t lastCommandAtMs_ = 0;
  const char *mode_ = "stopped";
  const char *lastError_ = "none";
};

}  // namespace stranger
