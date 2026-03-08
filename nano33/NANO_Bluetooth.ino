#include <ArduinoBLE.h>
#include <Arduino_APDS9960.h>
#include <Arduino_HTS221.h>

const int LED_PIN = 3;

// ===== BLE UUIDs =====
BLEService lampService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic cmdChar("19B10001-E8F2-537E-4F6C-D104768A1214", BLEWrite, 40);
BLEStringCharacteristic teleChar("19B10002-E8F2-537E-4F6C-D104768A1214", BLENotify, 220);

// ===== Sensors OK flags =====
bool apdsOk = false;
bool htsOk  = false;

// ===== Control =====
bool autoMode = true;
int manualBrightness = 160;
int appliedBrightness = 0;

// ===== Anti-flicker control =====
const float LUX_ALPHA = 0.08f;          // smaller = smoother
const unsigned long CTRL_PERIOD_MS = 60;
const int PWM_HYST = 4;
const int PWM_STEP_UP = 8;
const int PWM_STEP_DN = 6;

const int MIN_PWM = 0;
const int MAX_PWM = 255;
const float GAMMA = 2.2f;

// Fallback range if calibration is not good
const int DEFAULT_DARK = 30;
const int DEFAULT_BRIGHT = 600;

// Calibration
unsigned long calibStart = 0;
const unsigned long CALIB_MS = 5000;
int luxMin = 999999;
int luxMax = 0;
const int MIN_RANGE_SPAN = 120;

float luxFiltered = 0;

int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

void applyPWM(int v) {
  v = clampi(v, 0, 255);
  analogWrite(LED_PIN, v);
  appliedBrightness = v;
}

void startRecal() {
  calibStart = millis();
  luxMin = 999999;
  luxMax = 0;
}

int readLuxRaw() {
  if (!apdsOk) return -1;
  if (!APDS.colorAvailable()) return -1;
  int r, g, b, c;
  APDS.readColor(r, g, b, c);
  return c; // clear channel as lux-like
}

void updateLuxFilter(int luxRaw) {
  if (luxRaw < 0) return;
  if (luxFiltered == 0) luxFiltered = luxRaw;
  luxFiltered = luxFiltered + LUX_ALPHA * (luxRaw - luxFiltered);
}

void updateCalibration(int luxRaw) {
  if (luxRaw < 0) return;

  if (millis() - calibStart < CALIB_MS) {
    luxMin = min(luxMin, luxRaw);
    luxMax = max(luxMax, luxRaw);
  } else {
    luxMin = (int)(0.997 * luxMin + 0.003 * luxRaw);
    luxMax = (int)(0.997 * luxMax + 0.003 * luxRaw);
    if (luxMax - luxMin < MIN_RANGE_SPAN) luxMax = luxMin + MIN_RANGE_SPAN;
  }
}

int computeTargetPWM(float luxLike) {
  bool rangeOk = (luxMax > 0) && ((luxMax - luxMin) >= MIN_RANGE_SPAN);
  int dark = rangeOk ? luxMin : DEFAULT_DARK;
  int bright = rangeOk ? luxMax : DEFAULT_BRIGHT;

  float x = (luxLike - dark) / (float)max(1, (bright - dark)); // 0..1
  if (x < 0) x = 0;
  if (x > 1) x = 1;

  float y = 1.0f - x; // dark -> 1, bright -> 0
  y = pow(y, GAMMA);

  int pwm = (int)(MIN_PWM + y * (MAX_PWM - MIN_PWM));
  return clampi(pwm, 0, 255);
}

void movePWMtowards(int target) {
  int diff = target - appliedBrightness;
  if (abs(diff) < PWM_HYST) return;

  if (diff > 0) {
    applyPWM(appliedBrightness + min(diff, PWM_STEP_UP));
  } else {
    applyPWM(appliedBrightness - min(-diff, PWM_STEP_DN));
  }
}

String telemetryLine(float tempC, float hum, int luxVal) {
  String s;
  s.reserve(220);
  s += "ambient_light="; s += luxVal;
  s += ",temperature_c="; s += String(tempC, 1);
  s += ",humidity_percent="; s += String(hum, 1);
  s += ",light_range="; s += luxMin; s += "-"; s += luxMax;
  s += ",brightness_pwm="; s += appliedBrightness;
  s += ",mode="; s += (autoMode ? "auto" : "manual");
  return s;
}

void handleCmd(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "AUTO") {
    autoMode = true;
  } else if (cmd == "MANUAL") {
    autoMode = false;
    applyPWM(manualBrightness);
  } else if (cmd.startsWith("SET")) {
    int v = cmd.substring(3).toInt();
    manualBrightness = clampi(v, 0, 255);
    // IMPORTANT: do NOT force autoMode=false here
    if (!autoMode) applyPWM(manualBrightness);
  } else if (cmd == "RECAL") {
    startRecal();
  } else if (cmd == "STATUS") {
    // Next notify will contain latest values
  }
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(115200);

  // Visible start
  applyPWM(140);

  apdsOk = APDS.begin();
  htsOk  = HTS.begin();

  if (!apdsOk) {
    Serial.println("WARN apds init failed -> MANUAL fallback");
    autoMode = false;
    manualBrightness = 180;
    applyPWM(manualBrightness);
  }
  if (!htsOk) {
    Serial.println("WARN hts init failed -> NaN temp/hum");
  }

  if (!BLE.begin()) {
    Serial.println("BLE.begin failed");
    while (1) {}
  }

  BLE.setLocalName("SmartLamp");
  BLE.setDeviceName("SmartLamp");
  BLE.setAdvertisedService(lampService);

  lampService.addCharacteristic(cmdChar);
  lampService.addCharacteristic(teleChar);
  BLE.addService(lampService);

  cmdChar.writeValue("");
  BLE.advertise();

  startRecal();
  Serial.println("SmartLamp BLE + sensors ready");
}

void loop() {
  BLE.poll();

  // Read sensors
  int luxRaw = readLuxRaw();
  updateLuxFilter(luxRaw);
  updateCalibration(luxRaw);

  // Commands
  if (BLE.connected() && cmdChar.written()) {
    handleCmd(cmdChar.value());
  }

  // Control loop
  static unsigned long lastCtrl = 0;
  unsigned long now = millis();
  if (now - lastCtrl >= CTRL_PERIOD_MS) {
    lastCtrl = now;
    if (autoMode && apdsOk && luxRaw >= 0) {
      int target = computeTargetPWM(luxFiltered);
      movePWMtowards(target);
    } else {
      movePWMtowards(manualBrightness);
    }
  }

  // Temp/Hum
  float tempC = NAN, hum = NAN;
  if (htsOk) {
    tempC = HTS.readTemperature();
    hum   = HTS.readHumidity();
  }

  // Telemetry notify
  static unsigned long lastTele = 0;
  if (now - lastTele >= 500) {
    lastTele = now;
    String line = telemetryLine(tempC, hum, (int)luxFiltered);
    if (BLE.connected()) teleChar.writeValue(line);
    Serial.println(line);
  }

  delay(5);
}