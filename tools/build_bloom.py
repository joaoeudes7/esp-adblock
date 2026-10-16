#!/usr/bin/env python3
"""Preprocess hosts/domain blocklists into a Bloom filter bitmap for the
ESP8266/ESP32 DNS ad-blocker.

Why Bloom: the sorted-hash design spends 40 bits/domain (5-byte hashes). A Bloom
filter spends ~10 bits/domain at <1% false-positive, ~4x more domains in the same
flash. The device derives m from the file size, so the blob grows with the list.

File format (little-endian):
    offset 0 : b'BLM1'                 magic
    offset 4 : uint32 domain_count
    offset 8 : bitmap, ceil(m_bits/8) bytes  (m = bytes*8 bits)

k (BLOOM_K) and the FNV-1a hashing MUST match src/main.cpp.

Usage: build_bloom.py [out.bin] [--bits N] [src ...]
  With no sources given it downloads a curated multi-list set (StevenBlack base +
  Hagezi Pro.plus + OISD Big). Pass your own URLs/files to override.
"""
import re
import sys, os, math, urllib.request

BLOOM_K = 7            # hash functions -- must match firmware
BITS_PER = 10          # m/n  -> ~0.8% false positive at k=7
HASH_BYTES = 5         # retained only for the (unused) compatibility note
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME  = 0x100000001b3
U64 = (1 << 64) - 1

# Default = a union of well-regarded, curated lists (ads + trackers + malware +
# OEM/telemetry). They overlap a lot, so the union is not much bigger than the
# largest list, and the Bloom filter keeps it compact in flash.
DEFAULT_SOURCES = [
    # StevenBlack base: ads + malware
    'https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts',
    # Hagezi Pro.plus: ads + trackers + native (OEM) — comprehensive but curated
    'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.plus-onlydomains.txt',
    # OISD Big: large, curated, "block, don't break"
    'https://big.oisd.nl/domainswild',
    # Hagezi DoH/DoT bypass: block known encrypted-DNS endpoints so clients that try to
    # bypass this resolver (Chrome "secure DNS", Android Private DNS) fall back to it.
    'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/doh-onlydomains.txt',
    'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/doh-vpn-proxy-bypass-onlydomains.txt',
    # Turtlecute d3host: popular ads/trackers/analytics/social/OEM (129 host entries).
    'https://adblock.turtlecute.org/d3host.txt',
    # Hagezi TIF.mini (Threat Intel Feed, small variant): malware / phishing / botnet / scam.
    # Domain-only and curated — adds the security axis the ad lists don't cover.
    # (The full `tif` list is ~1.5M domains; too big for the ESP8266 4m2m 2MB FS.)
    'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/tif.mini-onlydomains.txt',
]

ADG = re.compile(r'^(@@)?\|\|([a-z0-9._-]+)\^?(\$.*)?$', re.I)

ALLOW_MISSING = False

def fnv64(b: bytes) -> int:
    h = FNV_OFFSET
    for c in b:
        h = ((h ^ c) * FNV_PRIME) & U64
    return h

def norm(d: str) -> str:
    d = d.strip().lower().lstrip('*').lstrip('.').rstrip('.')
    return d[4:] if d.startswith('www.') else d

def read_source(src: str) -> str:
    if os.path.exists(src):
        return open(src, errors='ignore').read()
    print(f'  downloading {src} ...', file=sys.stderr)
    return urllib.request.urlopen(src, timeout=180).read().decode('utf-8', 'ignore')

def main():
    global ALLOW_MISSING
    raw = [a for a in sys.argv[1:] if a != '--allow-missing']
    ALLOW_MISSING = '--allow-missing' in sys.argv[1:]
    bits_per = BITS_PER
    if '--bits' in raw:
        i = raw.index('--bits'); bits_per = int(raw[i + 1]); del raw[i:i + 2]
    out = raw[0] if raw else 'blocklist.bin'
    sources = raw[1:] if len(raw) > 1 else DEFAULT_SOURCES

    domains, allow = set(), set()
    skipped = 0
    for src in sources:
        try:
            data = read_source(src)
        except Exception as e:
            print(f'  !! FAILED to read {src}: {e}', file=sys.stderr)
            if not ALLOW_MISSING: sys.exit(1)
            continue
        for line in data.splitlines():
            line = line.split('#', 1)[0].strip() if not line.lstrip().startswith(('||', '@@')) else line.strip()
            if not line or line[0] in '!/[':
                continue
            m = ADG.match(line)
            if m:
                if m.group(3):
                    skipped += 1; continue
                (allow if m.group(1) else domains).add(norm(m.group(2)))
                continue
            if line.startswith(('||', '@@', '|')) or any(c in line for c in '^$*'):
                skipped += 1; continue
            parts = line.split()
            if parts[0] in ('0.0.0.0', '127.0.0.1', '::1', '::'):
                entries = parts[1:]
            else:
                entries = parts if len(parts) == 1 else []
            for d in entries:
                d = norm(d)
                if '.' in d and ' ' not in d:
                    domains.add(d)
    if allow:
        before = len(domains); domains -= allow
        print(f'allowlisted      : {before - len(domains):,} removed ({len(allow):,} @@ rules)', file=sys.stderr)

    # Drop any domain that is a subdomain of another entry: the query walks label
    # suffixes, so "a.com" already blocks "x.a.com". Removing the redundant subdomains
    # shrinks n (and thus the bitmap) with ZERO change in behaviour or false-positive rate.
    def has_parent(d):
        parts = d.split('.')
        for i in range(1, len(parts) - 1):        # parent keeps >= 2 labels
            if '.'.join(parts[i:]) in domains:
                return True
        return False
    before = len(domains)
    domains = {d for d in domains if not has_parent(d)}
    if before != len(domains):
        print(f'subdomain prune  : {before - len(domains):,} removed (covered by a parent rule)', file=sys.stderr)
    if skipped:
        print(f'skipped rules    : {skipped:,} (adblock syntax a DNS list cannot express)', file=sys.stderr)

    n = len(domains)
    m_bytes = max(1, (n * bits_per + 7) // 8)
    m = m_bytes * 8                       # firmware derives m the same way: size*8
    bits = bytearray(m_bytes)
    for d in domains:
        h = fnv64(d.encode())
        a = (h >> 32) & 0xFFFFFFFF
        b = h & 0xFFFFFFFF
        for i in range(BLOOM_K):
            bit = ((a + i * b) & 0xFFFFFFFF) % m
            bits[bit >> 3] |= 1 << (bit & 7)
    with open(out, 'wb') as f:
        f.write(b'BLM1' + n.to_bytes(4, 'little') + bytes(bits))

    fp = (1 - math.exp(-BLOOM_K * n / m)) ** BLOOM_K if n and m else 0.0
    size = 8 + m_bytes
    print(f'source domains   : {n:,}')
    print(f'bloom bitmap     : {m:,} bits / {m_bytes:,} bytes  (k={BLOOM_K}, ~{bits_per} bits/domain)')
    print(f'false positive   : {fp*100:.2f}%')
    print(f'flash blob       : {size:,} bytes  ({size/1024/1024:.2f} MB)  -> {out}')

if __name__ == '__main__':
    main()
