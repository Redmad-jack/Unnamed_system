# Stranger ESP32-S3 firmware

This is the PlatformIO firmware for the Stranger lower body controller.

## Board

Current target board:

- ESP32-S3 generic development board
- N16R8: 16MB Flash, 8MB PSRAM
- CH343 USB-UART
- Use the USB-UART / COM / PROG Type-C port for first-stage flashing and serial monitor

PlatformIO board target:

```ini
board = esp32-s3-devkitc-1
framework = arduino
```

The current firmware does not use PSRAM. It sets the flash size to 16MB and keeps serial on the CH343 USB-UART path.

## VS Code / IntelliSense

This PlatformIO project is nested under the main repository. If VS Code is opened at the repository root, C/C++ IntelliSense may not find `Arduino.h`, `Wire.h`, `Serial`, or Arduino types even though the firmware builds correctly.

Open the firmware workspace instead:

```text
/Users/jackzhang/Unnamed_sys/stranger_esp32s3.code-workspace
```

Then run:

```text
PlatformIO: Rebuild IntelliSense Index
```

If red squiggles remain after the index rebuild, run:

```text
C/C++: Reset IntelliSense Database
```

Keep `Arduino.h` included in every `.cpp` file that directly uses Arduino APIs:

```cpp
#include <Arduino.h>
```

PlatformIO `.cpp` files do not get the same automatic `Arduino.h` insertion that Arduino IDE applies to `.ino` sketches. I2C code lives in `tof_scan.*`, so `Wire.h` is included there instead of in `main.cpp`.

## Wiring used by this firmware

| Function | ESP32-S3 GPIO |
|---|---:|
| I2C SDA | GPIO8 |
| I2C SCL | GPIO9 |
| M1 PWM | GPIO4 |
| M1 DIR | GPIO10 |
| M2 PWM | GPIO5 |
| M2 DIR | GPIO11 |
| M3 PWM | GPIO6 |
| M3 DIR | GPIO12 |
| M4 PWM | GPIO7 |
| M4 DIR | GPIO13 |
| BNO085 SPI SCK | GPIO15 |
| BNO085 SPI MISO | GPIO16 |
| BNO085 SPI MOSI | GPIO17 |
| BNO085 SPI CS | GPIO18 |
| BNO085 INT | GPIO21 |
| BNO085 RST | GPIO47 |
| Board WS2812 RGB | GPIO48 |

The motor outputs initialize to `PWM=0`. The firmware will not move motors on boot.

The board's GPIO48 WS2812 RGB LED is explicitly cleared during boot. Its color is
not used as a power, fault, or motion status indicator.

Motor commands are guarded by `arm`. After `arm`, the firmware allows short timed motor pulses for testing. The arm window expires after 60 seconds and all motor pulses auto-stop.

The first local safety loop is ToF based. It does not estimate pose, distance traveled, or heading. Without encoders, motion remains open-loop and low-speed only; the closed loop is limited to near-field obstacle reaction. BNO085 IMU data is currently observation-only telemetry and does not stop or steer the chassis.

## Firmware structure

The firmware is split by responsibility:

| Module | Responsibility |
|---|---|
| `main.cpp` | Boot sequence, main loop, heartbeat scheduling |
| `motor_driver.*` | PWM/DIR output, arm/disarm, auto-stop, single-motor tests |
| `chassis.*` | 4WD differential mixing for throttle + turn, with obstacle gate filtering |
| `tof_scan.*` | TCA9548A / VL53L1X channel scan and distance telemetry |
| `imu_monitor.*` | BNO085 SPI initialization, yaw/pitch/roll, gyro, accel telemetry |
| `obstacle_gate.*` | ToF safety state, slow-zone clipping, hard-stop blocking |
| `roam_controller.*` | ESP32-local low-speed reactive roaming |
| `serial_protocol.*` | Text and JSON serial command parsing |
| `status_led.*` | Board GPIO48 WS2812 startup clear |
| `config.h` | Pin map, motor positions, limits, timing constants |

## Serial commands

Open the PlatformIO serial monitor at `115200`.

```text
help
status
scan
tof
imu
telemetry on
telemetry off
avoidance on
avoidance off
roam start
roam stop
arm
disarm
motors off
motor <1-4> <duty -250..250> [duration_ms <= 30000]
drive <throttle -250..250> <turn -250..250> [duration_ms <= 30000]
spin <duty -250..250> [duration_ms <= 30000]
test <1-4> [duty 1..250] [duration_ms <= 30000]
test all [duty 1..250] [duration_ms <= 30000]
```

Examples:

```text
scan
tof
imu
telemetry off
arm
motor 1 70 500
motor 1 -70 500
motor 1 250 30000
drive 70 0 500
drive 60 -20 500
spin 60 500
test 1
test all 60 400
roam start
roam stop
motors off
disarm
```

`motor 1 70 500` means: run motor 1 forward at duty 70 for 500 ms, then auto-stop.

`test 1` means: run motor 1 forward briefly, stop, then reverse briefly, then stop.

`motors off` immediately stops all PWM outputs and disarms the motor test gate.

`imu` prints one BNO085 telemetry snapshot. In the current firmware it is a safety-observation sensor only: no tilt threshold, impact threshold, heading hold, or automatic motor stop is applied.

`telemetry off` stops automatic `tof`, `obstacle`, `imu`, and `heartbeat` output so manual motor tests are readable. Manual commands such as `status`, `tof`, `imu`, and `scan` still print on demand. Use `telemetry on` to resume automatic telemetry for the Mac-side bridge.

Use a low duty first. If a motor does not move at duty 60-70, increase gradually. For isolated bench diagnosis, the firmware allows duty up to 250 out of the ESP32's 8-bit PWM range.

The maximum timed command window is 30000 ms. This is intended for bench
diagnosis with a multimeter or oscilloscope; keep the chassis lifted or otherwise
safe before running long full-duty tests.

4WD differential mixing:

```text
left  = throttle + turn
right = throttle - turn

left side  -> M1 front_left + M3 rear_left
right side -> M2 front_right + M4 rear_right
```

If either side exceeds the max duty, both sides are scaled down proportionally.

ToF obstacle gate:

```text
sensor_fault   -> block chassis drive/spin and keep PWM at zero
obstacle_stop  -> block normal chassis drive/spin and keep PWM at zero
slow_zone      -> cap forward throttle to 45 and bias away from the closer front sensor
clear          -> allow low-speed open-loop movement
```

Thresholds are currently:

| Zone | Distance |
|---|---:|
| hard stop | `< 250 mm` |
| slow zone | `250-600 mm` |
| clear | `> 600 mm` |

`motor`, `test`, and `test all` remain bring-up tools. They still require `arm`, but they do not pass through the ToF obstacle gate so that individual motor channels can be verified during wiring.

JSON commands are also accepted for the later Mac mini bridge:

```json
{"cmd":"arm"}
{"cmd":"status"}
{"cmd":"tof"}
{"cmd":"imu"}
{"cmd":"telemetry","enabled":false}
{"cmd":"avoidance","enabled":true}
{"cmd":"roam","enabled":true}
{"cmd":"motor","m":1,"duty":70,"ms":500}
{"cmd":"drive","throttle":70,"turn":-20,"ms":500}
{"cmd":"spin","duty":60,"ms":500}
{"cmd":"stop"}
```

Use `scan` after wiring the TCA9548A and VL53L1X sensors. The expected first result is TCA9548A at `0x70`, then VL53L1X at `0x29` on channels 0-3. Use `tof` after `scan` succeeds to inspect per-channel `distance_mm`, freshness, and VL53L1X range status.

Use `imu` after wiring the BNO085 in SPI mode. Expected bring-up output is `present=true`, `initialized=true`, `fresh=true`, and `state="ok"`. Slowly tilt or rotate the body and confirm `yaw_deg`, `pitch_deg`, `roll_deg`, `gyro_rad_s`, and `accel_m_s2` change. If the IMU is disconnected or in the wrong interface mode, `state` should remain `not_found`, `report_error`, `no_update`, or `stale`, but manual chassis control is not blocked by IMU state in this version.

BNO085 SPI wiring details:

| BNO085 pin | ESP32-S3 / power | Notes |
|---|---|---|
| `VIN` | `3V3` | Keep logic at 3.3V |
| `GND` | `GND` | Shared logic ground |
| `SCL` | GPIO15 | SPI SCK |
| `SDA` | GPIO16 | SPI MISO, BNO085 to ESP32-S3 |
| `DI` | GPIO17 | SPI MOSI, ESP32-S3 to BNO085 |
| `CS` | GPIO18 | SPI chip select |
| `INT` | GPIO21 | Data-ready interrupt, required for stable SPI |
| `RST` | GPIO47 | Reset, required for stable SPI |
| `P0/PS0` | `3V3` | SPI mode select |
| `P1/PS1` | `3V3` | SPI mode select |

`roam start` requires `arm` and `avoidance on`. Roam is local to the ESP32 and only uses conservative primitives: slow forward, slow-zone steering bias, hard-stop escape reverse, and turn-away.

## Local CLI notes

The PlatformIO executable installed by the VS Code extension may not be on the shell `PATH`. On this machine it is available at:

```bash
~/.platformio/penv/bin/pio
```

Build:

```bash
~/.platformio/penv/bin/pio run -d firmware/stranger_esp32s3
```

Upload to the detected CH343 serial port:

```bash
~/.platformio/penv/bin/pio run -d firmware/stranger_esp32s3 -t upload --upload-port /dev/cu.usbmodem5C4D0378301
```

If PlatformIO package installation fails with a Python SSL certificate error, rerun with:

```bash
PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" ~/.platformio/penv/bin/pio run -d firmware/stranger_esp32s3
```
