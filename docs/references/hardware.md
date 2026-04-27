# hardware.md

## Current hardware implementation plan

### System architecture
- **1 upper computer + 2 lower controllers + 1 shared vision module**
- **Upper computer**: runs YOLO vision, event parsing, dual-entity state machine, memory, policy, TTS generation, and dispatch
- **Lower controller A**: Shopkeeper entity hardware bridge — LEDs, servo, ToF sensor, audio playback
- **Lower controller B**: Stranger entity hardware bridge — LEDs, servo, ToF sensor, audio playback
- **Communication**: WiFi (WebSocket) between upper computer and both lower controllers
- **Audio output**: headphone jack on each entity body (visitor plugs in directly)
- **No display / projection in current phase**

---

## 1. Upper computer

### Role
- Shared camera input
- YOLO detection / zone judgement
- Fusion of local distance sensor data from both entities
- Event generation
- Shopkeeper / Stranger state update
- Memory + policy
- TTS generation and audio stream dispatch to each lower controller

### Recommended spec (self-built)
- **CPU**: Intel i5-13400F
- **GPU**: RTX 3060 12GB
- **RAM**: 16GB DDR5
- **Storage**: 512GB SSD

### Why this spec
- RTX 3060 12GB is sufficient for YOLOv8s at 30+ fps and local TTS inference
- LLM runs via Anthropic cloud API — no local GPU requirement for language model
- Self-built avoids paying OEM premium; desktop form factor is stable for exhibition deployment

---

## 2. Lower controllers (×2)

### Role
- Hardware bridge only
- Receive control commands from upper computer via WiFi
- Drive LEDs and servos
- Read local ToF sensor and report back to upper computer via WiFi
- Receive audio stream from upper computer and play via onboard I2S DAC
- Do **not** run YOLO / LLM / memory / high-level decision logic

### Recommended model
- **ESP32-S3 development board** ×2

### Why ESP32-S3
- Native WiFi (no external module needed)
- I2S peripheral for audio DAC output
- Sufficient GPIO for LED data line, servo PWM, I2C (ToF), I2S (DAC)
- Significantly cheaper than Arduino UNO R4 WiFi for equivalent capability

### Per-entity responsibilities
- Shopkeeper lower controller: warm/stable light language, optional forward-facing micro motion, near-field sensor, headphone audio output
- Stranger lower controller: cold/unstable light language, optional evasive micro motion, near-field sensor, headphone audio output

---

## 3. Shared vision module

### Role
- Global scene perception only
- Detect people, position, zone, lingering, re-approach
- Determine whether a person is closer to Shopkeeper / Stranger / in-between

### Recommended hardware
- **Logitech C930e** ×1 (1080p, 90° field of view)

### Compute location
- YOLO runs on **upper computer only**

### Why C930e over Brio 4K
- YOLO processes at 640×640 or 1280×720 — 4K resolution provides no benefit
- 90° wide angle covers both entity zones without repositioning
- Significantly lower cost

---

## 4. Local proximity sensing

### Role
- Confirm whether someone has entered the near-field zone of each entity
- Used as local grounding for each body
- Complements camera-based global detection

### Recommended hardware
- **VL53L1X ToF distance sensor** ×2
- One per entity, connected to ESP32 via I2C

### Placement
- Mount on each entity body facing forward at chest / head height

---

## 5. Lighting / state output

### Role
- Main non-screen state expression layer
- Show attention / warning / invitation / silence / instability

### Recommended hardware
- **WS2812B RGBW Ring 24** ×2
- One per entity, data line driven directly from ESP32 GPIO

### Suggested mapping
- Shopkeeper: warm, stable, territorial
- Stranger: cold, drifting, unstable

### Why Ring 24 over Ring 16
- Higher pixel density gives stronger visual presence at exhibition viewing distance
- WS2812B RGBW compatible with standard NeoPixel library

---

## 6. Micro-motion (optional but recommended)

### Role
- Minimal body reaction only
- No humanoid complexity

### Recommended hardware
- **MG90S metal-gear micro servo** ×2–4
- 1–2 per entity depending on mechanism

### Typical motion
- Shopkeeper: slight lean / orientation toward visitor
- Stranger: slight turn-away / hesitation / recoil

---

## 7. Audio output

### Principle
- TTS generation runs on the **upper computer**
- Upper computer streams PCM audio to each lower controller via WiFi
- Each lower controller decodes and plays audio locally through an I2S DAC
- Visitors plug headphones directly into the 3.5mm jack on the entity body
- No USB sound cards, no amplifier boards, no speaker cables from upper computer to entity

### Hardware per entity (on lower controller)
- **PCM5102A I2S DAC breakout board** ×1
- Connected to ESP32-S3 I2S peripheral
- 3.5mm stereo jack soldered to PCM5102A output
- PCM5102A output level is sufficient to drive standard headphones (32Ω and above) without additional amplification

### Audio routing
```
Upper computer
  → TTS synthesis → PCM audio
  → WiFi stream → ESP32-S3 (Shopkeeper) → PCM5102A I2S DAC → 3.5mm jack
  → WiFi stream → ESP32-S3 (Stranger)   → PCM5102A I2S DAC → 3.5mm jack
```

---

## 8. Communication

### Protocol
- **WiFi + WebSocket** between upper computer and both lower controllers
- All control commands and audio streaming use the same WiFi network
- Upper computer acts as WebSocket server; both ESP32 boards connect as clients

### Message types (upper → lower)
- LED command: color array (24 RGBW values) + transition mode
- Servo command: target angle + speed
- Audio chunk: raw PCM data (16-bit, 16kHz, mono)

### Message types (lower → upper)
- ToF reading: distance in mm + timestamp

### Development note
- Initial development uses **USB serial** for simplicity and stable debugging
- Migrate to WiFi WebSocket after LED/servo/sensor pipeline is verified stable
- Command message format stays identical across both transports — only the transport layer changes

---

## 9. Power

### Recommended hardware
- **Mean Well LRS-50-5 (5V 10A)** ×2
- One dedicated supply per entity for LED ring and servo load
- ESP32-S3 and PCM5102A powered from same 5V rail via onboard regulator

### Power rule
- Do not rely on USB bus power for LED rings or servos under load
- Use separate regulated 5V rail per entity; share common ground with ESP32
- Upper computer runs on standard wall outlet; no UPS required for course exhibition

---

## 10. Recommended BOM

| Category | Model | Qty | Est. price (¥) | Notes |
|---|---|---:|---:|---|
| Upper computer | i5-13400F + RTX 3060 12G + 16GB DDR5 + 512G SSD (self-built) | 1 | ~5500 | YOLO + local TTS sufficient |
| Lower controller | ESP32-S3 development board | 2 | ~40 / unit | Native WiFi + I2S |
| I2S DAC | PCM5102A breakout board | 2 | ~25 / unit | Headphone-level output, no amp needed |
| Shared camera | Logitech C930e (1080p 90°) | 1 | ~650 | Wide angle covers both zones |
| Local distance sensor | VL53L1X ToF (with breakout) | 2 | ~45 / unit | I2C, one per entity |
| LED state output | WS2812B RGBW Ring 24 | 2 | ~90 / unit | One per entity |
| Servo | MG90S metal-gear micro servo | 2–4 | ~22 / unit | Optional micro-motion |
| 5V regulated PSU | Mean Well LRS-50-5 (5V 10A) | 2 | ~120 / unit | One per entity, LEDs + servo |
| Cables / consumables | USB cables, Dupont wires, heat shrink, wire | — | ~80 | — |
| **Total** | | | **~6950** | |

---

## 11. Signal flow

### Perception flow
1. Shared camera → upper computer (USB)
2. YOLOv8 detection → visitor zone / position / lingering events
3. ESP32-A ToF + ESP32-B ToF → WiFi → upper computer
4. Upper computer fuses global camera events and local ToF events

### Decision flow
1. Upper computer builds PerceptionEvent list
2. Upper computer updates Shopkeeper state and Stranger state independently
3. Upper computer selects response policy for each entity
4. Upper computer generates TTS audio and LED / servo commands for each entity

### Execution flow
1. Upper computer → WiFi → ESP32-A: LED command + servo command + audio stream (Shopkeeper)
2. Upper computer → WiFi → ESP32-B: LED command + servo command + audio stream (Stranger)
3. ESP32-A drives Shopkeeper LED ring + servo + PCM5102A headphone output
4. ESP32-B drives Stranger LED ring + servo + PCM5102A headphone output
5. Visitor plugs headphones into 3.5mm jack on entity body to hear speech

---

## 12. Implementation order

### Phase 1
- Upper computer ↔ 2 ESP32-S3 boards via USB serial
- Control LED ring and servo only
- Verify command protocol and response latency

### Phase 2
- Add VL53L1X ToF sensors to both entities
- ESP32 reads distance via I2C and reports back to upper computer
- Verify near-field event generation

### Phase 3
- Add shared camera (C930e)
- Run YOLOv8 on upper computer
- Build zone events from detection output

### Phase 4
- Add PCM5102A I2S DAC to each ESP32
- Test TTS audio generation on upper computer and PCM stream to ESP32
- Verify headphone output quality and latency

### Phase 5
- Migrate communication from USB serial to WiFi WebSocket
- Command message format unchanged; only transport layer replaced
- Verify stability under continuous exhibition conditions

### Phase 6
- Integrate full dual-entity state machine + memory + policy
- End-to-end test: visitor enters zone → YOLO event → state update → TTS → headphone output + LED change

---

## 13. Final definition
- **Upper computer = eyes + world model + memory + decision + voice**
- **Lower controllers = bodies — light, motion, and local hearing/speaking**
- **Shopkeeper and Stranger share one world, but perceive and respond through separate bodies**
