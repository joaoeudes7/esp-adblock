# docs/ui-hosting.md — dashboard hosting: decisions

Status: **decided**. This records what the dashboard loads and where it lives, so the choices
aren't re-litigated later.

## What is in place today

| Asset | Where it lives | How it's delivered |
|---|---|---|
| Dashboard HTML/CSS + app JS | `web/index.html` | **inlined** into firmware (`tools/build_web.py` → `src/page.h`, PROGMEM) |
| Block page template | `web/blocked.html` | inlined (same step) |
| **VanJS** 1.6.1 (reactive state) | `web/van.min.js` | **inlined** (`build_web.py` replaces the CDN `<script src=…van…>`) |
| **Icons** (Lucide subset) | `web/index.html` (inline `LUCIDE` map + `createIcons`) | **inlined** — only the ~15 icons the page uses; no CDN, no runtime lib |

Dashboard page ≈ **39 KB** (inlined, PROGMEM). `MINIFY=0` disables minification.

## Decisions

1. **Keep the UI inline (option A).** No LittleFS/CDN for the app itself. Rationale: it's an
   appliance — a LAN with no internet must still serve the dashboard; inlining avoids a
   `fetch` dependency, version skew, and an extra `uploadfs`. Cost: the firmware binary is
   bigger and a UI change needs a reflash (acceptable here).
2. **VanJS is inlined, not CDN.** The reactive layer is *functional* (the UI wouldn't render
   without it), so it must work offline → `web/van.min.js` is vendored and inlined by the build.
3. **Icons are inlined (subset), and Open Props was removed.** No third-party is loaded at
   runtime: the page ships a small `LUCIDE` map with only the icons it uses plus a ~10-line
   `createIcons()` that swaps `<i data-lucide>` for inline `<svg>`. Open Props was dropped
   because every token already had a hard-coded fallback in `var(--x, <fallback>)`. Result:
   **zero external requests** — the dashboard works fully offline, and nothing about a
   blocked host leaks to a CDN. (A typo'd CDN dependency can't break the panel either.)

**Offline behaviour:** the dashboard is fully self-contained — stats, controls, tables and
icons all render with no internet. The block page is equally self-contained.

## Vendoring third-party assets
Everything the panel needs is already inlined (VanJS + the icon subset). There is nothing
left to vendor; keep new icons inside the `LUCIDE` map rather than re-adding a CDN.

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
