#pragma once

#include <Arduino.h>

#include "chassis.h"
#include "imu_monitor.h"
#include "line_sensors.h"
#include "motor_driver.h"
#include "obstacle_gate.h"
#include "roam_controller.h"
#include "tof_scan.h"

namespace stranger {

class SerialProtocol {
 public:
  SerialProtocol(MotorDriver &motors, ChassisController &chassis,
                 TofScanner &tof, ObstacleGate &gate, RoamController &roam,
                 ImuMonitor &imu, LineSensors &lineSensors);

  void update();
  void printHelp();
  void printStatus();
  void printHeartbeat();
  void printTelemetry();
  bool telemetryEnabled() const;

 private:
  void handleLine(String line);
  void handleText(String command);
  void handleJson(const String &line);

  void setAvoidance(bool enabled);
  void setLineTracking(bool enabled);
  void setRoam(bool enabled);
  void setTelemetry(bool enabled);
  void calibrateLine(const char *target);
  void setReacquire(bool enabled);
  void printAck(const char *action);
  void printAckValue(const char *action, const char *key, int value);
  void printMotionResult(const char *intent, const char *status,
                         const char *detail);
  void printError(const char *error);

  MotorDriver &motors_;
  ChassisController &chassis_;
  TofScanner &tof_;
  ObstacleGate &gate_;
  RoamController &roam_;
  ImuMonitor &imu_;
  LineSensors &lineSensors_;
  String line_;
  bool telemetryEnabled_ = false;
};

}  // namespace stranger
