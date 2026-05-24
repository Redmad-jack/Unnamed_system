#pragma once

#include <Adafruit_BNO08x.h>
#include <Arduino.h>

namespace stranger {

class ImuMonitor {
 public:
  ImuMonitor();

  void begin();
  void update();
  void printTelemetry(Stream &out) const;

  bool present() const;
  bool initialized() const;
  bool fresh() const;
  const char *stateName() const;
  uint32_t eventCount() const;
  uint32_t resetCount() const;

 private:
  bool initialize();
  bool enableReports();
  void handleEvent(const sh2_SensorValue_t &event);
  void updateEulerFromQuaternion();
  void markState();
  void printValue(Stream &out, bool available, float value,
                  uint8_t digits = 3) const;

  Adafruit_BNO08x bno08x_;
  sh2_SensorValue_t event_{};
  bool beginCalled_ = false;
  bool present_ = false;
  bool initialized_ = false;
  bool hasRotation_ = false;
  bool hasGyro_ = false;
  bool hasAccel_ = false;
  const char *state_ = "boot";
  const char *lastError_ = "none";
  uint32_t lastInitAttemptMs_ = 0;
  uint32_t lastPollMs_ = 0;
  uint32_t lastUpdateMs_ = 0;
  uint32_t eventCount_ = 0;
  uint32_t resetCount_ = 0;
  float quatReal_ = 1.0F;
  float quatI_ = 0.0F;
  float quatJ_ = 0.0F;
  float quatK_ = 0.0F;
  float yawDeg_ = 0.0F;
  float pitchDeg_ = 0.0F;
  float rollDeg_ = 0.0F;
  float gyroXRad_ = 0.0F;
  float gyroYRad_ = 0.0F;
  float gyroZRad_ = 0.0F;
  float accelXMps2_ = 0.0F;
  float accelYMps2_ = 0.0F;
  float accelZMps2_ = 0.0F;
};

}  // namespace stranger
