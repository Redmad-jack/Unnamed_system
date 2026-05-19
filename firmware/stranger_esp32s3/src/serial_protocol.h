#pragma once

#include <Arduino.h>

#include "chassis.h"
#include "motor_driver.h"
#include "tof_scan.h"

namespace stranger {

class SerialProtocol {
 public:
  SerialProtocol(MotorDriver &motors, ChassisController &chassis,
                 TofScanner &tof);

  void update();
  void printHelp();
  void printStatus();
  void printHeartbeat();

 private:
  void handleLine(String line);
  void handleText(String command);
  void handleJson(const String &line);

  void printAck(const char *action);
  void printAckValue(const char *action, const char *key, int value);
  void printError(const char *error);

  MotorDriver &motors_;
  ChassisController &chassis_;
  TofScanner &tof_;
  String line_;
};

}  // namespace stranger
