#!/usr/bin/env python3
"""Bake build-time config from `config.env` into the firmware + filesystem.

Run automatically by PlatformIO (see `extra_scripts` in platformio.ini), or by hand:
    python tools/gen_config.py

Reads <project>/config.env (gitignored) and writes:
    src/secrets.h   -> WIFI_SSID/WIFI_PASS/WEB_USER/WEB_PASS/WIFI_IP/WIFI_GW/WIFI_DNS/WIFI_HOST
    data/wifi.cfg   -> WIFI_SSID=/WIFI_PASS=/WIFI_IP=/WIFI_GW=/WIFI_DNS=/WIFI_HOST= (read at boot)
    data/dns.cfg    -> upstream resolver list, one IPv4 per line

If config.env is absent, nothing is written unless src/secrets.h is also missing,
in which case it is seeded from config.env.example defaults. Existing files are left
untouched when there is no config.env, so a plain `pio run` still works.
"""
import os

try:
    Import("env")                       # noqa: F821  (PlatformIO SCons context)
    ROOT = env.subst("$PROJECT_DIR")    # noqa: F821
except Exception:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CFG = os.path.join(ROOT, "config.env")
SECRETS = os.path.join(ROOT, "src", "secrets.h")
WIFICFG = os.path.join(ROOT, "data", "wifi.cfg")
BLOCKCFG = os.path.join(ROOT, "data", "block.cfg")
SYSLOGCFG = os.path.join(ROOT, "data", "syslog.cfg")
DNSCFG = os.path.join(ROOT, "data", "dns.cfg")

def parse(path):
    out = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip().upper()] = v.strip()
    return out

def cstr(v):
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

def main():
    cfg = CFG
    if not os.path.exists(cfg):
        if os.path.exists(SECRETS):
            print("[gen_config] no config.env — leaving secrets.h/wifi.cfg as-is")
            return
        alt = os.path.join(ROOT, "config.env.example")
        if not os.path.exists(alt):
            print("[gen_config] no config.env and no example — skipping")
            return
        cfg = alt
        print("[gen_config] no config.env — seeding src/secrets.h from config.env.example")
    c = parse(cfg)
    ssid = c.get("WIFI_SSID", "")
    pasw = c.get("WIFI_PASS", "")
    user = c.get("WEB_USER", "admin")
    web = c.get("WEB_PASS") or "change-me-please"
    ip = c.get("WIFI_IP", "")
    gw = c.get("WIFI_GW", "")
    dns = c.get("WIFI_DNS", "")
    host = c.get("WIFI_HOST", "esp-adblock")

    os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
    with open(SECRETS, "w", encoding="utf-8") as f:
        f.write("#pragma once\n// GENERATED from config.env by tools/gen_config.py — do not edit.\n")
        f.write("static const char* WIFI_SSID = %s;\n" % cstr(ssid or "YOUR_WIFI_SSID"))
        f.write("static const char* WIFI_PASS = %s;\n" % cstr(pasw or "YOUR_WIFI_PASSWORD"))
        f.write("static const char* WEB_USER = %s;\n" % cstr(user))
        f.write("static const char* WEB_PASS = %s;\n" % cstr(web))
        f.write("static const char* WIFI_IP = %s;\n" % cstr(ip))
        f.write("static const char* WIFI_GW = %s;\n" % cstr(gw))
        f.write("static const char* WIFI_DNS = %s;\n" % cstr(dns))
        f.write("static const char* WIFI_HOST = %s;\n" % cstr(host))
        f.write("// forwarding resolvers for clients; fastest probe wins (config.env UPSTREAM_DNS)\n")
        ups = []
        for u in c.get("UPSTREAM_DNS", "1.1.1.1").replace(";", ",").split(","):
            u = u.strip()
            o = u.split(".")
            if len(o) == 4 and all(x.isdigit() and 0 <= int(x) <= 255 for x in o) and u != "0.0.0.0" and u not in ups:
                ups.append(u)
        if not ups:
            ups = ["1.1.1.1"]
        f.write("#define UPSTREAM_DNS_LIST %s\n" % cstr(",".join(ups[:4])))
        f.write("// privacy/security header level 0..3 (config.env PRIVACY_LEVEL)\n#define SEC_LEVEL %s\n" % (c.get("PRIVACY_LEVEL", "2").strip() if c.get("PRIVACY_LEVEL", "2").strip() in ("0", "1", "2", "3") else "2"))

    os.makedirs(os.path.dirname(WIFICFG), exist_ok=True)
    with open(WIFICFG, "w", encoding="utf-8") as f:
        f.write("WIFI_SSID=%s\n" % ssid)
        f.write("WIFI_PASS=%s\n" % pasw)
        f.write("WIFI_IP=%s\n" % ip)
        f.write("WIFI_GW=%s\n" % gw)
        f.write("WIFI_DNS=%s\n" % dns)
        f.write("WIFI_HOST=%s\n" % host)

    with open(BLOCKCFG, "w", encoding="utf-8") as f:
        f.write(c.get("BLOCK_MODE", "ip").strip() + "\n")
        f.write(("1" if c.get("IPV4_ONLY", "1").strip().lower() in ("1", "true", "yes") else "0") + "\n")
        f.write(("1" if c.get("KEYWORD_BLOCK", "1").strip().lower() in ("1", "true", "yes") else "0") + "\n")
        f.write(("1" if c.get("REBIND_GUARD", "0").strip().lower() in ("1", "true", "yes") else "0") + "\n")
        try:
            ss = max(0, min(15, int(c.get("SAFESEARCH", "0").strip() or "0")))   # bitmask 1=Google 2=YouTube 4=Bing 8=DDG
        except ValueError:
            ss = 0
        f.write("%d\n" % ss)
    with open(SYSLOGCFG, "w", encoding="utf-8") as f:
        f.write(c.get("SYSLOG_HOST", "").strip() + "\n")
        f.write(c.get("SYSLOG_PORT", "514").strip() + "\n")

    os.makedirs(os.path.dirname(DNSCFG), exist_ok=True)
    with open(DNSCFG, "w", encoding="utf-8") as f:
        for u in ups:
            f.write(u + "\n")

    print("[gen_config] wrote src/secrets.h + data/wifi.cfg  (ssid=%r)" % ssid)

main()
