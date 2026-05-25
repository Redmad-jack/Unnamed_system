#pragma once

#include <Arduino.h>

#include "line_sensors.h"
#include "motor_driver.h"
#include "obstacle_gate.h"

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

  void setObstacleGate(ObstacleGate *gate);
  void setLineSensors(LineSensors *lineSensors);
  bool drive(int throttle, int turn, int durationMs);
  bool driveEscape(int throttle, int turn, int durationMs);
  bool driveLineSearch(int throttle, int turn, int durationMs);
  bool spin(int duty, int durationMs);
  void resetLastMix();
  DriveMix mix(int throttle, int turn) const;
  const DriveMix &lastMix() const;
  const GateDecision &lastGateDecision() const;
  const LineDecision &lastLineDecision() const;
  const char *lastError() const;

 private:
  bool applyDrive(int throttle, int turn, int durationMs, bool allowEscape,
                  bool allowLineSearch);

  MotorDriver &motors_;
  ObstacleGate *gate_ = nullptr;
  LineSensors *lineSensors_ = nullptr;
  DriveMix lastMix_ = {0, 0, 0, 0, 0, 0};
  GateDecision lastGateDecision_;
  LineDecision lastLineDecision_;
  const char *lastError_ = "none";
};

}  // namespace stranger
