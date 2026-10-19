#!/usr/bin/env python3
"""Preprocess hosts/domain blocklists into a Bloom filter bitmap for the
ESP8266/ESP32 DNS ad-blocker.

Why Bloom: the sorted-hash design spends 40 bits/domain (5-byte hashes). A Bloom
filter spends ~10 bits/domain at <1% false-positive, ~4x more domains in the same
flash. The device derives m from the file size, so the blob grows with the list.

File format (little-endian):
  BLM1 (bloom only):
    offset 0 : b'BLM1'                 magic
    offset 4 : uint32 domain_count
    offset 8 : bitmap, ceil(m_bits/8) bytes  (m = bytes*8 bits)
  BLM2 (bloom + hostname regexes) — used only when at least one regex is collected:
    offset 0  : b'BLM2'
    offset 4  : uint32 domain_count
    offset 8  : uint32 bitmap_bytes
    offset 12 : bitmap
    then      : b'RGX1' + uint16 count + (uint16 len + pattern_bytes)*

k (BLOOM_K) and the FNV-1a hashing MUST match src/main.cpp.

Usage: build_bin_list_block.py [out.bin] [--bits N] [src ...]
  With no sources given it downloads a curated multi-list set (StevenBlack base +
  Hagezi Ultimate + OISD Big). Pass your own URLs/files to override.
"""
import re
import sys, os, math, urllib.request

BLOOM_K = 7            # hash functions -- must match firmware
BITS_PER = 12          # m/n  -> ~0.33% false positive at k=7 (10 -> ~0.82%)
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
    # Hagezi Ultimate: the most aggressive curated tier (ads + trackers + native/OEM + more).
    # Unlike "social"-oriented lists it does NOT block platform roots (facebook.com / tiktok.com
    # / instagram.com / …) — only their ad & telemetry subdomains — so social apps keep working.
    'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/ultimate-onlydomains.txt',
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
    # AdGuard "Annoyances: Mobile App": mostly cosmetic (##/#$#/#%#) — which never affect
    # DNS and are dropped — so it adds only a handful of hostnames. Kept for completeness.
    'https://raw.githubusercontent.com/AdguardTeam/FiltersRegistry/master/filters/filter_20_Annoyances_MobileApp/filter.txt',
    # EasyList / EasyPrivacy: URL filters, but their `||host^` rules yield ~50k / ~43k
    # blockable domains. Tuned for URL filtering, so a few over-block at DNS level.
    'https://easylist.to/easylist/easylist.txt',
    'https://easylist.to/easylist/easyprivacy.txt',
    # hBlock — a DNS-oriented hosts aggregator (~481k domains). Heavily overlaps
    # OISD/Hagezi; subdomain pruning + the dedup set absorb the overlap.
    'https://hblock.molinero.dev/hosts',
]

# GAFAM (Google/Apple/Facebook(Meta)/Amazon/Microsoft) suffix sets. The builder compiles one
# small Bloom per provider into the bin's GAFM section; the firmware loads them into RAM and
# classifies ALLOWED lookups by suffix walk (so mail.google.com counts for Google). This is
# read-only telemetry ("share of DNS lookups"), not blocking.
GAFAM = [
    ['google.com', 'googleapis.com', 'gstatic.com', 'googlevideo.com', 'youtube.com', 'ggpht.com',
     'googleusercontent.com', 'gvt1.com', 'gmail.com', 'googlemail.com'],
    ['apple.com', 'icloud.com', 'mzstatic.com', 'cdn-apple.com', 'aaplimg.com', 'apple-dns.net', 'itunes.com'],
    ['facebook.com', 'fbcdn.net', 'instagram.com', 'cdninstagram.com', 'whatsapp.net', 'whatsapp.com',
     'messenger.com', 'fb.com'],
    ['amazon.com', 'amazonaws.com', 'cloudfront.net', 'media-amazon.com', 'ssl-images-amazon.com'],
    ['microsoft.com', 'windows.net', 'live.com', 'office.com', 'msftconnecttest.com', 'azureedge.net',
     'bing.com', 'msn.com', 'xboxlive.com', 'microsoftonline.com'],
]


def make_bloom(items, bits_per):
    n = len(items)
    mb = max(1, (n * bits_per + 7) // 8)
    m = mb * 8
    bm = bytearray(mb)
    for d in items:
        h = fnv64(d.encode())
        a, b = (h >> 32) & 0xFFFFFFFF, h & 0xFFFFFFFF
        for i in range(BLOOM_K):
            bit = ((a + i * b) & 0xFFFFFFFF) % m
            bm[bit >> 3] |= 1 << (bit & 7)
    return bytes(bm)


ADG = re.compile(r'^(@@)?\|\|([a-z0-9._-]+)\^?(\$.*)?$', re.I)

ALLOW_MISSING = False
NO_GAFAM = False        # --no-gafam: don't emit the GAFM (provider share) section
MAX_SRC_BYTES = 64 * 1024 * 1024   # a list source bigger than this is not a list

def fnv64(b: bytes) -> int:
    h = FNV_OFFSET
    for c in b:
        h = ((h ^ c) * FNV_PRIME) & U64
    return h

def norm(d: str) -> str:
    d = d.strip().lower().lstrip('*').lstrip('.').rstrip('.')
    return d[4:] if d.startswith('www.') else d

def parents(d: str) -> list:
    """Label suffixes that are still hostnames (>=2 labels) — what the device's suffix walk
    matches for `d` in addition to `d` itself."""
    parts = d.split('.')
    return ['.'.join(parts[i:]) for i in range(1, len(parts) - 1)]

# Only a real hostname may enter the bloom: one-or-more '.'-separated labels of
# [a-z0-9-] (no leading/trailing '-'), each 1..63 chars, whole name <=253. Rejects
# URL paths, IPs, catch-all sentinels, cosmetic leftovers and other DNS-unsupported junk.
_HOSTLABEL = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')
_IPV4 = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')
_SENTINEL = {'localhost', 'localhost.localdomain', 'local', 'broadcasthost', 'ip6-localhost',
             'ip6-loopback', 'ip6-localnet', 'ip6-mcastprefix', 'ip6-allnodes', 'ip6-allrouters', 'ip6-allhosts'}


def valid_host(d: str) -> bool:
    if not (1 <= len(d) <= 253) or '.' not in d:
        return False
    if _IPV4.match(d) or d in _SENTINEL:
        return False
    return all(_HOSTLABEL.match(l) for l in d.split('.'))

def read_source(src: str) -> str:
    if os.path.exists(src):
        return open(src, errors='ignore').read()
    print(f'  downloading {src} ...', file=sys.stderr)
    # Some list hosts (easylist.to, hblock) 403 a bare urllib UA.
    req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 (esp-adblock build_bin_list_block)'})
    last = None
    for attempt in (1, 2):                          # one retry: transient DNS/EOF/5xx
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                ctype = (r.headers.get('Content-Type') or '').lower()
                if r.status != 200 or 'html' in ctype:
                    raise ValueError(f'HTTP {r.status} {ctype!r} — not a list')
                body = r.read(MAX_SRC_BYTES + 1)
                if len(body) > MAX_SRC_BYTES:
                    raise ValueError(f'larger than {MAX_SRC_BYTES} bytes')
                return body.decode('utf-8', 'ignore')
        except Exception as e:
            last = e
    raise last

def main():
    global ALLOW_MISSING, NO_GAFAM
    raw = [a for a in sys.argv[1:] if a not in ('--allow-missing', '--no-gafam')]
    ALLOW_MISSING = '--allow-missing' in sys.argv[1:]
    NO_GAFAM = '--no-gafam' in sys.argv[1:]
    bits_per = BITS_PER
    if '--bits' in raw:
        i = raw.index('--bits')
        if i + 1 >= len(raw):
            sys.exit('build_bin_list_block: --bits needs a value')
        try:
            bits_per = int(raw[i + 1])
        except ValueError:
            sys.exit('build_bin_list_block: --bits value must be an integer')
        if not (1 <= bits_per <= 64):
            sys.exit('build_bin_list_block: --bits must be 1..64')
        del raw[i:i + 2]
    regex_files = []
    while '--regex' in raw:                 # extra hostname-regex sources (one pattern/line)
        i = raw.index('--regex')
        if i + 1 >= len(raw):
            sys.exit('build_bin_list_block: --regex needs a file')
        regex_files.append(raw[i + 1])
        del raw[i:i + 2]
    out = raw[0] if raw else 'blocklist.bin'
    sources = raw[1:] if len(raw) > 1 else DEFAULT_SOURCES

    domains, allow, regexes = set(), set(), set()
    skipped = 0
    bad = 0
    for src in sources:
        try:
            data = read_source(src)
        except Exception as e:
            print(f'  !! FAILED to read {src}: {e}', file=sys.stderr)
            if not ALLOW_MISSING: sys.exit(1)
            continue
        for line in data.splitlines():
            s = line.strip()
            if not s or s[0] in '![':
                continue
            # Cosmetic / scriptlet rules (##, #@#, #?#, #$#, #%#) never affect DNS, and the host
            # before the marker must NOT be taken as a domain (that would block a whole site).
            if any(x in s for x in ('##', '#@#', '#?#', '#$#', '#%#', '#@$#')):
                skipped += 1
                continue
            if ' #' in s:                   # inline hosts-style comment ("0.0.0.0 ads # note")
                s = s.split(' #', 1)[0].strip()
                if not s:
                    continue
            if s.startswith('/') and s.endswith('/') and len(s) > 2:   # AdGuard /regex/
                pat = s[1:-1]
                if '/' not in pat and ':' not in pat:                  # hostname-plausible only
                    regexes.add(pat)
                else:
                    skipped += 1
                continue
            m = ADG.match(s)
            if m and m.group(1):            # @@ exception: only the strict "||host^" form un-blocks
                if m.group(3):              # ...$mods (e.g. $domain=) -> too broad to allow globally
                    skipped += 1
                    continue
                d = norm(m.group(2))
                if valid_host(d):
                    allow.add(d)
                else:
                    bad += 1
                continue
            if s.startswith('||'):          # accept ONLY a bare host: "||host^"
                body = s[2:]
                # A path (/), wildcard (* ?), modifier ($) or alternation (|) means the rule is
                # scoped finer than DNS can honour -> generalizing to the host would over-block
                # (e.g. ||connect.facebook.net/signals/$third-party must NOT block the host).
                if any(c in body for c in '/*?$|'):
                    skipped += 1
                    continue
                host = body[:-1] if body.endswith('^') else body
                d = norm(host)
                if valid_host(d):
                    domains.add(d)
                elif d:
                    bad += 1
                continue
            if s.startswith(('@@', '|')) or any(c in s for c in '^$*'):
                skipped += 1
                continue
            parts = s.split()
            if parts[0] in ('0.0.0.0', '127.0.0.1', '::1', '::'):
                entries = parts[1:]
            else:
                entries = parts if len(parts) == 1 else []
            for d in entries:
                d = norm(d)
                if valid_host(d):
                    domains.add(d)
                elif d:
                    bad += 1
    for rf in regex_files:                  # extra hostname-regex patterns the user supplied
        try:
            data = read_source(rf)
        except Exception as e:
            print(f'  !! FAILED to read {rf}: {e}', file=sys.stderr)
            if not ALLOW_MISSING: sys.exit(1)
            continue
        for line in data.splitlines():
            p = line.strip()
            if p and p[0] != '#' and len(p) <= 254:
                regexes.add(p)

    if allow:
        before = len(domains)
        # A @@ allow covers its subdomains too, so drop any kept domain that is at or under it.
        domains = {d for d in domains if not any(s in allow for s in [d] + parents(d))}
        print(f'allowlisted      : {before - len(domains):,} removed ({len(allow):,} @@ rules)', file=sys.stderr)
        # A bloom cannot express an exception: if a parent of an @@ rule is still blocking,
        # the device's suffix walk re-blocks it and the @@ never takes effect. Say so.
        shadowed = [a for a in allow if any(s in domains for s in parents(a))]
        if shadowed:
            print(f'  !! {len(shadowed):,} @@ rules are shadowed by a blocking parent and will NOT take effect at runtime', file=sys.stderr)

    # Drop any domain that is a subdomain of another entry: the query walks label
    # suffixes, so "a.com" already blocks "x.a.com". Removing the redundant subdomains
    # shrinks n (and thus the bitmap) with ZERO change in behaviour or false-positive rate.
    def has_parent(d):
        return any(s in domains for s in parents(d))
    before = len(domains)
    domains = {d for d in domains if not has_parent(d)}
    if before != len(domains):
        print(f'subdomain prune  : {before - len(domains):,} removed (covered by a parent rule)', file=sys.stderr)
    if skipped:
        print(f'skipped rules    : {skipped:,} (adblock syntax a DNS list cannot express)', file=sys.stderr)
    if bad:
        print(f'rejected entries : {bad:,} (not a valid hostname)', file=sys.stderr)

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
    rx = sorted(regexes)
    # The firmware keeps a bounded number of patterns, each bounded in length (ESP8266:
    # 16 x 96 B; ESP32: 64 x 128 B — src/main.cpp MAX_RGX/RGX_MAXLEN). Records past those
    # limits are written here but ignored on the device, so say it instead of shipping a blob
    # whose effective contents differ per target.
    n_long = sum(1 for p in rx if len(p.encode()) >= 96)
    if len(rx) > 16 or n_long:
        print(f'  !! regex limits: {len(rx)} patterns, {n_long} of them >=96 B — the ESP8266 keeps '
              f'only the first 16 of <=96 B (ESP32: 64 x 128)', file=sys.stderr)
    gafam_blobs = [] if NO_GAFAM else [make_bloom(s, max(8, bits_per)) for s in GAFAM]
    blob = bytearray()
    if rx or gafam_blobs:
        # BLM2: explicit bitmap size so extra sections can follow it.
        #   'BLM2' | u32 n | u32 bitmap_bytes | bitmap
        #          | 'RGX1' | u16 count | (u16 len + pat)*          (hostname regexes; count may be 0)
        #          | 'GAFM' | 5 x (u16 bytes + bitmap)              (G/A/F/Amazon/Microsoft blooms)
        blob += b'BLM2' + n.to_bytes(4, 'little') + m_bytes.to_bytes(4, 'little') + bytes(bits)
        blob += b'RGX1' + len(rx).to_bytes(2, 'little')
        for p in rx:
            b = p.encode()
            blob += len(b).to_bytes(2, 'little') + b
        if gafam_blobs:
            blob += b'GAFM'
            for gb in gafam_blobs:
                blob += len(gb).to_bytes(2, 'little') + gb
    else:
        blob += b'BLM1' + n.to_bytes(4, 'little') + bytes(bits)
    tmp = out + '.tmp'
    with open(tmp, 'wb') as f:   # atomic: an interrupted run must not leave a short blob in place
        f.write(blob)
    os.replace(tmp, out)

    fp = (1 - math.exp(-BLOOM_K * n / m)) ** BLOOM_K if n and m else 0.0
    size = len(blob)  # exact: BLM2 + RGX1 + GAFM included
    print(f'source domains   : {n:,}')
    print(f'bloom bitmap     : {m:,} bits / {m_bytes:,} bytes  (k={BLOOM_K}, ~{bits_per} bits/domain)')
    print(f'hostname regexes : {len(rx):,}  (format {"BLM2" if (rx or gafam_blobs) else "BLM1"}; gafm={"5 blooms" if gafam_blobs else "off"})')
    print(f'false positive   : {fp*100:.2f}%')
    print(f'flash blob       : {size:,} bytes  ({size/1024/1024:.2f} MB)  -> {out}')

if __name__ == '__main__':
    main()
