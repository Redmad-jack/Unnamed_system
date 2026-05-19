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

struct MotorPins {
  const char *name;
  uint8_t pwmPin;
  uint8_t dirPin;
  uint8_t pwmChannel;
  bool invertDirection;
};

MotorPins motors[] = {
    {"M1", 4, 10, 0, false},
    {"M2", 5, 11, 1, false},
    {"M3", 6, 12, 2, false},
    {"M4", 7, 13, 3, false},
};

String serialLine;
uint32_t lastHeartbeatMs = 0;

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
  for (const MotorPins &motor : motors) {
    writePwm(motor, 0);
    digitalWrite(motor.dirPin, LOW);
  }
}

void setMotorDuty(uint8_t motorIndex, int duty) {
  if (motorIndex >= (sizeof(motors) / sizeof(motors[0]))) {
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

  Serial.printf("OK %s duty=%d pwm=%u dir=%u\n", motor.name, duty, magnitude,
                dirLevel ? 1 : 0);
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
      "{\"type\":\"status\",\"uptime_ms\":%lu,\"tca_0x70\":%s,\"sda\":%u,"
      "\"scl\":%u}\n",
      static_cast<unsigned long>(millis()),
      i2cProbe(TCA9548A_ADDR) ? "true" : "false", PIN_I2C_SDA, PIN_I2C_SCL);
}

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  help");
  Serial.println("  status");
  Serial.println("  scan");
  Serial.println("  motors off");
  Serial.println("  motor <1-4> <duty -255..255>");
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
  if (command == "motors off") {
    stopAllMotors();
    Serial.println("OK motors off");
    return;
  }

  int motorNumber = 0;
  int duty = 0;
  if (sscanf(command.c_str(), "motor %d %d", &motorNumber, &duty) == 2) {
    if (motorNumber < 1 || motorNumber > 4) {
      Serial.println("ERR motor number must be 1..4");
      return;
    }
    setMotorDuty(static_cast<uint8_t>(motorNumber - 1), duty);
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
