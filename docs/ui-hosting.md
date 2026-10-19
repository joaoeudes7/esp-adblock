# docs/ui-hosting.md — dashboard hosting: decisions

Status: **decided**. This records what the dashboard loads and where it lives, so the choices
aren't re-litigated later.

## What is in place today

| Asset | Where it lives | How it's delivered |
|---|---|---|
| Dashboard HTML/CSS + app JS | `web/index.html` | **inlined** into firmware (`tools/build_web.py` → `src/page.h`, PROGMEM) |
| Block page template | `web/blocked.html` | inlined (same step) |
| Destination map SVG | `web/world.svg` (built by `tools/build_world_svg.py`) | **inlined** into `src/page.h` (`WORLD_SVG`), served at `/world.svg` |
| **Alpine.js** 3 CSP build (declarative reactive state) | unpkg (`@alpinejs/csp@3.17.4`) | **CDN `<script src>`** — the browser downloads once and caches it; CSP allows `https://unpkg.com` |
| **Icons** (Lucide subset) | `web/index.html` (inline `LUCIDE` map + `createIcons`) | **inlined** — only the ~15 icons the page uses; no CDN, no runtime lib |
| **Favicons** (Recently blocked rows) | `icons.duckduckgo.com` | `<img>` from DuckDuckGo; URL cached in `localStorage` for 7 days, bytes cached by the browser (`img-src` allows that host) |
| **World map** (destination card) | `web/world.svg` | embedded in PROGMEM by `build_web.py`, served at `/world.svg` with an ETag and `max-age=86400` (browser-cached, separate from the dashboard body) |

Dashboard page ≈ **54 KB** minified in PROGMEM, plus a **~50 KB** inlined world SVG (`/world.svg`) fetched only by the map card. Alpine (~71 KB) is fetched from unpkg and cached by the browser. `MINIFY=0` disables minification.

## Decisions

1. **Keep the UI inline (option A).** No LittleFS/CDN for the app itself. Rationale: it's an
   appliance — a LAN with no internet must still serve the dashboard; inlining avoids a
   `fetch` dependency, version skew, and an extra `uploadfs`. Cost: the firmware binary is
   bigger and a UI change needs a reflash (acceptable here).
2. **Alpine comes from unpkg (pinned), not from firmware.** The `<script src>` points at
   `@alpinejs/csp@3.17.4`; the browser fetches once and caches it, so the firmware stays ~72 KB
   smaller. Trade-off: the panel UI needs internet on first load (the HTML shell still renders
   offline, but directives stay inert). Pin the exact version — `@3` would silently roll
   forward. `CSP_APP` must keep `https://unpkg.com` in `script-src`.
3. **Alpine CSP build — no `'unsafe-eval'`.** The page loads `@alpinejs/csp`, which
   parses directive expressions with its own AST evaluator instead of `new Function`. The firmware
   CSP stays at `script-src 'unsafe-inline'` (needed for the single inline script). Costs of that
   build: `x-data` must reference a registered component (`Alpine.data('dashboard', …)` →
   `x-data="dashboard"`), globals like `Math`/`Date` are not reachable from markup, and
   array/object literals and arrow functions are rejected — those moved into getters/methods.
4. **Favicons come from DuckDuckGo.** `favicon(host)` builds
   `https://icons.duckduckgo.com/ip3/<host>.ico?v=<ts>` and stores the URL per host in
   `localStorage` with a 7-day TTL; within the window every reload reuses the same URL (browser
   cache), after it the `?v=` changes and the icon is refetched. Privacy cost: each blocked host
   shown in the table is sent to DDG, which is the opposite of the zero-external-request stance —
   remove the `<img class=fav>` + `favicon()` if that matters. If DDG is unreachable, `@error`
   hides the image and the row still renders.
5. **Icons are inlined (subset), and Open Props was removed.** No icon font/library is loaded at
   runtime: the page ships a small `LUCIDE` map with only the icons it uses plus a ~10-line
   `createIcons()` that swaps `<i data-lucide>` for inline `<svg>`. Open Props was dropped
   because every token already had a hard-coded fallback in `var(--x, <fallback>)`. Result:
   **only Alpine is external.** Everything else (icons, CSS, app JS) is inlined, so the panel
   shell and the block page work offline; only the reactive UI needs the unpkg fetch.

**Offline behaviour:** the dashboard is fully self-contained — stats, controls, tables and
icons all render with no internet. The block page is equally self-contained.

## Vendoring third-party assets
Icons are inlined; keep new icons inside the `LUCIDE` map rather than adding a CDN. To update
Alpine, bump the pinned `@alpinejs/csp` version in `web/index.html` (CSP build, not the standard
one) and the host in `CSP_APP` if it ever moves.

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

## JS lib size (why Alpine)
| Lib | min | min+gzip | Note |
|---|---|---|---|
| lodash / underscore | 70 / 16 KB | 25 / 6 KB | bloat; not worth it |
| **Alpine.js (CSP build)** | ~71 KB | ~21 KB | **adopted** — declarative HTML, no eval, maintained |
| petite-vue | ~17 KB | ~6 KB | declarative, but frozen since 2022 |
| preact+htm | ~12 KB | ~4 KB | declarative in JS; JSX would need a build |
| VanJS | ~3 KB | ~1 KB | lightest, but imperative: UI in JS, manual `render()` |
| Sprae | ~13 KB | ~5 KB | declarative and tiny; new, ESM-first, API still moving |

The page is ~50 KB of HTML/CSS/JS in PROGMEM; Alpine is no longer embedded (browser cache).
That buys declarative templates (`x-for`/`x-model`/`x-show`) and deletes the manual
`render()`/DOM-id wiring, which is what made the code hard to read.
