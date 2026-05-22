const int BUTTON_PIN = 2;
const unsigned long BAUD_RATE = 115200;
const unsigned long DEBOUNCE_MS = 35;
const unsigned long RETRIGGER_GUARD_MS = 900;

int idleLevel = HIGH;
int pressedLevel = LOW;
int stableLevel = HIGH;
int lastRawLevel = HIGH;
bool wasPressed = false;
unsigned long lastRawChangeAt = 0;
unsigned long lastNewSentAt = 0;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(BAUD_RATE);
  delay(300);

  idleLevel = digitalRead(BUTTON_PIN);
  pressedLevel = idleLevel == HIGH ? LOW : HIGH;
  stableLevel = idleLevel;
  lastRawLevel = idleLevel;

  Serial.print("READY HAVE_SOME_AI_NEW_BUTTON PIN=");
  Serial.print(BUTTON_PIN);
  Serial.print(" IDLE=");
  Serial.print(idleLevel);
  Serial.print(" PRESSED=");
  Serial.println(pressedLevel);
}

void loop() {
  const unsigned long now = millis();
  const int rawLevel = digitalRead(BUTTON_PIN);

  if (rawLevel != lastRawLevel) {
    lastRawLevel = rawLevel;
    lastRawChangeAt = now;
  }

  if (now - lastRawChangeAt < DEBOUNCE_MS) {
    return;
  }

  if (stableLevel != rawLevel) {
    stableLevel = rawLevel;
    const bool isPressed = stableLevel == pressedLevel;

    if (isPressed && !wasPressed && now - lastNewSentAt >= RETRIGGER_GUARD_MS) {
      Serial.println("NEW");
      lastNewSentAt = now;
    }

    wasPressed = isPressed;
  }
}
