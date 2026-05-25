#include "line_sensors.h"

#include <math.h>

#include "motor_driver.h"

namespace stranger {
namespace {

const char *yn(bool value) { return value ? "true" : "false"; }

int clampCorrection(float value) {
  return constrain(static_cast<int>(roundf(value)), -LINE_MAX_CORRECTION_DUTY,
                   LINE_MAX_CORRECTION_DUTY);
}

}  // namespace

void LineSensors::begin() {
  analogReadResolution(12);
  initializeSamples();
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    pinMode(samples_[i].pin, INPUT);
    analogSetPinAttenuation(samples_[i].pin, ADC_11db);
  }
  pollAll();
  updateState();
}

void LineSensors::update() {
  const uint32_t now = millis();
  if (now - lastPollAtMs_ < LINE_POLL_INTERVAL_MS) {
    return;
  }
  pollAll();
  updateState();
}

LineDecision LineSensors::apply(int throttle, int turn,
                                bool allowSearch) const {
  LineDecision decision;
  decision.throttle = MotorDriver::clampDuty(throttle);
  decision.turn = MotorDriver::clampDuty(turn);
  decision.state = state_.kind;
  decision.reason = state_.reason;

  if (!enabled_) {
    decision.reason = "line_disabled";
    return decision;
  }

  if (state_.kind == LineKind::SensorFault) {
    if (decision.throttle == 0 && decision.turn == 0) {
      decision.reason = state_.reason;
      return decision;
    }
    decision.allowed = false;
    decision.adjusted = true;
    decision.throttle = 0;
    decision.turn = 0;
    decision.reason = state_.reason;
    return decision;
  }

  if (state_.kind == LineKind::LineLost) {
    if (decision.throttle == 0 && decision.turn == 0) {
      decision.reason = "line_lost_stop";
      return decision;
    }
    if (allowSearch && decision.throttle == 0) {
      decision.adjusted = true;
      decision.reason = "line_reacquire_search";
      return decision;
    }
    decision.allowed = false;
    decision.adjusted = true;
    decision.throttle = 0;
    decision.turn = 0;
    decision.reason = "line_lost";
    return decision;
  }

  if (state_.kind == LineKind::Noise) {
    if (noiseCount_ >= LINE_NOISE_STOP_COUNT) {
      decision.allowed = false;
      decision.adjusted = true;
      decision.throttle = 0;
      decision.turn = 0;
      decision.reason = "line_noise_stop";
      return decision;
    }
    if (decision.throttle > LINE_NOISE_MAX_DUTY) {
      decision.throttle = LINE_NOISE_MAX_DUTY;
      decision.adjusted = true;
    }
    decision.turn =
        MotorDriver::clampDuty(decision.turn + state_.correction);
    decision.adjusted = true;
    decision.reason = "line_noise_slow";
    return decision;
  }

  if (state_.kind == LineKind::Wide) {
    decision.throttle = min(decision.throttle, LINE_NOISE_MAX_DUTY);
    decision.turn =
        MotorDriver::clampDuty(decision.turn + state_.correction);
    decision.adjusted = true;
    decision.reason = "line_wide_slow";
    return decision;
  }

  if (state_.kind == LineKind::Reacquire) {
    decision.throttle = min(decision.throttle, LINE_REACQUIRE_MAX_DUTY);
    decision.turn =
        MotorDriver::clampDuty(decision.turn + state_.correction);
    decision.adjusted = true;
    decision.reason = "line_reacquire_adjusted";
    return decision;
  }

  if (decision.throttle > LINE_FOLLOW_MAX_DUTY) {
    decision.throttle = LINE_FOLLOW_MAX_DUTY;
    decision.adjusted = true;
  }
  if (state_.correction != 0) {
    decision.turn =
        MotorDriver::clampDuty(decision.turn + state_.correction);
    decision.adjusted = true;
  }
  decision.reason = decision.adjusted ? "line_follow_adjusted" : "line_follow";
  return decision;
}

void LineSensors::setEnabled(bool enabled) {
  enabled_ = enabled;
  if (!enabled_) {
    stopReacquire();
  }
  updateState();
}

bool LineSensors::enabled() const { return enabled_; }

bool LineSensors::calibrated() const { return calibrationReady(); }

bool LineSensors::calibrateFloor() {
  setCalibrationFromCurrent(floorRaw_);
  floorCalibrated_ = true;
  updateState();
  return calibrationReady();
}

bool LineSensors::calibrateTape() {
  setCalibrationFromCurrent(tapeRaw_);
  tapeCalibrated_ = true;
  updateState();
  return calibrationReady();
}

void LineSensors::requestReacquire(float yawDeg, bool imuAssist) {
  if (reacquireActive_) {
    return;
  }
  reacquireActive_ = true;
  reacquireImuAssist_ = imuAssist;
  reacquireDirection_ = lastValidError_ < 0 ? -1 : 1;
  reacquireSweepCount_ = 0;
  reacquireStartedAtMs_ = millis();
  reacquireLastSweepAtMs_ = reacquireStartedAtMs_;
  reacquireStartYawDeg_ = yawDeg;
  updateState();
}

void LineSensors::stopReacquire() {
  reacquireActive_ = false;
  reacquireImuAssist_ = false;
  reacquireSweepCount_ = 0;
  updateState();
}

bool LineSensors::reacquiring() const { return reacquireActive_; }

bool LineSensors::reacquireFailed() const {
  if (!reacquireActive_) {
    return false;
  }
  const uint32_t now = millis();
  return now - reacquireStartedAtMs_ > LINE_REACQUIRE_TIMEOUT_MS ||
         reacquireSweepCount_ > LINE_REACQUIRE_MAX_SWEEPS;
}

int LineSensors::reacquireTurnDuty(float yawDeg, bool imuFresh) {
  if (!reacquireActive_) {
    requestReacquire(yawDeg, imuFresh);
  }
  if (reacquireFailed()) {
    state_.reason = "line_reacquire_timeout";
    return 0;
  }

  const uint32_t now = millis();
  bool flip = now - reacquireLastSweepAtMs_ >= LINE_REACQUIRE_SWEEP_MS;
  if (reacquireImuAssist_ && imuFresh) {
    const float maxYaw =
        LINE_REACQUIRE_YAW_STEP_DEG * static_cast<float>(reacquireSweepCount_ + 1);
    if (fabsf(yawDelta(yawDeg, reacquireStartYawDeg_)) >= maxYaw) {
      flip = true;
    }
  }

  if (flip) {
    reacquireDirection_ = -reacquireDirection_;
    reacquireSweepCount_++;
    reacquireLastSweepAtMs_ = now;
    reacquireStartYawDeg_ = yawDeg;
  }

  return reacquireDirection_ * LINE_REACQUIRE_MAX_DUTY;
}

const LineState &LineSensors::state() const { return state_; }

const LineSample &LineSensors::sample(uint8_t index) const {
  static LineSample empty;
  if (index >= LINE_SENSOR_COUNT) {
    return empty;
  }
  return samples_[index];
}

const char *LineSensors::stateName() const { return stateName(state_.kind); }

const char *LineSensors::stateName(LineKind kind) const {
  switch (kind) {
    case LineKind::Disabled:
      return "disabled";
    case LineKind::SensorFault:
      return "sensor_fault";
    case LineKind::TrackFollow:
      return "track_follow";
    case LineKind::BiasLeft:
      return "bias_left";
    case LineKind::BiasRight:
      return "bias_right";
    case LineKind::LineLost:
      return "line_lost";
    case LineKind::Reacquire:
      return "reacquire";
    case LineKind::Noise:
      return "noise";
    case LineKind::Wide:
      return "wide";
  }
  return "unknown";
}

void LineSensors::printTelemetry(Stream &out) const {
  const uint32_t now = millis();
  out.printf(
      "{\"type\":\"line\",\"uptime_ms\":%lu,\"enabled\":%s,"
      "\"calibrated\":%s,\"state\":\"%s\",\"reason\":\"%s\","
      "\"detected_bits\":\"%s\",\"position\":%d,\"error\":%d,"
      "\"previous_error\":%d,\"correction\":%d,\"last_valid_error\":%d,"
      "\"lost_for_ms\":%lu,\"reacquire_state\":\"%s\","
      "\"reacquire_active\":%s,\"imu_assist\":%s,"
      "\"reacquire_start_yaw_deg\":",
      static_cast<unsigned long>(now), yn(enabled_), yn(calibrationReady()),
      stateName(), state_.reason, state_.detectedBits, state_.position,
      state_.error, state_.previousError, state_.correction,
      state_.lastValidError, static_cast<unsigned long>(state_.lostForMs),
      state_.reacquireState, yn(state_.reacquireActive),
      yn(state_.imuAssist));
  if (state_.imuAssist) {
    out.print(state_.reacquireStartYawDeg, 2);
  } else {
    out.print("null");
  }
  out.print(",\"sensors\":[");
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    const LineSample &sample = samples_[i];
    if (i > 0) {
      out.print(',');
    }
    out.printf(
        "{\"name\":\"%s\",\"pin\":%u,\"raw\":%d,\"confidence\":",
        sample.name, sample.pin, sample.raw);
    out.print(sample.confidence, 3);
    out.printf(",\"detected\":%s,\"fresh\":%s,\"floor_raw\":%d,"
               "\"tape_raw\":%d,\"age_ms\":",
               yn(sample.detected), yn(sampleFresh(i)), floorRaw_[i],
               tapeRaw_[i]);
    if (sample.updatedAtMs == 0) {
      out.print("null");
    } else {
      out.print(static_cast<unsigned long>(now - sample.updatedAtMs));
    }
    out.print('}');
  }
  out.println("]}");
}

void LineSensors::initializeSamples() {
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    samples_[i].name = LINE_SENSOR_CONFIGS[i].name;
    samples_[i].pin = LINE_SENSOR_CONFIGS[i].pin;
    samples_[i].raw = 0;
    samples_[i].confidence = 0.0F;
    samples_[i].detected = false;
    samples_[i].updatedAtMs = 0;
  }
}

void LineSensors::pollAll() {
  lastPollAtMs_ = millis();
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    samples_[i].raw = analogRead(samples_[i].pin);
    samples_[i].updatedAtMs = lastPollAtMs_;
  }
}

void LineSensors::updateState() {
  const uint32_t now = millis();
  state_.enabled = enabled_;
  state_.calibrated = calibrationReady();
  state_.fresh = allSamplesFresh();
  state_.updatedAtMs = now;
  state_.reacquireActive = reacquireActive_;
  state_.imuAssist = reacquireImuAssist_;
  state_.reacquireStartYawDeg = reacquireStartYawDeg_;
  state_.lastValidError = lastValidError_;
  state_.previousError = previousError_;
  state_.reacquireState = reacquireActive_ ? "searching" : "idle";

  if (!enabled_) {
    state_.kind = LineKind::Disabled;
    state_.reason = "line_disabled";
    state_.lostForMs = 0;
    state_.correction = 0;
    return;
  }

  if (!state_.fresh) {
    state_.kind = LineKind::SensorFault;
    state_.reason = "line_stale";
    state_.correction = 0;
    return;
  }

  if (!state_.calibrated) {
    state_.kind = LineKind::SensorFault;
    state_.reason = "line_uncalibrated";
    state_.correction = 0;
    for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
      samples_[i].confidence = 0.0F;
      samples_[i].detected = false;
    }
    updateDetectedBits();
    return;
  }

  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    samples_[i].confidence = confidenceFor(i, samples_[i].raw);
    samples_[i].detected = samples_[i].confidence >= LINE_CONFIDENCE_THRESHOLD;
  }
  updateDetectedBits();

  float totalConfidence = 0.0F;
  state_.position = computePosition(totalConfidence);
  state_.previousError = previousError_;
  state_.error = state_.position - LINE_CENTER_POSITION;
  state_.correction = computeCorrection(state_.error);

  if (state_.detectedMask == 0 || totalConfidence < LINE_MIN_TOTAL_CONFIDENCE) {
    if (lineLostStartedAtMs_ == 0) {
      lineLostStartedAtMs_ = now;
    }
    state_.lostForMs = now - lineLostStartedAtMs_;
    state_.kind = reacquireActive_ ? LineKind::Reacquire : LineKind::LineLost;
    state_.reacquireState = reacquireActive_ ? "searching" : "idle";
    state_.reason = reacquireActive_ ? "line_reacquire_no_line" : "line_lost";
    state_.correction = 0;
    return;
  }

  lineLostStartedAtMs_ = 0;
  state_.lostForMs = 0;
  lastValidError_ = state_.error;
  previousError_ = state_.error;

  if (state_.detectedMask == 0b101) {
    noiseCount_++;
    state_.kind = LineKind::Noise;
    state_.reason = "line_split_or_noise";
    return;
  }

  noiseCount_ = 0;

  if (state_.detectedMask == 0b111) {
    state_.kind = LineKind::Wide;
    state_.reason = "line_wide_marker";
    return;
  }

  if (reacquireActive_) {
    if (abs(state_.error) <= LINE_CENTER_ERROR_BAND &&
        samples_[1].detected) {
      reacquireActive_ = false;
      reacquireImuAssist_ = false;
      state_.reacquireActive = false;
      state_.imuAssist = false;
      state_.reacquireState = "found";
      state_.kind = LineKind::TrackFollow;
      state_.reason = "line_reacquired";
      return;
    }
    state_.kind = LineKind::Reacquire;
    state_.reacquireState = "line_visible";
    state_.reason = "line_reacquire_adjust";
    return;
  }

  if (abs(state_.error) <= LINE_CENTER_ERROR_BAND && samples_[1].detected) {
    state_.kind = LineKind::TrackFollow;
    state_.reason = "line_centered";
    return;
  }

  if (state_.error < 0) {
    state_.kind = LineKind::BiasLeft;
    state_.reason = "line_left";
    return;
  }

  state_.kind = LineKind::BiasRight;
  state_.reason = "line_right";
}

void LineSensors::updateDetectedBits() {
  state_.detectedMask = 0;
  state_.detectedBits[0] = samples_[0].detected ? '1' : '0';
  state_.detectedBits[1] = samples_[1].detected ? '1' : '0';
  state_.detectedBits[2] = samples_[2].detected ? '1' : '0';
  state_.detectedBits[3] = '\0';
  if (samples_[0].detected) {
    state_.detectedMask |= 0b100;
  }
  if (samples_[1].detected) {
    state_.detectedMask |= 0b010;
  }
  if (samples_[2].detected) {
    state_.detectedMask |= 0b001;
  }
}

void LineSensors::setCalibrationFromCurrent(int values[LINE_SENSOR_COUNT]) {
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    values[i] = samples_[i].raw;
  }
}

bool LineSensors::calibrationReady() const {
  if (!floorCalibrated_ || !tapeCalibrated_) {
    return false;
  }
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    if (abs(tapeRaw_[i] - floorRaw_[i]) < LINE_CALIBRATION_MIN_DELTA) {
      return false;
    }
  }
  return true;
}

float LineSensors::confidenceFor(uint8_t index, int raw) const {
  if (index >= LINE_SENSOR_COUNT || !calibrationReady()) {
    return 0.0F;
  }
  const float floorValue = static_cast<float>(floorRaw_[index]);
  const float tapeValue = static_cast<float>(tapeRaw_[index]);
  const float delta = tapeValue - floorValue;
  if (fabsf(delta) < static_cast<float>(LINE_CALIBRATION_MIN_DELTA)) {
    return 0.0F;
  }
  const float normalized = (static_cast<float>(raw) - floorValue) / delta;
  return constrain(normalized, 0.0F, 1.0F);
}

int LineSensors::computePosition(float &totalConfidence) const {
  const int weights[LINE_SENSOR_COUNT] = {LINE_POSITION_LEFT,
                                          LINE_POSITION_CENTER,
                                          LINE_POSITION_RIGHT};
  float weighted = 0.0F;
  totalConfidence = 0.0F;
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    const float confidence =
        samples_[i].confidence >= LINE_CONFIDENCE_THRESHOLD
            ? samples_[i].confidence
            : 0.0F;
    weighted += confidence * static_cast<float>(weights[i]);
    totalConfidence += confidence;
  }

  if (totalConfidence < LINE_MIN_TOTAL_CONFIDENCE) {
    return LINE_CENTER_POSITION + lastValidError_;
  }
  return static_cast<int>(roundf(weighted / totalConfidence));
}

int LineSensors::computeCorrection(int error) {
  const int delta = error - previousError_;
  return clampCorrection(LINE_KP * static_cast<float>(error) +
                         LINE_KD * static_cast<float>(delta));
}

bool LineSensors::allSamplesFresh() const {
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; i++) {
    if (!sampleFresh(i)) {
      return false;
    }
  }
  return true;
}

bool LineSensors::sampleFresh(uint8_t index) const {
  if (index >= LINE_SENSOR_COUNT) {
    return false;
  }
  const LineSample &sample = samples_[index];
  return sample.updatedAtMs != 0 &&
         millis() - sample.updatedAtMs <= LINE_STALE_MS;
}

float LineSensors::yawDelta(float currentDeg, float startDeg) {
  float delta = currentDeg - startDeg;
  while (delta > 180.0F) {
    delta -= 360.0F;
  }
  while (delta < -180.0F) {
    delta += 360.0F;
  }
  return delta;
}

}  // namespace stranger
