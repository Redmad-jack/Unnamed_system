#include "tof_scan.h"

#include <Wire.h>

#include "config.h"

namespace stranger {

void TofScanner::begin() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  disableTcaChannels();
}

bool TofScanner::tcaPresent() { return i2cProbe(TCA9548A_ADDR); }

void TofScanner::scan(Stream &out) {
  uint8_t count = 0;
  for (uint8_t address = 1; address < 127; address++) {
    if (i2cProbe(address)) {
      out.printf("{\"type\":\"i2c_device\",\"address\":\"0x%02X\"}\n",
                 address);
      count++;
    }
  }
  out.printf("{\"type\":\"i2c_scan\",\"devices\":%u}\n", count);

  if (!i2cProbe(TCA9548A_ADDR)) {
    out.printf("{\"type\":\"error\",\"error\":\"tca9548a_not_found\","
               "\"address\":\"0x%02X\"}\n",
               TCA9548A_ADDR);
    return;
  }

  for (uint8_t channel = 0; channel < 4; channel++) {
    const bool selected = selectTcaChannel(channel);
    delay(5);
    const bool tofPresent = selected && i2cProbe(VL53L1X_ADDR);
    out.printf(
        "{\"type\":\"tof_channel\",\"channel\":%u,\"vl53l1x_0x29\":%s}\n",
        channel, tofPresent ? "true" : "false");
  }
  disableTcaChannels();
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

}  // namespace stranger
