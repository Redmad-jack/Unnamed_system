#include "imu_monitor.h"

#include <SPI.h>
#include <math.h>

#include "config.h"

namespace stranger {
namespace {

constexpr float kRadToDeg = 57.29577951308232F;

float clampUnit(float value) {
  if (value > 1.0F) {
    return 1.0F;
  }
  if (value < -1.0F) {
    return -1.0F;
  }
  return value;
}

}  // namespace

ImuMonitor::ImuMonitor() : bno08x_(PIN_IMU_RST) {}

void ImuMonitor::begin() {
  beginCalled_ = true;
  SPI.begin(PIN_IMU_SCK, PIN_IMU_MISO, PIN_IMU_MOSI, PIN_IMU_CS);
  initialize();
}

void ImuMonitor::update() {
  const uint32_t now = millis();
  if (!initialized_) {
    if (now - lastInitAttemptMs_ >= IMU_INIT_RETRY_MS) {
      initialize();
    }
    markState();
    return;
  }

  if (now - lastPollMs_ < IMU_POLL_INTERVAL_MS) {
    markState();
    return;
  }
  lastPollMs_ = now;

  if (bno08x_.wasReset()) {
    resetCount_++;
    if (!enableReports()) {
      initialized_ = false;
      markState();
      return;
    }
  }

  for (uint8_t i = 0; i < 6; i++) {
    if (!bno08x_.getSensorEvent(&event_)) {
      break;
    }
    handleEvent(event_);
  }

  markState();
}

void ImuMonitor::printTelemetry(Stream &out) const {
  const bool freshNow = fresh();
  const bool hasAnyData = lastUpdateMs_ > 0;
  out.print("{\"type\":\"imu\",\"uptime_ms\":");
  out.print(static_cast<unsigned long>(millis()));
  out.print(",\"present\":");
  out.print(present_ ? "true" : "false");
  out.print(",\"initialized\":");
  out.print(initialized_ ? "true" : "false");
  out.print(",\"fresh\":");
  out.print(freshNow ? "true" : "false");
  out.print(",\"state\":\"");
  out.print(stateName());
  out.print("\",\"age_ms\":");
  if (hasAnyData) {
    out.print(static_cast<unsigned long>(millis() - lastUpdateMs_));
  } else {
    out.print("null");
  }
  out.print(",\"event_count\":");
  out.print(static_cast<unsigned long>(eventCount_));
  out.print(",\"reset_count\":");
  out.print(static_cast<unsigned long>(resetCount_));
  out.print(",\"yaw_deg\":");
  printValue(out, hasRotation_, yawDeg_, 2);
  out.print(",\"pitch_deg\":");
  printValue(out, hasRotation_, pitchDeg_, 2);
  out.print(",\"roll_deg\":");
  printValue(out, hasRotation_, rollDeg_, 2);
  out.print(",\"quat\":{\"real\":");
  printValue(out, hasRotation_, quatReal_, 5);
  out.print(",\"i\":");
  printValue(out, hasRotation_, quatI_, 5);
  out.print(",\"j\":");
  printValue(out, hasRotation_, quatJ_, 5);
  out.print(",\"k\":");
  printValue(out, hasRotation_, quatK_, 5);
  out.print("},\"gyro_rad_s\":{\"x\":");
  printValue(out, hasGyro_, gyroXRad_, 5);
  out.print(",\"y\":");
  printValue(out, hasGyro_, gyroYRad_, 5);
  out.print(",\"z\":");
  printValue(out, hasGyro_, gyroZRad_, 5);
  out.print("},\"accel_m_s2\":{\"x\":");
  printValue(out, hasAccel_, accelXMps2_, 5);
  out.print(",\"y\":");
  printValue(out, hasAccel_, accelYMps2_, 5);
  out.print(",\"z\":");
  printValue(out, hasAccel_, accelZMps2_, 5);
  out.print("},\"last_error\":\"");
  out.print(lastError_);
  out.println("\"}");
}

bool ImuMonitor::present() const { return present_; }

bool ImuMonitor::initialized() const { return initialized_; }

bool ImuMonitor::fresh() const {
  return initialized_ && lastUpdateMs_ > 0 && millis() - lastUpdateMs_ <= IMU_STALE_MS;
}

const char *ImuMonitor::stateName() const { return state_; }

uint32_t ImuMonitor::eventCount() const { return eventCount_; }

uint32_t ImuMonitor::resetCount() const { return resetCount_; }

bool ImuMonitor::initialize() {
  lastInitAttemptMs_ = millis();
  present_ = false;
  initialized_ = false;

  if (!bno08x_.begin_SPI(PIN_IMU_CS, PIN_IMU_INT, &SPI)) {
    lastError_ = "begin_spi_failed";
    markState();
    return false;
  }

  present_ = true;
  if (!enableReports()) {
    initialized_ = false;
    markState();
    return false;
  }

  initialized_ = true;
  lastError_ = "none";
  markState();
  return true;
}

bool ImuMonitor::enableReports() {
  if (!bno08x_.enableReport(SH2_GAME_ROTATION_VECTOR,
                            IMU_REPORT_INTERVAL_US)) {
    lastError_ = "game_rotation_report_failed";
    return false;
  }
  if (!bno08x_.enableReport(SH2_GYROSCOPE_CALIBRATED,
                            IMU_REPORT_INTERVAL_US)) {
    lastError_ = "gyro_report_failed";
    return false;
  }
  if (!bno08x_.enableReport(SH2_ACCELEROMETER, IMU_REPORT_INTERVAL_US)) {
    lastError_ = "accelerometer_report_failed";
    return false;
  }
  lastError_ = "none";
  return true;
}

void ImuMonitor::handleEvent(const sh2_SensorValue_t &event) {
  const uint32_t now = millis();
  switch (event.sensorId) {
    case SH2_GAME_ROTATION_VECTOR:
      quatReal_ = event.un.gameRotationVector.real;
      quatI_ = event.un.gameRotationVector.i;
      quatJ_ = event.un.gameRotationVector.j;
      quatK_ = event.un.gameRotationVector.k;
      hasRotation_ = true;
      updateEulerFromQuaternion();
      break;
    case SH2_GYROSCOPE_CALIBRATED:
      gyroXRad_ = event.un.gyroscope.x;
      gyroYRad_ = event.un.gyroscope.y;
      gyroZRad_ = event.un.gyroscope.z;
      hasGyro_ = true;
      break;
    case SH2_ACCELEROMETER:
      accelXMps2_ = event.un.accelerometer.x;
      accelYMps2_ = event.un.accelerometer.y;
      accelZMps2_ = event.un.accelerometer.z;
      hasAccel_ = true;
      break;
    default:
      return;
  }

  lastUpdateMs_ = now;
  eventCount_++;
}

void ImuMonitor::updateEulerFromQuaternion() {
  const float w = quatReal_;
  const float x = quatI_;
  const float y = quatJ_;
  const float z = quatK_;

  const float sinrCosp = 2.0F * (w * x + y * z);
  const float cosrCosp = 1.0F - 2.0F * (x * x + y * y);
  rollDeg_ = atan2f(sinrCosp, cosrCosp) * kRadToDeg;

  const float sinp = 2.0F * (w * y - z * x);
  pitchDeg_ = asinf(clampUnit(sinp)) * kRadToDeg;

  const float sinyCosp = 2.0F * (w * z + x * y);
  const float cosyCosp = 1.0F - 2.0F * (y * y + z * z);
  yawDeg_ = atan2f(sinyCosp, cosyCosp) * kRadToDeg;
}

void ImuMonitor::markState() {
  if (!beginCalled_) {
    state_ = "boot";
  } else if (!present_) {
    state_ = "not_found";
  } else if (!initialized_) {
    state_ = "report_error";
  } else if (lastUpdateMs_ == 0) {
    state_ = "no_update";
  } else if (!fresh()) {
    state_ = "stale";
  } else {
    state_ = "ok";
  }
}

void ImuMonitor::printValue(Stream &out, bool available, float value,
                            uint8_t digits) const {
  if (!available) {
    out.print("null");
    return;
  }
  out.print(value, digits);
}

}  // namespace stranger
