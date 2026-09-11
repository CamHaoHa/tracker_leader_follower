#pragma once

#ifndef NODE_ID
#error "Build node_left or node_right to select NODE_ID"
#endif

#if __has_include("config.local.h")
#include "config.local.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif
#ifndef SERVO_REVERSED
#define SERVO_REVERSED 0
#endif
#ifndef SERVO_CENTER_TRIM_MDEG
#define SERVO_CENTER_TRIM_MDEG 0
#endif
#ifndef SERVO_PULSE_MIN_US
#define SERVO_PULSE_MIN_US 1000
#endif
#ifndef SERVO_PULSE_MAX_US
#define SERVO_PULSE_MAX_US 2000
#endif
#ifndef SERVO_MIN_MDEG
#define SERVO_MIN_MDEG 0
#endif
#ifndef SERVO_MAX_MDEG
#define SERVO_MAX_MDEG 180000
#endif
#ifndef SERVO_PIN
#define SERVO_PIN 18
#endif
#ifndef ULTRASONIC_TRIG_PIN
#define ULTRASONIC_TRIG_PIN 23
#endif
#ifndef ULTRASONIC_ECHO_PIN
#define ULTRASONIC_ECHO_PIN 19
#endif
#ifndef SERVO_SETTLE_MIN_MS
#define SERVO_SETTLE_MIN_MS 60
#endif
#ifndef SERVO_SETTLE_MS_PER_DEG
#define SERVO_SETTLE_MS_PER_DEG 3
#endif
#ifndef SERVO_SETTLE_MAX_MS
#define SERVO_SETTLE_MAX_MS 700
#endif
#ifndef ULTRASONIC_TIMEOUT_US
#define ULTRASONIC_TIMEOUT_US 25000
#endif
#ifndef ULTRASONIC_MIN_GAP_MS
#define ULTRASONIC_MIN_GAP_MS 65
#endif

static_assert(NODE_ID == 0 || NODE_ID == 1, "NODE_ID must be 0 or 1");
static_assert(SERVO_REVERSED == 0 || SERVO_REVERSED == 1,
              "SERVO_REVERSED must be 0 or 1");
static_assert(SERVO_MIN_MDEG >= 0 && SERVO_MAX_MDEG <= 180000 &&
                  SERVO_MIN_MDEG < SERVO_MAX_MDEG,
              "Servo travel limits must be within 0..180000");
static_assert(SERVO_CENTER_TRIM_MDEG >= -90000 && SERVO_CENTER_TRIM_MDEG <= 90000,
              "Trim must be within +/-90 degrees");
static_assert(SERVO_PULSE_MIN_US >= 500 && SERVO_PULSE_MAX_US <= 2500 &&
                  SERVO_PULSE_MIN_US < SERVO_PULSE_MAX_US,
              "Servo pulse endpoints must be within 500..2500 us");
static_assert(SERVO_SETTLE_MIN_MS >= 60 && SERVO_SETTLE_MS_PER_DEG >= 0 &&
                  SERVO_SETTLE_MAX_MS >= SERVO_SETTLE_MIN_MS &&
                  SERVO_SETTLE_MAX_MS <= 700,
              "Settling must stay within 60..700 ms");
static_assert(ULTRASONIC_TIMEOUT_US > 0 && ULTRASONIC_TIMEOUT_US <= 25000,
              "Echo timeout must be bounded at 25 ms");
static_assert(ULTRASONIC_MIN_GAP_MS >= 65, "Leave at least 65 ms between pings");
static_assert(SERVO_PIN != ULTRASONIC_TRIG_PIN && SERVO_PIN != ULTRASONIC_ECHO_PIN &&
                  ULTRASONIC_TRIG_PIN != ULTRASONIC_ECHO_PIN,
              "Servo, trigger and echo must use distinct pins");
