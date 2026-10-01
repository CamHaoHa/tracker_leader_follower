#pragma once

// Copy to config.local.h. That file is intentionally ignored by git.

// The one supported network: a phone hotspot (WPA2-personal). The laptop and
// every box join it. The ESP32 radio is 2.4 GHz only: on an iPhone turn on
// "Maximise Compatibility" and keep the Personal Hotspot screen open while
// the boxes join.
// An iPhone's default hotspot name contains a typographic apostrophe (U+2019).
// Write it as the UTF-8 bytes \xE2\x80\x99 inside the C string, for example
// "Sam\xE2\x80\x99s iPhone".
#define WIFI_SSID "your-phone-hotspot"
#define WIFI_PASSWORD "your-hotspot-password"

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
