#include "serial_protocol.h"

#include <ArduinoJson.h>

#include "config.h"

namespace stranger {

SerialProtocol::SerialProtocol(MotorDriver &motors,
                               ChassisController &chassis, TofScanner &tof)
    : motors_(motors), chassis_(chassis), tof_(tof) {}

void SerialProtocol::update() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      handleLine(line_);
      line_ = "";
    } else {
      line_ += c;
    }
  }
}

void SerialProtocol::printHelp() {
  Serial.println("Commands:");
  Serial.println("  help");
  Serial.println("  status");
  Serial.println("  scan");
  Serial.println("  arm");
  Serial.println("  disarm");
  Serial.println("  motors off");
  Serial.println("  motor <1-4> <duty -120..120> [duration_ms]");
  Serial.println("  drive <throttle -120..120> <turn -120..120> [duration_ms]");
  Serial.println("  spin <duty -120..120> [duration_ms]");
  Serial.println("  test <1-4> [duty 1..120] [duration_ms]");
  Serial.println("  test all [duty 1..120] [duration_ms]");
  Serial.println("JSON examples:");
  Serial.println("  {\"cmd\":\"drive\",\"throttle\":70,\"turn\":-20,\"ms\":500}");
  Serial.println("  {\"cmd\":\"motor\",\"m\":1,\"duty\":70,\"ms\":500}");
}

void SerialProtocol::printStatus() {
  const DriveMix &mix = chassis_.lastMix();
  Serial.printf(
      "{\"type\":\"status\",\"uptime_ms\":%lu,\"motor_armed\":%s,"
      "\"max_test_duty\":%d,\"tca_0x70\":%s,\"sda\":%u,\"scl\":%u,"
      "\"last_left\":%d,\"last_right\":%d}\n",
      static_cast<unsigned long>(millis()), motors_.isArmed() ? "true" : "false",
      MOTOR_TEST_MAX_DUTY, tof_.tcaPresent() ? "true" : "false", PIN_I2C_SDA,
      PIN_I2C_SCL, mix.left, mix.right);
  motors_.printStatus(Serial);
}

void SerialProtocol::printHeartbeat() {
  Serial.printf("{\"type\":\"heartbeat\",\"uptime_ms\":%lu}\n",
                static_cast<unsigned long>(millis()));
}

void SerialProtocol::handleLine(String line) {
  line.trim();
  if (line.length() == 0) {
    return;
  }
  if (line.startsWith("{")) {
    handleJson(line);
    return;
  }
  handleText(line);
}

void SerialProtocol::handleText(String command) {
  command.trim();
  command.toLowerCase();

  if (command == "help") {
    printHelp();
    return;
  }
  if (command == "status") {
    printStatus();
    return;
  }
  if (command == "scan") {
    tof_.scan(Serial);
    return;
  }
  if (command == "arm") {
    motors_.arm();
    printAck("arm");
    return;
  }
  if (command == "disarm") {
    motors_.disarm("manual");
    chassis_.resetLastMix();
    printAck("disarm");
    return;
  }
  if (command == "motors off") {
    motors_.disarm("motors_off");
    chassis_.resetLastMix();
    printAck("motors_off");
    return;
  }

  int motorNumber = 0;
  int duty = 0;
  int durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "motor %d %d %d", &motorNumber, &duty,
             &durationMs) >= 2) {
    if (motors_.setMotorPulse(static_cast<uint8_t>(motorNumber), duty,
                              durationMs)) {
      printAckValue("motor", "motor", motorNumber);
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  int throttle = 0;
  int turn = 0;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "drive %d %d %d", &throttle, &turn,
             &durationMs) >= 2) {
    if (chassis_.drive(throttle, turn, durationMs)) {
      printAck("drive");
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  duty = 0;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "spin %d %d", &duty, &durationMs) >= 1) {
    if (chassis_.spin(duty, durationMs)) {
      printAck("spin");
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  duty = MOTOR_TEST_DEFAULT_DUTY;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (command.startsWith("test all")) {
    sscanf(command.c_str(), "test all %d %d", &duty, &durationMs);
    if (motors_.runAllMotorTests(duty, durationMs)) {
      printAck("test_all");
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  duty = MOTOR_TEST_DEFAULT_DUTY;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "test %d %d %d", &motorNumber, &duty,
             &durationMs) >= 1) {
    if (motors_.runMotorTest(static_cast<uint8_t>(motorNumber), duty,
                             durationMs)) {
      printAckValue("test", "motor", motorNumber);
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  printError("unknown_command");
}

void SerialProtocol::handleJson(const String &line) {
  JsonDocument doc;
  const DeserializationError error = deserializeJson(doc, line);
  if (error) {
    printError("json_parse_error");
    return;
  }

  const char *cmd = doc["cmd"] | "";
  if (strcmp(cmd, "arm") == 0) {
    motors_.arm();
    printAck("arm");
    return;
  }
  if (strcmp(cmd, "disarm") == 0 || strcmp(cmd, "stop") == 0 ||
      strcmp(cmd, "motors_off") == 0) {
    motors_.disarm(cmd);
    chassis_.resetLastMix();
    printAck(cmd);
    return;
  }
  if (strcmp(cmd, "status") == 0) {
    printStatus();
    return;
  }
  if (strcmp(cmd, "scan") == 0) {
    tof_.scan(Serial);
    return;
  }
  if (strcmp(cmd, "motor") == 0) {
    const int motorNumber = doc["m"] | 0;
    const int duty = doc["duty"] | 0;
    const int durationMs = doc["ms"] | MOTOR_TEST_DEFAULT_MS;
    if (motors_.setMotorPulse(static_cast<uint8_t>(motorNumber), duty,
                              durationMs)) {
      printAckValue("motor", "motor", motorNumber);
    } else {
      printError(motors_.lastError());
    }
    return;
  }
  if (strcmp(cmd, "drive") == 0) {
    const int throttle = doc["throttle"] | 0;
    const int turn = doc["turn"] | 0;
    const int durationMs = doc["ms"] | MOTOR_TEST_DEFAULT_MS;
    if (chassis_.drive(throttle, turn, durationMs)) {
      printAck("drive");
    } else {
      printError(motors_.lastError());
    }
    return;
  }
  if (strcmp(cmd, "spin") == 0) {
    const int duty = doc["duty"] | 0;
    const int durationMs = doc["ms"] | MOTOR_TEST_DEFAULT_MS;
    if (chassis_.spin(duty, durationMs)) {
      printAck("spin");
    } else {
      printError(motors_.lastError());
    }
    return;
  }

  printError("unknown_json_command");
}

void SerialProtocol::printAck(const char *action) {
  Serial.printf("{\"type\":\"ack\",\"action\":\"%s\"}\n", action);
}

void SerialProtocol::printAckValue(const char *action, const char *key,
                                   int value) {
  Serial.printf("{\"type\":\"ack\",\"action\":\"%s\",\"%s\":%d}\n", action,
                key, value);
}

void SerialProtocol::printError(const char *error) {
  Serial.printf("{\"type\":\"error\",\"error\":\"%s\"}\n", error);
}

}  // namespace stranger
