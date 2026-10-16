#!/usr/bin/env python3
"""Bake build-time config from `config.env` into the firmware + filesystem.

Run automatically by PlatformIO (see `extra_scripts` in platformio.ini), or by hand:
    python tools/gen_config.py

Reads <project>/config.env (gitignored) and writes:
    src/secrets.h   -> WIFI_SSID/WIFI_PASS/WEB_USER/WEB_PASS/WIFI_IP/WIFI_GW/WIFI_DNS/WIFI_HOST
    data/wifi.cfg   -> WIFI_SSID=/WIFI_PASS=/UPDATE_URL=/UPDATE_H= (read at boot)

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
    web = c.get("WEB_PASS", "CHANGE_ME_WEB_PASSWORD")
    ip = c.get("WIFI_IP", "")
    gw = c.get("WIFI_GW", "")
    dns = c.get("WIFI_DNS", "")
    host = c.get("WIFI_HOST", "c3adblock")

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

    os.makedirs(os.path.dirname(WIFICFG), exist_ok=True)
    with open(WIFICFG, "w", encoding="utf-8") as f:
        f.write("WIFI_SSID=%s\n" % ssid)
        f.write("WIFI_PASS=%s\n" % pasw)
        f.write("WIFI_IP=%s\n" % ip)
        f.write("WIFI_GW=%s\n" % gw)
        f.write("WIFI_DNS=%s\n" % dns)
        f.write("WIFI_HOST=%s\n" % host)
        f.write("UPDATE_URL=%s\n" % c.get("UPDATE_URL", ""))
        f.write("UPDATE_H=%s\n" % c.get("UPDATE_H", "24"))

    with open(BLOCKCFG, "w", encoding="utf-8") as f:
        f.write(c.get("BLOCK_MODE", "ip").strip() + "\n")
        f.write(("1" if c.get("IPV4_ONLY", "1").strip().lower() in ("1", "true", "yes") else "0") + "\n")
        f.write(("1" if c.get("KEYWORD_BLOCK", "1").strip().lower() in ("1", "true", "yes") else "0") + "\n")
        f.write(("1" if c.get("REBIND_GUARD", "0").strip().lower() in ("1", "true", "yes") else "0") + "\n")
    with open(SYSLOGCFG, "w", encoding="utf-8") as f:
        f.write(c.get("SYSLOG_HOST", "").strip() + "\n")
        f.write(c.get("SYSLOG_PORT", "514").strip() + "\n")

    print("[gen_config] wrote src/secrets.h + data/wifi.cfg  (ssid=%r)" % ssid)

main()
