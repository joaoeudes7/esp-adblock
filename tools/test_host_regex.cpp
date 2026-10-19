// Host-side check for src/host_regex.h:
//   c++ -std=c++11 tools/test_host_regex.cpp -o /tmp/thr && /tmp/thr
#include "../src/host_regex.h"
#include <cassert>
#include <cstdio>

static bool m(const char* p, const char* h) { return hostReMatch(p, h); }

int main() {
  assert(m("ads", "ads.example.com"));                 // unanchored search
  assert(!m("ads", "example.com"));
  assert(m("doubleclick", "ad.doubleclick.net"));
  assert(m("\\.doubleclick\\.net", "ad.doubleclick.net"));
  assert(m("^ads\\.example\\.com$", "ads.example.com"));      // anchors
  assert(!m("^ads\\.example\\.com$", "x.ads.example.com"));
  assert(m("connect\\.facebook\\.net$", "connect.facebook.net"));
  assert(!m("connect\\.facebook\\.net$", "connect.facebook.net.evil.com"));
  assert(m("doubleclick|googleads|adnxs", "x.adnxs.com"));     // alternation
  assert(!m("doubleclick|googleads", "example.com"));
  assert(m("^ad[0-9]+\\.[a-z]+\\.com$", "ad12.example.com"));  // class + ranges
  assert(!m("^ad[0-9]+\\.[a-z]+\\.com$", "adx.example.com"));
  assert(m("tracker[^s]", "trackerx.example.com"));            // negated class
  assert(!m("tracker[^s]", "trackers.example.com"));
  assert(m(".*\\.facebook\\.com", "graph.facebook.com"));      // '.*'
  assert(m("AD\\.example", "ad.example.com"));                 // case-insensitive
  assert(m("imasdk\\.googleapis\\.com", "imasdk.googleapis.com"));
  assert(!m("^imasdk\\.googleapis\\.com$", "imasdk.googleapis.com.evil.net")); // '$' for precision
  assert(m("x?y", "y") && m("x?y", "xy"));                     // optional
  assert(m("xo+", "xoo") && !m("xo+", "x"));                   // one-or-more
  printf("host_regex: all checks passed\n");
  return 0;
}
