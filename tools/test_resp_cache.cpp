// Host-side check for src/resp_cache.h:
//   c++ -std=c++11 tools/test_resp_cache.cpp -o /tmp/trc && /tmp/trc
#include "../src/resp_cache.h"
#include <cassert>
#include <cstdio>

int main() {
  RespCache<8, 64> c;   // N=8 -> 4 sets of 2

  c.clear();
  assert(!c.find(0, 0));                                    // empty -> miss
  RespCache<8, 64>::Entry* s = c.insert(0, 0);
  s->key = 0; s->expiry = 1000; s->len = 3; s->data[0] = 7;
  assert(c.find(0, 500) && c.find(0, 500)->data[0] == 7);  // fresh hit
  assert(!c.find(0, 1000));                                 // expired at exactly TTL
  assert(!c.find(99, 500));                                 // unknown key

  // 2-way: two keys colliding on the same set both survive (the whole point).
  c.clear();
  RespCache<8, 64>::Entry* a = c.insert(4, 0); a->key = 4; a->expiry = 1000; a->len = 1;  // set 0
  RespCache<8, 64>::Entry* b = c.insert(8, 0); b->key = 8; b->expiry = 1000; b->len = 1;  // set 0
  assert(c.find(4, 10) && c.find(8, 10));

  // A third key in the now-full set evicts exactly one (keeps two live).
  RespCache<8, 64>::Entry* d = c.insert(12, 0); d->key = 12; d->expiry = 1000; d->len = 1;  // set 0
  assert(c.find(12, 10));
  assert((c.find(4, 10) != 0) + (c.find(8, 10) != 0) == 1);

  // Different sets don't interfere.
  c.clear();
  RespCache<8, 64>::Entry* e0 = c.insert(0, 0); e0->key = 0; e0->expiry = 1000; e0->len = 1;
  RespCache<8, 64>::Entry* e1 = c.insert(4, 0); e1->key = 4; e1->expiry = 1000; e1->len = 1;  // set 0 full
  RespCache<8, 64>::Entry* e2 = c.insert(5, 0); e2->key = 5; e2->expiry = 1000; e2->len = 1;  // set 1
  assert(c.find(0, 10) && c.find(4, 10) && c.find(5, 10));

  // A stale slot is reused before a live one.
  c.clear();
  RespCache<8, 64>::Entry* f = c.insert(0, 0); f->key = 0; f->expiry = 10; f->len = 1;       // set 0, expires
  RespCache<8, 64>::Entry* g = c.insert(4, 0); g->key = 4; g->expiry = 100000; g->len = 1;   // set 0, live long
  RespCache<8, 64>::Entry* h = c.insert(8, 100); h->key = 8; h->expiry = 200000; h->len = 1; // stale slot reused
  assert(c.find(8, 150) && c.find(4, 150) && !c.find(0, 150));

  printf("resp_cache: all checks passed\n");
  return 0;
}
