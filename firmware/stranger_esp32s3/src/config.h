#pragma once

#include <Arduino.h>

namespace stranger {

constexpr uint8_t PIN_I2C_SDA = 8;
constexpr uint8_t PIN_I2C_SCL = 9;
constexpr uint32_t I2C_FREQ_HZ = 100000;

constexpr uint8_t PIN_BOARD_RGB = 48;
constexpr uint8_t BOARD_RGB_WS2812_COUNT = 8;

constexpr uint8_t PIN_IMU_SCK = 15;
constexpr uint8_t PIN_IMU_MISO = 16;
constexpr uint8_t PIN_IMU_MOSI = 17;
constexpr uint8_t PIN_IMU_CS = 18;
constexpr uint8_t PIN_IMU_INT = 21;
constexpr uint8_t PIN_IMU_RST = 47;

constexpr uint8_t PIN_LINE_LEFT = 1;
constexpr uint8_t PIN_LINE_CENTER = 2;
constexpr uint8_t PIN_LINE_RIGHT = 14;

constexpr uint8_t TCA9548A_ADDR = 0x70;
constexpr uint8_t VL53L1X_ADDR = 0x29;
constexpr uint8_t TOF_SENSOR_COUNT = 4;
constexpr uint8_t LINE_SENSOR_COUNT = 3;

constexpr uint32_t PWM_FREQ_HZ = 10000;
constexpr uint8_t PWM_RESOLUTION_BITS = 8;
constexpr uint16_t PWM_MAX_DUTY = (1U << PWM_RESOLUTION_BITS) - 1U;

constexpr int MOTOR_TEST_MAX_DUTY = 250;
constexpr int MOTOR_TEST_DEFAULT_DUTY = 70;
constexpr uint16_t MOTOR_TEST_DEFAULT_MS = 500;
constexpr uint16_t MOTOR_TEST_MAX_MS = 30000;
constexpr uint32_t MOTOR_ARM_TIMEOUT_MS = 60000;
constexpr uint8_t MOTOR_COUNT = 4;

constexpr uint16_t TOF_HARD_STOP_MM = 250;
constexpr uint16_t TOF_SLOW_ZONE_MM = 600;
constexpr uint16_t TOF_CLEAR_DISTANCE_MM = 4000;
constexpr uint16_t TOF_STALE_MS = 1000;
constexpr uint16_t TOF_POLL_INTERVAL_MS = 80;
constexpr uint16_t TOF_INIT_RETRY_MS = 1000;
constexpr uint16_t TOF_SENSOR_TIMEOUT_MS = 80;
constexpr uint32_t TOF_TIMING_BUDGET_US = 50000;

constexpr uint32_t IMU_REPORT_INTERVAL_US = 20000;
constexpr uint16_t IMU_STALE_MS = 500;
constexpr uint16_t IMU_POLL_INTERVAL_MS = 10;
constexpr uint16_t IMU_INIT_RETRY_MS = 1000;
constexpr uint16_t LINE_POLL_INTERVAL_MS = 50;
constexpr uint16_t LINE_STALE_MS = 500;
constexpr uint16_t LINE_CALIBRATION_MIN_DELTA = 120;
constexpr float LINE_CONFIDENCE_THRESHOLD = 0.55F;
constexpr float LINE_MIN_TOTAL_CONFIDENCE = 0.35F;
constexpr int LINE_CENTER_POSITION = 1000;
constexpr int LINE_POSITION_LEFT = 0;
constexpr int LINE_POSITION_CENTER = 1000;
constexpr int LINE_POSITION_RIGHT = 2000;
constexpr int LINE_CENTER_ERROR_BAND = 180;
constexpr int LINE_FOLLOW_MAX_DUTY = 65;
constexpr int LINE_REACQUIRE_MAX_DUTY = 35;
constexpr int LINE_NOISE_MAX_DUTY = 30;
constexpr uint8_t LINE_NOISE_STOP_COUNT = 3;
constexpr float LINE_KP = 0.045F;
constexpr float LINE_KD = 0.018F;
constexpr int LINE_MAX_CORRECTION_DUTY = 65;
constexpr uint16_t LINE_REACQUIRE_COMMAND_MS = 220;
constexpr uint16_t LINE_REACQUIRE_SWEEP_MS = 550;
constexpr uint16_t LINE_REACQUIRE_TIMEOUT_MS = 7000;
constexpr uint8_t LINE_REACQUIRE_MAX_SWEEPS = 8;
constexpr float LINE_REACQUIRE_YAW_STEP_DEG = 18.0F;

constexpr int OBSTACLE_SLOW_MAX_DUTY = 45;
constexpr int OBSTACLE_TURN_BIAS_DUTY = 20;
constexpr uint16_t OBSTACLE_BIAS_DIFF_MM = 80;

constexpr uint16_t TELEMETRY_INTERVAL_MS = 1000;

constexpr int ROAM_FORWARD_DUTY = 55;
constexpr int ROAM_SLOW_DUTY = 35;
constexpr int ROAM_BACK_DUTY = -35;
constexpr int ROAM_TURN_DUTY = 45;
constexpr uint16_t ROAM_COMMAND_MS = 300;
constexpr uint16_t ROAM_COMMAND_INTERVAL_MS = 180;
constexpr uint16_t ROAM_ESCAPE_PHASE_MS = 500;

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

static constexpr const char *TOF_SENSOR_NAMES[TOF_SENSOR_COUNT] = {
    "front_left",
    "front_right",
    "left",
    "right",
};

struct LineSensorPins {
  const char *name;
  uint8_t pin;
};

static constexpr LineSensorPins LINE_SENSOR_CONFIGS[LINE_SENSOR_COUNT] = {
    {"line_left", PIN_LINE_LEFT},
    {"line_center", PIN_LINE_CENTER},
    {"line_right", PIN_LINE_RIGHT},
};

}  // namespace stranger
