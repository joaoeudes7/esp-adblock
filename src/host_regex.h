#pragma once
#include <stdint.h>
// Tiny regex engine for HOSTNAME matching. At DNS we only have the host — no URL/path —
// so path/scheme regex rules from URL filters cannot ever apply and are dropped at build
// time (see tools/build_bin_list_block.py). This subset covers hostname patterns:
//   literals, '.' (any char), '*', '+', '?', '[abc]' / '[^abc]' with ranges 'a-z',
//   '\' escape, '^' start anchor, '$' end anchor, and top-level '|' alternation.
// Case-insensitive. Unanchored SEARCH semantics (like AdGuard /regex/) unless '^'.
// No groups / backreferences (use one pattern per line). Pure C++ -> host-testable
// (tools/test_host_regex.cpp).
static const int HOSTRE_MAXLEN = 160; // longest supported pattern
// Bounded backtracking (ReDoS guard): patterns come from a downloaded blocklist and the
// matcher runs on the single-threaded DNS path. Measured: a legitimate single-'*' pattern
// costs <= ~20k steps on a worst-case 253-char host, while a 4-star backtracker needs >1.4M
// steps at 40 chars (and grows ~len^3) = seconds on a 160 MHz ESP8266 -> watchdog reset.
// 100000 leaves realistic patterns untouched (real hostnames are <= ~60 chars, where even a
// 2-star pattern needs ~30k) and aborts the pathological ones. Exhausting it = NO match: a
// missed block is acceptable, a stalled resolver is not.
static const int HOSTRE_MAX_STEPS = 100000;
static int hr_steps = 0;
static inline bool hr_tick() { return ++hr_steps <= HOSTRE_MAX_STEPS; }

static inline char hr_lc(char c) { return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c; }

// One past the atom starting at re (a single char, an escaped char, a '.', or a class).
static const char* hr_atomEnd(const char* re) {
  if (re[0] == '\\' && re[1]) return re + 2;
  if (re[0] == '[') {
    const char* p = re + 1;
    if (*p == '^') p++;
    if (*p == ']') p++; // a leading ']' is a literal
    while (*p && *p != ']') { if (*p == '\\' && p[1]) p++; p++; }
    return (*p == ']') ? p + 1 : p;
  }
  return re + 1;
}
// Does the single atom [a, aEnd) accept character c?
static bool hr_atom(const char* a, const char* aEnd, char c) {
  if (a[0] == '.') return true;
  if (a[0] == '[') {
    bool neg = (a[1] == '^');
    const char* p = a + (neg ? 2 : 1);
    bool hit = false;
    while (p < aEnd - 1) { // stop before the closing ']'
      if (p[0] == '\\' && p + 1 < aEnd - 1) { if (hr_lc(c) == hr_lc(p[1])) hit = true; p += 2; continue; }
      if (p + 2 < aEnd - 1 && p[1] == '-') { char lo = hr_lc(p[0]), hi = hr_lc(p[2]); if (hr_lc(c) >= lo && hr_lc(c) <= hi) hit = true; p += 3; continue; }
      if (hr_lc(c) == hr_lc(p[0])) hit = true;
      p++;
    }
    return neg ? !hit : hit;
  }
  if (a[0] == '\\') return hr_lc(c) == hr_lc(a[1]);
  return hr_lc(c) == hr_lc(a[0]);
}
// Match at the start of `text` (must consume the whole pattern; `text` may have trailing chars).
static bool hr_here(const char* re, const char* text) {
  if (!hr_tick()) return false;
  for (;;) {
    if (*re == 0) return true;
    if (re[0] == '$' && re[1] == 0) return *text == 0;
    const char* ae = hr_atomEnd(re);
    char q = *ae;
    if (q == '?') {
      if (*text && hr_atom(re, ae, *text) && hr_here(ae + 1, text + 1)) return true;
      re = ae + 1;
      continue; // literal-chain stays iterative (bounded stack)
    }
    if (q == '*' || q == '+') {
      if (q == '+') { if (!(*text && hr_atom(re, ae, *text))) return false; text++; }
      const char* r2 = ae + 1;
      for (;;) { if (hr_here(r2, text)) return true; if (*text && hr_atom(re, ae, *text)) text++; else return false; }
    }
    if (!(*text && hr_atom(re, ae, *text))) return false;
    text++;
    re = ae; // next atom
  }
}
static bool hr_alt(const char* alt, const char* host) {
  const char* p = alt;
  if (*p == '^') return hr_here(p + 1, host); // anchored at the start
  for (const char* s = host;; s++) {          // unanchored search
    if (hr_here(p, s)) return true;
    if (*s == 0) break;
  }
  return false;
}
// True if `pat` matches anywhere in `host` (top-level '|' = alternatives).
static bool hostReMatch(const char* pat, const char* host) {
  hr_steps = 0; // one budget per hostname (see HOSTRE_MAX_STEPS)
  const char* p = pat;
  for (;;) {
    const char* q = p;
    bool inClass = false;
    while (*q) {
      if (*q == '\\' && q[1]) { q += 2; continue; }
      if (*q == '[') inClass = true;
      else if (*q == ']') inClass = false;
      else if (*q == '|' && !inClass) break;
      q++;
    }
    char buf[HOSTRE_MAXLEN + 1];
    int n = 0;
    for (const char* r = p; r < q && n < HOSTRE_MAXLEN; r++) buf[n++] = *r;
    buf[n] = 0;
    if (hr_alt(buf, host)) return true;
    if (*q == 0) break;
    p = q + 1;
  }
  return false;
}
