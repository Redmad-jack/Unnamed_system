#pragma once

#include <Arduino.h>

namespace stranger {

constexpr uint8_t PIN_I2C_SDA = 8;
constexpr uint8_t PIN_I2C_SCL = 9;
constexpr uint32_t I2C_FREQ_HZ = 100000;

constexpr uint8_t TCA9548A_ADDR = 0x70;
constexpr uint8_t VL53L1X_ADDR = 0x29;

constexpr uint32_t PWM_FREQ_HZ = 10000;
constexpr uint8_t PWM_RESOLUTION_BITS = 8;
constexpr uint16_t PWM_MAX_DUTY = (1U << PWM_RESOLUTION_BITS) - 1U;

constexpr int MOTOR_TEST_MAX_DUTY = 120;
constexpr int MOTOR_TEST_DEFAULT_DUTY = 70;
constexpr uint16_t MOTOR_TEST_DEFAULT_MS = 500;
constexpr uint16_t MOTOR_TEST_MAX_MS = 2000;
constexpr uint32_t MOTOR_ARM_TIMEOUT_MS = 60000;
constexpr uint8_t MOTOR_COUNT = 4;

struct MotorPins {
  const char *name;
  const char *position;
  uint8_t pwmPin;
  uint8_t dirPin;
  uint8_t pwmChannel;
  bool invertDirection;
};

static constexpr MotorPins MOTOR_CONFIGS[MOTOR_COUNT] = {
    {"M1", "front_left", 4, 10, 0, false},
    {"M2", "front_right", 5, 11, 1, false},
    {"M3", "rear_left", 6, 12, 2, false},
    {"M4", "rear_right", 7, 13, 3, false},
};

}  // namespace stranger
