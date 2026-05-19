#include "tof_scan.h"

#include <Wire.h>

namespace stranger {

void TofScanner::begin() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  sensor_.setBus(&Wire);
  sensor_.setTimeout(TOF_SENSOR_TIMEOUT_MS);
  initializeSamples();
  refreshTcaPresence();
  if (tcaPresent_) {
    initializeAllChannels();
  } else {
    disableTcaChannels();
  }
}

void TofScanner::update() {
  const uint32_t now = millis();
  if (!tcaPresent_) {
    if (now - lastInitAttemptAtMs_ >= TOF_INIT_RETRY_MS) {
      lastInitAttemptAtMs_ = now;
      if (refreshTcaPresence()) {
        initializeAllChannels();
      }
    }
    return;
  }

  if (now - lastPollAtMs_ < TOF_POLL_INTERVAL_MS) {
    return;
  }

  lastPollAtMs_ = now;
  pollChannel(nextChannel_);
  nextChannel_ = (nextChannel_ + 1) % TOF_SENSOR_COUNT;
}

bool TofScanner::tcaPresent() const { return tcaPresent_; }

void TofScanner::scan(Stream &out) {
  disableTcaChannels();
  delay(2);

  uint8_t count = 0;
  for (uint8_t address = 1; address < 127; address++) {
    if (i2cProbe(address)) {
      out.printf("{\"type\":\"i2c_device\",\"address\":\"0x%02X\"}\n",
                 address);
      count++;
    }
  }
  out.printf("{\"type\":\"i2c_scan\",\"devices\":%u}\n", count);

  tcaPresent_ = i2cProbe(TCA9548A_ADDR);
  if (!tcaPresent_) {
    out.printf("{\"type\":\"error\",\"error\":\"tca9548a_not_found\","
               "\"address\":\"0x%02X\"}\n",
               TCA9548A_ADDR);
    return;
  }

  for (uint8_t channel = 0; channel < TOF_SENSOR_COUNT; channel++) {
    const bool selected = selectTcaChannel(channel);
    delay(5);
    const bool tofPresent = selected && i2cProbe(VL53L1X_ADDR);
    samples_[channel].present = tofPresent;
    out.printf(
        "{\"type\":\"tof_channel\",\"channel\":%u,\"name\":\"%s\","
        "\"vl53l1x_0x29\":%s,\"initialized\":%s}\n",
        channel, samples_[channel].name, tofPresent ? "true" : "false",
        samples_[channel].initialized ? "true" : "false");
  }
  disableTcaChannels();
}

void TofScanner::printTelemetry(Stream &out) const {
  const uint32_t now = millis();
  out.printf("{\"type\":\"tof\",\"uptime_ms\":%lu,\"tca_0x70\":%s,"
             "\"sensors\":[",
             static_cast<unsigned long>(now), tcaPresent_ ? "true" : "false");

  for (uint8_t i = 0; i < TOF_SENSOR_COUNT; i++) {
    const TofSample &s = samples_[i];
    const bool fresh = sampleFresh(i);
    if (i > 0) {
      out.print(',');
    }
    out.printf("{\"channel\":%u,\"name\":\"%s\",\"present\":%s,"
               "\"initialized\":%s,\"fresh\":%s,\"range_valid\":%s,"
               "\"timeout\":%s,\"distance_mm\":",
               s.channel, s.name, s.present ? "true" : "false",
               s.initialized ? "true" : "false", fresh ? "true" : "false",
               s.rangeValid ? "true" : "false", s.timeout ? "true" : "false");
    if (fresh && (s.rangeValid || s.rangeStatus == VL53L1X::OutOfBoundsFail)) {
      out.print(s.rangeStatus == VL53L1X::OutOfBoundsFail
                    ? TOF_CLEAR_DISTANCE_MM
                    : s.distanceMm);
    } else {
      out.print("null");
    }
    out.printf(",\"age_ms\":");
    if (s.updatedAtMs == 0) {
      out.print("null");
    } else {
      out.print(static_cast<unsigned long>(now - s.updatedAtMs));
    }
    out.printf(",\"status\":\"%s\"}", rangeStatusName(s.rangeStatus));
  }
  out.println("]}");
}

const TofSample &TofScanner::sample(uint8_t index) const {
  if (index >= TOF_SENSOR_COUNT) {
    return samples_[0];
  }
  return samples_[index];
}

bool TofScanner::sampleFresh(uint8_t index) const {
  if (index >= TOF_SENSOR_COUNT) {
    return false;
  }
  const TofSample &s = samples_[index];
  return s.updatedAtMs != 0 && millis() - s.updatedAtMs <= TOF_STALE_MS;
}

bool TofScanner::refreshTcaPresence() {
  tcaPresent_ = i2cProbe(TCA9548A_ADDR);
  return tcaPresent_;
}

void TofScanner::initializeSamples() {
  for (uint8_t i = 0; i < TOF_SENSOR_COUNT; i++) {
    samples_[i].name = TOF_SENSOR_NAMES[i];
    samples_[i].channel = i;
    samples_[i].present = false;
    samples_[i].initialized = false;
    samples_[i].timeout = false;
    samples_[i].rangeValid = false;
    samples_[i].distanceMm = 0;
    samples_[i].rangeStatus = VL53L1X::None;
    samples_[i].updatedAtMs = 0;
  }
}

void TofScanner::initializeAllChannels() {
  for (uint8_t channel = 0; channel < TOF_SENSOR_COUNT; channel++) {
    initializeChannel(channel);
  }
  disableTcaChannels();
}

bool TofScanner::initializeChannel(uint8_t channel) {
  if (channel >= TOF_SENSOR_COUNT) {
    return false;
  }

  TofSample &s = samples_[channel];
  s.channel = channel;
  s.name = TOF_SENSOR_NAMES[channel];
  s.present = false;
  s.initialized = false;

  if (!selectTcaChannel(channel)) {
    return false;
  }
  delay(5);

  if (!i2cProbe(VL53L1X_ADDR)) {
    return false;
  }

  sensor_.setTimeout(TOF_SENSOR_TIMEOUT_MS);
  const bool ok = sensor_.init();
  s.present = ok;
  s.initialized = ok;
  if (!ok) {
    s.rangeStatus = VL53L1X::None;
    return false;
  }

  sensor_.setDistanceMode(VL53L1X::Long);
  sensor_.setMeasurementTimingBudget(TOF_TIMING_BUDGET_US);
  return true;
}

void TofScanner::pollChannel(uint8_t channel) {
  if (channel >= TOF_SENSOR_COUNT || !tcaPresent_) {
    return;
  }

  TofSample &s = samples_[channel];
  if (!s.initialized) {
    initializeChannel(channel);
    if (!s.initialized) {
      return;
    }
  }

  if (!selectTcaChannel(channel)) {
    s.present = false;
    s.initialized = false;
    s.timeout = true;
    s.rangeValid = false;
    s.rangeStatus = VL53L1X::None;
    return;
  }

  sensor_.setTimeout(TOF_SENSOR_TIMEOUT_MS);
  s.distanceMm = sensor_.readSingle(true);
  s.timeout = sensor_.timeoutOccurred();
  s.rangeStatus = sensor_.ranging_data.range_status;
  s.rangeValid = !s.timeout && isRangeValid(s.rangeStatus);
  s.present = !s.timeout;
  s.initialized = !s.timeout;
  s.updatedAtMs = millis();
}

bool TofScanner::i2cProbe(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool TofScanner::selectTcaChannel(uint8_t channel) {
  if (channel > 7) {
    return false;
  }

  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(1U << channel);
  return Wire.endTransmission() == 0;
}

void TofScanner::disableTcaChannels() {
  Wire.beginTransmission(TCA9548A_ADDR);
  Wire.write(0);
  Wire.endTransmission();
}

const char *TofScanner::rangeStatusName(VL53L1X::RangeStatus status) const {
  return VL53L1X::rangeStatusToString(status);
}

bool TofScanner::isRangeValid(VL53L1X::RangeStatus status) const {
  return status == VL53L1X::RangeValid ||
         status == VL53L1X::RangeValidMinRangeClipped ||
         status == VL53L1X::RangeValidNoWrapCheckFail;
}

}  // namespace stranger
