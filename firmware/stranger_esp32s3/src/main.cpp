#include <Arduino.h>

#include "chassis.h"
#include "imu_monitor.h"
#include "motor_driver.h"
#include "obstacle_gate.h"
#include "roam_controller.h"
#include "serial_protocol.h"
#include "status_led.h"
#include "tof_scan.h"

namespace {

stranger::MotorDriver motorDriver;
stranger::ChassisController chassis(motorDriver);
stranger::TofScanner tofScanner;
stranger::ImuMonitor imuMonitor;
stranger::ObstacleGate obstacleGate(tofScanner);
stranger::RoamController roamController(motorDriver, chassis, obstacleGate);
stranger::SerialProtocol serialProtocol(motorDriver, chassis, tofScanner,
                                        obstacleGate, roamController,
                                        imuMonitor);

uint32_t lastHeartbeatMs = 0;
uint32_t lastTelemetryMs = 0;

}  // namespace

void setup() {
  Serial.begin(115200);
  stranger::turnOffBoardRgb();
  delay(800);
  stranger::turnOffBoardRgb();

  motorDriver.begin();
  tofScanner.begin();
  imuMonitor.begin();
  obstacleGate.update();
  chassis.setObstacleGate(&obstacleGate);

  Serial.println();
  Serial.println("Stranger ESP32-S3 lower controller");
  Serial.println("Board target: generic ESP32-S3 N16R8 via esp32-s3-devkitc-1");
  serialProtocol.printHelp();
  serialProtocol.printStatus();
}

void loop() {
  motorDriver.update();
  tofScanner.update();
  imuMonitor.update();
  obstacleGate.update();
  roamController.update();
  serialProtocol.update();

  const uint32_t now = millis();
  if (serialProtocol.telemetryEnabled() &&
      now - lastTelemetryMs >= stranger::TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = now;
    serialProtocol.printTelemetry();
  }
  if (serialProtocol.telemetryEnabled() && now - lastHeartbeatMs >= 2000) {
    lastHeartbeatMs = now;
    serialProtocol.printHeartbeat();
  }
}
