#include <assert.h>
#include <stdio.h>

#include "wm_protocol.h"

int main() {
  wm::Command command{};
  const char* valid = "WM1 MEASURE 4294967295 180000\r\n";
  assert(wm::parse(valid, strlen(valid), command));
  assert(command.sequence == UINT32_MAX && command.bearing_mdeg == 180000);
  const char* invalid[] = {
      "WM1 MEASURE 0 90000", "WM1 MEASURE -1 90000", "WM1 MEASURE +1 90000",
      "WM1 MEASURE 4294967296 90000", "WM1 MEASURE 1 nan", "WM1 MEASURE 1 inf",
      "WM1 MEASURE 1 180001", "WM1 MEASURE 1 -1", "WM1 MEASURE 1 90.0",
      "WM1 MEASURE 1 90000 extra", "WM1 MEASURE  1 90000", "WM1 MEASURE 1 ",
      "WM2 MEASURE 1 90000", "WM1 MEASURE 1 90000\n\n"};
  for (const auto* text : invalid) assert(!wm::parse(text, strlen(text), command));
  const char embedded[] = "WM1 MEASURE 1 90000\0ignored";
  assert(!wm::parse(embedded, sizeof(embedded) - 1, command));
  for (size_t n = 0; n < strlen("WM1 MEASURE 1 0"); ++n)
    assert(!wm::parse("WM1 MEASURE 1 0", n, command));
  assert(wm::newer(1, UINT32_MAX));
  assert(!wm::newer(10, 10));
  assert(!wm::newer(9, 10));
  assert(!wm::newer(UINT32_MAX, 1));
  int32_t servo = 0;
  assert(wm::servo_position(30000, true, 5000, 0, 180000, servo) && servo == 155000);
  assert(!wm::servo_position(180000, false, 5000, 0, 180000, servo));
  assert(!wm::servo_position(20000, false, 0, 30000, 150000, servo));
  assert(wm::servo_position(90000, false, -10000, 30000, 150000, servo) && servo == 80000);
  puts("Firmware protocol/calibration tests passed");
}
