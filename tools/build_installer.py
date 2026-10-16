#!/usr/bin/env python3
"""Assemble the static web installer from PlatformIO build output.

    pio run -e esp8266 && pio run -t buildfs -e esp8266
    python3 tools/build_installer.py

Copies each board's flash image(s) into `installer/fw/` and writes
`installer/manifest.json` (offsets + SHA-256) consumed by `installer/index.html`.
Boards whose firmware is not built are skipped; a missing filesystem image is
flagged (`partial`) but the firmware is still installable.

The tool is a plain copy step — configs can be baked first with `config.env`
(see tools/gen_config.py); the installer then flashes that pre-configured image.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, ".pio", "build")

# PlatformIO's own upload writes boot_app0.bin to 0xe000 (seeds the OTA-data partition);
# it lives in the framework package, not in .pio/build.
PIO_CORE = os.environ.get("PLATFORMIO_CORE_DIR", os.path.expanduser("~/.platformio"))
BOOT_APP0 = glob.glob(os.path.join(PIO_CORE, "packages", "framework-arduinoespressif32",
                                   "tools", "partitions", "boot_app0.bin"))

# ESP32 partitions: bootloader/partition-table/ota-data/app/FS offsets come from partitions.csv.
# ESP8266 (`eagle.flash.4m2m.ld`): app at 0x0, 2 MB LittleFS at 0x200000.
# `chipFamily` mirrors the ESP Web Tools manifest convention.
BOARDS = {
    "esp8266": {
        "label": "ESP8266 (ESP-12E, 4 MB)",
        "chipFamily": "ESP8266",
        "parts": [("firmware.bin", 0x000000), ("littlefs.bin", 0x200000)],
    },
    "esp32dev": {
        "label": "ESP32 (DevKit, 4 MB)",
        "chipFamily": "ESP32",
        "parts": [
            ("bootloader.bin", 0x001000),
            ("partitions.bin", 0x008000),
            ("boot_app0.bin", 0x00E000),
            ("firmware.bin", 0x010000),
            ("littlefs.bin", 0x2B0000),
        ],
    },
    "c3": {
        "label": "ESP32-C3 (4 MB)",
        "chipFamily": "ESP32-C3",
        "parts": [
            ("bootloader.bin", 0x000000),
            ("partitions.bin", 0x008000),
            ("boot_app0.bin", 0x00E000),
            ("firmware.bin", 0x010000),
            ("littlefs.bin", 0x2B0000),
        ],
    },
    "esp32s3": {
        "label": "ESP32-S3 (4 MB)",
        "chipFamily": "ESP32-S3",
        "parts": [
            ("bootloader.bin", 0x000000),
            ("partitions.bin", 0x008000),
            ("boot_app0.bin", 0x00E000),
            ("firmware.bin", 0x010000),
            ("littlefs.bin", 0x2B0000),
        ],
    },
}


def part_source(env, name):
    """Absolute path of a part's source .bin, or None if it isn't built."""
    if name == "boot_app0.bin":
        return BOOT_APP0[0] if BOOT_APP0 else None
    return os.path.join(BUILD, env, name)


def partition_offsets():
    """name -> offset parsed from partitions.csv (ESP32 layouts), or {} if absent."""
    csv = os.path.join(ROOT, "partitions.csv")
    out = {}
    if not os.path.exists(csv):
        return out
    with open(csv, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "," not in line:
                continue
            cols = [c.strip() for c in line.split(",")]
            if len(cols) < 4 or not cols[3].lower().startswith("0x"):
                continue
            try:
                out[cols[0]] = int(cols[3], 16)
            except ValueError:
                continue
    return out


# part file suffix -> expected partitions.csv entry (ESP32 only; ESP8266 has no table)
CSV_PART = {"firmware.bin": "app0", "littlefs.bin": "spiffs", "boot_app0.bin": "otadata"}




def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_version():
    """Short, monotonic label: the newest build mtime + date."""
    mtimes = []
    for env in BOARDS:
        for name, _ in BOARDS[env]["parts"]:
            p = part_source(env, name)
            if p and os.path.exists(p):
                mtimes.append(os.path.getmtime(p))
    stamp = time.strftime("%Y-%m-%d", time.localtime(max(mtimes))) if mtimes else "unknown"
    return "%s build" % stamp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "installer"), help="output dir (default: installer/)")
    ap.add_argument("--version", default=None, help="override the manifest version label")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    fwdir = os.path.join(out, "fw")
    shutil.rmtree(fwdir, ignore_errors=True)
    os.makedirs(fwdir, exist_ok=True)

    parts_csv = partition_offsets()

    manifest = {
        "name": "ESP AdBlock",
        "version": args.version or build_version(),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boards": {},
    }

    for env, meta in BOARDS.items():
        parts = []
        for name, offset in meta["parts"]:
            src = part_source(env, name)
            if not src or not os.path.exists(src):
                continue
            rel = "fw/%s-%s" % (env, name.replace(".bin", "") + ".bin")
            dst = os.path.join(out, rel)
            shutil.copyfile(src, dst)
            parts.append({"file": rel, "offset": offset, "size": os.path.getsize(dst), "sha256": sha256(dst)})
            print("[installer] %-8s %-16s @0x%06x  %7d B" % (env, name, offset, os.path.getsize(dst)))
        if not any(p["file"].endswith("-firmware.bin") for p in parts):
            print("[installer] %-8s skipped (run `pio run -e %s` first)" % (env, env))
            continue
        has_fs = any(p["file"].endswith("littlefs.bin") for p in parts)
        if not has_fs:
            print("[installer] %-8s WARN: no filesystem image (run `pio run -t buildfs -e %s`)" % (env, env))
        if env != "esp8266":
            if not any(p["file"].endswith("boot_app0.bin") for p in parts):
                print("[installer] %-8s WARN: boot_app0.bin not found — the device boots via the "
                      "blank-otadata fallback" % env)
            # Guard against drift: offsets must match the partition table the firmware was built with.
            for p in parts:
                name = os.path.basename(p["file"])[len(env) + 1:]
                key = CSV_PART.get(name)
                if key and key in parts_csv and p["offset"] != parts_csv[key]:
                    raise SystemExit("[installer] %s/%s offset 0x%06x != partitions.csv %s=0x%06x — "
                                     "update BOARDS in tools/build_installer.py"
                                     % (env, name, p["offset"], key, parts_csv[key]))
        manifest["boards"][env] = {
            "label": meta["label"],
            "chipFamily": meta["chipFamily"],
            "flashSize": "4MB",
            "partial": not has_fs,
            "parts": parts,
        }

    # ESP Web Tools compatible view (`builds` + `parts[].path`) so the same manifest
    # also feeds <esp-web-install-button> when hosted next to the binaries.
    manifest["builds"] = [
        {
            "chipFamily": b["chipFamily"],
            "parts": [{"path": p["file"], "offset": p["offset"]} for p in b["parts"]],
        }
        for b in manifest["boards"].values()
    ]

    if not manifest["boards"]:
        raise SystemExit("[installer] no build output found — build at least one environment first")

    manifest["default"] = "esp8266" if "esp8266" in manifest["boards"] else next(iter(manifest["boards"]))
    path = os.path.join(out, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    print("[installer] wrote %s (%d boards, %s)" % (path, len(manifest["boards"]), manifest["version"]))
    print("[installer] serve it: python3 -m http.server -d installer 8000  ->  http://localhost:8000/")


if __name__ == "__main__":
    main()
