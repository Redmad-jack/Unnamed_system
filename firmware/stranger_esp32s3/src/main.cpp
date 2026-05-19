#include <Arduino.h>
#include <Wire.h>

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

namespace {

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
  uint8_t pwmPin;
  uint8_t dirPin;
  uint8_t pwmChannel;
  bool invertDirection;
};

MotorPins motors[MOTOR_COUNT] = {
    {"M1", 4, 10, 0, false},
    {"M2", 5, 11, 1, false},
    {"M3", 6, 12, 2, false},
    {"M4", 7, 13, 3, false},
};

String serialLine;
uint32_t lastHeartbeatMs = 0;
bool motorArmed = false;
uint32_t motorArmExpiresAtMs = 0;
uint32_t motorStopAtMs[MOTOR_COUNT] = {0, 0, 0, 0};
int motorCurrentDuty[MOTOR_COUNT] = {0, 0, 0, 0};

bool i2cProbe(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool selectTcaChannel(uint8_t channel) {
  if (channel > 7) {
    return false;
  }

  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(1U << channel);
  return Wire.endTransmission() == 0;
}

void disableTcaChannels() {
  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(0);
  Wire.endTransmission();
}

void writePwm(const MotorPins &motor, uint16_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(motor.pwmPin, duty);
#else
  ledcWrite(motor.pwmChannel, duty);
#endif
}

void attachPwm(const MotorPins &motor) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(motor.pwmPin, PWM_FREQ_HZ, PWM_RESOLUTION_BITS);
#else
  ledcSetup(motor.pwmChannel, PWM_FREQ_HZ, PWM_RESOLUTION_BITS);
  ledcAttachPin(motor.pwmPin, motor.pwmChannel);
#endif
  writePwm(motor, 0);
}

void stopAllMotors() {
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    writePwm(motors[i], 0);
    digitalWrite(motors[i].dirPin, LOW);
    motorStopAtMs[i] = 0;
    motorCurrentDuty[i] = 0;
  }
}

void disarmMotors(const char *reason) {
  stopAllMotors();
  motorArmed = false;
  motorArmExpiresAtMs = 0;
  if (reason != nullptr) {
    Serial.printf("OK motors disarmed: %s\n", reason);
  }
}

void armMotors() {
  stopAllMotors();
  motorArmed = true;
  motorArmExpiresAtMs = millis() + MOTOR_ARM_TIMEOUT_MS;
  Serial.printf("OK motors armed for %lu ms\n",
                static_cast<unsigned long>(MOTOR_ARM_TIMEOUT_MS));
}

bool requireMotorArmed() {
  if (motorArmed) {
    motorArmExpiresAtMs = millis() + MOTOR_ARM_TIMEOUT_MS;
    return true;
  }
  Serial.println("ERR motors are disarmed; send arm first");
  return false;
}

int clampTestDuty(int duty) {
  return constrain(duty, -MOTOR_TEST_MAX_DUTY, MOTOR_TEST_MAX_DUTY);
}

uint16_t clampRunMs(int durationMs) {
  return static_cast<uint16_t>(
      constrain(durationMs, 1, static_cast<int>(MOTOR_TEST_MAX_MS)));
}

void setMotorDutyRaw(uint8_t motorIndex, int duty) {
  if (motorIndex >= MOTOR_COUNT) {
    Serial.println("ERR motor index out of range");
    return;
  }

  const MotorPins &motor = motors[motorIndex];
  const bool reverse = duty < 0;
  const bool dirLevel = reverse ^ motor.invertDirection;
  const uint16_t magnitude = min<uint16_t>(abs(duty), PWM_MAX_DUTY);

  writePwm(motor, 0);
  digitalWrite(motor.dirPin, dirLevel ? HIGH : LOW);
  delay(2);
  writePwm(motor, magnitude);
  motorCurrentDuty[motorIndex] = duty;
}

void setMotorPulse(uint8_t motorIndex, int duty, uint16_t durationMs) {
  if (motorIndex >= MOTOR_COUNT) {
    Serial.println("ERR motor index out of range");
    return;
  }

  duty = clampTestDuty(duty);
  if (duty == 0) {
    setMotorDutyRaw(motorIndex, 0);
    motorStopAtMs[motorIndex] = 0;
    Serial.printf("OK %s stopped\n", motors[motorIndex].name);
    return;
  }

  setMotorDutyRaw(motorIndex, duty);
  motorStopAtMs[motorIndex] = millis() + durationMs;
  const MotorPins &motor = motors[motorIndex];
  const bool reverse = duty < 0;
  const bool dirLevel = reverse ^ motor.invertDirection;
  const uint16_t magnitude = min<uint16_t>(abs(duty), PWM_MAX_DUTY);
  Serial.printf("OK %s duty=%d pwm=%u dir=%u\n", motor.name, duty, magnitude,
                dirLevel ? 1 : 0);
  Serial.printf("OK %s auto_stop_ms=%u\n", motor.name, durationMs);
}

void updateMotorTimeouts() {
  const uint32_t now = millis();

  if (motorArmed && static_cast<int32_t>(now - motorArmExpiresAtMs) >= 0) {
    disarmMotors("arm timeout");
    return;
  }

  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    if (motorStopAtMs[i] != 0 &&
        static_cast<int32_t>(now - motorStopAtMs[i]) >= 0) {
      setMotorDutyRaw(i, 0);
      motorStopAtMs[i] = 0;
      Serial.printf("OK %s auto stopped\n", motors[i].name);
    }
  }
}

void runBlockingMotorTest(uint8_t motorIndex, int duty, uint16_t durationMs) {
  if (!requireMotorArmed()) {
    return;
  }
  if (motorIndex >= MOTOR_COUNT) {
    Serial.println("ERR motor index out of range");
    return;
  }

  duty = abs(clampTestDuty(duty));
  durationMs = clampRunMs(durationMs);
  if (duty == 0) {
    duty = MOTOR_TEST_DEFAULT_DUTY;
  }

  Serial.printf("TEST %s forward duty=%d duration_ms=%u\n",
                motors[motorIndex].name, duty, durationMs);
  setMotorDutyRaw(motorIndex, duty);
  delay(durationMs);
  setMotorDutyRaw(motorIndex, 0);
  delay(250);

  Serial.printf("TEST %s reverse duty=%d duration_ms=%u\n",
                motors[motorIndex].name, duty, durationMs);
  setMotorDutyRaw(motorIndex, -duty);
  delay(durationMs);
  setMotorDutyRaw(motorIndex, 0);
  motorStopAtMs[motorIndex] = 0;
  delay(250);

  Serial.printf("OK %s test done\n", motors[motorIndex].name);
}

void scanBaseI2cBus() {
  Serial.println("I2C base bus scan:");
  uint8_t count = 0;
  for (uint8_t address = 1; address < 127; address++) {
    if (i2cProbe(address)) {
      Serial.printf("  found 0x%02X\n", address);
      count++;
    }
  }
  Serial.printf("I2C base bus devices=%u\n", count);
}

void scanTofChannels() {
  Serial.println("TCA9548A channel scan:");
  if (!i2cProbe(TCA9548A_ADDR)) {
    Serial.printf("ERR TCA9548A not found at 0x%02X\n", TCA9548A_ADDR);
    return;
  }

  for (uint8_t channel = 0; channel < 4; channel++) {
    const bool selected = selectTcaChannel(channel);
    delay(5);
    const bool tofPresent = selected && i2cProbe(VL53L1X_ADDR);
    Serial.printf("  channel=%u vl53l1x_0x29=%s\n", channel,
                  tofPresent ? "present" : "missing");
  }
  disableTcaChannels();
}

void printStatus() {
  Serial.printf(
      "{\"type\":\"status\",\"uptime_ms\":%lu,\"motor_armed\":%s,"
      "\"max_test_duty\":%d,\"tca_0x70\":%s,\"sda\":%u,\"scl\":%u}\n",
      static_cast<unsigned long>(millis()),
      motorArmed ? "true" : "false", MOTOR_TEST_MAX_DUTY,
      i2cProbe(TCA9548A_ADDR) ? "true" : "false", PIN_I2C_SDA, PIN_I2C_SCL);
  for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
    Serial.printf("  %s duty=%d pwm_pin=%u dir_pin=%u invert=%u\n",
                  motors[i].name, motorCurrentDuty[i], motors[i].pwmPin,
                  motors[i].dirPin, motors[i].invertDirection ? 1 : 0);
  }
}

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  help");
  Serial.println("  status");
  Serial.println("  scan");
  Serial.println("  arm");
  Serial.println("  disarm");
  Serial.println("  motors off");
  Serial.println("  motor <1-4> <duty -120..120> [duration_ms]");
  Serial.println("  test <1-4> [duty 1..120] [duration_ms]");
  Serial.println("  test all [duty 1..120] [duration_ms]");
}

void handleCommand(String command) {
  command.trim();
  command.toLowerCase();

  if (command.length() == 0) {
    return;
  }
  if (command == "help") {
    printHelp();
    return;
  }
  if (command == "status") {
    printStatus();
    return;
  }
  if (command == "scan") {
    scanBaseI2cBus();
    scanTofChannels();
    return;
  }
  if (command == "arm") {
    armMotors();
    return;
  }
  if (command == "disarm") {
    disarmMotors("manual");
    return;
  }
  if (command == "motors off") {
    disarmMotors("motors off");
    return;
  }

  int motorNumber = 0;
  int duty = 0;
  int durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "motor %d %d %d", &motorNumber, &duty,
             &durationMs) >= 2) {
    if (motorNumber < 1 || motorNumber > 4) {
      Serial.println("ERR motor number must be 1..4");
      return;
    }
    if (duty != 0 && !requireMotorArmed()) {
      return;
    }
    setMotorPulse(static_cast<uint8_t>(motorNumber - 1), duty,
                  clampRunMs(durationMs));
    return;
  }

  duty = MOTOR_TEST_DEFAULT_DUTY;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (command.startsWith("test all")) {
    sscanf(command.c_str(), "test all %d %d", &duty, &durationMs);
    if (!requireMotorArmed()) {
      return;
    }
    for (uint8_t i = 0; i < MOTOR_COUNT; i++) {
      runBlockingMotorTest(i, duty, clampRunMs(durationMs));
    }
    disarmMotors("test all complete");
    return;
  }

  if (sscanf(command.c_str(), "test %d %d %d", &motorNumber, &duty,
             &durationMs) >= 1) {
    if (motorNumber < 1 || motorNumber > 4) {
      Serial.println("ERR motor number must be 1..4");
      return;
    }
    runBlockingMotorTest(static_cast<uint8_t>(motorNumber - 1), duty,
                         clampRunMs(durationMs));
    return;
  }

  Serial.println("ERR unknown command; type help");
}

void setupMotors() {
  for (const MotorPins &motor : motors) {
    pinMode(motor.dirPin, OUTPUT);
    digitalWrite(motor.dirPin, LOW);
    attachPwm(motor);
  }
  stopAllMotors();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(800);

  setupMotors();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  disableTcaChannels();

  Serial.println();
  Serial.println("Stranger ESP32-S3 lower controller smoke firmware");
  Serial.println("Board target: generic ESP32-S3 N16R8 via esp32-s3-devkitc-1");
  printHelp();
  printStatus();
}

void loop() {
  updateMotorTimeouts();

  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      handleCommand(serialLine);
      serialLine = "";
    } else {
      serialLine += c;
    }
  }

  const uint32_t now = millis();
  if (now - lastHeartbeatMs >= 2000) {
    lastHeartbeatMs = now;
    Serial.printf("{\"type\":\"heartbeat\",\"uptime_ms\":%lu}\n",
                  static_cast<unsigned long>(now));
  }
}
