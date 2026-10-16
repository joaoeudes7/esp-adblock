#pragma once
#include <stdint.h>
// Upstream resolver choice. Lowest probe RTT wins, but a switch needs to beat the
// current server by DNS_SWITCH_MARGIN_MS: otherwise a couple of ms of jitter would
// flip the forwarder every minute (and reset its RTT window for nothing).
// 0 = not measured yet, DNS_DEAD = probe failed. Pure C++ so it can be unit-tested
// on the host (tools/test_dns_pick.cpp) without an Arduino toolchain.
static const uint16_t DNS_DEAD = 0xFFFF;
static const uint16_t DNS_SWITCH_MARGIN_MS = 15;

inline int pickDns(const uint16_t* ms, int n, int cur) {
  int best = -1;
  for (int i = 0; i < n; i++)
    if (ms[i] && ms[i] != DNS_DEAD && (best < 0 || ms[i] < ms[best])) best = i;
  if (best < 0) return cur; // nothing answered: stay put
  if (cur < 0 || cur >= n) return best;
  if (ms[cur] == DNS_DEAD) return best; // current failed -> switch now
  if (best != cur && ms[best] + DNS_SWITCH_MARGIN_MS < ms[cur]) return best;
  return cur;
}
