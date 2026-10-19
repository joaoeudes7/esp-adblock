# docs/AI.md — install / run / configure

Contract for agents (Claude/OpenCode/Cursor/…). Values below are **verbatim** — do not normalize.

DNS sinkhole + dashboard. Serves **DNS UDP :53** (plus a TCP :53 fallback) and **web HTTP :80**. Blocklist = a Bloom
filter bitmap in flash (`BLM1`, `k=7`, FNV-1a 64). Targets: **ESP8266** and **ESP32/C3/S3**.

## Install

```bash
# deps: platformio (pio), python3
cp config.env.example config.env          # optional pre-flash: edit WIFI_SSID/WIFI_PASS/WEB_PASS
python tools/build_bloom.py data/blocklist.bin   # build the BLM1 blocklist (default sources)
pio run -e esp8266                                 # targets: esp8266 | esp32dev | c3 | esp32s3
pio run -e esp8266 -t upload   --upload-port <PORT>   # firmware
pio run -e esp8266 -t uploadfs --upload-port <PORT>   # filesystem (blocklist + data/*.cfg)
esptool --port <PORT> flash-id                     # confirm chip: ESP8266EX / ESP32-… (don't trust labels)
```
Build hooks (`extra_scripts`) run automatically: `tools/gen_config.py` (`config.env` →
`src/secrets.h` + `data/wifi.cfg`/`block.cfg`/`syslog.cfg`) and `tools/build_web.py`
(`web/*.html` → `src/page.h`). With no `config.env`, `gen_config` seeds from `config.env.example`.

## Run (verify)

```bash
# reach the device
ping esp-adblock.local                 # or: dns-sd -G v4 esp-adblock.local  /  getent hosts esp-adblock.local
curl -s http://esp-adblock.local/stats.json | python3 -c "import sys,json;print(json.load(sys.stdin)['ip'])"
dig @<ip> doubleclick.net              # -> <esp-ip>   (blocked)
dig @<ip> github.com                   # -> real IP    (forwarded)
curl -H 'Host: doubleclick.net' http://<ip>/     # -> block-page HTML
```
Find the device if mDNS is unavailable: fixed `WIFI_IP`; serial `WiFi up: <ip>` @115200 8N1;
router DHCP entry (`WIFI_HOST`, default `esp-adblock`); or scan TCP:80 for `/stats.json` with `"domains"`.

## Configure

### `config.env` (pre-flash; baked at compile — a few keys also have runtime endpoints)
Keys: `WIFI_SSID`, `WIFI_PASS`, `WIFI_IP`, `WIFI_GW`, `WIFI_DNS`, `WIFI_HOST`, `UPSTREAM_DNS`,
`WEB_USER`, `WEB_PASS`, `BLOCK_MODE` (`ip|zero|nxdomain`), `IPV4_ONLY` (`0|1`), `KEYWORD_BLOCK` (`0|1`),
`REBIND_GUARD` (`0|1`), `SAFESEARCH` (`0|1`), `PRIVACY_LEVEL` (`0..3`, response-header level; runtime-editable),
`SYSLOG_HOST`, `SYSLOG_PORT`.
`WIFI_DNS` = the resolver the **ESP itself** uses; **`UPSTREAM_DNS`** = the resolver(s) the device
**forwards client queries to** (comma-separated, up to 4; default `1.1.1.1` Cloudflare; Quad9 `9.9.9.9`,
Google `8.8.8.8`). Baked as `#define UPSTREAM_DNS_LIST` and seeded into `data/dns.cfg`; runtime-editable
at **`/setdns`** (persisted in `/dns.cfg`, one IPv4 per line). The active resolver is `upstream` in
`/stats.json`; every server is probed once a minute and the lowest-latency one wins.
Generates `src/secrets.h` + `data/wifi.cfg`, `data/block.cfg`, `data/syslog.cfg`.

### HTTP API
Mutating endpoints require **Basic auth** (`WEB_USER:WEB_PASS`) + header
**`X-Requested-With: esp-adblock`**. `/stats.json` and `/events` also require Basic auth
(they expose the client list and blocked-event log); `/allow` and `/proxy.pac` do not.

| Method | Route | Args | Effect |
|---|---|---|---|
| GET | `/` | — | Dashboard (**Basic auth**); with a blocked host `Host` → block page |
| GET | `/stats.json` | — | `ip, ver, boot, upstream, dnslist[{ip,ms,cur}], pf, blocked, allowed, cached, domains, rssi, temp, cpu, heap, uptime, pl, ph, pht, php, dns, dnsf, dnsl, dnsTo, vcc, blocking, resumeIn, defcreds, bmode, v4only, kw, rb, ss, syslog, sysport, ssid, proxy, clients[{ip,mac,name,blocked,allowed,ps}], custom[], wild[], allow[], keyword[], hosts[], ev[]` (+ diag `dq,bc,bch,bs,rc,lg,lw,ld`). `dns`=total ms, `dnsf`=upstream, `dnsl`=device, `cpu`=MHz, `vcc`=mV (ESP8266), `dnsTo`=DNS timeouts, `dnslist.ms`=-1 means probe failed, `cur` marks the active forwarder, `pf`=probe timeouts, `pl`=privacy level, `ph/pht`=headers now/max, `php`=pages rewritten, `boot`=boot counter, `ps`=client pause seconds left, `ssid`=connected network, `proxy`=PAC proxy |
| GET | `/setdns` | `d=ip[,ip…]` | Upstream candidates (1–4 IPv4, comma/space/newline separated); saves `/dns.cfg` and re-probes now |
| GET | `/events` | `since=seq` | Recent-blocked ring `{last, ev:[{seq,host}]}` (Basic auth) |
| GET | `/allow` | `d=domain` | Allowlist the domain (overrides blocklist). CSRF only, **no** Basic (used by block page) |
| GET | `/setblock` | `m=ip\|zero\|nxdomain`, `v4=0\|1`, `kw=0\|1`, `rb=0\|1`, `ss=0\|1`, `pl=0..3` | Block reply / IPv4-only / keyword / rebind guard / SafeSearch / privacy header level |
| GET | `/setname` | `ip=`, `n=name` | Set a client's friendly name (empty name removes it); persisted in `/names.cfg` |
| GET | `/pauseclient` | `ip=`, `s=seconds` | Pause blocking for one client (`s=0` resumes) |
| GET | `/resetstats` | — | Zero blocked/allowed/cached, per-client counts and the recent-blocked list |
| GET | `/setproxy` | `p=host:port` | PAC proxy address (empty = direct); served by `/proxy.pac` |
| GET | `/proxy.pac` | — | PAC file (`FindProxyForURL`); no auth (OS/browser fetch) |
| GET | `/scan` | — | Blocking Wi-Fi scan → JSON `[{s,r,e}]` (single request, no polling) |
| GET | `/setwifi` | `ssid=`, `pass=` | Try the new network for ~15s, persist only on success, else keep the current one |
| GET | `/setsyslog` | `h=host`, `p=port` | Remote syslog (empty host = off) |
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
| POST | `/upload` | multipart `blocklist.bin` | Replace blocklist (validates `BLM1`) |
| POST | `/update` | multipart `firmware.bin` | Firmware OTA |

```bash
curl -s  http://esp-adblock.local/stats.json | python3 -c "import sys,json;print(json.load(sys.stdin)['ip'])"
curl -u admin:PASS -H 'X-Requested-With: esp-adblock' 'http://esp-adblock.local/addblock?d=ads.example.com'   # -> ok
```

### `/rules.cfg` (user rules, on the FS)
One rule per line; `#` = comment. Written by `/addblock`, `/unblock`, `/allow`, `/addkeyword`, … (or edit + reboot).
```
block ads.example.com       # block the domain and all its subdomains
wildcard *.ads.example.com  # glob rule: any subdomain ('*' = any run of chars; '*' in a `block` line too)
allow safe.example.com      # exception (wins over block)
keyword doubleclick         # block hosts whose label matches the token
||ads.example.com^          # AdGuard shorthand = block
@@||safe.example.com^       # AdGuard shorthand = allow
```
Caps: `block` ≤ `MAX_CUSTOM` (ESP8266 48 / ESP32 200), `allow` ≤ `MAX_ALLOW` (64/128),
`keyword` ≤ `MAX_KW` (64), `wildcard` ≤ `MAX_WILD` (16). Defaults seed the first boot.

### CPU governor
`src/cpu_governor.h` — ondemand: full speed while DNS is busy, 80 MHz when idle (hysteresis).
Fast clock is taken from the device, capped at 300 MHz. `cpu_gov::markActivity()` (DNS path) +
`cpu_gov::checkIdle()` (loop). Current clock is `cpu` in `/stats.json`. No-op on unsupported chips.

## Formats / constants
| Item | Value |
|---|---|
| Blocklist file | `/blocklist.bin`: ASCII `BLM1` + `uint32` (LE) domain count, then the bitmap |
| `m` (bits) | `(file_size − 8) × 8` |
| Hash | FNV-1a 64 (`0xcbf29ce484222325`, prime `0x100000001b3`) |
| Bloom k | `7`; `idx_i = (a + i·b) mod m`, `a=hash>>32`, `b=hash & 0xffffffff` |
| CSRF header | `X-Requested-With: esp-adblock` |
| Auth | HTTP Basic, `WEB_USER` (default `admin`) : `WEB_PASS` |
| Hostname | `WIFI_HOST` (default `esp-adblock`) |
| WiFi order | `/wifi.cfg` (baked) → NVS (SmartConfig) → `secrets.h`; hold BOOT at power-on to re-provision, or change at runtime via `/scan` + `/setwifi` |

## Limits
- ESP8266 `4m2m` (2 MB FS + ~1 MB OTA region) — **firmware OTA over WiFi works** (`POST /update`); ~22 KB free heap at boot. `4m1m` only shrinks the filesystem.
- DNS serves **UDP :53** and a **TCP :53 fallback** (blocking, only for truncated/large replies a client retries over TCP). HTTPS block pages are impossible (cert) — standard sinkhole limit.
- Bloom false positive ~0.8%; subdomains are covered by suffix matching; the block page + `/allow` handles the rare case.
- Wildcard rules are glob (`*` only), not regex (no viable regex engine on ESP8266).
