#pragma once
#include <stdint.h>
// TTL-aware DNS response cache, 2-way set-associative.
// vs a direct-mapped cache of the same entry count it keeps more of the *frequently*
// hit domains: two keys that collide on the same set no longer evict each other.
// N = total entries (power of 2 -> N/2 sets), MAX = largest cached reply (bytes).
// Pure C++ (no Arduino): `now` in ms is a parameter, so it host-tests without a toolchain
// (tools/test_resp_cache.cpp).
template <int N, int MAX>
struct RespCache {
  struct Entry { uint32_t key; uint32_t expiry; uint16_t len; uint8_t data[MAX]; };
  Entry e[N];
  static const int SETS = N / 2;

  void clear() { for (int i = 0; i < N; i++) e[i].len = 0; }

  // Cached reply for `key`, or null on miss/expiry.
  Entry* find(uint32_t key, uint32_t now) {
    int base = (int)(key & (SETS - 1)) * 2;
    for (int i = 0; i < 2; i++) {
      Entry& s = e[base + i];
      if (s.len && s.key == key && (int32_t)(now - s.expiry) < 0) return &s;
    }
    return 0;
  }
  // Slot to write a fresh entry into: a free or stale one first, else the entry closer
  // to expiry (least remaining value — no extra RAM for a true LRU).
  Entry* insert(uint32_t key, uint32_t now) {
    int base = (int)(key & (SETS - 1)) * 2;
    for (int i = 0; i < 2; i++) {
      Entry& s = e[base + i];
      if (!s.len || (int32_t)(now - s.expiry) >= 0) return &s;
    }
    return (int32_t)(e[base].expiry - e[base + 1].expiry) <= 0 ? &e[base] : &e[base + 1];
  }
};
