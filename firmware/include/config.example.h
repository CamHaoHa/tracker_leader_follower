#pragma once

// Copy to config.local.h. That file is intentionally ignored by git.
#define WIFI_SSID "your-2.4-GHz-network"
#define WIFI_PASSWORD "your-password"

// 0 = home, 1 = school personal/hotspot, 2 = OneNet PEAP, 3 = tracker network.
// All profiles remain stored when switching this selection.
#define WIFI_PROFILE 0
#define SCHOOL_WIFI_SSID ""
#define SCHOOL_WIFI_PASSWORD ""

// Profile 3: left ESP32 creates this WPA2 network at 192.168.4.1/24.
// Right ESP32 and laptop join it and receive DHCP addresses (order may vary).
// Use the same private 8..63-character password on both boards. Empty passwords
// are rejected; the firmware never falls back to an open network.
// The preparation tool can generate matching private tracker_network.h files.
#define TRACKER_WIFI_SSID "TrackerNet"
#define TRACKER_WIFI_PASSWORD ""
#define TRACKER_WIFI_CHANNEL 6

// Optional/deferred OneNet: requires Arduino-ESP32 3.3+ with default CA bundle
// and server-domain verification support. PlatformIO's older core is unsuitable.
// Recompile before use to seed certificate time, or provide a trustworthy clock.
#define ONENET_USERNAME ""
#define ONENET_PASSWORD ""
#define ONENET_SERVER_DOMAIN "radius.mq.edu.au"
#define ONENET_BUILD_TIMEZONE "AEST-10AEDT,M10.1.0,M4.1.0/3"

// Adjust separately for each servo installation. Bearings use world axes:
// 0 degrees = +x (right), 90 degrees = +y (forward), 180 degrees = -x.
// A positive trim adds to the physical servo command after reversal.
#if NODE_ID == 0
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0
#elif NODE_ID == 1  // middle box, or the right box of a two-box layout
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0
#else  // NODE_ID 2: the right box of a three-box layout
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0
#endif

// Start conservatively; calibrate pulse range and travel for your servo.
// These pulse endpoints map to servo coordinates 0 and 180 degrees.
#define SERVO_PULSE_MIN_US 1000
#define SERVO_PULSE_MAX_US 2000
#define SERVO_MIN_MDEG 0
#define SERVO_MAX_MDEG 180000

// Same pin map on every box. GPIO34 is input-only with no internal pull
// resistors; power the sensor from 3V3 and wire ECHO directly (no divider).
#define SERVO_PIN 33
#define ULTRASONIC_TRIG_PIN 32
#define ULTRASONIC_ECHO_PIN 34

// Buzzer: middle box only (node 1), + to GPIO25 and - to GND. Boxes without
// BUZZER_PIN have no buzzer and ignore WM2 BUZZ. In a two-box layout node 1
// is the right box (node_right_pair): GPIO25 is driven there too.
// BUZZER_TONE_HZ is the square wave for a passive buzzer; set it to 0 for an
// active buzzer, which only needs the pin held HIGH.
#if NODE_ID == 1
#define BUZZER_PIN 25
#endif
#define BUZZER_TONE_HZ 2000

#define SERVO_SETTLE_MIN_MS 60
#define SERVO_SETTLE_MS_PER_DEG 3
#define SERVO_SETTLE_MAX_MS 700
#define ULTRASONIC_TIMEOUT_US 25000
#define ULTRASONIC_MIN_GAP_MS 65
