#!/usr/bin/env python3
"""Self-check for build_bloom.py: BLM1 header + Bloom membership round-trip."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build_bloom.py")
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME = 0x100000001b3
U64 = (1 << 64) - 1
K = 7


def fnv64(b):
    h = FNV_OFFSET
    for c in b:
        h = ((h ^ c) * FNV_PRIME) & U64
    return h


def member(bm, m, domain):
    h = fnv64(domain.lower().encode())
    a, b = (h >> 32) & 0xFFFFFFFF, h & 0xFFFFFFFF
    for i in range(K):
        bit = ((a + i * b) & 0xFFFFFFFF) % m
        if not (bm[bit >> 3] >> (bit & 7)) & 1:
            return False
    return True


class TestBloom(unittest.TestCase):
    def test_format_and_membership(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.txt")
            out = os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("ads.example.com\n"
                        "0.0.0.0 tracker.example.net\n"
                        "||bad.example.org^\n"
                        "@@||ok.example.org^\n")
            r = subprocess.run([sys.executable, BUILD, out, src], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(out, "rb").read()
            self.assertEqual(data[:4], b"BLM1")
            n = struct.unpack("<I", data[4:8])[0]
            self.assertEqual(n, 3)                      # ads, tracker, bad (ok allowlisted, no matching block)
            bm, m = data[8:], (len(data) - 8) * 8
            for dom in ("ads.example.com", "tracker.example.net", "bad.example.org"):
                self.assertTrue(member(bm, m, dom), dom)
            self.assertFalse(member(bm, m, "definitely-not-in-the-list.example"))


if __name__ == "__main__":
    unittest.main()
