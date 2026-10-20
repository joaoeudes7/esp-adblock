# docs/AI.md — install / run / configure

Contract for agents (Claude/OpenCode/Cursor/…). Values below are **verbatim** — do not normalize.

DNS sinkhole + dashboard. Serves **DNS UDP :53** (plus a TCP :53 fallback) and **web HTTP :80**. Blocklist = a Bloom
filter bitmap in flash (`BLM1`, `k=7`, FNV-1a 64), optionally followed by a `RGX1` section of **hostname regexes**
(`BLM2`) for patterns a Bloom filter can't express. Targets: **ESP8266** and **ESP32/C3/S3**. The dashboard also
renders an estimated destination map from `geo_table.h` (`/14` → country byte, served as `/world.svg`).

## Install

```bash
# deps: python3 + a CURRENT PlatformIO (`pip install -U platformio` in a venv; the
# distro/apt `platformio` 4.3.4 is too old → AttributeError 'resultcallback'; issue #4).
# `pio` downloads the toolchain on first build; `esptool` ships with PlatformIO.
cp config.env.example config.env          # optional pre-flash: edit WIFI_SSID/WIFI_PASS/WEB_PASS
python3 tools/build_bin_list_block.py data/blocklist.bin  # blocklist; with no sources it DOWNLOADS the
                                          # default lists → needs internet (`--allow-missing` to tolerate a dead source).
                                          # add `--regex FILE` (1 hostname pattern/line) to emit a BLM2 + RGX1 section
esptool --port <PORT> flash-id            # confirm the chip FIRST: ESP8266EX / ESP32-… (don't trust labels)
pio run -e esp8266 -t upload   --upload-port <PORT>   # firmware; pick -e to match the chip:
                                          # esp8266 | esp32dev | c3 | esp32s3  (`-t upload` builds first)
pio run -e esp8266 -t uploadfs --upload-port <PORT>   # filesystem: data/blocklist.bin + data/*.cfg
                                          # (requires the blocklist file built above; erases LittleFS)
pio device monitor                        # 115200 8N1 → note `WiFi up: <ip>`
```
Needs a **≥4 MB flash** board (ESP-01 / 1 MB won't fit the `4m2m` layout). Some boards require
**BOOT/FLASH held** while plugging in, and a **CP210x/CH340** USB-serial driver.
**No PlatformIO?** Use the static browser installer in `installer/` (Web Serial/WebUSB, Chromium
desktop, HTTPS or `localhost`): flash + SHA-256/MD5 verification, then Wi-Fi provisioning over
**Improv Wi-Fi Serial** (or the text `CFG ssid|host|ip|gw|dns …` / `CFG commit` fallback for a
static IP). Build it with `python3 tools/build_installer.py` — see `installer/README.md`.
Build hooks (`extra_scripts`) run automatically: `tools/gen_config.py` (`config.env` →
`src/secrets.h` + `data/wifi.cfg`/`block.cfg`) and `tools/build_web.py`
(`web/*.html` + `web/world.svg` → `src/page.h`). With no `config.env`, `gen_config` seeds from `config.env.example`.

## Run (verify)

```bash
# reach the device
ping esp-adblock.local                 # or: dns-sd -G v4 esp-adblock.local  /  getent hosts esp-adblock.local
curl -s -u "$WEB_USER:$WEB_PASS" http://esp-adblock.local/stats.json | python3 -c "import sys,json;print(json.load(sys.stdin)['ip'])"   # /stats.json needs Basic auth
dig @<ip> doubleclick.net              # -> <esp-ip>   (blocked)
dig @<ip> github.com                   # -> real IP    (forwarded)
curl -H 'Host: doubleclick.net' http://<ip>/     # -> block-page HTML
```
Find the device if mDNS is unavailable: fixed `WIFI_IP`; serial `WiFi up: <ip>` @115200 8N1;
router DHCP entry (`WIFI_HOST`, default `esp-adblock`); or scan TCP:80 for `/stats.json` with `"domains"`.

## Update

Firmware, filesystem, blocklist and baked config each have a **separate** path. Everything mutating
needs **Basic auth** (`WEB_USER:WEB_PASS`) **and** the header `X-Requested-With: esp-adblock`.

### Credentials from `config.env`
Read them without sourcing the file (they are baked into `src/secrets.h` at build time):

```sh
get(){ grep -E "^$1=" config.env | head -1 | cut -d= -f2-; }
U=$(get WEB_USER); P=$(get WEB_PASS); H='X-Requested-With: esp-adblock'
IP=$(curl -s -u "$U:$P" http://esp-adblock.local/stats.json \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['ip'])")
```

No `config.env`? The build seeds from `config.env.example` (`admin` / its `WEB_PASS`).

### Already installed — OTA, no USB

```sh
# firmware (reboots; ~25 s until it answers again)
curl -u "$U:$P" -H "$H" -F "f=@.pio/build/esp8266/firmware.bin" http://$IP/update   # -> ok, rebooting
# blocklist (validated as BLM1/BLM2)
curl -u "$U:$P" -H "$H" -F "f=@data/blocklist.bin" http://$IP/upload                # -> ok
# verify what landed
curl -s -u "$U:$P" http://$IP/stats.json \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['ver'],'boot',d['boot'],'heap',d['heap'])"
```

The dashboard does the same from *Advanced → Maintenance* (blocklist) and *Advanced → Danger zone*
(firmware). What `gen_config` bakes into `secrets.h` is **not** part of a firmware OTA: change it with
the runtime endpoints (`/setblock`, `/setdns`, `/setwifi`, `/setproxy`) or rebuild
**and re-flash the filesystem**.

### Not installed, bricked, or no network — USB

```sh
pio run -e esp8266 -t upload   --upload-port <PORT>   # firmware only
pio run -e esp8266 -t uploadfs --upload-port <PORT>   # filesystem: data/*.cfg + default blocklist
```

⚠ `uploadfs` **erases LittleFS**: the uploaded blocklist, `rules.cfg`, `names.cfg`, `hosts.cfg` and
`stats.cfg` (counters) are replaced by `data/*`. Re-upload the blocklist afterwards.

### What survives what
| action | LittleFS | EEPROM/NVS (WiFi creds) |
|---|---|---|
| `POST /update` (firmware OTA) | kept | kept |
| `-t uploadfs` | **erased** → `data/*` again | kept |
| BOOT held at power-on | kept | cleared — effective only when `/wifi.cfg` is absent |

`/stats.cfg` (blocked/allowed/cached, provider share, DNSSEC and header-rewriter counters) is
kept across a firmware OTA; `/resetstats` zeroes it. The destination map is RAM-only and always
restarts empty on boot.

`/boot.cfg` holds the optional boot/crash record (`src/boot_debug.h`), **compiled only with
`-D BOOT_DEBUG=1`** — normal builds omit it entirely (no SNTP client, no extra flash writes and
no extra `/stats.json` keys). `src/boot_debug.h` stores: boot epoch (SNTP; 0 until/if it
answers), reset class, and the previous boot's last snapshot (uptime, lowest free heap + when +
context, and why it ended). It is rewritten at boot, every 5 min and whenever the heap low-water
drops ~1 KB, so a crash cannot erase the evidence; the always-on counter stays in `/boot.cnt`.
Exposed in `/stats.json` as `bt` (boot epoch), `nt` (now), `rst` (why this boot started) and
`prev.{id,bt,up,hmin,hup,hctx,end,sus}`: `prev.end` is `ota`/`provision` for restarts the
firmware initiated, and `prev.sus == "oom"` flags a low-heap panic/watchdog. Reboot detection
is simply `boot`/`prev.id` changing; `prev.up` vs `prev.hmin` shows whether it died early.

```sh
PLATFORMIO_BUILD_FLAGS="-D BOOT_DEBUG=1" pio run -e esp8266   # then upload via POST /update
```

An interrupted OTA leaves the running firmware in place: the image goes to the spare app region and
the bootloader switches only after a complete, valid write. On ESP32 the new image is confirmed only
after 60 s of uptime, so a crash/boot loop before that rolls back to the previous slot on reset
(the ESP8266 Updater has no rollback: recover over USB).
> Just after a reboot the first request can fail (`curl` exit 7 / HTTP `000`); retry once.

### Storage map
| area | contents |
|---|---|
| LittleFS | `/blocklist.bin`, `/rules.cfg`, `/hosts.cfg`, `/names.cfg`, `/dns.cfg`, `/block.cfg`, ``/proxy.cfg`, `/stats.cfg` (persisted counters + GAFM/DNSSEC/header %), `/boot.cnt` (boot counter), `/boot.cfg` (boot/crash record, `BOOT_DEBUG` builds only), `/wifi.cfg` (legacy `/custom.txt`, `/allow.txt` still read) |
| built in | `secrets.h` (WiFi + `WEB_USER`/`WEB_PASS` + `UPSTREAM_DNS` seed), `page.h` (`web/*.html` + `world.svg`), `geo_table.h` (`/14` → country, DB-IP CC BY 4.0), block page template |
| EEPROM/NVS | WiFi `ssid`/`pass` (SmartConfig, `/setwifi`) |

**WiFi precedence:** `/wifi.cfg` (baked into the FS image) **wins** over NVS and `secrets.h`. So on a
device installed with `uploadfs`, holding BOOT clears NVS but the baked `/wifi.cfg` still wins — use
*Advanced → Wi-Fi → Change* (`/setwifi`, which rewrites `/wifi.cfg`) instead.

## Configure

### `config.env` (pre-flash; baked at compile — a few keys also have runtime endpoints)
Keys: `WIFI_SSID`, `WIFI_PASS`, `WIFI_IP`, `WIFI_GW`, `WIFI_DNS`, `WIFI_HOST`, `UPSTREAM_DNS`,
`WEB_USER`, `WEB_PASS`, `BLOCK_MODE` (`ip|zero|nxdomain`), `IPV4_ONLY` (`0|1`), `KEYWORD_BLOCK` (`0|1`),
`REBIND_GUARD` (`0|1`), `SAFESEARCH` (`0|1`), `PRIVACY_LEVEL` (`0..3`, response-header level; runtime-editable).
`WIFI_DNS` = the resolver the **ESP itself** uses; **`UPSTREAM_DNS`** = the resolver(s) the device
**forwards client queries to** (comma-separated, up to 4; default `1.1.1.1` Cloudflare; Quad9 `9.9.9.9`,
Google `8.8.8.8`). Baked as `#define UPSTREAM_DNS_LIST` and seeded into `data/dns.cfg`; runtime-editable
at **`/setdns`** (persisted in `/dns.cfg`, one IPv4 per line). The active resolver is `upstream` in
`/stats.json`; every server is probed once a minute and the lowest-latency one wins.
Generates `src/secrets.h` + `data/wifi.cfg`, `data/block.cfg`.

### HTTP API
Mutating endpoints require **Basic auth** (`WEB_USER:WEB_PASS`) + header
**`X-Requested-With: esp-adblock`**. `/stats.json` and `/events` also require Basic auth
(they expose the client list and blocked-event log); `/allow`, `/proxy.pac`, `/wpad.dat` and `/dns-query` do not.

| Method | Route | Args | Effect |
|---|---|---|---|
| GET | `/` | — | Dashboard (**Basic auth**); with a blocked host `Host` → block page |
| GET | `/world.svg` | — | Simplified world map SVG for the destination card (**Basic auth**, same as `/`); inlined in PROGMEM |
| GET | `/stats.json` | — | `ip, ver, boot, upstream, dnslist[{ip,ms,cur}], pf, blocked, allowed, cached, domains, rssi, temp, cpu, heap, uptime, upat, pl, ph, pht, php, psv, dns, dnsf, dnsl, dnsTo, vcc, blocking, resumeIn, defcreds, bmode, bttl, v4only, kw, rb, ss, ssid, proxy, gafam[Google,Apple,Meta,Amazon,Microsoft,other], dnss[ad_set,total], geo[[cc,count]], geoMapped, clients[{ip,mac,name,blocked,allowed,ps,pac}], custom[], wild[], allow[], keyword[], url[], hosts[], evSeq` (+ diag `dq,bc,bch,bs,rc,lg,lw,ld`). `dns`=total ms, `dnsf`=upstream, `dnsl`=device, `cpu`=MHz, `vcc`=mV (ESP8266), `dnsTo`=DNS timeouts, `dnslist.ms`=-1 means probe failed, `cur` marks the active forwarder, `pf`=probe timeouts, `pl`=privacy level, `ph/pht`=headers now/max, `php/psv`=pages rewritten/all pages, `pac`=requests seen on the black-hole port, `boot`=boot counter, `upat`=seconds since the last successful blocklist upload (0 = not since boot), `ps`=client pause seconds left, `ssid`=connected network, `proxy`=PAC proxy, `gafam`=provider share of allowed lookups, `dnss`=forwarded answers with the DNSSEC `AD` bit, `geo`=estimated destination counts by country (RAM since reboot; `geoMapped` = total mapped). Totals survive reboots via `/stats.cfg`. |
| GET | `/setdns` | `d=ip[,ip…]` | Upstream candidates (1–4 IPv4, comma/space/newline separated); saves `/dns.cfg` and re-probes now |
| GET | `/events` | `since=seq` | Recent-blocked ring `{last, ev:[{seq,host}]}` (Basic auth) |
| GET | `/allow` | `d=domain`, `s=seconds` (optional) | Allowlist the domain (overrides blocklist). With `s` it is a **temporary** allow (RAM, capped at 24 h). CSRF only, **no** Basic (used by block page) |
| GET | `/setblock` | `m=ip\|zero\|nxdomain`, `ttl=0..86400`, `v4=0\|1`, `kw=0\|1`, `rb=0\|1`, `ss=0\|1`, `pl=0..3` | Block reply / blocked-answer cache TTL / IPv4-only / keyword / rebind guard / SafeSearch / privacy header level |
| GET | `/setname` | `ip=`, `n=name` | Set a client's friendly name (empty name removes it); persisted in `/names.cfg` |
| GET | `/pauseclient` | `ip=`, `s=seconds` | Pause blocking for one client (`s=0` resumes) |
| GET | `/resetstats` | — | Zero blocked/allowed/cached, per-client counts, GAFM/DNSSEC/header counters, the geo map and the recent-blocked list |
| GET | `/setproxy` | `p=host:port` | PAC proxy address (empty = direct); served by `/proxy.pac` |
| GET | `/proxy.pac` | — | PAC file (`FindProxyForURL`); no auth (OS/browser fetch). Emits the `url` rules as `PROXY <ip>:81` (black-hole) |
| GET | `/wpad.dat` | — | Alias of `/proxy.pac` for WPAD; the DNS answers `wpad`/`wpad.*` with the device IP |
| GET/POST | `/dns-query` | GET `?dns=<base64url>`, POST body `application/dns-message` | DoH (RFC 8484) over **plain HTTP** (no TLS, no cert); same block/CNAME/TTL policy. No auth |
| GET | `/__dnscheck` | — | Resolver-usage probe; **no auth**. The dashboard fetches `http://<random>.dnscheck/__dnscheck`, which resolves only if the client's DNS goes through this device |
| GET | `/scan` | — | Blocking Wi-Fi scan → JSON `[{s,r,e}]` (single request, no polling) |
| GET | `/setwifi` | `ssid=`, `pass=` | Try the new network for ~15s, persist only on success, else keep the current one |
| GET | `/sethost` | `n=name`, `ip=` | Add/replace a local DNS record |
| GET | `/delhost` | `n=name` | Remove a local DNS record |
| GET | `/addblock` | `d=domain` | Add a `block` rule (or a `wildcard` rule if `d` contains `*`) |
| GET | `/unblock` | `d=domain` | Remove that `block`/`wildcard` rule |
| GET | `/addkeyword` | `t=token` | Add a keyword rule (auth+CSRF) |
| GET | `/delkeyword` | `t=token` | Remove a keyword rule |
| GET | `/delallow` | `d=domain` | Remove an allowlist entry |
| GET/POST | `/rules` | GET: text; POST: body `Content-Type: text/plain` | Read / replace the whole `/rules.cfg` (reparsed after a write) |
| GET | `/pause` | `s=seconds` (0 = indefinite) | Pause blocking |
| GET | `/resume` | — | Resume blocking |
| POST | `/upload` | multipart `blocklist.bin` | Replace blocklist (validates `BLM1`/`BLM2`) |
| POST | `/update` | multipart `firmware.bin` | Firmware OTA |

```bash
curl -s -u "$U:$P"  http://esp-adblock.local/stats.json | python3 -c "import sys,json;print(json.load(sys.stdin)['ip'])"
curl -u admin:PASS -H 'X-Requested-With: esp-adblock' 'http://esp-adblock.local/addblock?d=ads.example.com'   # -> ok
```

### `/rules.cfg` (user rules, on the FS)
One rule per line; `#` = comment. Written by `/addblock`, `/unblock`, `/allow`, `/addkeyword`, … (or edit + reboot).
```
block ads.example.com       # block the domain and all its subdomains
wildcard *.ads.example.com  # glob rule: any subdomain ('*' = any run of chars; '*' in a `block` line too)
allow safe.example.com      # exception (wins over block)
keyword doubleclick         # block hosts whose label matches the token
url /js/ads.js              # PAC URL-block: matched (substring) against the full URL by the
                            # client's PAC, which routes it here to be DROPPED (no proxy/cert)
||ads.example.com^          # AdGuard shorthand = block
@@||safe.example.com^       # AdGuard shorthand = allow
```
Caps: `block` ≤ `MAX_CUSTOM` (ESP8266 48 / ESP32 200), `allow` ≤ `MAX_ALLOW` (64/128),
`keyword` ≤ `MAX_KW` (64), `wildcard` ≤ `MAX_WILD` (16), `url` ≤ `MAX_URL` (24/64). Defaults seed the first boot.
`url` patterns must avoid `'` `"` `\` (emitted into the PAC's JS); matches hit the black-hole on port 81 (`BLACKHOLE_PORT`).

### CPU governor
`src/cpu_governor.h` — ondemand: full speed while DNS is busy, 80 MHz when idle (hysteresis).
Fast clock is taken from the device, capped at 300 MHz. `cpu_gov::markActivity()` (DNS path) +
`cpu_gov::checkIdle()` (loop). Current clock is `cpu` in `/stats.json`. No-op on unsupported chips.

### Dashboard telemetry
- **Destination map**: for each allowed answer, the first public A record indexes
  `GEO_TABLE[ip >> 18]` (one byte per `/14`, 16 384 entries, `255` = mixed/unknown). Counts live
  in RAM (`geoHits`) and reset on reboot; nothing is persisted. Regenerate with
  `python3 tools/build_geo_table.py dbip-country-lite.csv` (monthly; DB-IP Lite, CC BY 4.0).
  `web/world.svg` is simplified by `tools/build_world_svg.py` and inlined via `build_web.py`.
- **GAFM share**: the blocklist builder can carry a `GAFM` section of provider Blooms; the
  firmware only reads it for telemetry (share of *allowed* lookups), never for blocking.
  Counters are persisted in `/stats.cfg`.
- **DNSSEC**: forwarded replies are inspected for the `AD` bit (`dnss[valid,total]`); no
  validation is performed by the device.

### Serial provisioning (firmware side)
Two protocols on the console (115200 8N1):
- **Improv Wi-Fi Serial** (binary, `IMPROV`-framed) — state/info/scan/provision/set-hostname,
  handled by `improvHandleRPC()`. Used by the browser installer.
- **Plain-text `CFG`** — `CFG ssid <name>`, `CFG host <hostname>`, `CFG ip|gw|dns <address>`,
  `CFG commit`; answers `CFGSAVED`. Used for a static IP, which Improv does not carry.
Both rewrite `/wifi.cfg` and preserve unrelated keys (`UPSTREAM_DNS`, …).

## Formats / constants
| Item | Value |
|---|---|
| Blocklist file `BLM1` | ASCII `BLM1` + `uint32` (LE) domain count, then the bitmap (no regex) |
| Blocklist file `BLM2` | `BLM2` + `uint32` n + `uint32` bitmap_bytes + bitmap + `RGX1` + `uint16` count + (`uint16` len + pattern)* + `GAFM` + 5 × (`uint16` bytes + bitmap). Emitted by default; `BLM1` only with `--no-gafam` and no regex |
| `m` (bits) | `BLM1`: `(file_size − 8) × 8`; `BLM2`: `bitmap_bytes × 8` |
| Hash | FNV-1a 64 (`0xcbf29ce484222325`, prime `0x100000001b3`) |
| Bloom k | `7`; `idx_i = (a + i·b) mod m`, `a=hash>>32`, `b=hash & 0xffffffff` |
| Hostname regex | `BLM2` only; loaded to RAM (`MAX_RGX` = 16 ESP8266 / 64 ESP32, `RGX_MAXLEN` = 96 / 128), matched on the host **and each suffix** only on a bloom miss |
| Geo table | `GEO_TABLE[ip >> 18]` → country index (one byte per `/14`); `GEO_NCODES` codes in `GEO_CODES`; `255` = mixed/unknown; DB-IP Lite, CC BY 4.0 |
| CSRF header | `X-Requested-With: esp-adblock` |
| Auth | HTTP Basic, `WEB_USER` (default `admin`) : `WEB_PASS` |
| Hostname | `WIFI_HOST` (default `esp-adblock`) |
| WiFi order | `/wifi.cfg` (baked) → NVS (SmartConfig) → `secrets.h`; since `/wifi.cfg` wins, BOOT-hold only helps when it is absent — change at runtime via `/scan` + `/setwifi` (rewrites `/wifi.cfg`) |

## Limits
- ESP8266 `4m2m` (2 MB FS + ~1 MB OTA region) — **firmware OTA over WiFi works** (`POST /update`); ~22 KB free heap at boot. `4m1m` only shrinks the filesystem.
- DNS serves **UDP :53** and a **TCP :53 fallback** (blocking, only for truncated/large replies a client retries over TCP). HTTPS block pages are impossible (cert) — standard sinkhole limit.
- Bloom false positive ~0.8%; subdomains are covered by suffix matching; the block page + `/allow` handles the rare case.
- **CNAME deep inspection**: if an upstream answer contains a CNAME/chain whose target is blocklisted, the reply is answered as **NXDOMAIN** (catches first-party / CNAME-cloaked trackers). Counts as a block.
- **Never blocked**: infrastructure/reserved TLDs — `.arpa` (reverse DNS, `home.arpa`, DDR `_dns.resolver.arpa`), `.localhost`, `.test`, `.invalid`, `.example`, `.onion`; and all-numeric names (IP literals used as hostnames). These were only Bloom false positives and blocking them broke PTR/DDR/local names.
- **TTL clamp**: relayed answer RRs have their TTL rewritten down to `TTL_CLAMP_S` (300 s; `0` off). Faster block/allow propagation, at the cost of more re-resolves (absorbed by the response cache).
- Wildcard rules (`/rules.cfg`) are glob (`*` only). The **hostname regexes** carried by a `BLM2` blob use a small engine: literals, `.`, `*`, `+`, `?`, `[abc]`/`[^abc]` (ranges), `\` escape, `^`/`$` anchors, and top-level `|` alternation — case-insensitive, unanchored search. No groups/backrefs. Only **hostname** patterns apply (the DNS sees no URL/path); URL/regex-from-URL lists are dropped at build time.
- Regex cost: they run on every **bloom miss** (the common path) for each suffix, so keep the count small; disabled entirely (`numRgx=0`) unless a `BLM2` blob provides them.
