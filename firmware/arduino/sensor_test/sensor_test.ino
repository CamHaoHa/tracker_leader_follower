#include <Arduino.h>

// Standalone HC-SR04 bench test for a classic ESP32.
// TRIG -> GPIO32; ECHO -> GPIO34, wired directly.
// Sensor VCC -> 3V3 (ECHO is then a 3.3 V signal, so there is no divider) and a
// common ground with the ESP32. GPIO34 is input-only, no internal pull resistors.
// Disconnect servo power for this test; this sketch does not drive a servo.
constexpr uint8_t TRIG_PIN = 32;
constexpr uint8_t ECHO_PIN = 34;
constexpr unsigned long ECHO_TIMEOUT_US = 30000;
// Bench-test acceptance limits, not the full playing-area geometry.
// Default project placement needs about 234 cm to reach the opposite far corner.
constexpr float MIN_DISTANCE_CM = 2.0f;
constexpr float MAX_DISTANCE_CM = 200.0f;

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);
  delay(1000);
  Serial.println("HC-SR04 test: TRIG=32, ECHO=34, units=cm");
  Serial.println("Accepted range: 2-200 cm. Other distances report OUT OF RANGE.");
  Serial.println("Point at a flat target about 20-50 cm away.");
}

void loop() {
  if (digitalRead(ECHO_PIN) == HIGH) {
    Serial.println("ECHO already HIGH: check ECHO wiring, sensor power and ground.");
    delay(500);
    return;
  }

  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  const unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) {
    Serial.println("NO ECHO: check target, power, common ground and wiring.");
  } else {
    const float distance_cm = duration * 0.0343f / 2.0f;
    if (distance_cm < MIN_DISTANCE_CM || distance_cm > MAX_DISTANCE_CM) {
      Serial.println("OUT OF RANGE: outside 2-200 cm; reading rejected.");
    } else {
      Serial.print("Distance: ");
      Serial.print(distance_cm, 1);
      Serial.print(" cm | echo: ");
      Serial.print(duration);
      Serial.println(" us");
    }
  }
  delay(500);
}
