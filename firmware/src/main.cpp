#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_arduino_version.h>

#include "settings.h"
#include "wm_protocol.h"

#if ESP_ARDUINO_VERSION_MAJOR != 2
#error "Use the pinned PlatformIO Arduino 2.x toolchain (LEDC API differs in 3.x)"
#endif

namespace {

constexpr uint16_t kHostPort = 4210;
constexpr uint16_t kNodePort = 4211;
constexpr uint32_t kHelloIntervalMs = 2000;
constexpr uint32_t kReconnectIntervalMs = 10000;
constexpr uint32_t kSessionIdleMs = 30000;
constexpr uint8_t kServoChannel = 0;
constexpr uint8_t kServoBits = 16;
constexpr uint32_t kServoPeriodUs = 20000;
constexpr size_t kCacheSize = 16;

WiFiUDP udp;
bool udp_ready = false;
bool servo_ready = false;
uint32_t reconnect_at = 0;
uint32_t last_hello_at = 0;
uint32_t servo_ready_at = 0;
uint32_t last_ping_at = 0;
int32_t current_servo_mdeg = 90000;
uint32_t current_bearing_mdeg = 90000;

struct Result {
  bool valid = false;
  uint32_t sequence = 0;
  uint32_t requested_bearing = 0;
  uint32_t actual_bearing = 0;
  uint32_t distance_mm = 0;
  const char* status = "INVALID";
};

Result results[kCacheSize];
size_t next_result = 0;
bool have_owner = false;
IPAddress owner_ip;
uint32_t latest_sequence = 0;
uint32_t last_command_at = 0;

struct Pending {
  bool active = false;
  wm::Command command{};
  IPAddress address;
} pending;

bool reached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void send_text(const IPAddress& address, const char* text) {
  if (!udp_ready || WiFi.status() != WL_CONNECTED) return;
  if (!udp.beginPacket(address, kHostPort)) return;
  udp.write(reinterpret_cast<const uint8_t*>(text), strlen(text));
  udp.endPacket();
}

void send_result(const IPAddress& address, const Result& result) {
  char message[96];
  snprintf(message, sizeof(message), "WM1 RANGE %u %lu %lu %lu %s", NODE_ID,
           static_cast<unsigned long>(result.sequence),
           static_cast<unsigned long>(result.actual_bearing),
           static_cast<unsigned long>(result.distance_mm), result.status);
  send_text(address, message);
  Serial.println(message);
}

void finish(const IPAddress& address, const wm::Command& command,
            uint32_t distance_mm, const char* status) {
  Result& result = results[next_result];
  result.valid = true;
  result.sequence = command.sequence;
  result.requested_bearing = command.bearing_mdeg;
  result.actual_bearing = current_bearing_mdeg;
  result.distance_mm = distance_mm;
  result.status = status;
  next_result = (next_result + 1) % kCacheSize;
  send_result(address, result);
}

void write_servo(int32_t position_mdeg) {
  const uint32_t pulse_us = SERVO_PULSE_MIN_US +
      (static_cast<uint64_t>(position_mdeg) *
       (SERVO_PULSE_MAX_US - SERVO_PULSE_MIN_US) + 90000) / 180000;
  const uint32_t duty = (static_cast<uint64_t>(pulse_us) *
      ((1UL << kServoBits) - 1) + kServoPeriodUs / 2) / kServoPeriodUs;
  ledcWrite(kServoChannel, duty);
}

void handle_command(const IPAddress& address, const wm::Command& command) {
  const uint32_t now = millis();
  if (!pending.active && have_owner && now - last_command_at >= kSessionIdleMs) {
    have_owner = false;
    for (auto& result : results) result.valid = false;
  }
  // One host coordinates both pingers. A second host cannot seize an active scan.
  if (have_owner && address != owner_ip) return;

  for (const auto& result : results) {
    if (!result.valid || result.sequence != command.sequence) continue;
    if (result.requested_bearing == command.bearing_mdeg) send_result(address, result);
    return;  // A repeated sequence never moves the servo or emits another ping.
  }
  if (pending.active) return;  // Includes retries while the servo is settling.
  if (have_owner && !wm::newer(command.sequence, latest_sequence)) return;

  have_owner = true;
  owner_ip = address;
  latest_sequence = command.sequence;
  last_command_at = now;

  int32_t target_servo_mdeg = 0;
  if (!servo_ready || !wm::servo_position(command.bearing_mdeg, SERVO_REVERSED,
          SERVO_CENTER_TRIM_MDEG, SERVO_MIN_MDEG, SERVO_MAX_MDEG, target_servo_mdeg)) {
    finish(address, command, 0, "INVALID");
    return;
  }

  const uint32_t movement = static_cast<uint32_t>(abs(target_servo_mdeg - current_servo_mdeg));
  uint32_t settle_ms = SERVO_SETTLE_MIN_MS +
      (static_cast<uint64_t>(movement) * SERVO_SETTLE_MS_PER_DEG + 999) / 1000;
  settle_ms = min(settle_ms, static_cast<uint32_t>(SERVO_SETTLE_MAX_MS));
  // Preserve the longer startup settle when the initial physical position is unknown.
  const uint32_t remaining_ms = servo_ready_at - now;
  if (remaining_ms <= SERVO_SETTLE_MAX_MS && remaining_ms > settle_ms) settle_ms = remaining_ms;
  servo_ready_at = now + settle_ms;
  write_servo(target_servo_mdeg);
  current_servo_mdeg = target_servo_mdeg;
  // This is the calibrated requested bearing, NOT an encoder measurement.
  current_bearing_mdeg = command.bearing_mdeg;
  pending.active = true;
  pending.command = command;
  pending.address = address;
}

void receive_commands() {
  for (unsigned i = 0; i < 4; ++i) {
    const int size = udp.parsePacket();
    if (size <= 0) return;
    const IPAddress address = udp.remoteIP();
    const uint16_t port = udp.remotePort();
    char buffer[96];
    if (size >= static_cast<int>(sizeof(buffer)) || port != kHostPort) {
      udp.flush();
      continue;
    }
    const int received = udp.read(buffer, sizeof(buffer));
    wm::Command command{};
    if (received == size && wm::parse(buffer, static_cast<size_t>(received), command))
      handle_command(address, command);
  }
}

void measure_if_ready() {
  if (!pending.active) return;
  const uint32_t now = millis();
  if (!reached(now, servo_ready_at) || now - last_ping_at < ULTRASONIC_MIN_GAP_MS) return;
  const Pending request = pending;
  pending.active = false;
  last_ping_at = now;

  if (digitalRead(ULTRASONIC_ECHO_PIN) == HIGH) {
    finish(request.address, request.command, 0, "INVALID");
    return;
  }
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  // The only blocking acquisition is bounded to 25 ms. Servo settling is asynchronous.
  const uint32_t duration_us = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  if (duration_us == 0) {
    finish(request.address, request.command, 0, "TIMEOUT");
    return;
  }
  // Nominal room-temperature speed of sound: 0.343 mm/us, round trip / 2.
  const uint32_t distance_mm = (duration_us * 343UL + 1000UL) / 2000UL;
  if (distance_mm < 20 || distance_mm > 4000)
    finish(request.address, request.command, 0, "INVALID");
  else
    finish(request.address, request.command, distance_mm, "OK");
}

void network_tick() {
  const uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (udp_ready) {
      udp.stop();
      udp_ready = false;
      pending.active = false;  // Never execute an old measurement after reconnect.
      Serial.println("Wi-Fi disconnected; pending measurement cancelled");
    }
    if (WIFI_SSID[0] != '\0' && reached(now, reconnect_at)) {
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      reconnect_at = now + kReconnectIntervalMs;
      Serial.println("Connecting to configured Wi-Fi");
    }
    return;
  }
  if (!udp_ready) {
    udp_ready = udp.begin(kNodePort) == 1;
    if (!udp_ready) return;
    Serial.printf("Node %u ready at %s:%u\n", NODE_ID, WiFi.localIP().toString().c_str(), kNodePort);
    last_hello_at = now - kHelloIntervalMs;
  }
  if (now - last_hello_at >= kHelloIntervalMs) {
    last_hello_at = now;
    const IPAddress local = WiFi.localIP();
    const IPAddress mask = WiFi.subnetMask();
    IPAddress broadcast;
    for (unsigned i = 0; i < 4; ++i)
      broadcast[i] = static_cast<uint8_t>(local[i] | static_cast<uint8_t>(~mask[i]));
    char message[24];
    snprintf(message, sizeof(message), "WM1 HELLO %u", NODE_ID);
    send_text(broadcast, message);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  servo_ready = wm::servo_position(90000, SERVO_REVERSED, SERVO_CENTER_TRIM_MDEG,
                                  SERVO_MIN_MDEG, SERVO_MAX_MDEG, current_servo_mdeg);
  if (servo_ready) {
    servo_ready = ledcSetup(kServoChannel, 50, kServoBits) != 0;
    if (servo_ready) {
      ledcAttachPin(SERVO_PIN, kServoChannel);
      write_servo(current_servo_mdeg);
      servo_ready_at = millis() + SERVO_SETTLE_MAX_MS;
    }
  }
  if (!servo_ready) Serial.println("Servo configuration failed; commands will return INVALID");
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  Serial.printf("Whack-a-Mole sensor node %u, Arduino %u.%u.%u\n", NODE_ID,
                ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH);
  if (WIFI_SSID[0] == '\0')
    Serial.println("No Wi-Fi credentials: copy include/config.example.h to include/config.local.h");
}

void loop() {
  network_tick();
  if (udp_ready) {
    receive_commands();
    measure_if_ready();
  }
  delay(1);
}
