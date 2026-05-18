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
- IMU integration
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
