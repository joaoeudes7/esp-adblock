# Web installer

Static, framework-free page that flashes the firmware over **Web Serial** (esptool-js) or
**WebUSB** (CH340/CH341), then provisions Wi-Fi over the same cable using **Improv Wi-Fi
Serial** — the protocol ESP Web Tools / Tasmota / ESPHome use.

## Build + serve

```sh
# 1. compile the targets you want to publish (firmware + optional filesystem image)
pio run -e esp8266 && pio run -t buildfs -e esp8266
pio run -e c3       && pio run -t buildfs -e c3

# 2. assemble the binaries + manifest (offsets + SHA-256)
python3 tools/build_installer.py

# 3. serve it (Web Serial needs a secure context: https or localhost)
python3 -m http.server -d installer 8000     # -> http://localhost:8000/
```

`installer/fw/` and `installer/manifest.json` are generated; only `index.html` is committed.

## What the page does

1. **Install** — board + serial port, chip auto-detected (refuses on a board mismatch), each
   part fetched and SHA-256 checked, then flashed at the offsets from `partitions.csv`
   (bootloader / partition table / boot_app0 / app / filesystem). When esptool-js reports
   progress the page also passes an MD5 callback, so the written flash is read back and
   verified.
2. **Configure Wi-Fi** — reopens the port and speaks **Improv Wi-Fi Serial**:
   *current state*, *device info*, **network scan** (fills the SSID list) and *send Wi-Fi
   settings*, plus *set hostname*. No reflash to change networks.
   A **static IP** (advanced section) is outside Improv, so filling it switches to the
   plain-text `CFG` protocol instead.
3. **Baked config** — optionally pre-configure `config.env`, rebuild, and the flashed image
   carries `/wifi.cfg` + `secrets.h` already. Credentials then live inside the public
   `.bin` — use only for a build you control.

## Requirements

Chromium-based desktop browser (Chrome/Edge/Opera) with Web Serial, or WebUSB for a CH340
bridge. Firefox, Safari and mobile lack both. Serve over HTTPS or `localhost`.

esptool-js 0.7.0 is **vendored** at `vendor/esptool-js.js` (no CDN at runtime — same
supply-chain stance as the inlined Alpine in the dashboard). To update: download
`bundle.js` from the npm release and replace that file.

## Manifest

`tools/build_installer.py` emits both keys: `boards` (used by this page — labels, flash size,
SHA-256) and `builds` (`chipFamily` + `parts[].path`, the **ESP Web Tools** schema), so the
same `manifest.json` can also feed `<esp-web-install-button>` when hosted beside the binaries.

## Serial protocols (firmware side)

Improv Wi-Fi Serial (binary, `IMPROV` framed) is handled by `improvHandleRPC()`; the text
fallback is a line protocol:

```
CFG ssid <name>      CFG host <hostname>      CFG ip|gw|dns <address>      CFG commit
```

The device answers `CFGSAVED` (text) or the Improv state/result packets. Both paths write
`/wifi.cfg`, preserving unrelated keys (`UPSTREAM_DNS`, …). See the serial-provisioning section
of `src/main.cpp`.
