# hardware.md

## Current hardware implementation plan

*Stranger mobile body hardware plan — single-entity version*

---

## 0. Current scope

This project currently implements **Stranger only**. The previous two-entity hardware plan with Shopkeeper + Stranger, two ESP32 controllers, ESP32-side audio DAC playback, and a fixed external upper computer is no longer the active plan for this repository.

Current active hardware target:

- One mobile Stranger body
- One Mac mini carried by the body as the upper computer
- One ESP32-S3 as the lower body controller
- Four VL53L1X ToF sensors for local obstacle sensing
- One TCA9548A I2C multiplexer for the ToF bus
- One four-channel brushed DC motor driver board
- Four 36JP555 brushed DC geared motors
- One small speaker connected directly to the Mac mini
- One small screen as Stranger's visible body-state surface

Out of current scope:

- Second ESP32
- Shopkeeper entity
- ESP32 + PCM5102A audio playback
- Wheel encoders
- IMU control-loop integration; BNO085 SPI wiring is reserved below for a later phase
- Full SLAM, precise odometry, or map-based navigation

The first hardware milestone is **local ToF obstacle avoidance**, then motor behavior and body presentation can be integrated into the Stranger runtime.

---

## 1. System architecture

```text
Stranger mobile body
├── Mac mini
│   ├── Runs the Python Stranger runtime
│   ├── Runs LLM, memory, policy, audio generation, and developer API
│   ├── Outputs sound directly to a small speaker
│   ├── Drives or serves the small body screen
│   └── Sends body commands to ESP32-S3 over USB serial
│
├── ESP32-S3
│   ├── Reads four VL53L1X ToF sensors through TCA9548A
│   ├── Applies local obstacle-avoidance gate
│   ├── Outputs PWM + DIR signals to motor driver
│   └── Reports sensor and safety state back to Mac mini
│
├── TCA9548A I2C multiplexer
│   └── VL53L1X ToF sensors x4
│
├── Four-channel brushed DC motor driver
│   └── 36JP555 geared brushed DC motors x4
│
├── Small speaker
│   └── Connected to Mac mini audio output
│
└── Small screen
    └── Stranger body-state surface, not an operator dashboard
```

### Role split

| Layer | Hardware | Responsibility |
|---|---|---|
| Upper computer | Mac mini | Stranger runtime, LLM, memory, policy, TTS/audio output, high-level movement intent |
| Lower controller | ESP32-S3 | ToF polling, local obstacle gate, motor PWM/DIR output, sensor telemetry |
| Sensor layer | TCA9548A + VL53L1X x4 | Near-field distance sensing for obstacle avoidance |
| Actuation layer | Four-channel driver + 36JP555 x4 | Brushed DC motor movement |
| Presentation layer | Speaker + small screen | Voice and body-state expression |

The ESP32-S3 must not run LLM logic, memory, policy selection, or artistic behavior rules. Its local logic is allowed to override motion commands for hardware safety and obstacle avoidance.

---

## 2. Upper computer

### Recommended hardware

- **Mac mini** carried by the Stranger body

### Responsibilities

- Run the current Stranger Python system
- Maintain state, memory, policy, expression, and runtime trace
- Generate or stream audio through the existing runtime path
- Play audio directly through a small speaker connected to the Mac mini
- Send compact motion / body commands to ESP32-S3
- Receive ToF and safety telemetry from ESP32-S3
- Continue serving the developer dashboard for operator use

### Design notes

- Audio should stay on the Mac mini path for now.
- ESP32-side PCM5102A / I2S audio is removed from the active plan.
- The small speaker is part of the Stranger body, not a separate distributed audio node.
- The small screen is a body-state surface and should not expose internal debug state, hidden prompts, memory tables, or numeric policy internals to visitors.

---

## 3. Lower controller

### Recommended hardware

- **ESP32-S3 development board** x1

### Responsibilities

- Communicate with Mac mini over USB serial in the first implementation phase
- Poll four VL53L1X ToF sensors through TCA9548A
- Maintain a local obstacle state
- Apply local obstacle avoidance before motor output
- Generate PWM + DIR outputs for four DC motors
- Report ToF distances, motor output summary, and local safety state to Mac mini

### Non-responsibilities

- No LLM calls
- No memory persistence
- No policy selection
- No direct generation of Stranger speech
- No autonomous rewriting of behavior rules
- No claim of precise localization or path following in the current phase

---

## Complete wiring plan

This wiring plan is the current recommended plan for the first ESP32-S3 body controller build. The exact ESP32-S3 GPIO numbers must be verified against the actual development board before power-on, because some ESP32-S3 boards reserve different pins for flash, PSRAM, USB, bootstrapping, or onboard peripherals.

### Wiring assumptions

- Logic voltage is **3.3V**.
- Mac mini connects to ESP32-S3 through USB for flashing, serial command, and first-stage debugging.
- TCA9548A and VL53L1X sensor logic run from the ESP32-S3 3.3V rail.
- The motor driver motor-bus supply is separate from ESP32-S3 logic power.
- The motor driver's isolated signal side is powered by ESP32-S3 logic power through the driver's `+V` / `-V` control header.
- Small speaker and small screen connect to the Mac mini, not to ESP32-S3, unless a later display design explicitly changes this.

### Proposed ESP32-S3 pin map

| Function | ESP32-S3 GPIO | Connected hardware | Notes |
|---|---:|---|---|
| I2C SDA | GPIO8 | TCA9548A `SDA` | Suggested only; confirm board support |
| I2C SCL | GPIO9 | TCA9548A `SCL` | Suggested only; confirm board support |
| M1 PWM | GPIO4 | Motor driver `P1` | LEDC PWM, start low duty |
| M1 DIR | GPIO10 | Motor driver `D1` | `0` forward, `1` reverse per driver manual |
| M2 PWM | GPIO5 | Motor driver `P2` | LEDC PWM |
| M2 DIR | GPIO11 | Motor driver `D2` | Direction can be inverted in firmware if mechanical mounting requires |
| M3 PWM | GPIO6 | Motor driver `P3` | LEDC PWM |
| M3 DIR | GPIO12 | Motor driver `D3` | Direction can be inverted in firmware if needed |
| M4 PWM | GPIO7 | Motor driver `P4` | LEDC PWM |
| M4 DIR | GPIO13 | Motor driver `D4` | Direction can be inverted in firmware if needed |
| BNO085 SPI SCK | GPIO15 | BNO085 `SCL` | Optional later IMU; SPI mode, not I2C |
| BNO085 SPI MISO | GPIO16 | BNO085 `SDA` | Optional later IMU; BNO085 -> ESP32-S3 |
| BNO085 SPI MOSI | GPIO17 | BNO085 `DI` | Optional later IMU; ESP32-S3 -> BNO085 |
| BNO085 SPI CS | GPIO18 | BNO085 `CS` | Optional later IMU chip select |
| BNO085 INT | GPIO21 | BNO085 `INT` | Optional later IMU data-ready interrupt |
| BNO085 RST | GPIO47 | BNO085 `RST` | Optional later IMU reset |
| Serial command | USB | Mac mini | Use USB CDC / serial monitor first |

Avoid using ESP32-S3 pins that are tied to USB D+/D-, boot mode, flash, PSRAM, or board-specific onboard peripherals. If the chosen development board exposes a safer documented I2C pair, prefer the board's documented pair and update this table before firmware is finalized.

### Mac mini wiring

| Mac mini side | Connected device | Purpose |
|---|---|---|
| USB | ESP32-S3 USB port | Flashing, serial command, telemetry |
| Audio output / USB audio | Small speaker | Stranger voice output |
| HDMI / USB-C display output | Small screen | Stranger body-state surface |
| Power input | Mac mini power supply / mobile power solution | Upper-computer power |

The small screen is a body-state surface. It should display body modes and visual states, not developer logs or internal numeric state.

### ESP32-S3 to TCA9548A wiring

Use the TCA9548A board's upstream connector, labeled as `J9` in the referenced schematic.

| TCA9548A upstream pin | ESP32-S3 connection | Notes |
|---|---|---|
| `GND` | ESP32-S3 `GND` | Shared logic ground |
| `VCC` | ESP32-S3 `3V3` | Keep I2C at 3.3V |
| `SCL` | ESP32-S3 I2C SCL, proposed GPIO9 | Verify actual board pin |
| `SDA` | ESP32-S3 I2C SDA, proposed GPIO8 | Verify actual board pin |
| `RESET` | Pull up to `3V3`, or optional ESP32 GPIO later | First build can keep it pulled high |

TCA9548A address pins:

| Pin | First-build setting | Result |
|---|---|---|
| `A0` | GND | Address bit 0 = 0 |
| `A1` | GND | Address bit 1 = 0 |
| `A2` | GND | Address bit 2 = 0, final I2C address `0x70` |

If the expansion board switches already set `A0`, `A1`, and `A2`, keep all three at GND for the first build.

### TCA9548A to VL53L1X wiring

Use four downstream TCA9548A channels:

| TCA9548A channel | Sensor name | Placement |
|---:|---|---|
| 0 | `front_left` | Front-left obstacle sensing |
| 1 | `front_right` | Front-right obstacle sensing |
| 2 | `left` | Left side clearance |
| 3 | `right` | Right side clearance |

The referenced TCA9548A channel connector order is:

```text
TCA9548A J1-J8
1 GND
2 VCC
3 SCLn
4 SDAn
```

The referenced VL53L1X module connector order is:

```text
VL53L1X P1
1 VIN
2 SDA
3 SCL
4 GND
```

Required cross-wiring for each ToF sensor:

| TCA9548A channel pin | VL53L1X pin | Purpose |
|---|---|---|
| `GND` | `GND` | Logic ground |
| `VCC` | `VIN` | Sensor module input power |
| `SCLn` | `SCL` | I2C clock |
| `SDAn` | `SDA` | I2C data |

Do not use a straight 1-to-1 cable unless the cable has already been rewired to match this mapping.

Optional VL53L1X pins:

| Pin | Current plan |
|---|---|
| `XSHUT` | Leave unconnected for first build if module pull-up is present |
| `GPIO1` | Leave unconnected for first build |

Because TCA9548A isolates the sensors by channel, `XSHUT` address reassignment is not needed for the first four-sensor build.

### Optional ESP32-S3 to BNO085 IMU wiring

This is a reserved wiring plan for a later heading / turn-confirmation phase. It is not part of the current ToF-first bring-up. The BNO085 should not be connected through the TCA9548A ToF multiplexer.

Use **SPI** for the Adafruit BNO085 breakout when possible. The BNO08x I2C path is known to be troublesome with some ESP32 / ESP32-S3 and I2C multiplexer combinations, while SPI keeps the IMU off the ToF safety bus.

Power and mode pins:

| BNO085 pin | ESP32-S3 / rail | Purpose |
|---|---|---|
| `VIN` | ESP32-S3 `3V3` | IMU logic power |
| `GND` | ESP32-S3 `GND` | Shared logic ground |
| `P0` / `PS0` | `3V3` | Select SPI mode |
| `P1` / `PS1` | `3V3` | Select SPI mode |

SPI and control pins:

| BNO085 pin | SPI meaning | ESP32-S3 GPIO | Notes |
|---|---|---:|---|
| `SCL` | `SCK` | GPIO15 | SPI clock |
| `SDA` | `MISO` | GPIO16 | BNO085 data to ESP32-S3 |
| `DI` | `MOSI` | GPIO17 | ESP32-S3 data to BNO085 |
| `CS` | chip select | GPIO18 | Keep separate from motor / ToF pins |
| `INT` | data ready | GPIO21 | Input interrupt; optional in early polling tests but recommended |
| `RST` | reset | GPIO47 | Output reset; recommended for recovery |

Planned IMU responsibilities:

- Short-turn yaw confirmation for commands such as `turn 45` or `spin_angle 90`
- Heading hold during low-speed open-loop driving
- Angular-rate limiting for safer spin behavior
- Tilt / lift / impact detection for local safety state

Limits:

- The IMU does not replace wheel encoders.
- It should not be used as factual distance traveled.
- It should not be treated as full localization, odometry, SLAM, or path replay.

### ESP32-S3 to motor driver control wiring

The motor driver control side uses one PWM line and one direction line per motor. The driver's isolated signal side must also receive logic power.

Control power:

| Motor driver signal header | ESP32-S3 connection | Notes |
|---|---|---|
| `+V` | ESP32-S3 `3V3` | Driver manual supports 3-5.5V signal-side supply |
| `-V` | ESP32-S3 `GND` | Signal-side ground |

Control signals:

| Motor | Motor driver pin | ESP32-S3 GPIO | Signal type |
|---|---|---:|---|
| M1 | `P1` | GPIO4 | PWM |
| M1 | `D1` | GPIO10 | Direction |
| M2 | `P2` | GPIO5 | PWM |
| M2 | `D2` | GPIO11 | Direction |
| M3 | `P3` | GPIO6 | PWM |
| M3 | `D3` | GPIO12 | Direction |
| M4 | `P4` | GPIO7 | PWM |
| M4 | `D4` | GPIO13 | Direction |

Driver logic from the manual:

| P line | D line | Motor state |
|---|---|---|
| PWM | 0 | Forward |
| PWM | 1 | Reverse |
| 0 | 0 or 1 | Brake / stop |

Firmware should support per-motor direction inversion, because final forward movement depends on motor placement and wiring polarity.

### Motor driver to 36JP555 motor wiring

| Motor driver output | Motor | Notes |
|---|---|---|
| `M1` output terminal | 36JP555 motor 1 | Verify physical wheel position during bring-up |
| `M2` output terminal | 36JP555 motor 2 | Verify physical wheel position during bring-up |
| `M3` output terminal | 36JP555 motor 3 | Verify physical wheel position during bring-up |
| `M4` output terminal | 36JP555 motor 4 | Verify physical wheel position during bring-up |

Initial suggested physical naming:

| Motor | Physical position |
|---|---|
| M1 | front_left wheel |
| M2 | front_right wheel |
| M3 | rear_left wheel |
| M4 | rear_right wheel |

If the mechanical layout uses a different order, update both wiring and firmware constants before movement testing.

### Motor power wiring

| Motor driver power terminal | Connection |
|---|---|
| Motor bus `VCC` / positive | Motor battery or regulated motor supply positive |
| Motor bus `GND` / negative | Motor battery or regulated motor supply negative |

Important boundaries:

- Do not power motors from ESP32-S3 USB.
- Do not connect motor bus positive to ESP32-S3.
- The motor bus and ESP32 logic side are separated by the driver's isolated signal design; only connect ESP32 to the driver's signal-side `+V` / `-V` unless the driver vendor documentation requires another connection.
- Keep motor wiring physically away from I2C sensor wiring where possible.
- Twist motor leads or route them away from the ToF/I2C harness to reduce noise.

### Power wiring overview

| Subsystem | Power source | Notes |
|---|---|---|
| Mac mini | Dedicated Mac mini supply / mobile AC or battery solution | Upper computer |
| ESP32-S3 | USB from Mac mini for first build | Also provides serial |
| TCA9548A | ESP32-S3 `3V3` | Logic only |
| VL53L1X x4 | TCA9548A channel `VCC` to sensor `VIN` | Keep logic at 3.3V |
| Motor driver signal side | ESP32-S3 `3V3` and `GND` to `+V` / `-V` | Isolated signal input side |
| Motor driver motor bus | Separate motor supply / battery | Must match 36JP555 and driver current demand |
| Small speaker | Mac mini audio / USB / own power | Do not route through ESP32 |
| Small screen | Mac mini HDMI / USB-C and screen power | Do not expose debug dashboard to visitors |

### First power-on checklist

1. Disconnect motor bus power.
2. Power ESP32-S3 from USB.
3. Confirm TCA9548A appears at I2C address `0x70`.
4. Confirm each VL53L1X responds only on its selected TCA9548A channel.
5. Confirm Serial telemetry prints four distance values.
6. Connect motor driver signal-side `+V` / `-V`, still with motor bus power disconnected.
7. Confirm PWM and DIR pins idle to safe values (`PWM = 0`).
8. Connect one motor channel only with low current / low PWM for first motor test.
9. Verify forward / reverse / brake for one motor.
10. Repeat for M2-M4.
11. Only after each motor channel is verified, test four-wheel low-speed motion with ToF obstacle gate enabled.

---

## 4. ToF obstacle sensing

### Hardware

- **VL53L1X ToF sensor** x4
- **TCA9548A I2C multiplexer** x1

The ToF model is VL53L1X and matches the provided VL53L1X documentation.

### Why TCA9548A

All VL53L1X modules share the same default I2C address. TCA9548A gives each sensor an independent downstream I2C channel, so the ESP32-S3 can poll four identical sensors without address conflict.

### Suggested placement

| Sensor | Purpose |
|---|---|
| `front_left` | Front obstacle and left-front bias |
| `front_right` | Front obstacle and right-front bias |
| `left` | Side clearance while turning or drifting left |
| `right` | Side clearance while turning or drifting right |

Exact placement should be adjusted after body shape and wheelbase are fixed.

### Wiring notes

The currently referenced VL53L1X breakout schematic exposes:

```text
VL53L1X P1
1 VIN
2 SDA
3 SCL
4 GND
```

The referenced TCA9548A expansion board channel connectors expose:

```text
TCA9548A J1-J8
1 GND
2 VCC
3 SCLn
4 SDAn
```

Do not assume a straight 1-to-1 cable between these boards. The harness must intentionally cross the lines:

```text
TCA GND -> VL53L1X GND
TCA VCC -> VL53L1X VIN
TCA SCL -> VL53L1X SCL
TCA SDA -> VL53L1X SDA
```

The current physical build is expected to use this corrected wiring.

### Initial obstacle logic

The first firmware milestone should implement only the local ToF obstacle gate:

```text
if front distance < hard_stop_mm:
    brake / stop
elif front distance < slow_zone_mm:
    limit forward speed
elif front_left is closer than front_right:
    bias turn right
elif front_right is closer than front_left:
    bias turn left
```

Suggested starting thresholds:

| Zone | Distance | Behavior |
|---|---:|---|
| hard stop | `< 250 mm` | Stop or brake immediately |
| slow zone | `250-600 mm` | Limit forward speed |
| clear | `> 600 mm` | Allow normal low-speed motion |

These thresholds are starting points only. They must be tuned on the actual body and exhibition floor.

---

## 5. Motor drive

### Hardware

- **Fierce four-channel brushed DC motor driver board Ver2.3** x1
- **36JP555 brushed DC geared motor** x4

### Driver characteristics from the provided manual

- 12-48V motor bus input
- Recommended operating input: 11-48V
- Four independent full-bridge channels
- Signal input compatible with 3-5.5V logic supply
- Recommended PWM frequency: 1-20kHz
- Practical starting PWM frequency: 10kHz
- Each motor uses simple two-line control:
  - `P` line: PWM speed control
  - `D` line: direction control
- PWM at `0` brakes/stops the motor regardless of direction line

### Control-side pin logic

For motor 1:

| Signal | Meaning |
|---|---|
| `P1` | Motor 1 speed PWM |
| `D1` | Motor 1 direction |

Manual logic:

| P1 | D1 | Motor state |
|---|---|---|
| PWM | 0 | Forward |
| PWM | 1 | Reverse |
| 0 | 0 or 1 | Brake / stop |

Other channels follow the same pattern:

| Motor | PWM | Direction |
|---|---|---|
| M1 | P1 | D1 |
| M2 | P2 | D2 |
| M3 | P3 | D3 |
| M4 | P4 | D4 |

### ESP32-S3 output requirement

The ESP32-S3 needs eight control outputs for the motor driver:

```text
M1_PWM, M1_DIR
M2_PWM, M2_DIR
M3_PWM, M3_DIR
M4_PWM, M4_DIR
```

PWM should start with a conservative limit and ramp:

- Start at low duty cycle
- Apply acceleration ramp
- Avoid instant full-speed reversal
- Force PWM to zero before direction changes when tuning early firmware

Even though the driver supports frequent direction changes, the full mobile body should still use conservative motion profiles to protect the mechanical structure and power system.

---

## 6. Movement model

### Current phase

The current movement model is **open-loop, low-speed, reactive roaming**:

- Mac mini sends high-level motion intent or wheel-speed command
- ESP32-S3 reads ToF sensors
- ESP32-S3 gates or clips motion based on obstacle distances
- ESP32-S3 outputs final PWM + DIR to the motor driver

The system may use PWM duration as a rough motion estimate, but it must not treat PWM as a factual measurement of distance traveled.

### Accepted current limitations

- No wheel encoders
- No precise odometry
- No repeatable route execution
- No guaranteed straight-line travel
- No confirmed turn angle
- Minor drift is acceptable in the current clean exhibition environment

### Deferred additions

If stable route repetition or stronger turn confirmation becomes necessary later, add:

1. Wheel or motor encoders for actual wheel rotation feedback
2. A six-axis IMU for short-turn yaw confirmation

The IMU is intentionally deferred for now. The current implementation should finish ToF-based obstacle avoidance first.

---

## 7. Screen as body-state surface

### Role

The small screen is the Stranger body's visible state surface. It replaces the earlier LED-ring-first presentation plan.

### Design boundary

The screen should not become a conventional UI or dashboard. It should not expose:

- raw state vector values
- policy rule IDs
- memory tables
- hidden prompt fragments
- logs intended for operators

Suitable display modes:

- silence
- disturbance
- attention
- withdrawal
- drift
- near-field alert
- speaking / listening boundary

The developer dashboard remains separate on the Mac mini / operator interface.

---

## 8. Audio output

### Current plan

Audio is generated and played by the Mac mini directly through a small speaker.

### Removed from active plan

- ESP32-S3 I2S audio playback
- PCM5102A DAC
- WiFi audio chunk streaming to ESP32
- Headphone jack on the lower controller

### Runtime boundary

The same existing audio safety principle still applies: Stranger speech must come from governed `ExpressionOutput` / existing audio runtime output, not from an uncontrolled raw text playback shortcut.

---

## 9. Communication

### First phase transport

- **USB serial** between Mac mini and ESP32-S3

Reasons:

- The Mac mini is carried by the body, so USB is physically reasonable
- Lower latency and fewer WiFi failure modes
- Easier debugging during motor and ToF bring-up

### Later transport

WiFi is not needed for the first body prototype. It may be reconsidered only if the physical layout later requires wireless separation.

### Suggested message shape

Mac mini to ESP32-S3:

```json
{
  "type": "drive",
  "m1": 20,
  "m2": 20,
  "m3": 20,
  "m4": 20,
  "duration_ms": 300
}
```

```json
{
  "type": "body_mode",
  "screen_mode": "silent",
  "intensity": 0.4
}
```

ESP32-S3 to Mac mini:

```json
{
  "type": "tof",
  "front_left_mm": 430,
  "front_right_mm": 380,
  "left_mm": 900,
  "right_mm": 760
}
```

```json
{
  "type": "safety",
  "state": "obstacle_stop",
  "reason": "front_left_hard_stop"
}
```

The exact protocol should be finalized before firmware is integrated with the Python runtime.

---

## 10. Power and safety boundaries

### Required power separation

The motor bus must use an appropriate independent supply or battery sized for four 36JP555 motors and the driver board. ESP32-S3 logic, the TCA9548A / VL53L1X sensors, screen, Mac mini, and speaker power should be planned separately.

### Minimum current-stage safety behavior

For the current stage, implement ToF obstacle avoidance first:

- If any front ToF sensor enters hard-stop range, motor PWM must go to zero.
- If an obstacle is inside the slow zone, forward speed must be capped.
- ESP32-S3 should apply this gate locally before motor output.

### Later safety behavior

After ToF obstacle avoidance is stable, add:

- serial command timeout -> stop
- startup neutral state -> PWM zero
- speed limit and acceleration ramp
- command validation
- manual emergency stop
- low-voltage / power fault handling if measurable

The current plan intentionally sequences these after the first ToF avoidance milestone, not before it.

---

## 11. Recommended BOM

| Category | Model / part | Qty | Notes |
|---|---|---:|---|
| Upper computer | Mac mini | 1 | Carried by the Stranger body |
| Lower controller | ESP32-S3 development board | 1 | Body controller |
| I2C multiplexer | TCA9548A expansion board | 1 | Expands one I2C bus to ToF channels |
| ToF sensor | VL53L1X breakout | 4 | Local obstacle sensing |
| Motor driver | Fierce four-channel brushed DC motor driver Ver2.3 | 1 | PWM + DIR control |
| Drive motor | 36JP555 brushed DC geared motor | 4 | No encoder in current phase |
| Display | Small screen | 1 | Body-state surface |
| Audio | Small speaker | 1 | Connected to Mac mini |
| Power | Motor supply / battery | TBD | Must match motor and driver current demand |
| Wiring | Sensor harness, motor wires, USB cable, power wiring | TBD | Must follow corrected ToF line order |

Deferred:

| Category | Part | Reason |
|---|---|---|
| IMU | Six-axis IMU | Deferred until ToF avoidance is stable |
| Wheel feedback | Encoders | Deferred because current route accepts small drift |
| Audio DAC | PCM5102A | Removed from active plan |

---

## 12. Signal flow

### Sensor flow

```text
VL53L1X x4
  -> TCA9548A selected channel
  -> ESP32-S3 I2C read
  -> local obstacle state
  -> serial telemetry to Mac mini
```

### Motion flow

```text
Stranger runtime / body behavior layer
  -> movement intent
  -> USB serial command
  -> ESP32-S3 obstacle gate
  -> PWM + DIR
  -> four-channel motor driver
  -> 36JP555 motors
```

### Audio flow

```text
Stranger runtime
  -> governed expression / TTS path
  -> Mac mini audio output
  -> small speaker
```

### Screen flow

```text
Stranger runtime state / expression output
  -> body-state mode
  -> small screen rendering
```

---

## 13. Implementation order

### Phase 1: ToF bring-up

- Wire ESP32-S3 to TCA9548A
- Wire four VL53L1X sensors with corrected line order
- Poll each TCA9548A channel one at a time
- Report four distance readings over serial
- Confirm distance stability on the actual body

### Phase 2: Local ToF obstacle gate

- Define sensor names and placement
- Implement hard-stop and slow-zone thresholds
- Keep final motor output at zero while obstacle state is unsafe
- Report `clear`, `slow_zone`, and `obstacle_stop` states

### Phase 3: Motor driver bring-up

- Connect ESP32-S3 PWM + DIR lines to the motor driver signal header
- Verify one motor at a time
- Verify forward, reverse, brake, and low-duty ramp
- Expand to four motors only after each channel is confirmed

### Phase 4: Open-loop roaming

- Add conservative movement primitives:
  - stop
  - slow forward
  - slow reverse
  - soft left
  - soft right
  - turn away from obstacle
- Keep movement speed low
- Accept minor drift

### Phase 5: Mac mini runtime bridge

- Add a Python body bridge later under the main project
- Send high-level movement intent from the Stranger runtime
- Receive ToF and safety telemetry
- Preserve the separation between artistic behavior rules and lower-level hardware safety

### Phase 6: Body presentation

- Connect Mac mini audio output to the small speaker
- Implement the small screen as body-state surface
- Map Stranger expression/state into screen modes without exposing operator internals

### Deferred Phase: IMU / encoder additions

- Add six-axis IMU only if turn confirmation becomes necessary
- Add encoders only if route repetition, straight-line correction, or odometry becomes necessary

---

## 14. Final definition

```text
Mac mini = mind, memory, language, voice, high-level intent
ESP32-S3 = local body controller, ToF obstacle gate, motor output
VL53L1X array = near-field obstacle sense
Motor driver + 36JP555 motors = open-loop low-speed movement
Small screen = Stranger body-state surface
Small speaker = Stranger voice output
```

Current physical behavior target:

- Low-speed reactive roaming
- Local ToF obstacle avoidance
- Acceptable minor drift
- No precise odometry claim
- No stable route repetition claim
