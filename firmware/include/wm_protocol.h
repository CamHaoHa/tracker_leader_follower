#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace wm {

struct Command {
  uint32_t sequence;
  uint32_t bearing_mdeg;
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
  constexpr char prefix[] = "WM1 MEASURE ";
  constexpr size_t prefix_length = sizeof(prefix) - 1;
  if (length < prefix_length || memcmp(data, prefix, prefix_length) != 0) return false;
  size_t pos = prefix_length;
  Command command{};
  if (!decimal(data, length, pos, command.sequence) || command.sequence == 0) return false;
  if (pos >= length || data[pos++] != ' ') return false;
  if (!decimal(data, length, pos, command.bearing_mdeg) || command.bearing_mdeg > 180000)
    return false;
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
