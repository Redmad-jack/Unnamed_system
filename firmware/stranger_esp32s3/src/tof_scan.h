#pragma once

#include <Arduino.h>

namespace stranger {

class TofScanner {
 public:
  void begin();
  bool tcaPresent();
  void scan(Stream &out);

 private:
  bool i2cProbe(uint8_t address);
  bool selectTcaChannel(uint8_t channel);
  void disableTcaChannels();
};

}  // namespace stranger
