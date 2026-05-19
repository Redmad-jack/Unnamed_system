# Stranger ESP32-S3 firmware

This is the first PlatformIO firmware scaffold for the Stranger lower body controller.

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

The first smoke firmware does not use PSRAM. It sets the flash size to 16MB and keeps serial on the CH343 USB-UART path.

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

The motor outputs initialize to `PWM=0`. The firmware will not move motors on boot.

Motor commands are guarded by `arm`. After `arm`, the firmware allows short timed motor pulses for testing. The arm window expires after 60 seconds and all motor pulses auto-stop.

## Serial commands

Open the PlatformIO serial monitor at `115200`.

```text
help
status
scan
arm
disarm
motors off
motor <1-4> <duty -120..120> [duration_ms]
test <1-4> [duty 1..120] [duration_ms]
test all [duty 1..120] [duration_ms]
```

Examples:

```text
scan
arm
motor 1 70 500
motor 1 -70 500
test 1
test all 60 400
motors off
disarm
```

`motor 1 70 500` means: run motor 1 forward at duty 70 for 500 ms, then auto-stop.

`test 1` means: run motor 1 forward briefly, stop, then reverse briefly, then stop.

`motors off` immediately stops all PWM outputs and disarms the motor test gate.

Use a low duty first. If a motor does not move at duty 60-70, increase gradually, but keep the first mechanical test below 120.

Use `scan` after wiring the TCA9548A and VL53L1X sensors. The expected first result is TCA9548A at `0x70`, then VL53L1X at `0x29` on channels 0-3.

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
