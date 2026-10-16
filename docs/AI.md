# docs/AI.md — install / run / configure

Contract for agents (Claude/OpenCode/Cursor/…). Values below are **verbatim** — do not normalize.

DNS sinkhole + dashboard. Serves **DNS UDP :53** and **web HTTP :80**. Blocklist = a Bloom
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
`REBIND_GUARD` (`0|1`), `SAFESEARCH` (`0|1`), `SYSLOG_HOST`, `SYSLOG_PORT`, `UPDATE_URL`, `UPDATE_H`.
`WIFI_DNS` = the resolver the **ESP itself** uses; **`UPSTREAM_DNS`** = the resolver the device
**forwards client queries to** (default `1.1.1.1` Cloudflare; Quad9 `9.9.9.9`, Google `8.8.8.8`) —
**compile-time only** (`#define UPSTREAM_IP`), exposed as `upstream` in `/stats.json`. No runtime endpoint.
Generates `src/secrets.h` + `data/wifi.cfg`, `data/block.cfg`, `data/syslog.cfg`.

### HTTP API
Mutating endpoints require **Basic auth** (`WEB_USER:WEB_PASS`) + header
**`X-Requested-With: esp-adblock`**. Read-only (`/stats.json`, `/events`) is open.

| Method | Route | Args | Effect |
|---|---|---|---|
| GET | `/` | — | Dashboard (**Basic auth**); with a blocked host `Host` → block page |
| GET | `/stats.json` | — | `ip, ver, blocked, allowed, cached, domains, rssi, temp, cpu, heap, uptime, dns, dnsTo, vcc, blocking, resumeIn, defcreds, bmode, v4only, kw, rb, ss, syslog, sysport, clients[], custom[], wild[], allow[], keyword[], hosts[], ev[]` (+ diag `dq,bc,bch,bs,rc,lg,lw,ld`). `dns`=RTT ms, `cpu`=MHz, `vcc`=mV (ESP8266), `dnsTo`=timeouts |
| GET | `/events` | `since=seq` | Recent-blocked ring `{last, ev:[{seq,host}]}` |
| GET | `/allow` | `d=domain` | Allowlist the domain (overrides blocklist). CSRF only, **no** Basic (used by block page) |
| GET | `/setblock` | `m=ip\|zero\|nxdomain`, `v4=0\|1`, `kw=0\|1`, `rb=0\|1`, `ss=0\|1` | Block reply / IPv4-only / keyword / rebind guard / SafeSearch |
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
| GET | `/forgetwifi` | — | Clear saved WiFi and reboot |
| GET | `/fetchnow` | — | Fetch the remote blocklist now |
| GET | `/setupdate` | `u=url`, `h=hours` | Configure scheduled remote blocklist pull |
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
| WiFi order | `/wifi.cfg` (baked) → NVS (SmartConfig) → `secrets.h`; hold BOOT at power-on to re-provision |

## Limits
- ESP8266 `4m2m` (2 MB FS + ~1 MB OTA region) — **firmware OTA over WiFi works** (`POST /update`); ~22 KB free heap at boot. `4m1m` only shrinks the filesystem.
- DNS is **UDP/53 only** (no TCP fallback). HTTPS block pages are impossible (cert) — standard sinkhole limit.
- Bloom false positive ~0.8%; subdomains are covered by suffix matching; the block page + `/allow` handles the rare case.
- Wildcard rules are glob (`*` only), not regex (no viable regex engine on ESP8266).
