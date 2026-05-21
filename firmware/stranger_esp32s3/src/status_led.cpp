#include "status_led.h"

#include <Arduino.h>
#include <esp32-hal-rmt.h>

#include "config.h"

namespace stranger {
namespace {

rmt_obj_t *boardRgbRmt = nullptr;

bool ensureBoardRgbRmt() {
  if (boardRgbRmt != nullptr) {
    return true;
  }

  boardRgbRmt = rmtInit(PIN_BOARD_RGB, RMT_TX_MODE, RMT_MEM_64);
  if (boardRgbRmt == nullptr) {
    return false;
  }

  rmtSetTick(boardRgbRmt, 100);
  return true;
}

void appendWs2812Byte(uint8_t value, rmt_data_t *data, size_t &index) {
  for (uint8_t bit = 0; bit < 8; bit++) {
    const bool high = (value & (1 << (7 - bit))) != 0;
    data[index].level0 = 1;
    data[index].duration0 = high ? 8 : 4;
    data[index].level1 = 0;
    data[index].duration1 = high ? 4 : 8;
    index++;
  }
}

}  // namespace

void turnOffBoardRgb() {
  if (!ensureBoardRgbRmt()) {
    return;
  }

  rmt_data_t ledData[BOARD_RGB_WS2812_COUNT * 24];
  size_t index = 0;
  for (uint8_t led = 0; led < BOARD_RGB_WS2812_COUNT; led++) {
    appendWs2812Byte(0, ledData, index);  // Green
    appendWs2812Byte(0, ledData, index);  // Red
    appendWs2812Byte(0, ledData, index);  // Blue
  }

  rmtWriteBlocking(boardRgbRmt, ledData, BOARD_RGB_WS2812_COUNT * 24);
  delayMicroseconds(80);
}

}  // namespace stranger
