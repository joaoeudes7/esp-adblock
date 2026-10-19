#!/usr/bin/env python3
"""Self-check for build_bin_list_block.py: BLM1 header + Bloom membership round-trip."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build_bin_list_block.py")
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
            r = subprocess.run([sys.executable, BUILD, out, src, "--no-gafam"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(out, "rb").read()
            self.assertEqual(data[:4], b"BLM1")
            n = struct.unpack("<I", data[4:8])[0]
            self.assertEqual(n, 3)                      # ads, tracker, bad (ok is allowlisted)
            bm, m = data[8:], (len(data) - 8) * 8
            for dom in ("ads.example.com", "tracker.example.net", "bad.example.org"):
                self.assertTrue(member(bm, m, dom), dom)
            self.assertFalse(member(bm, m, "definitely-not-in-the-list.example"))


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bb", BUILD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestValidation(unittest.TestCase):
    def test_valid_host(self):
        m = _load()
        for d in ("ads.example.com", "a.b.co.uk", "sub.domain-x.io", "xn--80ak6aa92e.com"):
            self.assertTrue(m.valid_host(d), d)
        for d in ("/js/x.js", "0.0.0.0", "127.0.0.1", "::1", "localhost", "com",
                  "a..b.com", "-bad.com", "bad-.com", "exa mple.com", "a.com/x",
                  "foo_bar.com", "1.2.3.4", "a" * 64 + ".com"):
            self.assertFalse(m.valid_host(d), d)

    def test_junk_not_in_bin(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "s.txt"), os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("site.com##.banner\n"                           # cosmetic -> host NOT added
                    "/wp-content/x/*\n"                             # url path (not ||) -> dropped
                    "||slot.example.com^$third-party\n"             # $ modifier -> skipped
                    "||connect.facebook.net/signals/$third-party\n"  # path + $ -> skipped
                    "||scoped.example.net^$domain=a.com\n"          # page-scoped -> skipped
                    "||real.example.com^\n"                         # the only accepted entry
                    "bad--host-.com\n")                             # malformed -> rejected
            r = subprocess.run([sys.executable, BUILD, out, src], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            n = struct.unpack("<I", open(out, "rb").read(8)[4:8])[0]
            # Only "||host^" is accepted: any / * ? $ | rule is dropped, so nothing a path-scoped
            # rule targets (connect.facebook.net/signals) can ever slip in as a whole host.
            self.assertEqual(n, 1)               # real.example.com

    def test_wildcard_host_rule_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "s.txt"), os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("||ads*.example.com^\nseed.example.net\n")
            r = subprocess.run([sys.executable, BUILD, out, src, "--no-gafam"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(out, "rb").read()
            self.assertEqual(data[:4], b"BLM1")                      # no regex produced
            n = struct.unpack("<I", data[4:8])[0]
            self.assertEqual(n, 1)                                   # only seed.example.net


class TestBlm2Regex(unittest.TestCase):
    """BLM2 header + RGX1 section — the layout src/main.cpp loadRegexSection() parses:
    'BLM2' | u32 n | u32 bitmap_bytes | bitmap | 'RGX1' | u16 count | (u16 len + pattern)*.
    Without a test that actually emits a regex, a framing regression ships green."""

    PATTERN = b"^ads[0-9]+\\.example\\.net$"

    def test_blm2_layout_and_regex_section(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.txt")
            pats = os.path.join(d, "r.txt")
            out = os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("||host.example.com^\n")
            with open(pats, "w", encoding="utf-8") as f:
                f.write("# comment line\n" + self.PATTERN.decode() + "\n")
            r = subprocess.run([sys.executable, BUILD, out, src, "--regex", pats, "--no-gafam"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(out, "rb").read()
            self.assertEqual(data[:4], b"BLM2")
            n, bitmap_bytes = struct.unpack("<II", data[4:12])
            self.assertEqual(n, 1)
            # bitmap starts at 12 (NOT 8): the firmware's bloomBase must match
            self.assertEqual(bitmap_bytes, len(data) - 12 - (6 + 2 + len(self.PATTERN)))
            bm = data[12:12 + bitmap_bytes]
            self.assertTrue(member(bm, bitmap_bytes * 8, "host.example.com"))
            off = 12 + bitmap_bytes
            self.assertEqual(data[off:off + 4], b"RGX1")
            self.assertEqual(struct.unpack("<H", data[off + 4:off + 6])[0], 1)
            ln = struct.unpack("<H", data[off + 6:off + 8])[0]
            self.assertEqual(data[off + 8:off + 8 + ln], self.PATTERN)
            self.assertEqual(off + 8 + ln, len(data))          # no trailing bytes

    def test_membership_golden_vector(self):
        """Pin the exact hash and bit indices: a change to the hash, k, or the bit formula
        breaks this even if the builder and the test helper change together."""
        h = fnv64(b"ads.example.com")
        self.assertEqual(h, 0xC0933158979AA55E)
        a, b = (h >> 32) & 0xFFFFFFFF, h & 0xFFFFFFFF
        bits = sorted({((a + i * b) & 0xFFFFFFFF) % 1024 for i in range(K)})
        self.assertEqual(bits, [20, 46, 344, 370, 396, 694, 720])


class TestGafmDefault(unittest.TestCase):
    """Default build (no --no-gafam) appends GAFM after RGX1, which forces BLM2 even with
    zero regexes. Pin the framing src/main.cpp loadRegexSection()/loadGafamSection() read."""

    def test_default_layout_has_gafm(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.txt")
            out = os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("seed.example.net\n")
            r = subprocess.run([sys.executable, BUILD, out, src], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(out, "rb").read()
            self.assertEqual(data[:4], b"BLM2")
            n, bitmap_bytes = struct.unpack("<II", data[4:12])
            self.assertEqual(n, 1)
            off = 12 + bitmap_bytes
            self.assertEqual(data[off:off + 4], b"RGX1")
            self.assertEqual(struct.unpack("<H", data[off + 4:off + 6])[0], 0)  # no regex
            off += 6
            self.assertEqual(data[off:off + 4], b"GAFM")
            off += 4
            for _ in range(5):                       # 5 provider blooms: u16 len + bitmap
                ln = struct.unpack("<H", data[off:off + 2])[0]
                self.assertGreater(ln, 0)
                off += 2 + ln
            self.assertEqual(off, len(data))         # no trailing bytes

    def test_reported_size_matches_file(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.txt")
            out = os.path.join(d, "b.bin")
            with open(src, "w", encoding="utf-8") as f:
                f.write("seed.example.net\n")
            r = subprocess.run([sys.executable, BUILD, out, src], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            m = __import__("re").search(r"flash blob\s*:\s*([\d,]+) bytes", r.stdout)
            self.assertIsNotNone(m, r.stdout)
            self.assertEqual(int(m.group(1).replace(",", "")), os.path.getsize(out))


if __name__ == "__main__":
    unittest.main()
