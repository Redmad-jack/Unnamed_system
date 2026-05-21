#pragma once

#include <Arduino.h>
#include <VL53L1X.h>

#include "config.h"

namespace stranger {

struct TofSample {
  const char *name = "";
  uint8_t channel = 0;
  bool present = false;
  bool initialized = false;
  bool timeout = false;
  bool rangeValid = false;
  uint16_t distanceMm = 0;
  VL53L1X::RangeStatus rangeStatus = VL53L1X::None;
  uint32_t updatedAtMs = 0;
};

class TofScanner {
 public:
  void begin();
  void update();
  bool tcaPresent() const;
  void scan(Stream &out);
  void printTelemetry(Stream &out) const;

  const TofSample &sample(uint8_t index) const;
  bool sampleFresh(uint8_t index) const;

 private:
  bool refreshTcaPresence();
  void initializeSamples();
  void initializeAllChannels();
  bool initializeChannel(uint8_t channel);
  void pollChannel(uint8_t channel);
  bool i2cProbe(uint8_t address);
  bool selectTcaChannel(uint8_t channel);
  void disableTcaChannels();
  const char *rangeStatusName(VL53L1X::RangeStatus status) const;
  bool isRangeValid(VL53L1X::RangeStatus status) const;

  VL53L1X sensor_;
  TofSample samples_[TOF_SENSOR_COUNT];
  bool tcaPresent_ = false;
  uint8_t nextChannel_ = 0;
  uint32_t lastPollAtMs_ = 0;
  uint32_t lastInitAttemptAtMs_ = 0;
};

}  // namespace stranger
