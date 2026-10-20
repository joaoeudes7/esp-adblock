// Optional boot/crash forensics (/boot.cfg). Build with -D BOOT_DEBUG=1 to include it.
//
// The heap watermark and the uptime live in RAM, so an OOM/panic erases exactly the evidence
// needed to diagnose it. This module keeps a tiny record in LittleFS so the NEXT boot can
// report: when the boot started (wall clock via SNTP), how long it survived, how low the heap
// got, and how the previous boot ended (reset reason, or an explicit intent tag for the
// restarts the firmware itself causes — OTA/provisioning — so they are not read as a crash).
//
// Off by default: with BOOT_DEBUG=0 every entry point below is an empty inline stub, so a
// normal build carries no extra code, no SNTP client and no flash writes. Exposed in
// /stats.json as bt/nt/rst/prev.* — those keys simply do not exist in a release build.
#pragma once
#include <time.h>

#ifndef BOOT_DEBUG
#define BOOT_DEBUG 0
#endif

enum { BOOT_INTENT_OTA = 1, BOOT_INTENT_PROVISION = 2 };

#if !BOOT_DEBUG

static inline uint32_t bootDbgInit(uint32_t id) { return id; }
static inline void bootDbgTick(bool) {}
static inline void bootDbgMarkRestart(uint8_t) {}
static inline void bootDbgNoteHeap(uint32_t, uint8_t) {}
static inline void bootDbgAddJson(String&) {}

#else

enum { BDR_POWER = 0, BDR_SOFT, BDR_PANIC, BDR_WDT, BDR_BROWNOUT, BDR_EXT, BDR_OTHER };
struct BootDbgRec {
  uint32_t id;     // boot counter (mirrors /boot.cnt)
  uint32_t epoch;  // wall-clock at boot (0 until SNTP answers)
  uint32_t up;     // uptime (s) at the last save
  uint32_t hmin;   // lowest free heap seen (0 = never sampled)
  uint32_t hup;    // uptime (s) of that low point
  uint16_t reason; // reset class that started THIS boot (becomes "end" for the next one)
  uint8_t ctx;     // 1 = web handler, 2 = DNS path (at the low point)
  uint8_t intent;  // restart we initiated: BOOT_INTENT_OTA / BOOT_INTENT_PROVISION
};
static const uint32_t BDR_MAGIC = 0x42535431UL; // "BST1"
static const uint32_t BDR_PERIOD_MS = 300000UL; // heartbeat: every 5 min
static const uint32_t BDR_NONE = 0xFFFFFFFFUL;
static BootDbgRec bdrCur, bdrPrev;                    // this boot + last saved state of the previous
static uint32_t bdrEpoch = 0;                         // wall-clock of this boot (0 = unknown)
static uint32_t bdrHmin = BDR_NONE, bdrHup = 0;       // live watermark mirrored from noteHeap()
static uint8_t bdrCtx = 0;
static uint32_t bdrSavedHmin = BDR_NONE;              // watermark already on flash (write limiter)
static uint32_t bdrLastSave = 0, bdrLastNtp = 0;
static bool bdrDirty = false, bdrNet = false;

static uint8_t bdrResetClass() {
#if defined(ESP8266)
  switch (ESP.getResetInfoPtr()->reason) {
    case REASON_DEFAULT_RST: return BDR_POWER;
    case REASON_EXT_SYS_RST: return BDR_EXT;
    case REASON_SOFT_RESTART:
    case REASON_DEEP_SLEEP_AWAKE: return BDR_SOFT;
    case REASON_EXCEPTION_RST: return BDR_PANIC;
    case REASON_WDT_RST:
    case REASON_SOFT_WDT_RST: return BDR_WDT;
    default: return BDR_OTHER;
  }
#else
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return BDR_POWER;
    case ESP_RST_EXT: return BDR_EXT;
    case ESP_RST_SW: return BDR_SOFT;
    case ESP_RST_PANIC: return BDR_PANIC;
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return BDR_WDT;
    case ESP_RST_BROWNOUT: return BDR_BROWNOUT;
    default: return BDR_OTHER;
  }
#endif
}
static const char* bdrResetName(uint8_t c) {
  switch (c) {
    case BDR_POWER: return "power";
    case BDR_SOFT: return "software";
    case BDR_PANIC: return "panic";
    case BDR_WDT: return "watchdog";
    case BDR_BROWNOUT: return "brownout";
    case BDR_EXT: return "external";
    default: return "unknown";
  }
}
static const char* bdrEndName(const BootDbgRec& r) {
  if (!r.id) return "";
  if (r.intent == BOOT_INTENT_OTA) return "ota";
  if (r.intent == BOOT_INTENT_PROVISION) return "provision";
  return bdrResetName((uint8_t)r.reason);
}
// Heuristic: the previous boot died of a memory fault. A low watermark + panic/WDT is the
// signature of an allocation failure (the SDK aborts, or the loop starves in a full heap).
static bool bdrOomSuspect() {
  return bdrPrev.hmin && bdrPrev.hmin < 4096 && bdrPrev.up > 120 &&
         (bdrPrev.reason == BDR_PANIC || bdrPrev.reason == BDR_WDT);
}
static void bdrSave() {
  File f = LittleFS.open("/boot.cfg", "w");
  if (!f) return;
  f.write((const uint8_t*)&BDR_MAGIC, sizeof BDR_MAGIC);
  f.write((const uint8_t*)&bdrCur, sizeof bdrCur);
  f.write((const uint8_t*)&bdrPrev, sizeof bdrPrev);
  f.close();
  bdrSavedHmin = bdrCur.hmin ? bdrCur.hmin : BDR_NONE;
  bdrDirty = false;
}
static void bdrPersist() {
  bdrCur.up = millis() / 1000;
  if (bdrEpoch && !bdrCur.epoch) bdrCur.epoch = bdrEpoch;
  if (bdrHmin != BDR_NONE) {
    bdrCur.hmin = bdrHmin;
    bdrCur.hup = bdrHup;
    bdrCur.ctx = bdrCtx;
  }
  bdrSave();
}
static void bootDbgMarkRestart(uint8_t intent) {
  bdrCur.intent = intent;
  bdrPersist();
}
// Called once at boot with the (already incremented) /boot.cnt value. Returns the id to use,
// adopting a higher recorded id so switching this build on/off stays monotonic.
static uint32_t bootDbgInit(uint32_t id) {
  BootDbgRec last;
  memset(&last, 0, sizeof last);
  File f = LittleFS.open("/boot.cfg", "r");
  if (f) {
    uint32_t magic = 0;
    if (f.read((uint8_t*)&magic, sizeof magic) != sizeof magic || magic != BDR_MAGIC ||
        f.read((uint8_t*)&last, sizeof last) != sizeof last)
      memset(&last, 0, sizeof last);
    f.close();
  }
  if (last.id >= id) id = last.id + 1;
  // Only claim "previous boot" when the record chains to this one. If release builds ran in
  // between (BOOT_DEBUG toggled off), the file is stale and its snapshot would be mislabelled.
  bool chained = last.id && last.id + 1 == id;
  memset(&bdrPrev, 0, sizeof bdrPrev);
  if (chained) {
    bdrPrev = last;                   // last saved state of the boot this one replaces...
    bdrPrev.reason = bdrResetClass(); // ...plus how it ended (reason observed at this boot)
  }
  memset(&bdrCur, 0, sizeof bdrCur);
  bdrCur.id = id;
  bdrCur.reason = bdrResetClass();
  bdrHmin = BDR_NONE;
  bdrHup = 0;
  bdrCtx = 0;
  bdrEpoch = 0;
  bdrSavedHmin = BDR_NONE;
  bdrDirty = false;
  bdrSave();
  Serial.printf("[boot] #%u %s | previous #%u: up=%us hmin=%u@%us ctx=%u end=%s%s\n",
                (unsigned)bdrCur.id, bdrResetName((uint8_t)bdrCur.reason), (unsigned)bdrPrev.id,
                (unsigned)bdrPrev.up, (unsigned)bdrPrev.hmin, (unsigned)bdrPrev.hup,
                (unsigned)bdrPrev.ctx, bdrEndName(bdrPrev), bdrOomSuspect() ? " (suspect OOM)" : "");
  return id;
}
// Main's noteHeap() calls this only when it sees a new low point; ctx matches its own codes.
static void bootDbgNoteHeap(uint32_t h, uint8_t ctx) {
  bdrHmin = h;
  bdrHup = millis() / 1000;
  bdrCtx = ctx;
  // Persist a near-OOM dip quickly instead of waiting for the 5-min heartbeat. The 1 KB step
  // keeps flash writes rare while still leaving a trail of a fast leak right up to the crash.
  if (bdrSavedHmin - h >= 1024) bdrDirty = true;
}
static void bootDbgTick(bool netUp) {
  if (netUp && !bdrNet) { // start SNTP lazily, once the link is actually up
    configTime(0, 0, "pool.ntp.org", "time.cloudflare.com");
    bdrNet = true;
  }
  if (!bdrEpoch && bdrNet && (uint32_t)(millis() - bdrLastNtp) >= 10000UL) {
    bdrLastNtp = millis();
    time_t t = time(nullptr);
    if (t > 1700000000L) { // SNTP answered: back-date this boot from the uptime
      bdrEpoch = (uint32_t)t - millis() / 1000;
      bdrCur.epoch = bdrEpoch;
      bdrPersist();
    }
  }
  if (bdrDirty || (uint32_t)(millis() - bdrLastSave) >= BDR_PERIOD_MS) {
    bdrLastSave = millis();
    bdrPersist();
  }
}
static void bootDbgAddJson(String& j) {
  uint32_t now = bdrEpoch ? bdrEpoch + (uint32_t)(millis() / 1000) : 0;
  j += ",\"bt\":" + String((unsigned long)bdrEpoch) + ",\"nt\":" + String((unsigned long)now) +
       ",\"rst\":\"" + bdrResetName(bdrResetClass()) + "\",\"prev\":{\"id\":" +
       String((unsigned long)bdrPrev.id) + ",\"bt\":" + String((unsigned long)bdrPrev.epoch) +
       ",\"up\":" + String((unsigned long)bdrPrev.up) + ",\"hmin\":" +
       String((unsigned long)bdrPrev.hmin) + ",\"hup\":" + String((unsigned long)bdrPrev.hup) +
       ",\"hctx\":" + String((unsigned long)bdrPrev.ctx) + ",\"end\":\"" + bdrEndName(bdrPrev) +
       "\",\"sus\":\"" + (bdrOomSuspect() ? "oom" : "") + "\"}";
}

#endif // BOOT_DEBUG
