/*
 * Lock-scan node: the single-box SEARCH/TRACK sketch (30 September 2026)
 * running UNCHANGED on each box, with Wi-Fi reporting added so the laptop
 * can draw the spot. The laptop never commands this box; it only listens.
 *
 * Everything marked "added" is instrumentation around the sketch:
 *   - Wi-Fi join with the box's configured profile 0/1 (settings.h)
 *   - one UDP line per ping and per pass to the laptop (its port 4210):
 *       LS <node> HELLO                      every 2 s (broadcast until the
 *                                            laptop has answered once)
 *       LS <node> PING <angle> <cm>          every reading (-1.0 = no echo)
 *       LS <node> LOCK <angle> <cm>          Target found -> TRACK
 *       LS <node> TRACK <angle> <cm> <hits>  end of a pass with hits
 *       LS <node> MISS <lostCount>           end of an empty pass
 *       LS <node> LOST                       Target lost -> SEARCH
 *   - the laptop's address is learned from any packet it sends to port 4211
 *
 * Build and upload: pio run -e lock_left|lock_middle|lock_right -t upload
 * (NODE_ID 0, 1, 2; pins and Wi-Fi from config.local.h as for the WM2 build).
 */
#include <WiFi.h>
#include <Arduino.h>
#include <ESP32Servo.h>

#include <WiFiUdp.h>                                   // added
#include <stdarg.h>                                    // added
#include "settings.h"                                  // added: NODE_ID, Wi-Fi profile, box pins
static const uint8_t kConfiguredServoPin = SERVO_PIN;  // added
#undef SERVO_PIN                                       // added: the sketch declares it as a constant
#if WIFI_PROFILE != 0 && WIFI_PROFILE != 1
#error "lockscan_main.cpp joins a home/school network only: use WIFI_PROFILE 0 or 1"
#endif

const uint8_t TRIG_PIN = ULTRASONIC_TRIG_PIN;   // 32 on every box (config.local.h)
const uint8_t ECHO_PIN = ULTRASONIC_ECHO_PIN;   // 34
const uint8_t SERVO_PIN = kConfiguredServoPin;  // 33

const int MIN_ANGLE = 0;
const int MAX_ANGLE = 180;
const int STEP_DEG = 3;
const int SETTLE_MS = 40;
const float MAX_RANGE_CM = 100.0;
const int WINDOW_DEG = 15;      // how far either side to look while tracking
const float MAX_JUMP_CM = 25.0; // reject readings that jump too far from the target's distance
const int LOST_LIMIT = 4;       // empty scans before giving up and searching again

Servo servo;

enum Mode
{
  SEARCH,
  TRACK
};
Mode mode = SEARCH;

// Search state
int searchAngle = MIN_ANGLE;
int searchDir = 1;

// Track state
int lockedAngle = 90;
float lockedDist = 0;
int lostCount = 0;
bool scanForward = true;

// ---- added: Wi-Fi and reporting -------------------------------------------
WiFiUDP udp;
bool udpReady = false;
bool wifiWasUp = false;
IPAddress hostAddress;
uint16_t hostPort = 4210;
bool hostKnown = false;
unsigned long lastHelloMs = 0;

void startWifi()
{
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
#if WIFI_PROFILE == 1
  WiFi.begin(SCHOOL_WIFI_SSID, SCHOOL_WIFI_PASSWORD);
#else
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#endif
}

void sendLine(const IPAddress &to, uint16_t port, const char *line)
{
  if (!udpReady || !udp.beginPacket(to, port))
    return;
  udp.write(reinterpret_cast<const uint8_t *>(line), strlen(line));
  udp.endPacket();
}

// One report line to the laptop, once it is known. Costs well under a
// millisecond; the sketch's own timing (SETTLE_MS + pulseIn) is untouched.
void report(const char *fmt, ...)
{
  if (!udpReady || !hostKnown)
    return;
  char line[80];
  int n = snprintf(line, sizeof(line), "LS %u ", (unsigned)NODE_ID);
  va_list args;
  va_start(args, fmt);
  vsnprintf(line + n, sizeof(line) - n, fmt, args);
  va_end(args);
  sendLine(hostAddress, hostPort, line);
}

// Between pings: keep the UDP socket in step with Wi-Fi, learn the laptop's
// address from anything it sends, and say HELLO every 2 s.
void service()
{
  const bool up = WiFi.status() == WL_CONNECTED;
  if (!up)
  {
    if (udpReady)
    {
      udp.stop();
      udpReady = false;
      hostKnown = false;
    }
    wifiWasUp = false;
    return;
  }
  if (!wifiWasUp)
  {
    wifiWasUp = true;
    Serial.print("Node ");
    Serial.print(NODE_ID);
    Serial.print(" on Wi-Fi at ");
    Serial.print(WiFi.localIP());
    Serial.println(":4211 (lock-scan sketch, reports to the laptop's 4210)");
  }
  if (!udpReady)
    udpReady = udp.begin(4211) == 1;
  if (!udpReady)
    return;
  for (int i = 0; i < 8; ++i)
  {
    if (udp.parsePacket() <= 0)
      break;
    hostAddress = udp.remoteIP();
    hostPort = udp.remotePort();
    hostKnown = true;
    udp.flush();
  }
  if (millis() - lastHelloMs >= 2000)
  {
    lastHelloMs = millis();
    char line[24];
    snprintf(line, sizeof(line), "LS %u HELLO", (unsigned)NODE_ID);
    if (hostKnown)
      sendLine(hostAddress, hostPort, line);
    else
      sendLine(WiFi.broadcastIP(), 4210, line);
  }
}
// ---- end added --------------------------------------------------------------

float readDistanceCm()
{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000UL);
  if (duration == 0)
    return -1;
  return duration * 0.0343 / 2.0;
}

float aimAndRead(int angle)
{
  service();                          // added
  servo.write(angle);
  delay(SETTLE_MS);
  float d = readDistanceCm();         // sketch: return readDistanceCm();
  report("PING %d %.1f", angle, d);   // added
  return d;
}

// Take one reading while tracking accumulate it if it looks like our object
void sample(int angle, long &angleSum, float &distSum, int &hits)
{
  float d = aimAndRead(angle);
  bool inRange = d > 0 && d < MAX_RANGE_CM;
  bool sameObject = fabs(d - lockedDist) < MAX_JUMP_CM;
  if (inRange && sameObject)
  {
    angleSum += angle;
    distSum += d;
    hits++;
  }
}

void search()
{
  float d = aimAndRead(searchAngle);

  if (d > 0 && d < MAX_RANGE_CM)
  {
    lockedAngle = searchAngle;
    lockedDist = d;
    lostCount = 0;
    mode = TRACK;
    Serial.println("Target found -> TRACK");
    report("LOCK %d %.1f", lockedAngle, lockedDist);   // added
    return;
  }

  searchAngle += searchDir * STEP_DEG;
  if (searchAngle >= MAX_ANGLE)
  {
    searchAngle = MAX_ANGLE;
    searchDir = -1;
  }
  else if (searchAngle <= MIN_ANGLE)
  {
    searchAngle = MIN_ANGLE;
    searchDir = 1;
    }
}

void track()
{
  int lo = max(MIN_ANGLE, lockedAngle - WINDOW_DEG);
  int hi = min(MAX_ANGLE, lockedAngle + WINDOW_DEG);

  long angleSum = 0;
  float distSum = 0;
  int hits = 0;

  if (scanForward)
  {
    for (int a = lo; a <= hi; a += STEP_DEG)
      sample(a, angleSum, distSum, hits);
  }
  else
  {
    for (int a = hi; a >= lo; a -= STEP_DEG)
      sample(a, angleSum, distSum, hits);
  }
  scanForward = !scanForward;

  if (hits > 0)
  {
    lockedAngle = angleSum / hits;                          // centre of the object
    lockedDist = 0.7 * lockedDist + 0.3 * (distSum / hits); // smoothed distance
    lostCount = 0;
    servo.write(lockedAngle);

    Serial.print("Angle: ");
    Serial.print(lockedAngle);
    Serial.print("  Distance: ");
    Serial.print(lockedDist);
    Serial.println(" cm");
    report("TRACK %d %.1f %d", lockedAngle, lockedDist, hits);   // added
  }
  else if (++lostCount >= LOST_LIMIT)
  {
    Serial.println("Target lost -> SEARCH");
    report("LOST");                                            // added
    mode = SEARCH;
    searchAngle = lockedAngle;
  }
  else
  {
    report("MISS %d", lostCount);                              // added
  }
}

void setup()
{
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  servo.attach(SERVO_PIN);
  servo.write(90);
  delay(500);
  Serial.printf("Lock-scan node %u, pins servo=%u TRIG=%u ECHO=%u, Wi-Fi profile %u\n",   // added
                (unsigned)NODE_ID, SERVO_PIN, TRIG_PIN, ECHO_PIN, (unsigned)WIFI_PROFILE);
  startWifi();                                                                                // added
}

void loop()
{
  if (mode == SEARCH)
    search();
  else
    track();
}
