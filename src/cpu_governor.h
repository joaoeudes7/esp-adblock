#pragma once
// CPU governor (ondemand) — keeps the chip at its boot clock shortly after DNS activity and
// drops to 80 MHz once the resolver has been quiet for a while (with hysteresis, so it never
// thrashes). Platform-agnostic: the "fast" clock is taken from the device itself (the clock
// the board booted at, capped at MAX_MHZ for power), and only the get/set primitives differ,
// so the policy below is identical on ESP8266 and the ESP32 family. Other targets: no-op.
//
//   cpu_gov::markActivity();   // once per handled DNS query — stamps the last-activity time
//   cpu_gov::checkIdle();      // every loop() — self-throttles (~2x/s) and switches the clock
#if defined(ESP8266) || defined(ESP32)
#include <Arduino.h>
#if defined(ESP8266)
#include <user_interface.h> // system_update_cpu_freq()
inline uint32_t cpu_gov_getMhz() { return ESP.getCpuFreqMHz(); }
inline bool cpu_gov_setMhz(uint32_t m) { return system_update_cpu_freq(m); }
#else
#include <esp32-hal-cpu.h> // get/setCpuFrequencyMhz()
inline uint32_t cpu_gov_getMhz() { return getCpuFrequencyMhz(); }
inline bool cpu_gov_setMhz(uint32_t m) { return setCpuFrequencyMhz(m); }
#endif

namespace cpu_gov {
const uint32_t ACTIVE_WINDOW_MS = 2000; // stay fast for this long after the last query
const uint32_t IDLE_MS = 3000;          // drop to slow once quiet for this long
const uint32_t CHECK_MS = 500;          // how often checkIdle() re-evaluates
const uint32_t MAX_MHZ = 300;           // cap the fast clock (whatever the chip offers) for power
const uint32_t SLOW_MHZ = 80;           // idle clock (lowest usable on both families)

inline uint32_t& lastActivity() {
  static uint32_t t = 0;
  return t;
}
inline uint32_t& fastMhz() {
  static uint32_t m = 0;
  return m;
} // device boot clock, captured on 1st use
inline bool& fast() {
  static bool f = true;
  return f;
}

inline void markActivity() { lastActivity() = millis(); }

inline void checkIdle() {
  static uint32_t lastCheck = 0;
  if ((uint32_t)(millis() - lastCheck) < CHECK_MS) return;
  lastCheck = millis();
  if (!fastMhz()) { // "fast" = the clock the board booted at, capped
    uint32_t m = cpu_gov_getMhz();
    fastMhz() = (m > MAX_MHZ) ? MAX_MHZ : m;
  }
  uint32_t t = lastActivity();
  uint32_t age = t ? (uint32_t)(millis() - t) : 0xFFFFFFFFu; // never used yet -> treat as idle
  if (age < ACTIVE_WINDOW_MS) {
    if (!fast()) {
      cpu_gov_setMhz(fastMhz());
      fast() = true;
    }
  } else if (age > IDLE_MS && fast()) {
    cpu_gov_setMhz(SLOW_MHZ);
    fast() = false;
  }
}
} // namespace cpu_gov
#else
namespace cpu_gov {
inline void markActivity() {}
inline void checkIdle() {}
} // namespace cpu_gov
#endif
