#pragma once

#include <Arduino.h>

#include "config.h"

namespace stranger {

class MotorDriver {
 public:
  void begin();
  void update();

  void arm();
  void disarm(const char *reason);
  void stopAll();

  bool isArmed() const;
  const char *lastError() const;

  bool setMotorPulse(uint8_t motorNumber, int duty, int durationMs);
  bool applyWheelDuties(int frontLeft, int frontRight, int rearLeft,
                        int rearRight, int durationMs);
  bool runMotorTest(uint8_t motorNumber, int duty, int durationMs);
  bool runAllMotorTests(int duty, int durationMs);

  void printStatus(Stream &out) const;

  static int clampDuty(int duty);
  static uint16_t clampDurationMs(int durationMs);

 private:
  void attachPwm(const MotorPins &motor);
  void writePwm(const MotorPins &motor, uint16_t duty);
  void setMotorDutyRaw(uint8_t motorIndex, int duty);
  bool ensureArmedForNonZero(int duty);
  bool ensureMotorNumber(uint8_t motorNumber);
  void clearError();
  void setError(const char *message);

  bool armed_ = false;
  uint32_t armExpiresAtMs_ = 0;
  uint32_t stopAtMs_[MOTOR_COUNT] = {0, 0, 0, 0};
  int currentDuty_[MOTOR_COUNT] = {0, 0, 0, 0};
  const char *lastError_ = "none";
};

}  // namespace stranger
