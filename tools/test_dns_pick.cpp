// Host-side check for src/dns_pick.h:  c++ -std=c++11 tools/test_dns_pick.cpp -o /tmp/t && /tmp/t
#include "../src/dns_pick.h"
#include <cassert>
#include <cstdio>

int main() {
  uint16_t a[] = {40, 12, 30};
  assert(pickDns(a, 3, 0) == 1);            // clearly faster server wins

  uint16_t b[] = {20, 30, 0};
  assert(pickDns(b, 3, 0) == 0);            // 10 ms better < margin: no flap

  uint16_t c[] = {30, 20, 0};
  assert(pickDns(c, 3, 0) == 0);            // 10 ms better, current still fine

  uint16_t d[] = {36, 20, 0};
  assert(pickDns(d, 3, 0) == 1);            // 16 ms better > margin: switch (35 < 36)

  uint16_t e[] = {DNS_DEAD, 30, 50};
  assert(pickDns(e, 3, 0) == 1);            // dead current -> fastest alive, no wait

  uint16_t f[] = {0, 0, 0};
  assert(pickDns(f, 3, 2) == 2);            // no measurements -> stay

  uint16_t g[] = {DNS_DEAD, DNS_DEAD};
  assert(pickDns(g, 2, 0) == 0);            // all dead -> stay, keep trying current

  uint16_t h[] = {50, DNS_DEAD, 60};
  assert(pickDns(h, 3, 1) == 0);            // dead current, current index 1

  printf("dns_pick: all checks passed\n");
  return 0;
}
