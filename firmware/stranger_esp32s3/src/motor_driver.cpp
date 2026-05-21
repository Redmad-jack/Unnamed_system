#include "motor_driver.h"

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

namespace stranger {

void MotorDriver::begin() {
  for (const MotorPins &motor : MOTOR_CONFIGS) {
    pinMode(motor.dirPin, OUTPUT);
    digitalWrite(motor.dirPin, LOW);
    attachPwm(motor);
  }
  stopAll();
}

void MotorDriver::update() {
  const uint32_t now = millis();

  if (armed_ && static_cast<int32_t>(now - armExpiresAtMs_) >= 0) {
    disarm("arm_timeout");
    return;
  }

  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    if (stopAtMs_[i] != 0 && static_cast<int32_t>(now - stopAtMs_[i]) >= 0) {
      setMotorDutyRaw(i, 0);
      stopAtMs_[i] = 0;
    }
  }
}

void MotorDriver::arm() {
  stopAll();
  armed_ = true;
  armExpiresAtMs_ = millis() + MOTOR_ARM_TIMEOUT_MS;
  clearError();
}

void MotorDriver::disarm(const char *reason) {
  stopAll();
  armed_ = false;
  armExpiresAtMs_ = 0;
  setError(reason == nullptr ? "disarmed" : reason);
}

void MotorDriver::stopAll() {
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    setMotorDutyRaw(i, 0);
    stopAtMs_[i] = 0;
  }
}

bool MotorDriver::isArmed() const { return armed_; }

const char *MotorDriver::lastError() const { return lastError_; }

bool MotorDriver::setMotorPulse(uint8_t motorNumber, int duty, int durationMs) {
  if (!ensureMotorNumber(motorNumber)) {
    return false;
  }

  duty = clampDuty(duty);
  const uint8_t motorIndex = motorNumber - 1;

  if (duty == 0) {
    setMotorDutyRaw(motorIndex, 0);
    stopAtMs_[motorIndex] = 0;
    clearError();
    return true;
  }

  if (!ensureArmedForNonZero(duty)) {
    return false;
  }

  setMotorDutyRaw(motorIndex, duty);
  stopAtMs_[motorIndex] = millis() + clampDurationMs(durationMs);
  clearError();
  return true;
}

bool MotorDriver::applyWheelDuties(int frontLeft, int frontRight, int rearLeft,
                                   int rearRight, int durationMs) {
  frontLeft = clampDuty(frontLeft);
  frontRight = clampDuty(frontRight);
  rearLeft = clampDuty(rearLeft);
  rearRight = clampDuty(rearRight);

  const bool hasMotion =
      frontLeft != 0 || frontRight != 0 || rearLeft != 0 || rearRight != 0;
  if (!hasMotion) {
    stopAll();
    clearError();
    return true;
  }

  if (!ensureArmedForNonZero(1)) {
    return false;
  }

  const int duties[MOTOR_COUNT] = {frontLeft, frontRight, rearLeft, rearRight};
  const uint32_t stopAt = millis() + clampDurationMs(durationMs);
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    setMotorDutyRaw(i, duties[i]);
    stopAtMs_[i] = stopAt;
  }

  clearError();
  return true;
}

bool MotorDriver::runMotorTest(uint8_t motorNumber, int duty, int durationMs) {
  if (!ensureMotorNumber(motorNumber)) {
    return false;
  }
  if (!ensureArmedForNonZero(1)) {
    return false;
  }

  duty = abs(clampDuty(duty));
  if (duty == 0) {
    duty = MOTOR_TEST_DEFAULT_DUTY;
  }
  const uint16_t runMs = clampDurationMs(durationMs);
  const uint8_t motorIndex = motorNumber - 1;

  setMotorDutyRaw(motorIndex, duty);
  delay(runMs);
  setMotorDutyRaw(motorIndex, 0);
  delay(250);
  setMotorDutyRaw(motorIndex, -duty);
  delay(runMs);
  setMotorDutyRaw(motorIndex, 0);
  stopAtMs_[motorIndex] = 0;

  clearError();
  return true;
}

bool MotorDriver::runAllMotorTests(int duty, int durationMs) {
  if (!ensureArmedForNonZero(1)) {
    return false;
  }

  for (uint8_t motorNumber = 1; motorNumber <= MOTOR_COUNT; motorNumber++) {
    if (!runMotorTest(motorNumber, duty, durationMs)) {
      return false;
    }
    delay(250);
  }
  disarm("test_all_complete");
  return true;
}

void MotorDriver::printStatus(Stream &out) const {
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    const MotorPins &motor = MOTOR_CONFIGS[i];
    out.printf(
        "{\"type\":\"motor_state\",\"motor\":%u,\"name\":\"%s\","
        "\"position\":\"%s\",\"duty\":%d,\"pwm_pin\":%u,\"dir_pin\":%u,"
        "\"invert\":%s}\n",
        i + 1, motor.name, motor.position, currentDuty_[i], motor.pwmPin,
        motor.dirPin, motor.invertDirection ? "true" : "false");
  }
}

int MotorDriver::clampDuty(int duty) {
  return constrain(duty, -MOTOR_TEST_MAX_DUTY, MOTOR_TEST_MAX_DUTY);
}

uint16_t MotorDriver::clampDurationMs(int durationMs) {
  return static_cast<uint16_t>(
      constrain(durationMs, 1, static_cast<int>(MOTOR_TEST_MAX_MS)));
}

void MotorDriver::attachPwm(const MotorPins &motor) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(motor.pwmPin, PWM_FREQ_HZ, PWM_RESOLUTION_BITS);
#else
  ledcSetup(motor.pwmChannel, PWM_FREQ_HZ, PWM_RESOLUTION_BITS);
  ledcAttachPin(motor.pwmPin, motor.pwmChannel);
#endif
  writePwm(motor, 0);
}

void MotorDriver::writePwm(const MotorPins &motor, uint16_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(motor.pwmPin, duty);
#else
  ledcWrite(motor.pwmChannel, duty);
#endif
}

void MotorDriver::setMotorDutyRaw(uint8_t motorIndex, int duty) {
  if (motorIndex >= MOTOR_COUNT) {
    setError("motor_index_out_of_range");
    return;
  }

  const MotorPins &motor = MOTOR_CONFIGS[motorIndex];
  const bool reverse = duty < 0;
  const bool dirLevel = reverse ^ motor.invertDirection;
  const uint16_t magnitude = min<uint16_t>(abs(duty), PWM_MAX_DUTY);

  writePwm(motor, 0);
  digitalWrite(motor.dirPin, dirLevel ? HIGH : LOW);
  delay(2);
  writePwm(motor, magnitude);
  currentDuty_[motorIndex] = duty;
}

bool MotorDriver::ensureArmedForNonZero(int duty) {
  if (duty == 0) {
    clearError();
    return true;
  }
  if (!armed_) {
    setError("motors_disarmed");
    return false;
  }
  armExpiresAtMs_ = millis() + MOTOR_ARM_TIMEOUT_MS;
  clearError();
  return true;
}

bool MotorDriver::ensureMotorNumber(uint8_t motorNumber) {
  if (motorNumber < 1 || motorNumber > MOTOR_COUNT) {
    setError("motor_number_must_be_1_to_4");
    return false;
  }
  clearError();
  return true;
}

void MotorDriver::clearError() { lastError_ = "none"; }

void MotorDriver::setError(const char *message) { lastError_ = message; }

}  // namespace stranger
