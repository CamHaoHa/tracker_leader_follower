/*
 * ONE BOARD'S PART IN FOLLOWING A PLAYER
 *
 * This file controls one servo and one ultrasonic sensor. NODE_ID selects the
 * board by position, left to right: 0, 1, 2 with three boxes (0, 1 with two);
 * all run this same program.
 *
 * The movement-tracking calculations live on the LAPTOP:
 *   whack/controller.py coordinates measurements and acquisition/recovery;
 *   whack/tracking.py combines distances with the known sensor positions,
 *   estimates player position and velocity, and predicts a near-future point.
 * The laptop turns that point into an aiming angle for each sensor. For a
 * sensor at (sx, sy) and target at (px, py), the geometric direction is
 * atan2(py - sy, px - sx). The board receives the resulting angle, not (x, y).
 *
 * A normal tracking cycle is:
 *   laptop sends AIM to BOTH boards -> both servos move at the same time;
 *   each board sends READY when its estimated settling time has elapsed;
 *   laptop sends FIRE to ONE board -> that board sends its RANGE result;
 *   laptop leaves an acoustic gap, then requests the other board's range;
 *   laptop updates the position/velocity estimate and chooses the next aim.
 *
 * The sensors report echoes from reflecting surfaces; neither this firmware
 * nor the servo measures an exact target bearing or identifies a person.
 * Background rejection, combining the two observations, and the on-screen dot
 * belong to the laptop. In profile 3 the left board also supplies Wi-Fi, but
 * being the access point does not make it the tracking coordinator.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_arduino_version.h>
#include <atomic>

#include "settings.h"
#include "wm_protocol.h"

#if ESP_ARDUINO_VERSION_MAJOR != 2 && ESP_ARDUINO_VERSION_MAJOR != 3
#error "This firmware supports Arduino-ESP32 core 2.x and 3.x"
#endif
#if WIFI_PROFILE == 2
#if ESP_ARDUINO_VERSION_MAJOR < 3 || (ESP_ARDUINO_VERSION_MAJOR == 3 && ESP_ARDUINO_VERSION_MINOR < 3)
#error "OneNet requires Arduino-ESP32 3.3+ with EAP CA bundle/domain checks. Use WIFI_PROFILE 0 or 1 on this core."
#else
#include <esp_eap_client.h>
#include <esp_wifi.h>
#include <sys/time.h>
#include <time.h>
#endif
#endif

namespace {

// UDP ports identify the receiving programs: 4210 is the laptop coordinator,
// 4211 is this node. A sequence number identifies one aim/measurement cycle so
// delayed packets from an earlier cycle cannot be mistaken for new data.
constexpr uint16_t kHostPort = 4210;
constexpr uint16_t kNodePort = 4211;
constexpr uint32_t kHelloIntervalMs = 2000;
constexpr uint32_t kReconnectIntervalMs = WIFI_PROFILE == 2 ? 45000 : 10000;
constexpr uint32_t kSessionIdleMs = 30000;
constexpr uint8_t kServoChannel = 0;
constexpr uint8_t kServoBits = 16;
constexpr uint32_t kServoPeriodUs = 20000;
#if BUZZER_PIN >= 0 && BUZZER_TONE_HZ > 0
// A LEDC timer has one frequency, and the servo needs its 50 Hz on channel 0.
// Core 2.x ties channels to timers in pairs (0+1, 2+3, ...), so the tone must
// stay off channel 1; channel 2 runs from the next timer. Core 3.x picks a
// free timer for a new frequency, so channel 2 is independent there as well.
constexpr uint8_t kBuzzerChannel = 2;
constexpr uint8_t kBuzzerBits = 10;
#endif
constexpr size_t kCacheSize = 16;

WiFiUDP udp;
// UDP readiness, PWM setup success and a servo's settling deadline are separate:
// a working network does not prove that the motor is configured or has arrived.
bool udp_ready = false;
bool servo_ready = false;
#if WIFI_PROFILE == 3 && NODE_ID == 0
std::atomic<bool> ap_running{false};
bool ap_configured = false;
#endif
uint32_t reconnect_at = 0;
uint32_t last_hello_at = 0;
uint32_t servo_ready_at = 0;
uint32_t last_ping_at = 0;
bool have_ping = false;
// Bearings use millidegrees (mdeg): 90000 means 90 degrees. World bearings are
// shared by BOTH nodes: 0 = right (+x), 90 = forward (+y), 180 = left (-x).
// Servo coordinates may differ after applying mounting reversal and trim.
int32_t current_servo_mdeg = 90000;   // Commanded target in servo coordinates.
int32_t servo_output_mdeg = 90000;    // Position currently written to the PWM.
uint32_t last_slew_at = 0;
// Ramp the pulse width toward the target instead of jumping. A full-speed SG90
// jump on a 70 degree aim rocks the whole enclosure. 150 deg/s is gentle; a
// single move only ramps faster when it would not fit the settle cap.
constexpr uint32_t kServoSlewMdegPerMs = 150;
uint32_t slew_rate_mdeg_per_ms = kServoSlewMdegPerMs;
uint32_t current_bearing_mdeg = 90000;
#if BUZZER_PIN >= 0
// The buzzer is separate from tracking: no owner, sequence, lease or reply.
wm::BuzzTimer buzzer;
bool buzzer_ready = false;
bool buzzer_on = false;
#endif

// Cache completed FIRE results verbatim; a UDP retry must not emit another ping.
// UDP may lose, delay, reorder or duplicate a datagram. Remembering the original
// response makes a repeated request repeat the answer, not the physical action.
// A FireLease is a short-lived, one-use permission to trigger ultrasound after
// an AIM has settled; its rules are defined in wm_protocol.h.
struct Transaction {
  bool valid = false;
  wm::Command command{};
  wm::FireLease lease{};
  bool aim_accepted = false;
  bool settled = false;
  bool range_ready = false;
  uint32_t actual_bearing = 0;  // Commanded world angle; there is no angle encoder.
  uint32_t distance_mm = 0;
  uint32_t sample_ms = 0;  // This board's millis() when the trigger starts.
  uint32_t age_us = 0;     // Acquisition elapsed time, measured with micros().
  const char* status = "INVALID";
};

Transaction transactions[kCacheSize];
size_t next_transaction = 0;
int pending_index = -1;
bool have_owner = false;
IPAddress owner_ip;
uint32_t latest_sequence = 0;
uint32_t last_command_at = 0;

// millis() wraps after about 49.7 days. Signed subtraction compares these short
// deadlines correctly across that wrap, unlike a simple `now >= deadline`.
bool reached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool network_available() {
#if WIFI_PROFILE == 3 && NODE_ID == 0
  // An AP has no upstream STA connection; WL_CONNECTED never becomes true.
  return ap_configured && ap_running.load(std::memory_order_relaxed) &&
         WiFi.getMode() == WIFI_AP;
#else
  return WiFi.status() == WL_CONNECTED;
#endif
}

IPAddress network_address() {
  // Profile 3 left has an AP address; the other modes use a station address.
  // Sending broadcasts with the wrong interface's IP/mask would hide the node.
#if WIFI_PROFILE == 3 && NODE_ID == 0
  return WiFi.softAPIP();
#else
  return WiFi.localIP();
#endif
}

IPAddress network_mask() {
#if WIFI_PROFILE == 3 && NODE_ID == 0
  return WiFi.softAPSubnetMask();
#else
  return WiFi.subnetMask();
#endif
}

void reset_session() {
  // Drop permissions, queued settling work, and cached sequences together. A
  // connection restored later must not resurrect a FIRE from an old session.
  // This does not park or disable the servo: PWM keeps holding its last target.
  pending_index = -1;
  have_owner = false;
  latest_sequence = 0;
  next_transaction = 0;
  for (auto& transaction : transactions) transaction = Transaction{};
}

void send_text(const IPAddress& address, const char* text, uint16_t port = kHostPort) {
  if (!udp_ready || !network_available()) return;
  if (!udp.beginPacket(address, port)) return;
  udp.write(reinterpret_cast<const uint8_t*>(text), strlen(text));
  udp.endPacket();
}

void send_hello(const IPAddress& address, uint16_t port = kHostPort) {
  // HELLO announces identity and protocol version, not a position measurement.
  // It can be broadcast periodically or returned to a unicast DISCOVER request.
  char message[24];
  snprintf(message, sizeof(message), "WM2 HELLO %u", NODE_ID);
  send_text(address, message, port);
}

void send_ready(const IPAddress& address, const Transaction& transaction) {
  // Report time LEFT on the existing lease. Sending READY again must not reset
  // its deadline; otherwise delayed retries could keep an old FIRE valid forever.
  const uint32_t lease_ms = transaction.aim_accepted ? transaction.lease.remaining(millis()) : 0;
  char message[96];
  snprintf(message, sizeof(message), "WM2 READY %u %lu %lu %lu %s", NODE_ID,
           static_cast<unsigned long>(transaction.command.sequence),
           static_cast<unsigned long>(transaction.actual_bearing),
           static_cast<unsigned long>(lease_ms), lease_ms ? "OK" : "INVALID");
  send_text(address, message);
}

void send_result(const IPAddress& address, const Transaction& transaction) {
  // WM1 is retained for older single-node probes. WM2 adds timing information.
  // sample_ms is local to THIS board: the two ESP32 clocks are not synchronized.
  // The laptop uses its request/receipt times and age_us to estimate when each
  // range was taken. It must not subtract left sample_ms from right sample_ms.
  // Replayed results retain the original timestamps, rather than looking fresh.
  char message[128];
  if (transaction.command.kind == wm::CommandKind::Measure) {
    snprintf(message, sizeof(message), "WM1 RANGE %u %lu %lu %lu %s", NODE_ID,
             static_cast<unsigned long>(transaction.command.sequence),
             static_cast<unsigned long>(transaction.actual_bearing),
             static_cast<unsigned long>(transaction.distance_mm), transaction.status);
  } else {
    snprintf(message, sizeof(message), "WM2 RANGE %u %lu %lu %lu %s %lu %lu", NODE_ID,
             static_cast<unsigned long>(transaction.command.sequence),
             static_cast<unsigned long>(transaction.actual_bearing),
             static_cast<unsigned long>(transaction.distance_mm), transaction.status,
             static_cast<unsigned long>(transaction.sample_ms),
             static_cast<unsigned long>(transaction.age_us));
  }
  send_text(address, message);
}

void finish(Transaction& transaction, uint32_t distance_mm, const char* status,
            uint32_t sample_ms = 0, uint32_t age_us = 0) {
  // Mark every outcome complete, including TIMEOUT/INVALID. A failure is not an
  // instruction to keep firing: another physical measurement needs a new cycle.
  transaction.range_ready = true;
  transaction.distance_mm = distance_mm;
  transaction.status = status;
  transaction.sample_ms = sample_ms;
  transaction.age_us = age_us;
  transaction.lease.revoke();
  send_result(owner_ip, transaction);
}

void write_servo(int32_t position_mdeg) {
  // This receives an already validated INTERNAL servo coordinate. Conversion:
  //   world bearing -> optional reversal -> centre trim -> travel-limit check
  //   -> pulse width in microseconds -> LEDC duty count.
  // The first three steps happen in wm::servo_position(), before this call.
  //
  // Pulse mapping is linear:
  //   pulse_us = min_us + (position_degrees / 180) * (max_us - min_us).
  // Adding 90000 before dividing by 180000 rounds to the nearest microsecond.
  // The 64-bit intermediate avoids overflow during multiplication.
  //
  // Current provisional SG90 mapping on BOTH boards, in their private configs:
  //   endpoints 500..2500 us give 1500 us at 90 degrees;
  //   temporary internal limits 30..150 degrees permit about 833..2167 us.
  // These endpoint numbers define the SCALE; the travel limits determine which
  // part may actually be commanded. The mapping is provisional, not a measured
  // guarantee of full 180-degree travel. Each board keeps its own calibration.
  const uint32_t pulse_us = SERVO_PULSE_MIN_US +
      (static_cast<uint64_t>(position_mdeg) *
       (SERVO_PULSE_MAX_US - SERVO_PULSE_MIN_US) + 90000) / 180000;
  // LEDC is the ESP32's hardware PWM generator. At 50 Hz, each period is
  // 20000 us; duty expresses pulse_us / 20000 on a 16-bit scale (0..65535).
  // Hardware continues producing holding pulses while loop() handles networking.
  const uint32_t duty = (static_cast<uint64_t>(pulse_us) *
      ((1UL << kServoBits) - 1) + kServoPeriodUs / 2) / kServoPeriodUs;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWriteChannel(kServoChannel, duty);
#else
  ledcWrite(kServoChannel, duty);
#endif
}

#if BUZZER_PIN >= 0
void write_buzzer(bool on) {
  if (!buzzer_ready || on == buzzer_on) return;
  buzzer_on = on;
#if BUZZER_TONE_HZ > 0
  // Passive buzzer: a 50 % square wave at BUZZER_TONE_HZ, duty 0 when silent.
  const uint32_t duty = on ? (1UL << kBuzzerBits) / 2 : 0;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWriteChannel(kBuzzerChannel, duty);
#else
  ledcWrite(kBuzzerChannel, duty);
#endif
#else
  digitalWrite(BUZZER_PIN, on ? HIGH : LOW);  // Active buzzer: steady level.
#endif
}
#endif

void handle_buzz(uint32_t duration_ms) {
  // Sound until now + duration; each BUZZ replaces the deadline and 0 silences
  // at once. A box without a buzzer accepts the command and does nothing.
#if BUZZER_PIN >= 0
  write_buzzer(buzzer.command(millis(), duration_ms));
#else
  (void)duration_ms;
#endif
}

void buzzer_tick() {
  // Failsafe: the board ends the sound itself. The laptop has to keep asking,
  // so one that crashed or left the network cannot leave the buzzer on.
#if BUZZER_PIN >= 0
  if (buzzer.expired(millis())) write_buzzer(false);
#endif
}

void acquire(Transaction& transaction) {
  // If ECHO is already high, we cannot associate the next pulse with our own
  // trigger reliably. Report INVALID without firing; check wiring/old echoes.
  if (digitalRead(ULTRASONIC_ECHO_PIN) == HIGH) {
    finish(transaction, 0, "INVALID");
    return;
  }
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  // Record trigger time BEFORE waiting for the echo. A later receipt time on the
  // laptop would make a moving target appear newer than the actual observation.
  const uint32_t started_us = micros();
  const uint32_t sample_ms = millis();
  last_ping_at = sample_ms;
  have_ping = true;
  // A 10 us trigger asks the HC-SR04 to transmit its ultrasonic burst. ECHO's
  // high duration represents the sound's outward-and-return travel time.
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  // Only acquisition blocks, for at most 25 ms; settling never blocks UDP.
  const uint32_t duration_us = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  // age_us includes trigger/acquisition waiting up to result preparation. It is
  // distinct from duration_us, which is just ECHO's high pulse width. Neither
  // value includes the subsequent Wi-Fi delivery time to the laptop.
  const uint32_t age_us = micros() - started_us;
  if (duration_us == 0) {
    finish(transaction, 0, "TIMEOUT", sample_ms, age_us);
    return;
  }
  // At nominal room temperature, sound travels about 0.343 mm per microsecond.
  // Distance is time * speed / 2 because the echo makes a round trip:
  //   distance_mm = duration_us * 343 / 2000.
  // Adding 1000 rounds the integer result. Temperature and which body surface
  // reflected the sound affect real accuracy; this is not body-centre ranging.
  const uint32_t distance_mm = (duration_us * 343UL + 1000UL) / 2000UL;
  if (distance_mm < 20 || distance_mm > 4000)
    finish(transaction, 0, "INVALID", sample_ms, age_us);
  else
    finish(transaction, distance_mm, "OK", sample_ms, age_us);
}

void reject(const IPAddress& address, const wm::Command& command) {
  Transaction rejected{};
  rejected.command = command;
  rejected.actual_bearing = command.kind == wm::CommandKind::Aim ?
      command.bearing_mdeg : current_bearing_mdeg;
  if (command.kind == wm::CommandKind::Aim) send_ready(address, rejected);
  else send_result(address, rejected);
}

void slew_servo() {
  // Called every loop pass: move the PWM output a bounded step toward the
  // commanded target so a large aim becomes a smooth ramp, never a jump.
  if (!servo_ready || servo_output_mdeg == current_servo_mdeg) return;
  const uint32_t now = millis();
  const uint32_t elapsed = now - last_slew_at;
  if (elapsed == 0) return;
  last_slew_at = now;
  const int32_t max_step = static_cast<int32_t>(min<uint32_t>(elapsed, 50) * slew_rate_mdeg_per_ms);
  const int32_t delta = current_servo_mdeg - servo_output_mdeg;
  if (delta > max_step) servo_output_mdeg += max_step;
  else if (delta < -max_step) servo_output_mdeg -= max_step;
  else servo_output_mdeg = current_servo_mdeg;
  write_servo(servo_output_mdeg);
}

void handle_command(const IPAddress& address, const wm::Command& command) {
  const uint32_t now = millis();
  if (have_owner && now - last_command_at >= kSessionIdleMs) reset_session();
  // One coordinator owns the acoustic schedule. Other hosts cannot trigger it.
  // Local spacing protects this sensor from its own preceding pulse; only the
  // laptop can also keep LEFT and RIGHT transmissions apart. Concurrent bursts
  // could make one sensor hear the other sensor's sound instead of its own echo.
  if (have_owner && address != owner_ip) return;

  // Look for an existing sequence before accepting new work. A duplicate FIRE
  // returns its saved result; a duplicate AIM never repeats a servo movement.
  for (size_t i = 0; i < kCacheSize; ++i) {
    Transaction& transaction = transactions[i];
    if (!transaction.valid || transaction.command.sequence != command.sequence) continue;
    last_command_at = now;
    if (command.kind == wm::CommandKind::Fire &&
        transaction.command.kind == wm::CommandKind::Aim) {
      // consume() permits exactly one FIRE after READY, before lease expiry,
      // and at least 65 ms after this node's previous trigger. An early, expired,
      // or too-soon FIRE is consumed and rejected, not delayed until it is legal.
      // Delaying it could make the ping collide with the other node's turn.
      if (transaction.range_ready) {
        send_result(address, transaction);
      } else if (!transaction.lease.consume(now, have_ping, last_ping_at, ULTRASONIC_MIN_GAP_MS)) {
        if (pending_index == static_cast<int>(i)) pending_index = -1;
        finish(transaction, 0, "INVALID");
      } else {
        acquire(transaction);  // Never queue a FIRE to execute at a later time.
      }
    } else if (command.kind == transaction.command.kind &&
               command.bearing_mdeg == transaction.command.bearing_mdeg) {
      if (command.kind == wm::CommandKind::Aim) {
        // Retries while settling wait for the initial READY, without moving.
        if (transaction.settled || !transaction.aim_accepted || transaction.lease.consumed)
          send_ready(address, transaction);
      } else if (transaction.range_ready) {
        send_result(address, transaction);
      }
    } else {
      reject(address, command);
    }
    return;
  }

  // Once a result leaves the small cache, its older sequence is still rejected.
  // Sequence comparison also handles the unsigned 32-bit counter wrapping.
  if (have_owner && !wm::newer(command.sequence, latest_sequence)) {
    reject(address, command);
    return;
  }
  // Legacy MEASURE is serialized; WM2 AIM may supersede an older unfired aim.
  if (pending_index >= 0 && command.kind == wm::CommandKind::Measure) return;
  have_owner = true;
  owner_ip = address;
  latest_sequence = command.sequence;
  last_command_at = now;
  // A newer aim replaces any unfinished aim and revokes older firing grants.
  // This is useful when the player's predicted direction changes mid-settle.
  for (auto& transaction : transactions) transaction.lease.revoke();
  pending_index = -1;

  const int index = static_cast<int>(next_transaction);
  next_transaction = (next_transaction + 1) % kCacheSize;
  Transaction& transaction = transactions[index];
  transaction = Transaction{};
  transaction.valid = true;
  transaction.command = command;
  transaction.actual_bearing = command.bearing_mdeg;
  // A FIRE with no matching remembered AIM cannot acquire a new permission.
  if (command.kind == wm::CommandKind::Fire) {
    transaction.actual_bearing = current_bearing_mdeg;
    finish(transaction, 0, "INVALID");
    return;
  }

  // World angle -> physical command. Reversed mounting uses 180000 - bearing;
  // trim is then added, and the final coordinate must be inside the configured
  // limits. Rejecting an unreachable angle is essential: silently clamping it
  // would tell the laptop the beam points somewhere it does not actually point.
  int32_t target_servo_mdeg = 0;
  if (!servo_ready || !wm::servo_position(command.bearing_mdeg, SERVO_REVERSED,
          SERVO_CENTER_TRIM_MDEG, SERVO_MIN_MDEG, SERVO_MAX_MDEG, target_servo_mdeg)) {
    if (command.kind == wm::CommandKind::Aim) send_ready(address, transaction);
    else finish(transaction, 0, "INVALID");
    return;
  }

  // Estimate the mechanical wait from angular movement: by default 60 ms plus
  // 3 ms per degree, capped at 700 ms. This needs checking with the loaded mount;
  // READY means this timer elapsed, not that an encoder confirmed the position.
  // Store a deadline instead of delay(settle_ms), so Wi-Fi remains responsive
  // and the other ESP32 can be moving at the same time.
  // Movement is measured from where the ramp currently is, so an AIM that
  // supersedes an unfinished move is timed from the real position estimate.
  const uint32_t movement = static_cast<uint32_t>(abs(target_servo_mdeg - servo_output_mdeg));
  const uint32_t remaining_ms = reached(now, servo_ready_at) ? 0 : servo_ready_at - now;
  uint32_t settle_ms = 0;
  if (movement != 0) {
    // Ramp at the gentle rate unless that would overrun the settle cap; then
    // ramp just fast enough to arrive with the minimum settle time to spare.
    const uint32_t budget_ms = SERVO_SETTLE_MAX_MS - SERVO_SETTLE_MIN_MS;
    slew_rate_mdeg_per_ms = max(kServoSlewMdegPerMs, (movement + budget_ms - 1) / budget_ms);
    const uint32_t ramp_ms = (movement + slew_rate_mdeg_per_ms - 1) / slew_rate_mdeg_per_ms;
    const uint32_t lag_ms = (static_cast<uint64_t>(movement) * SERVO_SETTLE_MS_PER_DEG + 999) / 1000;
    settle_ms = SERVO_SETTLE_MIN_MS + max(ramp_ms, lag_ms);
    settle_ms = min(settle_ms, static_cast<uint32_t>(SERVO_SETTLE_MAX_MS));
    last_slew_at = now;  // slew_servo() ramps the output from here on.
  } else {
    settle_ms = remaining_ms;  // No extra wait for an unchanged, settled servo.
  }
  servo_ready_at = now + settle_ms;
  current_servo_mdeg = target_servo_mdeg;
  current_bearing_mdeg = command.bearing_mdeg;  // Commanded bearing, not an encoder reading.
  transaction.aim_accepted = true;
  pending_index = index;
}

void receive_commands() {
  // Process a bounded number of datagrams per loop so traffic cannot indefinitely
  // postpone the settling check. Parsing is length-delimited and rejects bad
  // numbers/extra data before a command reaches either actuator or sensor.
  for (unsigned i = 0; i < 4; ++i) {
    const int size = udp.parsePacket();
    if (size <= 0) return;
    const IPAddress address = udp.remoteIP();
    const uint16_t port = udp.remotePort();
    char buffer[96];
    if (size >= static_cast<int>(sizeof(buffer))) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
      udp.clear();
#else
      udp.flush();
#endif
      continue;
    }
    const int received = udp.read(buffer, sizeof(buffer));
    wm::Command command{};
    if (received == size && wm::parse(buffer, static_cast<size_t>(received), command)) {
      // Discovery is read-only and never touches owner/sequence/servo/lease state.
      // Reply to the actual source port so diagnostics can use an ephemeral port.
      if (command.kind == wm::CommandKind::Discover) send_hello(address, port);
      else if (port != kHostPort) continue;
      // Like discovery, BUZZ stays outside the AIM/FIRE transactions: it takes
      // no ownership, uses no sequence, revokes no lease and sends no reply.
      else if (command.kind == wm::CommandKind::Buzz) handle_buzz(command.duration_ms);
      else handle_command(address, command);
    }
  }
}

void settle_if_ready() {
  // Called repeatedly while the motor moves. WM2 never fires ultrasound here:
  // it grants READY, then waits for the laptop to choose this node's acoustic turn.
  if (pending_index < 0) return;
  const uint32_t now = millis();
  if (!reached(now, servo_ready_at)) return;
  Transaction& transaction = transactions[pending_index];
  if (transaction.command.kind == wm::CommandKind::Measure &&
      have_ping && now - last_ping_at < ULTRASONIC_MIN_GAP_MS) return;
  pending_index = -1;
  transaction.settled = true;
  if (transaction.command.kind == wm::CommandKind::Aim) {
    // The 1000 ms, one-use lease begins now, at completion of the settling wait.
    // The host uses its remaining time when deciding whether a FIRE is still safe
    // to send; this board enforces expiry even if that packet arrives late.
    transaction.lease.settle(now);
    send_ready(owner_ip, transaction);
  } else {
    // Legacy WM1 MEASURE combines aiming and firing for the single-node probe.
    // The live two-node controller uses the separate WM2 AIM/FIRE sequence.
    acquire(transaction);
  }
}

const char* selected_ssid() {
  // Profile selection does not erase another environment's credentials:
  // 0 = home, 1 = school personal/hotspot, 2 = OneNet enterprise, 3 = TrackerNet.
  // In Arduino sketches tracker_network.h may override the selected profile;
  // per-board mounting settings remain in tracker_config.h.
#if WIFI_PROFILE == 3
  return TRACKER_WIFI_SSID;
#elif WIFI_PROFILE == 2
  return ONENET_SSID;
#elif WIFI_PROFILE == 1
  return SCHOOL_WIFI_SSID;
#else
  return WIFI_SSID;
#endif
}

#if WIFI_PROFILE == 2 && ESP_ARDUINO_VERSION_MAJOR == 3 && ESP_ARDUINO_VERSION_MINOR >= 3
bool set_certificate_clock() {
  // A build-time clock is a bootstrap approximation, not a persistent RTC.
  // Recompile immediately before campus use; NTP updates it after connection.
  if (time(nullptr) >= 1735689600) return true;
  const char* months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char month[4] = {};
  tm built = {};
  int year = 0;
  sscanf(__DATE__, "%3s %d %d", month, &built.tm_mday, &year);
  sscanf(__TIME__, "%d:%d:%d", &built.tm_hour, &built.tm_min, &built.tm_sec);
  const char* found = strstr(months, month);
  if (!found) return false;
  built.tm_mon = (found - months) / 3;
  built.tm_year = year - 1900;
  built.tm_isdst = -1;
  setenv("TZ", ONENET_BUILD_TIMEZONE, 1);
  tzset();
  timeval clock = {mktime(&built), 0};
  return clock.tv_sec >= 1735689600 && settimeofday(&clock, nullptr) == 0;
}

bool eap_setting(esp_err_t status) {
  if (status == ESP_OK) return true;
  esp_wifi_sta_enterprise_disable();
  Serial.printf("OneNet setup failed: %s\n", esp_err_to_name(status));
  return false;
}
#endif

void begin_network() {
  // Radio setup is separate from the tracking protocol. Either network role
  // still receives laptop commands and returns only this board's own readings.
#if WIFI_PROFILE == 3
  const size_t ssid_length = strlen(TRACKER_WIFI_SSID);
  const size_t password_length = strlen(TRACKER_WIFI_PASSWORD);
  if (ssid_length == 0 || ssid_length > 32 || password_length < 8 || password_length > 63) {
    Serial.println("Tracker network needs an SSID of 1..32 bytes and a shared password of 8..63 bytes");
    return;  // Never create an open AP or fall back to another network.
  }
#if NODE_ID == 0
  ap_configured = false;
  if (WiFi.getMode() != WIFI_MODE_NULL) WiFi.softAPdisconnect(true);
  const IPAddress ap_ip(192, 168, 4, 1);
  const IPAddress subnet(255, 255, 255, 0);
  // AP-only mode: the left sensor hosts the network; the laptop still schedules
  // both trackers' AIM/FIRE commands. Clients use the ordinary DHCP pool.
  // The right board and laptop receive addresses according to DHCP allocation;
  // the right board is not guaranteed to be 192.168.4.2. Internet is unnecessary.
  if (!WiFi.mode(WIFI_AP) ||
      !WiFi.softAP(TRACKER_WIFI_SSID, TRACKER_WIFI_PASSWORD, TRACKER_WIFI_CHANNEL, 0, 4) ||
      !WiFi.softAPConfig(ap_ip, ap_ip, subnet)) {
    WiFi.softAPdisconnect(true);
    Serial.println("Tracker access point setup failed; retrying shortly");
    return;
  }
  ap_configured = true;
  WiFi.setSleep(false);
  Serial.printf("Tracker network: %s, left node 192.168.4.1, channel %u\n",
                TRACKER_WIFI_SSID, TRACKER_WIFI_CHANNEL);
  Serial.println("Connect the laptop to this network; right node receives its address by DHCP");
#else
  // Explicit zero IP selects DHCP, rather than retaining any previous static IP.
  const IPAddress automatic(0, 0, 0, 0);
  if (!WiFi.config(automatic, automatic, automatic)) {
    Serial.println("Tracker network DHCP setup failed; retrying shortly");
    return;
  }
  WiFi.begin(TRACKER_WIFI_SSID, TRACKER_WIFI_PASSWORD);
#endif
#elif WIFI_PROFILE == 2 && ESP_ARDUINO_VERSION_MAJOR == 3 && ESP_ARDUINO_VERSION_MINOR >= 3
  if (!ONENET_USERNAME[0] || !ONENET_PASSWORD[0] || !ONENET_SERVER_DOMAIN[0]) {
    Serial.println("OneNet needs ONENET_USERNAME, ONENET_PASSWORD and ONENET_SERVER_DOMAIN");
    return;
  }
  if (!set_certificate_clock()) {
    Serial.println("OneNet certificate clock unavailable; recompile before use");
    return;
  }
  WiFi.disconnect();
  if (!WiFi.STA.connect(ONENET_SSID, nullptr, 0, nullptr, false)) return;
  if (!eap_setting(esp_eap_client_use_default_cert_bundle(true)) ||
      !eap_setting(esp_eap_client_set_domain_name(ONENET_SERVER_DOMAIN)) ||
      !eap_setting(esp_eap_client_set_disable_time_check(false)) ||
      !eap_setting(esp_eap_client_set_eap_methods(ESP_EAP_TYPE_PEAP)) ||
      !eap_setting(esp_eap_client_set_identity(reinterpret_cast<const unsigned char*>(ONENET_USERNAME), strlen(ONENET_USERNAME))) ||
      !eap_setting(esp_eap_client_set_username(reinterpret_cast<const unsigned char*>(ONENET_USERNAME), strlen(ONENET_USERNAME))) ||
      !eap_setting(esp_eap_client_set_password(reinterpret_cast<const unsigned char*>(ONENET_PASSWORD), strlen(ONENET_PASSWORD))) ||
      !eap_setting(esp_wifi_sta_enterprise_enable())) return;
  eap_setting(esp_wifi_connect());
#elif WIFI_PROFILE == 1
  WiFi.begin(SCHOOL_WIFI_SSID, SCHOOL_WIFI_PASSWORD);
#else
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#endif
}

void network_tick() {
  // Keep reconnecting without parking the main loop in a long connection wait.
  // A dropped STA link or stopped AP invalidates pending command permissions.
  const uint32_t now = millis();
  if (!network_available()) {
    // Revoke every lease/cache and release ownership across network loss.
    if (have_owner) reset_session();
    if (udp_ready) {
      udp.stop();
      udp_ready = false;
      Serial.println("Wi-Fi disconnected; pending commands cancelled");
    }
    if (selected_ssid()[0] != '\0' && reached(now, reconnect_at)) {
      reconnect_at = now + kReconnectIntervalMs;
      begin_network();
      Serial.printf("Starting Wi-Fi profile %u\n", WIFI_PROFILE);
    }
    return;
  }
  if (have_owner && now - last_command_at >= kSessionIdleMs) reset_session();
  if (!udp_ready) {
    udp_ready = udp.begin(kNodePort) == 1;
    if (!udp_ready) return;
    Serial.printf("Node %u ready at %s:%u (WM2 AIM/FIRE)\n", NODE_ID, network_address().toString().c_str(), kNodePort);
#if WIFI_PROFILE == 2 && ESP_ARDUINO_VERSION_MAJOR == 3 && ESP_ARDUINO_VERSION_MINOR >= 3
    configTime(0, 0, "pool.ntp.org", "time.google.com");
#endif
    last_hello_at = now - kHelloIntervalMs;
  }
  if (now - last_hello_at >= kHelloIntervalMs) {
    last_hello_at = now;
    const IPAddress local = network_address();
    const IPAddress mask = network_mask();
    // Set all host bits (the bits outside the subnet mask) to 1 to form this
    // network's broadcast address. Both nodes periodically announce themselves
    // so the laptop can discover DHCP addresses without hard-coding them.
    IPAddress broadcast;
    for (unsigned i = 0; i < 4; ++i)
      broadcast[i] = static_cast<uint8_t>(local[i] | static_cast<uint8_t>(~mask[i]));
    send_hello(broadcast);
  }
}

}  // namespace

void setup() {
  // Arduino calls setup() once after power-on/upload/reset. Requesting 90 degrees
  // immediately centres the PWM command, so the servo can move before networking
  // is ready. Both sensor mounts should face forward at this world bearing.
  Serial.begin(115200);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  servo_ready = wm::servo_position(90000, SERVO_REVERSED, SERVO_CENTER_TRIM_MDEG,
                                  SERVO_MIN_MDEG, SERVO_MAX_MDEG, current_servo_mdeg);
  if (servo_ready) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    servo_ready = ledcAttachChannel(SERVO_PIN, 50, kServoBits, kServoChannel);
#else
    servo_ready = ledcSetup(kServoChannel, 50, kServoBits) != 0;
    if (servo_ready) ledcAttachPin(SERVO_PIN, kServoChannel);
#endif
    if (servo_ready) {
      servo_output_mdeg = current_servo_mdeg;  // Boot position unknown: one direct move.
      write_servo(current_servo_mdeg);
      last_slew_at = millis();
      // The initial physical position is unknown, so preserve the full startup
      // settling allowance even if the first requested angle is also 90 degrees.
      servo_ready_at = millis() + SERVO_SETTLE_MAX_MS;
    }
  }
  if (!servo_ready) Serial.println("Servo configuration failed; commands will return INVALID");
#if BUZZER_PIN >= 0
#if BUZZER_TONE_HZ > 0
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  buzzer_ready = ledcAttachChannel(BUZZER_PIN, BUZZER_TONE_HZ, kBuzzerBits, kBuzzerChannel);
  if (buzzer_ready) ledcWriteChannel(kBuzzerChannel, 0);
#else
  buzzer_ready = ledcSetup(kBuzzerChannel, BUZZER_TONE_HZ, kBuzzerBits) != 0;
  if (buzzer_ready) {
    ledcAttachPin(BUZZER_PIN, kBuzzerChannel);  // Attaches with duty 0: silent.
    ledcWrite(kBuzzerChannel, 0);
  }
#endif
#else
  digitalWrite(BUZZER_PIN, LOW);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  buzzer_ready = true;
#endif
  if (!buzzer_ready) Serial.println("Buzzer configuration failed; BUZZ commands are ignored");
#endif
  WiFi.persistent(false);
#if WIFI_PROFILE == 3 && NODE_ID == 0
  // Wi-Fi events run on another task. Only the loop edits UDP/session state.
  WiFi.onEvent([](arduino_event_id_t event) {
    if (event == ARDUINO_EVENT_WIFI_AP_START) ap_running.store(true, std::memory_order_relaxed);
    if (event == ARDUINO_EVENT_WIFI_AP_STOP) ap_running.store(false, std::memory_order_relaxed);
  });
  // begin_network validates credentials before enabling the AP radio.
#else
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
#endif
  Serial.printf("Tracker node %u, Arduino %u.%u.%u, Wi-Fi profile %u\n", NODE_ID,
                ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
                WIFI_PROFILE);
  Serial.printf("Pins: servo=%u, TRIG=%u, ECHO=%u (sensor on 3V3, ECHO wired directly)\n",
                static_cast<unsigned>(SERVO_PIN), static_cast<unsigned>(ULTRASONIC_TRIG_PIN),
                static_cast<unsigned>(ULTRASONIC_ECHO_PIN));
#if BUZZER_PIN < 0
  Serial.println("Buzzer: none");
#elif BUZZER_TONE_HZ > 0
  Serial.printf("Buzzer: pin=%u, %u Hz tone\n", static_cast<unsigned>(BUZZER_PIN),
                static_cast<unsigned>(BUZZER_TONE_HZ));
#else
  Serial.printf("Buzzer: pin=%u, steady HIGH (active buzzer)\n",
                static_cast<unsigned>(BUZZER_PIN));
#endif
  if (selected_ssid()[0] == '\0')
    Serial.println("No Wi-Fi credentials: edit tracker_config.h (Arduino IDE) or include/config.local.h (PlatformIO)");
}

void loop() {
  // Arduino calls loop() continuously. This is cooperative scheduling: perform
  // short pieces of work, then return so the next piece can run promptly.
  // Checking settling before and after receive_commands handles both an old
  // deadline that just elapsed and a new unchanged-angle AIM ready immediately.
  // There is no autonomous scan or player prediction on the board. Ultrasound
  // happens only for a permitted FIRE (or the retained WM1 measurement command).
  slew_servo();
  buzzer_tick();
  network_tick();
  if (udp_ready) {
    settle_if_ready();
    receive_commands();
    settle_if_ready();
  }
  delay(1);  // Yield briefly to background tasks; not a servo-settling delay.
}
