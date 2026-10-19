# esp-adblock

A hardened **Pi-hole-style DNS ad-blocker** for **ESP8266** and **ESP32 / C3 / S3** — *no PSRAM required*.

> 📰 The upstream project was featured on [Tom's Hardware](https://www.tomshardware.com/networking/clever-hacker-fits-537-000-domains-in-a-tiny-usd5-esp32-ad-blocking-dongle-firmware-uses-only-around-50kb-of-ram-and-can-answer-blocked-lookups-in-10-milliseconds), [XDA Developers](https://www.xda-developers.com/this-tiny-esp32-powered-gadget-blocks-537000-domains-only-uses-50kb-of-ram/), and [Korben](https://korben.info/en/half-million-ad-blocking-domains-50kb-ram-esp32.html).

> **This is a fork.** It started from
> [M-Abozaid/esp32-c3-adblock](https://github.com/M-Abozaid/esp32-c3-adblock) (MIT © 2026 zed —
> itself *inspired by* [s60sc/ESP32_AdBlocker](https://github.com/s60sc/ESP32_AdBlocker)) and was
> **substantially extended**: an **ESP8266** target, a **Bloom-filter** blocklist (replacing the
> sorted hashes), a rewritten dashboard, user rules, a DNS-rebinding guard, metrics, and more.
> See [Features](#features) and the [ESP8266 fork notes](#esp8266-port-fork-notes).

## Features

**Blocking**
- DNS sinkhole on **UDP :53** — blocks a domain **and all its subdomains** (query-time suffix match).
- Blocklist = a **Bloom filter bitmap in flash** (`BLM1`): **O(1) RAM**, ~**1.5 byte/domain**, ~**0.8% false positive**.
- **Hostname regexes** (`BLM2`) — a `RGX1` section after the bitmap carries patterns a Bloom filter can't express (built with `--regex FILE`). Small engine, matched on the host + each suffix on a bloom miss; optional (a `BLM1` without it costs nothing).
- **Multi-source** default union: StevenBlack, **Hagezi Ultimate** (most aggressive curated tier — blocks ad/telemetry across social apps like TikTok *without* blocking the platform domains), OISD Big, Hagezi DoH/DoT (anti-bypass), **Hagezi TIF.mini** (malware/phishing), Turtlecute, EasyList, EasyPrivacy, hBlock, AdGuard Annoyances/MobileApp → **~631k domains** (after subdomain pruning + dedup).
- **Subdomain pruning** at build time (removes entries already covered by a parent rule) — smaller bitmap, **no behaviour or FP change**.
- **Block reply modes**: ESP IP (shows a block page), `0.0.0.0`, or `NXDOMAIN`.
- **Keyword heuristic** (whole-label match: `ads`, `tracker`, `analytics`, …) + editable **user rules** in `/rules.cfg` (`block` / `allow` / `keyword`, plus AdGuard `||domain^` / `@@||domain^` shorthand).
- **Wildcard rules** in `/rules.cfg` (`wildcard *.ads.example.com` / `block *.x.y`) — glob `*` matcher, no allocation; `*.ads.com` never matches `notads.com`.
- **CNAME-cloaking defense** — when an upstream answer uses a CNAME that points at a blocklisted name (a tracker hidden behind the site's own first-party name), the whole reply is answered as NXDOMAIN. Catches a common modern tracker bypass that plain host lookups miss.
- **TTL clamp** — relayed answers have their TTL rewritten down to ≤ `TTL_CLAMP_S` (300 s, `0` = off) so a new block/allow takes effect in minutes instead of hours (clients cache answers).
- **Infrastructure-safe** — never blocks `.arpa` (reverse DNS, `home.arpa`, DDR `_dns.resolver.arpa`), `.localhost`, `.test`, `.invalid`, `.example`, `.onion`, or all-numeric/IP-literal names; those were only Bloom false positives.
- **SafeSearch** (opt-in): forces Google / Bing / YouTube / DuckDuckGo SafeSearch by answering their consumer domains with the provider's enforcing IP (`AAA` NODATA too, so IPv6 can't bypass).
- **Allowlist** via the block page — **"Allow this site"** (permanent) or **"Continue for 5 minutes"** (temporary, RAM only, max 24 h via `/allow?s=`), both override the blocklist.
- **Built-in connectivity-check allowlist** (Android/Apple/Windows/Firefox/OPPO) so devices don't show a false captive portal.
- **IPv4-only** mode (strips AAAA, returns NODATA).
- **DNS-rebinding guard** (opt-in): if an upstream answer carries a private/reserved **A or AAAA** (`10/8`, `192.168/16`, `172.16–31`, `127/8`, `169.254/16`, `fc00::/7`, `fe80::/10`, `::1`, IPv4-mapped…), it answers **NXDOMAIN** instead of leaking an internal IP.
- **Pause / resume** blocking (for N seconds or indefinitely), plus **per-client pause**.
- **Privacy response headers** (level 0–3, runtime) on the pages the device serves: `nosniff`, frame-deny, referrer policy, Permissions-Policy, CSP, COOP/CORP at the top level.
- **DoH (plain HTTP)** — `/dns-query` (RFC 8484, GET `?dns=<base64url>` or POST `application/dns-message`) resolves through the same policy (block/CNAME/TTL) **without TLS/cert**. For a cooperating app/network where `:53` is unavailable; OS-native DoH still needs HTTPS, so plain UDP/TCP `:53` stays the universal path.
- **Proxy (PAC) + URL rules** — the device serves `/proxy.pac` (and the WPAD alias `/wpad.dat`). Besides routing everything through a real proxy you run (`PROXY host:port; DIRECT`), `url <substr>` rules (`/rules.cfg`) make the client's PAC route **matching URLs** (path included!) to this device's **black-hole** (port 81) to be dropped — so `meusite.com/js/ads.js` can be blocked without the device serving as a proxy and **without any certificate/MITM**. Local/private hosts stay `DIRECT`. Note: works only for clients configured with the PAC (explicit/PAC proxy); HTTPS paths are matched by the PAC but only dropped (no content served).

**Forwarding**
- **Async, non-blocking** upstream forwarder (txid-matched in-flight table) — no per-query stall, web/OTA stay responsive.
- **TCP :53 fallback** — large/truncated answers a client retries over TCP are forwarded over TCP (blocking, rare); without it the retry failed.
- **Multiple upstream resolvers with auto-pick** — `config.env` key `UPSTREAM_DNS` (comma-separated, up to 4; default **Cloudflare `1.1.1.1`**; Quad9 `9.9.9.9`, Google `8.8.8.8`), editable at `/setdns` and persisted in `/dns.cfg`. Each server is probed every minute and the lowest-latency one is used; two failed probes switch away immediately, and the active resolver is shown on the dashboard (`upstream` + `dnslist` in `/stats.json`).
- **TTL-aware response cache** for repeated domains.
- **Local DNS records** (`/hosts.cfg`) and answers its **own hostname**.
- **"Am I using this resolver?" check** — a `Test DNS` button probes a private `*.dnscheck` name that only this resolver can answer.
- Live **DNS latency** (RTT), **supply voltage** (ESP8266), timeout counter, loop-timing and CPU-clock diagnostics in the dashboard.

**Dashboard** — `http://esp-adblock.local/`
- Live stats: blocked / allowed / cached, list size, **per-client** block+allow, **recently-blocked** ring, devices table (friendly names + **per-client pause**), DNS RTT (split into **forward** vs **device** ms), VCC, firmware **version**.
- **Where traffic goes** — an estimated destination map + top countries for the IPs this device resolved (one flash lookup per `/14` from `geo_table.h`, no RAM index; built from DB-IP Lite, CC BY 4.0). RAM-only, so it reads "since reboot".
- **Provider share + DNSSEC telemetry** — GAFM (Google/Apple/Meta/Amazon/Microsoft) share of allowed lookups, and the percentage of forwarded answers with the DNSSEC `AD` bit set. Read-only counters, no extra lookups.
- **Counters survive reboots** (`/stats.cfg`): blocked/allowed/cached, provider share, DNSSEC and header-rewriter percentages are flushed to LittleFS, so the dashboard totals don't reset on every OTA/reboot (the **Reset** button still zeroes everything).
- **Blocklist freshness nudge** — `/stats.json` carries `upat` (seconds since the last successful upload); the dashboard warns when the list has not been updated since boot.
- Controls: pause/resume, block mode, IPv4-only, keyword, **SafeSearch**, rebind guard, block + **wildcard** rules, local names, **privacy header level**, **proxy (PAC)**, **blocklist upload** (the **browser** fetches the URL over HTTPS and POSTs it — the device never does TLS), **firmware OTA**, **Change Wi-Fi** (scan → pick → password, tested before saving).
- **Auto-refresh by default** — the page polls every ~5s (no toggle); backs off to 30s when the device is offline or the tab is hidden, and the header **Refresh** button forces one now. A **boot id** reloads open pages after a device reboot.
- **Rules editor**: block/wildcard lists plus the **raw `/rules.cfg`** (pre-loaded, editable, replaces the file).
- UI: **Alpine.js** (declarative state, CSP build from unpkg) with the **Lucide** icon subset **inlined** (no icon CDN), loading overlay, responsive dark theme, keyboard-sortable tables and a11y.

**CPU governor** (`src/cpu_governor.h`)
- **Ondemand**: full speed while the resolver is busy, drops to **80 MHz** after a quiet period (hysteresis). Agnostic across ESP8266 / ESP32 / C3 / S3 (fast clock taken from the device, capped at 300 MHz for power).

**Provisioning & connectivity**
- WiFi order: **`/wifi.cfg` (baked) → NVS (SmartConfig/ESP-Touch) → `secrets.h`**; no captive portal; **hold BOOT** at power-on to re-provision.
- Static IP + hostname, **mDNS** (`esp-adblock.local`).
- **OTA**: firmware (`/update`, works over WiFi — the `4m2m` layout has a ~1 MB OTA region) and blocklist (`/upload`) over HTTP, plus ArduinoOTA (`pio -t upload`).
- **Browser installer** (`installer/`) — flashes over **Web Serial / WebUSB**, verifies SHA-256 + MD5 read-back, then provisions Wi-Fi on the same cable over **Improv Wi-Fi Serial** (scan / send credentials / set hostname, no reflash). A static-IP form falls back to the plain-text `CFG` protocol (`CFG ssid|host|ip|gw|dns …`, `CFG commit`). See [installer/README.md](installer/README.md).

**Ops & security**
- HTTP **Basic auth** on every state-changing endpoint + a **CSRF header** (`X-Requested-With`).
- **Remote syslog**, sent lazily off-idle (never competes with DNS latency).
- **Status LED blink** on each blocked lookup (built-in LED by default).
- WiFi watchdog, DNS-first loop, safe reboot paths.

**Targets & tooling**
- Builds for **ESP8266** (`esp12e`, `4m2m`) and **ESP32 / C3 / S3**.
- Tools: `build_bin_list_block.py` (blocklists → `BLM1`/`BLM2`), `build_web.py` (HTML + `world.svg` → `page.h`), `gen_config.py` (`config.env` → `secrets.h` + `data/*.cfg`), `build_geo_table.py` (DB-IP CSV → `geo_table.h`), `build_world_svg.py` (simplified map), `build_installer.py` (binaries + manifest).
- CI builds the ESP8266 + ESP32 matrix and runs the blocklist/regex/geo-tool tests.

The trick everyone misses: you don't need to keep the blocklist in RAM. This fork stores
the domains as a **Bloom-filter bitmap in flash** (`BLM1`) and probes it with `k=7` FNV-1a
hashes — **~1.5 byte/domain** at ~0.8% false positive, **O(1) RAM**, matched in microseconds.

```
query in ──▶ extract domain ──▶ FNV-1a hash (+ parent suffixes)
         ──▶ probe the flash Bloom bitmap (short-circuits on the first zero bit)
              ├─ blocked ──▶ answer ESP IP / 0.0.0.0 / NXDOMAIN
              └─ allowed ──▶ forward to upstream resolver, relay the reply
```

## Why this is interesting

Most ESP32/ESP8266 DNS sinkholes load the blocklist (domain *strings*) into RAM, so they
demand PSRAM. This fork keeps **no blocklist in RAM** — a **Bloom bitmap in flash** instead:

| | string-in-RAM approach | this (Bloom-in-flash) |
|---|---|---|
| Hardware | ESP32 + PSRAM (~$8) | ESP8266 / ESP32, **no PSRAM** |
| ~600k domains | ~6 MB of RAM | **~0.74 MB of flash** |
| RAM used | most of it | **~O(1)** (a handful of bytes + I/O cache) |
| Lookup | string compare | **~2 flash reads/query** (short-circuit; <1 warm) |
| False positive | n/a | ~0.8% (subdomains covered by suffix match) |

**Why a Bloom filter?** It's the sweet spot for a tiny flash + tiny RAM budget: constant
RAM regardless of list size, ~1.5 byte/domain, and — because the query walks label
suffixes and the filter short-circuits on non-members — the common (non-blocked) lookup
costs ~1–2 flash reads. Build `--bits` trades size for false-positive rate.

The same trick works on bigger chips. On a 16 MB ESP32-S3 the bitmap holds **~13M domains**
in flash, with the same ~O(1) RAM.

## Hardware

- **ESP8266** (e.g. ESP-12/NodeMCU, 4 MB) — the tested target here: `pio run -e esp8266 -t upload`
- **ESP32-C3** (tested on a C3 SuperMini), 4 MB flash, **no PSRAM needed**
- Classic **ESP32** (DevKit / WROOM) and **ESP32-S3** also build: `pio run -e esp32dev|c3|esp32s3 -t upload`
- Power it from a **stable USB source** (a phone charger or your router's USB port).
  Cheap/loose USB adapters can brown out the radio during WiFi transmit (a low supply
  shows up as a low `vcc` in the dashboard and higher DNS latency).

## Build & flash (PlatformIO)

One USB flash to get going — after that, **firmware and blocklist both update over WiFi** (see below).

> ⚠️ Use a **current PlatformIO** — the VSCode PlatformIO extension's bundled core, or
> `pip install -U platformio` in a venv. The distro/apt `platformio` package (e.g. 4.3.4) is
> too old and fails with `AttributeError: ... 'resultcallback'` (issue #4). There is also a
> **one-click browser installer** in [`installer/`](installer/README.md) (Web Serial/WebUSB +
> Improv Wi-Fi provisioning); host it over HTTPS or `localhost`.

```bash
# 1. configure (optional, but recommended): copy the template and fill it in.
#    tools/gen_config.py bakes it at build time into src/secrets.h (firmware) and
#    data/*.cfg (filesystem) — so you never edit secrets.h by hand.
#    - WIFI_SSID / WIFI_PASS: leave empty to provision at runtime via SmartConfig (below).
#    - WEB_USER / WEB_PASS: they gate the dashboard's state-changing endpoints
#      (/addblock, /unblock, /upload, /update) and network OTA.
cp config.env.example config.env
#    then edit config.env

# 2. build the blocklist Bloom filter (default = StevenBlack + Hagezi Ultimate + OISD Big
#    + Hagezi DoH/DoT + Hagezi TIF.mini + Turtlecute + EasyList + EasyPrivacy + hBlock
#    + AdGuard Annoyances/MobileApp → ~631k domains after pruning)
python3 tools/build_bin_list_block.py data/blocklist.bin

# 3. flash firmware + the blocklist filesystem (the one and only USB flash)
pio run -e esp8266 -t upload          # -e esp32dev | c3 | esp32s3 for the ESP32 family
pio run -e esp8266 -t uploadfs

# 4. watch it boot, note the IP / open the dashboard
pio device monitor                    # -> http://esp-adblock.local
```

### Your own blocklists

`build_bin_list_block.py OUT.bin [SOURCE ...]` takes any mix of URLs and local files, in any of
these formats:

- **hosts files** — `0.0.0.0 ads.example.com tracker.example.com` (all domains on the line are included)
- **plain domain lists** — one domain per line
- **AdGuard / Adblock basic rules** — `||ads.example.com^` blocks, `@@||ok.example.com^`
  removes a domain (e.g. to mirror an AdGuard Home allowlist)
- **Hostname regexes** — AdGuard `/regex/` rules whose pattern contains no `/` or `:`
  (anything else is a URL rule a DNS sinkhole can't apply) are collected into the bin's
  `RGX1` section. Add your own with `--regex FILE` (one pattern per line).

**Strict, safe extraction.** From a network rule only a bare host is accepted: `||host^`
(or `||host`, or a plain/`hosts` line whose leading `*.` is the usual "domain + subdomains"
wildcard). **Any** `/`, `*`, `?`, `$` or `|` in the rule drops it — those mean the rule is
scoped finer than DNS can honour, and generalizing to the host would over-block. The classic
case: `||connect.facebook.net/signals/$third-party` is path-scoped on purpose (that host also
serves the login SDK), so it is **not** turned into a whole-host block. Cosmetic/scriptlet
(`##`, `#@#`, `#$#`, `#%#`, `#?#`), `$` modifiers, `|...|` anchors, wildcards, IPv4/IPv6 and
malformed names are all discarded and counted (`skipped rules` / `rejected entries`).

Entries covered by a parent rule are pruned (`x.ads.example.com` is dropped when
`ads.example.com` is already present), and `--bits N` trades bitmap size for the
false-positive rate. The file is **`BLM2`** by default (the `GAFM` telemetry section, see below);
it falls back to plain **`BLM1`** only with `--no-gafam` and no regex. `RGX1` carries the
hostname regexes when `--regex` is used. An `@@` rule only un-blocks that exact entry — it
can't carve a subdomain out of a blocked parent. If a source can't be downloaded the build
stops instead of silently producing a smaller list (`--allow-missing` to override).

The hostname regex engine (firmware) supports literals, `.`, `*`, `+`, `?`, `[abc]`/`[^abc]`
with ranges, `\` escape, `^`/`$` anchors and top-level `|` alternation — case-insensitive,
**unanchored search** (add `$` for precision). It runs only on a bloom miss, matched against
the host and each parent suffix. No groups/backreferences.

### Destination map data

The map and the country table are generated, not hand-edited:

```bash
python3 tools/build_geo_table.py dbip-country-lite-YYYY-MM.csv.gz   # -> src/geo_table.h
python3 tools/build_world_svg.py ne_110m_admin_0_countries.geojson  # -> web/world.svg
```

`src/geo_table.h` is 16 KB: one byte per `/14` IPv4 block, looked up with `ip >> 18` (one flash
read, no search, no RAM index). A block keeps its majority country only when that country holds
at least 60% of the block (`--min-share`); below that it is `255` and the map leaves it grey
instead of painting a wrong country. The counters are RAM-only, so the card reads "since
reboot". Data: [DB-IP](https://db-ip.com) Lite (**CC BY 4.0** — attribution is required);
regenerate monthly, a stale table paints stale countries. The SVG is Natural Earth 110m
(public domain), projected and simplified by the tool.

### WiFi setup (no re-flash needed)

There is **no captive portal**. WiFi is provisioned in this order at boot:
**`/wifi.cfg` (baked from `config.env`) → NVS (SmartConfig) → `config.env` defaults**.
- **Pre-flash (recommended):** set `WIFI_SSID`/`WIFI_PASS` in `config.env` — baked into
  `data/wifi.cfg`, so `pio run -t uploadfs` alone re-provisions over USB.
- **SmartConfig / ESP-Touch:** leave `WIFI_SSID` empty; use the ESP-Touch app on a **2.4 GHz**
  phone to push the SSID/password (no open AP, no BLE). Credentials are stored in NVS.
- **Reset:** hold **BOOT** at power-on, or change the network from **Advanced settings → Wi-Fi → Change** (scan → pick → password; the device tests it before saving and keeps the old network if it fails — it preserves the static IP/gateway/DNS/host settings, so BOOT-hold is the only reset that clears those).

## Over-the-air updates (no more USB)

The dashboard at **http://esp-adblock.local** does it all:

- **Blocklist** — drop a freshly built `blocklist.bin` into *Blocklist → Upload*, or paste a
  URL and press **Download & upload**: the **browser** fetches the file (it does HTTPS) and
  POSTs it to `/upload`. The device never does TLS, so it is the same path on ESP8266 and
  ESP32. The URL must allow CORS — `raw.githubusercontent.com` and `cdn.jsdelivr.net` do; a
  GitHub *release* asset does not (open it in a tab and drop the file in *Upload* instead).
  A fresh default list is rebuilt **every Monday** by CI and published CORS-friendly at
  `https://raw.githubusercontent.com/joaoeudes7/esp-adblock/blocklist/blocklist.bin`
  (and as the `blocklist` release asset).
- **Firmware** — upload `.pio/build/<env>/firmware.bin` under *Firmware → OTA update*; the
  device verifies it and reboots into the new image. Or push over WiFi from the CLI:
  ```bash
  pio run -e esp8266 -t upload --upload-port esp-adblock.local --upload-protocol espota
  ```

**Flash layout:** the ESP8266 `4m2m` build gives a 2 MB blocklist filesystem plus a **~1 MB OTA
region**, so **firmware OTA over WiFi works** (`POST /update`, or `pio -t upload --upload-port <ip>`).
Switch to `eagle.flash.4m1m.ld` (~1 MB FS) only if you'd rather have a smaller filesystem. The
Bloom blocklist is compact — ~1.5 byte/domain, i.e. **~1.9M domains** fit in a 2 MB filesystem
(`--bits N` trades size for false-positive rate).

## Security

`/stats.json` and `/events` require **HTTP Basic Auth** too (they carry the client
list and the blocked-event log). Every state-changing endpoint requires Basic Auth
(`WEB_USER`/`WEB_PASS`, set in `config.env`) **plus** the `X-Requested-With: esp-adblock`
CSRF header:

- `/addblock`, `/unblock`, `/addkeyword`, `/delkeyword`, `/delallow`, `/setname`, `/pauseclient`
- `/pause`, `/resume`, `/resetstats`, `/setblock`, `/setdns`
- `/sethost`, `/delhost`, `/setsyslog`, `/setproxy`
- `/setwifi`, `/scan`
- `/upload`, `/update` (blocklist and firmware OTA), `/rules` (POST)

`/allow` and `/proxy.pac` are CSRF-gated read/one-shot endpoints used by the block page
and by client OSes (no Basic auth).

Network OTA (`ArduinoOTA`, e.g. `pio run -t upload --upload-port esp-adblock.local
--upload-protocol espota`) requires the same `WEB_PASS`.

Without this, anyone who could reach the device on the LAN could reflash it
with arbitrary firmware or rewrite the blocklist with zero credentials — worth
knowing given the device sits in the path of every DNS query on your network.
Custom blocked-domain names are also HTML-escaped before being rendered on the
dashboard, closing a stored-XSS path where a domain string containing markup
(added via `/addblock`) would otherwise execute in the viewing browser.

**Basic Auth here is a LAN-trust-boundary control, not encryption.** Everything
is plain HTTP on :80 — this chip has no realistic budget to run a TLS server.
Basic Auth credentials are base64 (not encrypted) and sent on every authenticated
request; anyone who can already sniff your LAN traffic (open/guest WiFi, ARP
spoofing) can read them off the wire. This hardens against the common case —
another device on your network hitting the API with no credentials at all, or a
browser tab CSRF'ing it — not against an on-path network attacker.

**CSRF via cached Basic Auth:** browsers auto-attach cached Basic Auth
credentials to *any* subsequent request to an already-authenticated origin —
including one triggered by a totally unrelated page the same browser visits
later (e.g. `<img src="http://esp-adblock.local/resetstats">`, no JS required).
That would let any webpage silently drive this API once you've logged into the
dashboard once, regardless of who's on your LAN. Every mutating endpoint above
now also requires a custom `X-Requested-With: esp-adblock` header, which a plain
`<img>`/auto-submitted `<form>` CSRF can't attach (only same-origin `fetch()`
can, which is what the dashboard's own JS does).

**Default credentials:** if `config.env` still has the placeholder
`WEB_PASS=change-me-please` value from `config.env.example`, the device boots with a
"password" that's public (it's sitting in this repo's example file). The firmware logs a
warning over serial and shows a banner on the dashboard when this is the case — but it will
still boot and run, so don't skip setting real values in `config.env` before trusting
this on a network you don't fully control.

Out of scope for now: the WiFi setup portal's access point (`ESP-ADBlock-XXXX`)
is still open (unencrypted) by design — it needs to be joinable without knowing
a password first. The real WiFi password you type into the portal is only as
safe as that local radio link during the brief setup window.

## Use it

Point a device's DNS at the C3's IP, or add it as a **secondary resolver** behind
your main DNS. Test:

```bash
dig @<esp-ip> doubleclick.net   # -> <esp-ip>  (blocked -> block page; 0.0.0.0 only with BLOCK_MODE=zero)
dig @<esp-ip> github.com        # -> real IP  (forwarded)
```

## Gotchas (learned the hard way)

- **ModemManager** (default on Fedora/Ubuntu) grabs `/dev/ttyACM0` and toggles
  DTR/RTS, which **resets the C3** and blocks serial. Fix:
  ```bash
  sudo systemctl stop ModemManager
  echo 'ATTRS{idVendor}=="303a", ENV{ID_MM_DEVICE_IGNORE}="1"' | sudo tee /etc/udev/rules.d/99-esp-no-modemmanager.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
  ```
- The C3's USB-Serial-JTAG console can swallow early boot output until the host
  connects (`while(!Serial)` helps).
- DNS clients add an **EDNS OPT** record; a blocked reply must contain only the
  question + answer (ANCOUNT=1, NSCOUNT=ARCOUNT=0) or it's malformed.

## Done / how it could grow

- ✅ Web dashboard — per-client block/allow counts, add custom domains
- ✅ mDNS (`esp-adblock.local`) for discovery
- ✅ OTA — firmware + blocklist update over WiFi (the blocklist is fetched by the browser over HTTPS, then POSTed to `/upload`; the device does no TLS)
- ✅ WiFi provisioning — baked `config.env` → SmartConfig (ESP-Touch), no captive portal
- ✅ Browser installer — Web Serial/WebUSB flash + Improv Wi-Fi serial provisioning (`installer/`)
- ✅ Dashboard insight — destination map, GAFM share, DNSSEC `AD` percentage, counters persisted across reboots
- ✅ Lookup cost — the Bloom filter probes ~2 flash reads/query cold (<1 warm), because non-members short-circuit on the first zero bit. The old "~18 reads/lookup" prefix-index item is obsolete.
- ⬜ Act as the DHCP server (hand itself out as DNS) for true plug-and-play

## Credits & License

Fork of [M-Abozaid/esp32-c3-adblock](https://github.com/M-Abozaid/esp32-c3-adblock)
(MIT © 2026 zed), which is *inspired by* [s60sc/ESP32_AdBlocker](https://github.com/s60sc/ESP32_AdBlocker)
— the "answer 0.0.0.0 for blocklisted domains" idea.

This fork adds the **ESP8266** target, the **Bloom-filter** blocklist, the rewritten dashboard,
user rules, the DNS-rebinding guard, metrics, and more.

Licensed under **MIT** — see [LICENSE](LICENSE). The original copyright notice is retained.
IP geolocation data: **DB-IP Lite** (CC BY 4.0), via `tools/build_geo_table.py`.

---

# ESP8266 port (fork notes)

This fork adds an **ESP8266** target and two lookup/forwarding upgrades. Everything is
selected per-platform with `#if defined(ESP8266)`; the ESP32-C3/ESP32 builds stay.

## Build & flash (ESP8266)
```bash
pio run -e esp8266                 # firmware
python tools/build_bin_list_block.py data/blocklist.bin   # blocklist -> BLM1 bloom blob
pio run -e esp8266 -t buildfs      # LittleFS image (blocklist)
pio run -e esp8266 -t upload       # flash firmware
pio run -e esp8266 -t uploadfs     # flash filesystem (blocklist)
```

## What's different on the ESP8266
- **No RAM-resident blocklist.** ~40 KB free heap can't hold an index. The blocklist is a
  **Bloom filter bitmap in flash** (`BLM1` header + bits), probed with `k=7` FNV-1a
  hashes. ~**1.5 byte/domain** at ~0.8% false positive → ~4x more domains than the
  original 40-bit sorted-hash design. The bitmap grows with the list; the ESP-12 (4 MB,
  `4m2m` = 2 MB FS) holds **~1.6 M domains**.
- **`tools/build_bin_list_block.py`** replaces the sorted-hash tool (the firmware now only reads
  `BLM1`). Same source parsing (hosts / domain lists / AdGuard rules, `@@` allowlist).
- **Async DNS forwarder.** The old forwarder blocked ~1 s per query (freezing web/OTA and
  serializing lookups). Queries are now sent upstream immediately and matched by txid in a
  small in-flight table; replies are relayed from `pollUpstream()` in the main loop.
- **TTL-aware response cache** (`/stats.json` → `cached`) for repeated domains.
- `Preferences` → EEPROM shim, `Updater` API, BearSSL TLS (small buffers), `ESP8266mDNS`.
- **HTML lives in `web/*.html`** (real files) and is inlined into `src/page.h` at build time
  by `tools/build_web.py` (extra_scripts) — served from flash, no FS dependency. Edit the
  `.html`, rebuild. `web/index.html` = dashboard; `web/blocked.html` = block page (`{{HOST}}`/`{{REASON}}`);
  `web/world.svg` = destination map (`WORLD_SVG`, served at `/world.svg`).

## WiFi provisioning (SmartConfig / ESP-Touch only)
Order at boot: **`/wifi.cfg` (baked) → NVS (SmartConfig) → `secrets.h`**. No captive portal.
- **Pre-flash (recommended, zero runtime cost):** fill `config.env` (from `config.env.example`)
  and `pio run -t upload`. `tools/gen_config.py` bakes `src/secrets.h` (firmware) **and**
  `data/wifi.cfg` (read at boot) — so `pio run -t uploadfs` alone re-provisions WiFi without
  recompiling. Optional **static IP**: `WIFI_IP`/`WIFI_GW`/`WIFI_DNS`; DHCP name `WIFI_HOST` (default `esp-adblock`).
  The **forwarding resolver(s)** for clients are `UPSTREAM_DNS` in `config.env` (comma-separated, baked at build; default Cloudflare `1.1.1.1`). The device keeps probing them and uses the fastest; edit the list at runtime from **Advanced settings → Upstream DNS** (or `/setdns`).
- **SmartConfig / ESP-Touch** — app on a **2.4 GHz** phone pushes SSID/password (no AP, no
  BLE, nothing visible). 120 s window; creds saved to NVS. Use when `WIFI_SSID` is empty.
- **Configured but link down** → reboot + retry.
- **Hold BOOT at power-on** to force re-provisioning, or change the network at runtime from the dashboard (**Advanced settings → Wi-Fi → Change** → `GET /scan` + `GET /setwifi?ssid=&pass=`; the new network is tested before it is saved, and the old one is kept if it fails).
- **Auth:** dashboard Basic Auth uses fixed user `admin` + the `WEB_PASS` from `config.env` (the same credentials gate network OTA).

## Block page + allow
Blocked A records resolve to the **ESP's own IP**, so an HTTP client gets a "why is this
blocked" page (reason + **"Allow this site"** and **"Continue for 5 minutes"**) instead of a dead `0.0.0.0`.
The buttons call `GET /allow?d=<host>` (and `&s=300` for the temporary one; CSRF-gated, no
Basic auth): *Allow* adds the domain to `/rules.cfg` (`allow <domain>`), *Continue* holds it in
a small RAM table (`MAX_TEMPALLOW`, up to 24 h) that is gone after a reboot. HTTP only — HTTPS still shows a
cert error (standard sinkhole limit). Finding the device's IP: serial `WiFi up: <ip>`, mDNS
`esp-adblock.local`, the router's DHCP list (`WIFI_HOST`), or `GET /stats.json` → `ip`.

## Notes / ceilings
- `4m2m` (2 MB FS) plus a ~1 MB OTA region — **firmware OTA over WiFi works** (`POST /update`).
  Use `eagle.flash.4m1m.ld` (1 MB FS) if you prefer a smaller filesystem.
- Bloom false positives (~0.8%) can block a rare legitimate domain; subdomains are covered
  by the query-time suffix matching.
- Statistics: `domains` = real count from the header; `cached` = served from the response cache;
  totals persist in `/stats.cfg`. The destination map is RAM-only ("since reboot").
