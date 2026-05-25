#pragma once

#include <Arduino.h>

#include "config.h"

namespace stranger {

struct LineSample {
  const char *name = "";
  uint8_t pin = 0;
  int raw = 0;
  float confidence = 0.0F;
  bool detected = false;
  uint32_t updatedAtMs = 0;
};

enum class LineKind {
  Disabled,
  SensorFault,
  TrackFollow,
  BiasLeft,
  BiasRight,
  LineLost,
  Reacquire,
  Noise,
  Wide,
};

struct LineState {
  LineKind kind = LineKind::SensorFault;
  bool enabled = true;
  bool calibrated = false;
  bool fresh = false;
  uint8_t detectedMask = 0;
  char detectedBits[4] = "000";
  int position = LINE_CENTER_POSITION;
  int error = 0;
  int previousError = 0;
  int correction = 0;
  int lastValidError = 0;
  bool reacquireActive = false;
  const char *reacquireState = "idle";
  bool imuAssist = false;
  float reacquireStartYawDeg = 0.0F;
  uint32_t lostForMs = 0;
  uint32_t updatedAtMs = 0;
  const char *reason = "boot";
};

struct LineDecision {
  bool allowed = true;
  bool adjusted = false;
  int throttle = 0;
  int turn = 0;
  LineKind state = LineKind::Disabled;
  const char *reason = "line_disabled";
};

class LineSensors {
 public:
  void begin();
  void update();
  void printTelemetry(Stream &out) const;
  LineDecision apply(int throttle, int turn, bool allowSearch = false) const;

  void setEnabled(bool enabled);
  bool enabled() const;
  bool calibrated() const;
  bool calibrateFloor();
  bool calibrateTape();

  void requestReacquire(float yawDeg = 0.0F, bool imuAssist = false);
  void stopReacquire();
  bool reacquiring() const;
  bool reacquireFailed() const;
  int reacquireTurnDuty(float yawDeg = 0.0F, bool imuFresh = false);

  const LineState &state() const;
  const LineSample &sample(uint8_t index) const;
  const char *stateName() const;
  const char *stateName(LineKind kind) const;

 private:
  void initializeSamples();
  void pollAll();
  void updateState();
  void updateDetectedBits();
  void setCalibrationFromCurrent(int values[LINE_SENSOR_COUNT]);
  bool calibrationReady() const;
  float confidenceFor(uint8_t index, int raw) const;
  int computePosition(float &totalConfidence) const;
  int computeCorrection(int error);
  bool allSamplesFresh() const;
  bool sampleFresh(uint8_t index) const;
  static float yawDelta(float currentDeg, float startDeg);

  LineSample samples_[LINE_SENSOR_COUNT];
  bool enabled_ = true;
  bool floorCalibrated_ = false;
  bool tapeCalibrated_ = false;
  int floorRaw_[LINE_SENSOR_COUNT] = {0, 0, 0};
  int tapeRaw_[LINE_SENSOR_COUNT] = {0, 0, 0};
  int previousError_ = 0;
  int lastValidError_ = 0;
  uint8_t noiseCount_ = 0;
  bool reacquireActive_ = false;
  bool reacquireImuAssist_ = false;
  int reacquireDirection_ = 1;
  uint8_t reacquireSweepCount_ = 0;
  float reacquireStartYawDeg_ = 0.0F;
  uint32_t reacquireStartedAtMs_ = 0;
  uint32_t reacquireLastSweepAtMs_ = 0;
  LineState state_;
  uint32_t lastPollAtMs_ = 0;
  uint32_t lineLostStartedAtMs_ = 0;
};

}  // namespace stranger
