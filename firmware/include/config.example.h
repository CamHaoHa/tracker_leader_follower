#pragma once

// Copy to config.local.h. That file is intentionally ignored by git.
#define WIFI_SSID "your-2.4-GHz-network"
#define WIFI_PASSWORD "your-password"

// Adjust separately for each servo installation. Bearings use world axes:
// 0 degrees = +x (right), 90 degrees = +y (forward), 180 degrees = -x.
// A positive trim adds to the physical servo command after reversal.
#if NODE_ID == 0
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0
#else
#define SERVO_REVERSED 0
#define SERVO_CENTER_TRIM_MDEG 0
#endif

// Start conservatively; calibrate pulse range and travel for your servo.
// These pulse endpoints map to servo coordinates 0 and 180 degrees.
#define SERVO_PULSE_MIN_US 1000
#define SERVO_PULSE_MAX_US 2000
#define SERVO_MIN_MDEG 0
#define SERVO_MAX_MDEG 180000

#define SERVO_PIN 18
#define ULTRASONIC_TRIG_PIN 23
#define ULTRASONIC_ECHO_PIN 19
#define SERVO_SETTLE_MIN_MS 60
#define SERVO_SETTLE_MS_PER_DEG 3
#define SERVO_SETTLE_MAX_MS 700
#define ULTRASONIC_TIMEOUT_US 25000
#define ULTRASONIC_MIN_GAP_MS 65
