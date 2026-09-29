#include <Arduino.h>

// Bench test for ONE box: a positional servo plus an HC-SR04, no Wi-Fi.
// Prints every servo move and every range reading on the USB serial port so
// you can see both parts working before the tracker firmware goes on.
//
// Board: any classic ESP32 dev board (Freenove WROOM-32E, ELEGOO ESP-WROOM-32).
// Arduino core 2.x (PlatformIO) or 3.x (Arduino IDE) - both are handled below.
//
// Wiring (same GPIO map as the tracker firmware):
//   Servo signal (orange) -> GPIO33      servo red -> VIN (5 V)   servo brown -> GND
//   HC-SR04 TRIG          -> GPIO32      sensor VCC -> 3V3
//   HC-SR04 ECHO          -> GPIO34      wired directly: on 3V3 the ECHO signal is
//                                        3.3 V, so there is no divider.
//   Every ground goes to an ESP32 GND pin.
//   Never power the sensor from 5 V with ECHO wired directly: a 5 V ECHO would
//   exceed what an ESP32 input tolerates.
//
// Serial monitor at 115200 baud, line ending "Newline". Commands:
//   <number>   aim the servo at that many degrees (30..150), then ping 3 times
//   p          ping once at the current bearing
//   s          start/stop the automatic sweep (60 -> 120 -> 60 in 10 deg steps)
//   c          centre the servo at 90 degrees
//   ?          print this list again
// The sweep is ON after boot. Send "s" to stop it and drive by hand.

// ---- pins and servo mapping ---------------------------------------------
constexpr uint8_t SERVO_PIN = 33;
constexpr uint8_t TRIG_PIN = 32;
constexpr uint8_t ECHO_PIN = 34;

// Bench finding (2026-09-15): the SG90 needs 500..2500 us to reach a full
// 0..180 degree scale. 500/2500 are not verified mechanical end stops, so the
// allowed travel is kept well inside them.
constexpr uint32_t PULSE_MIN_US = 500;
constexpr uint32_t PULSE_MAX_US = 2500;
constexpr int TRAVEL_MIN_DEG = 30;
constexpr int TRAVEL_MAX_DEG = 150;
constexpr uint8_t SERVO_CHANNEL = 0;
constexpr uint8_t SERVO_BITS = 16;
constexpr uint32_t SERVO_PERIOD_US = 20000;  // 50 Hz

// ---- timing ---------------------------------------------------------------
constexpr uint32_t SETTLE_MS = 400;        // wait after a move before pinging
constexpr uint32_t PING_GAP_MS = 65;       // HC-SR04 minimum spacing
constexpr uint32_t ECHO_TIMEOUT_US = 30000;  // ~5 m round trip
constexpr int PINGS_PER_POSITION = 3;
constexpr int SWEEP_MIN_DEG = 60;
constexpr int SWEEP_MAX_DEG = 120;
constexpr int SWEEP_STEP_DEG = 10;

// ---- state ----------------------------------------------------------------
bool servo_ready = false;
int servo_deg = 90;
uint32_t moved_at = 0;
uint32_t last_ping_at = 0;
int pings_left = 0;
bool sweeping = true;
int sweep_dir = +1;
String line;

// ---------------------------------------------------------------------------
uint32_t pulse_for(int deg) {
  return PULSE_MIN_US + (uint32_t)deg * (PULSE_MAX_US - PULSE_MIN_US) / 180;
}

bool servo_begin() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  return ledcAttachChannel(SERVO_PIN, 50, SERVO_BITS, SERVO_CHANNEL);
#else
  if (ledcSetup(SERVO_CHANNEL, 50, SERVO_BITS) == 0) return false;
  ledcAttachPin(SERVO_PIN, SERVO_CHANNEL);
  return true;
#endif
}

void servo_write(int deg) {
  deg = constrain(deg, TRAVEL_MIN_DEG, TRAVEL_MAX_DEG);
  const uint32_t pulse_us = pulse_for(deg);
  const uint32_t duty = ((uint64_t)pulse_us * ((1UL << SERVO_BITS) - 1) + SERVO_PERIOD_US / 2) / SERVO_PERIOD_US;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWriteChannel(SERVO_CHANNEL, duty);
#else
  ledcWrite(SERVO_CHANNEL, duty);
#endif
  servo_deg = deg;
  moved_at = millis();
  pings_left = PINGS_PER_POSITION;
  Serial.printf("[%7lu ms] SERVO  -> %3d deg   pulse %4lu us   duty %5lu/65535\n",
                (unsigned long)moved_at, deg, (unsigned long)pulse_us, (unsigned long)duty);
}

void ping() {
  const uint32_t now = millis();
  last_ping_at = now;
  if (digitalRead(ECHO_PIN) == HIGH) {
    Serial.printf("[%7lu ms] PING   %3d deg   ECHO STUCK HIGH - power-cycle the sensor, check ECHO wiring and ground\n",
                  (unsigned long)now, servo_deg);
    return;
  }
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  const uint32_t echo_us = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (echo_us == 0) {
    Serial.printf("[%7lu ms] PING   %3d deg   NO ECHO (nothing within ~5 m, or no power / no common ground)\n",
                  (unsigned long)now, servo_deg);
    return;
  }
  const float cm = echo_us / 58.0f;
  Serial.printf("[%7lu ms] PING   %3d deg   %6.1f cm   echo %5lu us%s\n",
                (unsigned long)now, servo_deg, cm, (unsigned long)echo_us,
                cm < 2.0f ? "   (too close)" : cm > 400.0f ? "   (beyond rated range)" : "");
}

void print_help() {
  Serial.println();
  Serial.println("Commands: <deg> aim | p ping | s sweep on/off | c centre | ? help");
  Serial.printf("Travel %d..%d deg, pulse %lu..%lu us, sweep %d..%d deg in %d deg steps\n",
                TRAVEL_MIN_DEG, TRAVEL_MAX_DEG, (unsigned long)PULSE_MIN_US, (unsigned long)PULSE_MAX_US,
                SWEEP_MIN_DEG, SWEEP_MAX_DEG, SWEEP_STEP_DEG);
  Serial.println();
}

void handle_command(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  const char c = cmd[0];
  if (c == '?' || c == 'h') {
    print_help();
  } else if (c == 'p') {
    pings_left = 1;
  } else if (c == 's') {
    sweeping = !sweeping;
    Serial.printf("[%7lu ms] SWEEP  %s\n", (unsigned long)millis(), sweeping ? "on" : "off");
  } else if (c == 'c') {
    sweeping = false;
    servo_write(90);
  } else if (isDigit(c) || c == '-' || c == '+') {
    sweeping = false;
    const int deg = cmd.toInt();
    if (deg < TRAVEL_MIN_DEG || deg > TRAVEL_MAX_DEG) {
      Serial.printf("Ignored %d: travel is limited to %d..%d deg on this bench\n", deg, TRAVEL_MIN_DEG, TRAVEL_MAX_DEG);
    } else {
      servo_write(deg);
    }
  } else {
    Serial.printf("Unknown command '%s'. Send ? for help.\n", cmd.c_str());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);  // GPIO34 is input-only, no internal pull resistors
  delay(1000);

  Serial.println();
  Serial.println("=== Servo + HC-SR04 bench test ===");
  Serial.printf("Arduino-ESP32 core %u.%u.%u, chip %s rev %u, %u MHz\n",
                ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getCpuFreqMHz());
  Serial.printf("Pins: servo=%u  TRIG=%u  ECHO=%u\n", SERVO_PIN, TRIG_PIN, ECHO_PIN);
  Serial.println("Power: servo red on VIN. Sensor VCC on 3V3, ECHO wired directly (no divider).");

  servo_ready = servo_begin();
  if (!servo_ready) {
    Serial.println("SERVO  PWM setup FAILED - LEDC channel unavailable; only ranging will run");
  } else {
    servo_write(90);  // always start from the centre
  }
  if (digitalRead(ECHO_PIN) == HIGH) {
    Serial.println("WARNING: ECHO is already HIGH at boot. Sensor unpowered, ECHO floating, or hung. Fix before trusting ranges.");
  }
  print_help();
  Serial.printf("[%7lu ms] SWEEP  on (send s to stop)\n", (unsigned long)millis());
}

void loop() {
  // Serial commands, one per line.
  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      handle_command(line);
      line = "";
    } else if (line.length() < 16) {
      line += c;
    }
  }

  const uint32_t now = millis();
  const bool settled = now - moved_at >= SETTLE_MS;
  const bool gap_ok = now - last_ping_at >= PING_GAP_MS;

  if (pings_left > 0 && settled && gap_ok) {
    ping();
    pings_left--;
    return;
  }

  if (sweeping && servo_ready && pings_left == 0 && settled) {
    int next = servo_deg + sweep_dir * SWEEP_STEP_DEG;
    if (next > SWEEP_MAX_DEG) { sweep_dir = -1; next = servo_deg - SWEEP_STEP_DEG; }
    if (next < SWEEP_MIN_DEG) { sweep_dir = +1; next = servo_deg + SWEEP_STEP_DEG; }
    servo_write(next);
  }
}
