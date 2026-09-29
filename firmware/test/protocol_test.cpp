#include <assert.h>
#include <stdio.h>

#include "wm_protocol.h"

int main() {
  wm::Command command{};
  const char* valid = "WM1 MEASURE 4294967295 180000\r\n";
  assert(wm::parse(valid, strlen(valid), command));
  assert(command.sequence == UINT32_MAX && command.bearing_mdeg == 180000);
  assert(command.kind == wm::CommandKind::Measure);
  const char* aim = "WM2 AIM 100 45000";
  assert(wm::parse(aim, strlen(aim), command));
  assert(command.kind == wm::CommandKind::Aim && command.sequence == 100 &&
         command.bearing_mdeg == 45000);
  const char* fire = "WM2 FIRE 100\r\n";
  assert(wm::parse(fire, strlen(fire), command));
  assert(command.kind == wm::CommandKind::Fire && command.sequence == 100 &&
         command.bearing_mdeg == 0);
  const char* discoveries[] = {"WM2 DISCOVER", "WM2 DISCOVER\r\n"};
  for (const char* discovery : discoveries) {
    assert(wm::parse(discovery, strlen(discovery), command));
    assert(command.kind == wm::CommandKind::Discover && command.sequence == 0 &&
           command.bearing_mdeg == 0);
  }
  const char* buzz = "WM2 BUZZ 400";
  assert(wm::parse(buzz, strlen(buzz), command));
  assert(command.kind == wm::CommandKind::Buzz && command.duration_ms == 400 &&
         command.sequence == 0 && command.bearing_mdeg == 0);
  const char* buzz_limits[] = {"WM2 BUZZ 0", "WM2 BUZZ 2000\r\n"};
  const uint32_t buzz_values[] = {0, 2000};
  for (size_t i = 0; i < 2; ++i) {
    assert(wm::parse(buzz_limits[i], strlen(buzz_limits[i]), command));
    assert(command.kind == wm::CommandKind::Buzz && command.duration_ms == buzz_values[i]);
  }
  // A later command of another kind does not inherit the duration.
  assert(wm::parse(fire, strlen(fire), command) && command.duration_ms == 0);
  const char* invalid[] = {
      "WM1 MEASURE 0 90000", "WM1 MEASURE -1 90000", "WM1 MEASURE +1 90000",
      "WM1 MEASURE 4294967296 90000", "WM1 MEASURE 1 nan", "WM1 MEASURE 1 inf",
      "WM1 MEASURE 1 180001", "WM1 MEASURE 1 -1", "WM1 MEASURE 1 90.0",
      "WM1 MEASURE 1 90000 extra", "WM1 MEASURE  1 90000", "WM1 MEASURE 1 ",
      "WM2 MEASURE 1 90000", "WM1 MEASURE 1 90000\n\n", "WM2 AIM 0 90000",
      "WM2 AIM 1 180001", "WM2 AIM 1", "WM2 FIRE 0", "WM2 FIRE 1 90000",
      "WM2 FIRE +1", "WM2 FIRE 4294967296", "WM2 FIRE 1\n\n", "WM1 FIRE 1",
      "WM1 DISCOVER", "WM2 DISCOVER 1", "WM2 DISCOVER 1 0", "WM2 DISCOVER ",
      "WM2 DISCOVERx", "WM2 DISCOVER\n\n", "WM2 DISCOVE",
      "WM2 BUZZ", "WM2 BUZZ ", "WM2 BUZZ 2001", "WM2 BUZZ -1", "WM2 BUZZ +1",
      "WM2 BUZZ 1.5", "WM2 BUZZ 400 1", "WM2 BUZZ  400", "WM2 BUZZ 4294967296",
      "WM2 BUZZ 400\n\n", "WM2 BUZZ on", "WM1 BUZZ 400", "WM2 BUZZER 400"};
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

  wm::FireLease lease;
  assert(lease.remaining(100) == 0);
  lease.settle(100);
  assert(lease.remaining(100) == 1000);
  lease.settle(200);  // A duplicated AIM/READY must not renew a grant.
  assert(lease.remaining(200) == 900);
  assert(lease.consume(200, true, 135, 65));
  assert(!lease.consume(201, true, 135, 65));
  assert(lease.remaining(201) == 0);

  lease = wm::FireLease{};
  assert(!lease.consume(100, false, 0, 65));  // FIRE before READY.
  lease.settle(110);
  assert(lease.remaining(110) == 0);  // No delayed ping after rejecting FIRE.

  lease = wm::FireLease{};
  lease.settle(100);
  assert(!lease.consume(200, true, 136, 65));  // Too close to the previous ping.
  assert(!lease.consume(210, true, 136, 65));  // Retry cannot revive it.

  lease = wm::FireLease{};
  lease.settle(100);
  assert(lease.remaining(1099) == 1);
  assert(!lease.consume(1100, false, 0, 65));  // Expiry boundary is exclusive.

  lease = wm::FireLease{};
  lease.settle(UINT32_MAX - 100);
  assert(lease.remaining(0) == 899);  // millis wrap is harmless.
  assert(lease.consume(0, true, UINT32_MAX - 64, 65));

  lease = wm::FireLease{};
  lease.settle(100);
  lease.revoke();  // Superseding AIM, Wi-Fi loss or session expiry.
  assert(!lease.consume(101, false, 0, 65));

  wm::BuzzTimer buzzer;
  assert(!buzzer.expired(0));                 // Silent until told otherwise.
  assert(buzzer.command(100, 400));           // Sound until 500.
  assert(!buzzer.expired(499));
  assert(buzzer.command(300, 400));           // A repeat replaces the deadline: 700.
  assert(!buzzer.expired(699));
  assert(buzzer.expired(700));                // Deadline boundary silences.
  assert(!buzzer.expired(701));               // ...exactly once.
  assert(buzzer.command(1000, 2000));
  assert(!buzzer.command(1100, 0));           // BUZZ 0 silences at once.
  assert(!buzzer.sounding && !buzzer.expired(5000));
  assert(buzzer.command(2000, 999999));       // Never longer than the 2 s failsafe.
  assert(!buzzer.expired(3999) && buzzer.expired(4000));
  assert(buzzer.command(UINT32_MAX - 100, 400));
  assert(!buzzer.expired(UINT32_MAX) && !buzzer.expired(298));  // millis wrap.
  assert(buzzer.expired(299));
  puts("Firmware protocol/calibration tests passed");
}
