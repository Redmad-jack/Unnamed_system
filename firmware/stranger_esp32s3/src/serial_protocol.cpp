#include "serial_protocol.h"

#include <ArduinoJson.h>

#include "config.h"

namespace stranger {

SerialProtocol::SerialProtocol(MotorDriver &motors,
                               ChassisController &chassis, TofScanner &tof,
                               ObstacleGate &gate, RoamController &roam)
    : motors_(motors),
      chassis_(chassis),
      tof_(tof),
      gate_(gate),
      roam_(roam) {}

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
  Serial.println("  tof");
  Serial.println("  telemetry on");
  Serial.println("  telemetry off");
  Serial.println("  avoidance on");
  Serial.println("  avoidance off");
  Serial.println("  roam start");
  Serial.println("  roam stop");
  Serial.println("  arm");
  Serial.println("  disarm");
  Serial.println("  motors off");
  Serial.println("  motor <1-4> <duty -250..250> [duration_ms <= 30000]");
  Serial.println(
      "  drive <throttle -250..250> <turn -250..250> [duration_ms <= 30000]");
  Serial.println("  spin <duty -250..250> [duration_ms <= 30000]");
  Serial.println("  test <1-4> [duty 1..250] [duration_ms <= 30000]");
  Serial.println("  test all [duty 1..250] [duration_ms <= 30000]");
  Serial.println("JSON examples:");
  Serial.println("  {\"cmd\":\"tof\"}");
  Serial.println("  {\"cmd\":\"telemetry\",\"enabled\":false}");
  Serial.println("  {\"cmd\":\"avoidance\",\"enabled\":true}");
  Serial.println("  {\"cmd\":\"roam\",\"enabled\":true}");
  Serial.println("  {\"cmd\":\"drive\",\"throttle\":70,\"turn\":-20,\"ms\":500}");
  Serial.println("  {\"cmd\":\"motor\",\"m\":1,\"duty\":70,\"ms\":500}");
}

void SerialProtocol::printStatus() {
  const DriveMix &mix = chassis_.lastMix();
  Serial.printf(
      "{\"type\":\"status\",\"uptime_ms\":%lu,\"motor_armed\":%s,"
      "\"max_test_duty\":%d,\"max_duration_ms\":%u,\"tca_0x70\":%s,"
      "\"sda\":%u,\"scl\":%u,"
      "\"last_left\":%d,\"last_right\":%d,\"avoidance_enabled\":%s,"
      "\"obstacle_state\":\"%s\",\"roam_enabled\":%s,\"roam_mode\":\"%s\"}\n",
      static_cast<unsigned long>(millis()), motors_.isArmed() ? "true" : "false",
      MOTOR_TEST_MAX_DUTY, MOTOR_TEST_MAX_MS,
      tof_.tcaPresent() ? "true" : "false", PIN_I2C_SDA, PIN_I2C_SCL,
      mix.left, mix.right, gate_.enabled() ? "true" : "false", gate_.stateName(),
      roam_.enabled() ? "true" : "false", roam_.mode());
  motors_.printStatus(Serial);
  gate_.printState(Serial);
}

void SerialProtocol::printHeartbeat() {
  Serial.printf("{\"type\":\"heartbeat\",\"uptime_ms\":%lu}\n",
                static_cast<unsigned long>(millis()));
}

void SerialProtocol::printTelemetry() {
  tof_.printTelemetry(Serial);
  gate_.printState(Serial);
}

bool SerialProtocol::telemetryEnabled() const { return telemetryEnabled_; }

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
  if (command == "tof") {
    printTelemetry();
    return;
  }
  if (command == "telemetry on") {
    setTelemetry(true);
    return;
  }
  if (command == "telemetry off") {
    setTelemetry(false);
    return;
  }
  if (command == "avoidance on") {
    setAvoidance(true);
    return;
  }
  if (command == "avoidance off") {
    setAvoidance(false);
    return;
  }
  if (command == "roam start") {
    setRoam(true);
    return;
  }
  if (command == "roam stop") {
    setRoam(false);
    return;
  }
  if (command == "arm") {
    motors_.arm();
    printAck("arm");
    return;
  }
  if (command == "disarm") {
    roam_.stop();
    motors_.disarm("manual");
    chassis_.resetLastMix();
    printAck("disarm");
    return;
  }
  if (command == "motors off") {
    roam_.stop();
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
      printError(chassis_.lastError());
    }
    return;
  }

  duty = 0;
  durationMs = MOTOR_TEST_DEFAULT_MS;
  if (sscanf(command.c_str(), "spin %d %d", &duty, &durationMs) >= 1) {
    if (chassis_.spin(duty, durationMs)) {
      printAck("spin");
    } else {
      printError(chassis_.lastError());
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
    roam_.stop();
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
  if (strcmp(cmd, "tof") == 0) {
    printTelemetry();
    return;
  }
  if (strcmp(cmd, "telemetry") == 0) {
    setTelemetry(doc["enabled"] | true);
    return;
  }
  if (strcmp(cmd, "avoidance") == 0) {
    setAvoidance(doc["enabled"] | true);
    return;
  }
  if (strcmp(cmd, "roam") == 0) {
    setRoam(doc["enabled"] | true);
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
      printError(chassis_.lastError());
    }
    return;
  }
  if (strcmp(cmd, "spin") == 0) {
    const int duty = doc["duty"] | 0;
    const int durationMs = doc["ms"] | MOTOR_TEST_DEFAULT_MS;
    if (chassis_.spin(duty, durationMs)) {
      printAck("spin");
    } else {
      printError(chassis_.lastError());
    }
    return;
  }

  printError("unknown_json_command");
}

void SerialProtocol::setAvoidance(bool enabled) {
  if (!enabled) {
    roam_.stop();
  }
  gate_.setEnabled(enabled);
  Serial.printf("{\"type\":\"ack\",\"action\":\"avoidance\",\"enabled\":%s}\n",
                enabled ? "true" : "false");
}

void SerialProtocol::setRoam(bool enabled) {
  if (roam_.setEnabled(enabled)) {
    Serial.printf("{\"type\":\"ack\",\"action\":\"roam\",\"enabled\":%s}\n",
                  enabled ? "true" : "false");
  } else {
    printError(roam_.lastError());
  }
}

void SerialProtocol::setTelemetry(bool enabled) {
  telemetryEnabled_ = enabled;
  Serial.printf("{\"type\":\"ack\",\"action\":\"telemetry\",\"enabled\":%s}\n",
                enabled ? "true" : "false");
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
