#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace wm {

enum class CommandKind { Measure, Aim, Fire, Discover };

struct Command {
  uint32_t sequence;
  uint32_t bearing_mdeg;
  CommandKind kind = CommandKind::Measure;
};

// Length-delimited parsing rejects embedded NULs, signs, floats, overflow,
// extra tokens, and non-ASCII input before any motor or trigger operation.
inline bool decimal(const char* data, size_t length, size_t& pos, uint32_t& out) {
  const size_t start = pos;
  uint32_t value = 0;
  while (pos < length && data[pos] >= '0' && data[pos] <= '9') {
    const uint32_t digit = static_cast<uint32_t>(data[pos] - '0');
    if (value > (UINT32_MAX - digit) / 10) return false;
    value = value * 10 + digit;
    ++pos;
  }
  if (pos == start) return false;
  out = value;
  return true;
}

inline bool parse(const char* data, size_t length, Command& out) {
  Command command{};
  size_t pos = 0;
  if (length >= 12 && memcmp(data, "WM1 MEASURE ", 12) == 0) {
    pos = 12;
  } else if (length >= 8 && memcmp(data, "WM2 AIM ", 8) == 0) {
    pos = 8;
    command.kind = CommandKind::Aim;
  } else if (length >= 9 && memcmp(data, "WM2 FIRE ", 9) == 0) {
    pos = 9;
    command.kind = CommandKind::Fire;
  } else if (length >= 12 && memcmp(data, "WM2 DISCOVER", 12) == 0) {
    pos = 12;
    command.kind = CommandKind::Discover;
  } else {
    return false;
  }
  if (command.kind != CommandKind::Discover &&
      (!decimal(data, length, pos, command.sequence) || command.sequence == 0)) return false;
  if (command.kind == CommandKind::Measure || command.kind == CommandKind::Aim) {
    if (pos >= length || data[pos++] != ' ') return false;
    if (!decimal(data, length, pos, command.bearing_mdeg) || command.bearing_mdeg > 180000)
      return false;
  }
  // A single optional line terminator is accepted for manual UDP testing.
  if (pos < length && data[pos] == '\r') ++pos;
  if (pos < length && data[pos] == '\n') ++pos;
  if (pos != length) return false;
  out = command;
  return true;
}

inline bool newer(uint32_t candidate, uint32_t previous) {
  const uint32_t delta = candidate - previous;
  return delta != 0 && delta < UINT32_C(0x80000000);
}

// A READY grants exactly one immediate FIRE. Retrying READY never changes the
// deadline, and even an early/expired FIRE consumes the sequence without a ping.
// All arithmetic remains valid across millis() wrap (leases are under 2^31 ms).
struct FireLease {
  uint32_t deadline = 0;
  bool ready = false;
  bool consumed = false;

  void settle(uint32_t now, uint32_t duration_ms = 1000) {
    if (!ready && !consumed) {
      deadline = now + duration_ms;
      ready = true;
    }
  }
  uint32_t remaining(uint32_t now) const {
    if (!ready || consumed || static_cast<int32_t>(deadline - now) <= 0) return 0;
    return deadline - now;
  }
  bool consume(uint32_t now, bool have_ping, uint32_t last_ping, uint32_t gap_ms) {
    const bool allowed = remaining(now) != 0 && (!have_ping || now - last_ping >= gap_ms);
    consumed = true;
    return allowed;
  }
  void revoke() { consumed = true; }
};

inline bool servo_position(uint32_t bearing_mdeg, bool reverse, int32_t trim_mdeg,
                           int32_t minimum, int32_t maximum, int32_t& position) {
  if (bearing_mdeg > 180000) return false;
  const int32_t angle = static_cast<int32_t>(bearing_mdeg);
  const int32_t candidate = (reverse ? 180000 - angle : angle) + trim_mdeg;
  if (candidate < minimum || candidate > maximum) return false;
  position = candidate;
  return true;
}

}  // namespace wm
