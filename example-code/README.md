# What is this?
A real-time dual-sensor 2d object tracking system running on embedded Linux, featuring noise filtering and direct framebuffer rendering. The system uses two ultrasonic sensors to track the movement of an object while rendering graphics directly to the Linux framebuffer.

[![Watch the video](https://img.youtube.com/vi/Rb5tlce1iRw/0.jpg)](https://www.youtube.com/watch?v=Rb5tlce1iRw)

# Hardware
* Luckfox pico mini b (Rockchip RV1103 SoC)
* 2x HC-SR04 Ultrasound modules (UART mode)
* Wires and USB cable

# How It Works
The system uses two stationary ultrasonic sensors positioned at 90 degrees angle from each other to perform 2D object tracking, X and Y positions. The Python script:  
* Reads ultrasonic measurements from both sensors simultaneously through separate UART interfaces
* Performs quick background calibration to establish environmental baseline
* Tracks an object in real-time with smart noise filtering
* Implements object visibility checking and movement thresholds
* Renders the tracking display directly to the Linux framebuffer using double buffering
* Provides smooth object tracking with position filtering

Additionally, it can run an X11 VNC server for remote viewing from any device with a VNC client.

# Sensor Requirements

<img width="1071" height="399" alt="image" src="https://github.com/user-attachments/assets/f0899b0e-07ac-41d8-9417-1da70cf95cb4" />

> [!WARNING]
> Enable UART mode by following the instructions table on the PCB and solder the shown pad (typically M1). If your module doesn't have these configuration options, it may only support the traditional GPIO pulse method, which is not compatible with this implementation.

The system uses UART mode because Linux cannot guarantee the high-precision timing required for the traditional GPIO pulse method due to its preemptive kernel scheduler. In UART mode:  
1. Send the trigger command `0xA0` via UART
2. The module handles ultrasound emission and echo processing internally
3. Wait for response with timeout
4. Successful measurements return exactly 3 bytes that combine to give distance in micrometers (µm)

# Configuration and Wiring
Both UART interfaces should be configured for 9600 bps 8N1 communication. The ultrasonic sensors use 3.3V power.  

<img width="1623" height="329" alt="image" src="https://github.com/user-attachments/assets/c3e947d1-a1e1-444a-ac2b-584564a706e7" />

```
SoC        SR04-Bottom   SR04-Left
──────────────────────────────────
3V3  ─────→ VCC    ───→ VCC
GND  ─────→ GND    ───→ GND  
P53  ─────→ RX
P52  ─────→ TX
P56  ────────────────→ RX
P57  ────────────────→ TX

Power:
SoC 3V3  → Both SR04 VCC
SoC GND  → Both SR04 GND

Signals:
SoC Pin 53 → Bottom SR04 RX
SoC Pin 52 → Bottom SR04 TX
SoC Pin 56 → Left SR04 RX  
SoC Pin 57 → Left SR04 TX
```

# Key Features
* **Dual-sensor 2D tracking** - Stationary sensors provide X-Y coordinate tracking
* **Smart noise filtering** - Movement thresholds and stability checking eliminate jitter
* **Object visibility detection** - Automatic detection when objects enter/leave sensor range
* **Double-buffered rendering** - Flicker-free graphics with direct framebuffer access
* **Real-time performance** - Optimized for 30 FPS tracking and display
* **Quick calibration** - Fast background measurement for immediate operation
* **Position smoothing** - Weighted averaging for smooth object movement

# Tracking Parameters
```python
MAX_DISTANCE_CM = 30                  # Maximum tracking range
OBJECT_THRESHOLD_CM = 1.0             # Difference from background to detect object
NOISE_THRESHOLD_CM = 0.5              # Filter out small movements
MIN_MOVEMENT_CM = 0.5                 # Minimum movement to update position
UPDATE_RATE = 0.033                   # 30fps target
```

# Pre-requisites
* Python 3
* `pyserial` library
* Framebuffer device at `/dev/fb0`
* Framebuffer configured: `fbset -g 320 240 320 240 16`

Execute the tracker with `python3 tracker.py`. The system will perform quick automatic calibration, then begin tracking with real-time display.

![dd](https://github.com/user-attachments/assets/5f192a05-9a24-45d6-91be-348f8319d427)

# Portability
The code is designed for easy adaptation to different embedded systems:
* Uses standard Linux device nodes (`/dev/ttyS*`, `/dev/fb*`)
* Hardware-agnostic through `pyserial` library
* Configurable parameters at script top
* Automatic display detection and scaling
* Modular class design for easy customization

# Performance Tips
* Use lower display resolutions (320x240) for better performance
* Keep `MAX_DISTANCE_CM` appropriate for your application
* Ensure stable 3.3V power supply to sensors
* Allow sufficient time between ultrasonic measurements
* Consider material properties - some surfaces absorb ultrasound unpredictably
* For longer range, use 5V sensors with level shifters for 3.3V SoC compatibility
