# docs/ui-hosting.md — dashboard hosting: decisions

Status: **decided**. This records what the dashboard loads and where it lives, so the choices
aren't re-litigated later.

## What is in place today

| Asset | Where it lives | How it's delivered |
|---|---|---|
| Dashboard HTML/CSS + app JS | `web/index.html` | **inlined** into firmware (`tools/build_web.py` → `src/page.h`, PROGMEM) |
| Block page template | `web/blocked.html` | inlined (same step) |
| **VanJS** 1.6.1 (reactive state) | `web/van.min.js` | **inlined** (`build_web.py` replaces the CDN `<script src=…van…>`) |
| **Lucide** 1.57.0 (icons) | — | **CDN** — `https://unpkg.com/lucide@1.57.0/dist/umd/lucide.min.js` |
| **Open Props** 1.7.23 (design tokens) | — | **CDN** — `https://unpkg.com/open-props@1.7.23/open-props.min.css` |

Dashboard page ≈ **24 KB** (inlined, PROGMEM). `MINIFY=0` disables minification.

## Decisions

1. **Keep the UI inline (option A).** No LittleFS/CDN for the app itself. Rationale: it's an
   appliance — a LAN with no internet must still serve the dashboard; inlining avoids a
   `fetch` dependency, version skew, and an extra `uploadfs`. Cost: the firmware binary is
   bigger and a UI change needs a reflash (acceptable here).
2. **VanJS is inlined, not CDN.** The reactive layer is *functional* (the UI wouldn't render
   without it), so it must work offline → `web/van.min.js` is vendored and inlined by the build.
3. **Lucide + Open Props stay on a CDN (pinned).** They are *decorative*: if the CDN is
   unreachable, the dashboard still renders — Lucide icons simply don't appear, and Open Props
   tokens fall back to the hard-coded values in every `var(--x, <fallback>)`. Pinned versions
   (`@1.57.0`, `@1.7.23`) avoid silent breakage.

**Offline behaviour:** the dashboard *works* offline (stats, controls, tables — all VanJS);
only the Lucide icons are missing. The block page is fully self-contained.

## If you later want 100% offline
Vendor Lucide + Open Props into the repo and inline them the same way as VanJS (extend
`build_web.py`). Cost: ~40 KB more in the firmware binary (the Open Props bundle is ~29 KB, the
Lucide UMD ~450 KB — prefer importing only the Lucide icons actually used).

## Alternatives considered (kept for reference)
| Option | Where the JS/CSS lives | Firmware | Offline? |
|---|---|---|---|
| **A. Inline** *(chosen)* | firmware flash | large (~24 KB) | ✅ works |
| B. LittleFS | `data/` (FS image) | small | ✅ works |
| C. Hosted (CDN/Pages) | CDN / GitHub Pages / jsDelivr | minimal | ❌ breaks offline |

- **B** would shrink the `.bin` (~24 KB moves to `littlefs.bin`) and still work offline, at the
  cost of an `uploadfs` per UI change. Good middle ground if binary size ever matters.
- **C** minimizes the firmware but depends on the internet, adds version skew, and weakens the
  security posture (a compromised CDN injects JS that then talks to the ESP). Not chosen.

## JS lib size (why VanJS)
| Lib | min | min+gzip | Note |
|---|---|---|---|
| lodash / underscore | 70 / 16 KB | 25 / 6 KB | bloat; not worth it |
| Alpine.js | ~44 KB | ~15 KB | declarative |
| petite-vue | ~17 KB | ~6 KB | declarative |
| preact+htm | ~12 KB | ~4 KB | declarative in JS |
| **VanJS** | ~3 KB | **~1 KB** | **adopted** — lightest reactive option |
