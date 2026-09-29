#pragma once

#ifndef NODE_ID
#error "Build node_left, node_middle or node_right (node_right_pair for two boxes) to select NODE_ID"
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
// Keep home and school settings together; selection never deletes either one.
#ifndef WIFI_PROFILE
#define WIFI_PROFILE 0
#endif
#ifndef SCHOOL_WIFI_SSID
#define SCHOOL_WIFI_SSID ""
#endif
#ifndef SCHOOL_WIFI_PASSWORD
#define SCHOOL_WIFI_PASSWORD ""
#endif
#ifndef TRACKER_WIFI_SSID
#define TRACKER_WIFI_SSID "TrackerNet"
#endif
#ifndef TRACKER_WIFI_PASSWORD
#define TRACKER_WIFI_PASSWORD ""
#endif
#ifndef TRACKER_WIFI_CHANNEL
#define TRACKER_WIFI_CHANNEL 6
#endif
#ifndef ONENET_SSID
#define ONENET_SSID "Macquarie OneNet"
#endif
#ifndef ONENET_USERNAME
#define ONENET_USERNAME ""
#endif
#ifndef ONENET_PASSWORD
#define ONENET_PASSWORD ""
#endif
#ifndef ONENET_SERVER_DOMAIN
#define ONENET_SERVER_DOMAIN "radius.mq.edu.au"
#endif
// Used to seed certificate time before Wi-Fi. Recompile before OneNet use;
// __DATE__/__TIME__ follow the build machine timezone, configurable below.
#ifndef ONENET_BUILD_TIMEZONE
#define ONENET_BUILD_TIMEZONE "AEST-10AEDT,M10.1.0,M4.1.0/3"
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
// One pin map for every box: servo signal GPIO33, TRIG GPIO32, ECHO GPIO34.
// GPIO34 is input-only and has no internal pull resistors. The sensor is
// powered from 3V3, so ECHO is a 3.3 V signal wired directly (no divider).
#ifndef SERVO_PIN
#define SERVO_PIN 33
#endif
#ifndef ULTRASONIC_TRIG_PIN
#define ULTRASONIC_TRIG_PIN 32
#endif
#ifndef ULTRASONIC_ECHO_PIN
#define ULTRASONIC_ECHO_PIN 34
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

static_assert(NODE_ID >= 0 && NODE_ID <= 9, "NODE_ID must be 0..9: the wire protocol carries one digit");
static_assert(WIFI_PROFILE >= 0 && WIFI_PROFILE <= 3,
              "WIFI_PROFILE: 0=home, 1=school personal/hotspot, 2=OneNet PEAP, 3=tracker AP");
static_assert(TRACKER_WIFI_CHANNEL >= 1 && TRACKER_WIFI_CHANNEL <= 13,
              "TRACKER_WIFI_CHANNEL must be within 1..13");
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
