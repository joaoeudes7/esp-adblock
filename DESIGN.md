---
name: ESP ADBlock
description: A calm, plainspoken control panel for an ESP DNS ad-blocker.
colors:
  background: "#0d1117"
  surface: "#161b22"
  panel: "#1c2128"
  panel-hover: "#272e38"
  line: "#30363d"
  ink: "#e6edf3"
  muted: "#9aa4b2"
  success: "#3fb950"
  success-soft: "#2a5a37"
  danger: "#e5534b"
  danger-soft: "#5a2a2a"
  warning: "#e3b341"
  warning-bg: "#2a1717"
  warning-line: "#6e2b28"
  warning-ink: "#ffd9d5"
  lead: "#0f2318"
  flash: "#1f6f3d"
typography:
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  heading:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.3
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
    lineHeight: 1.4
  metric:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.1
rounded:
  sm: "8px"
  md: "10px"
  pill: "999px"
spacing:
  sm: "8px"
  md: "14px"
  lg: "26px"
components:
  button:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-hover:
    backgroundColor: "#272e38"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "7px 9px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "16px"
  badge:
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
---

# Design System: ESP ADBlock

## 1. Overview

**Creative North Star: "The Household Shield"**

A tool that a non-specialist opens on a phone to answer two questions: where do I point my
devices, and is it working. Everything else waits behind a fold. The surface is a quiet dark
panel, closer to a well-labeled appliance than to a product dashboard: one family, one accent,
one vocabulary of controls. It is calm because it is doing a small job very well, not because
it is being stylish.

The system explicitly rejects the generic SaaS look named in PRODUCT.md: no grid of identical
stat cards, no hero number with a tiny label, no gradient headings, no uppercase tracked
"eyebrow" above every section, no colored side-stripe borders, no over-rounded corners. It also
rejects the cluttered admin panel: everything exposed at once, washed-out gray, borders on
every side. Density is earned only where a table genuinely needs it.

**Key Characteristics:**
- One system sans, hierarchy by size + weight.
- One accent (green) reserved for primary action and "good" state.
- Flat surfaces, 1px hairlines, tonal layering. A single shadow, on toasts only.
- Advanced settings live behind one `<details>` fold; the default screen is short.
- Motion conveys state only, and is suppressed under `prefers-reduced-motion`.

## 2. Colors

A restrained slate ramp with two signal colors; the palette stays out of the user's way.

### Primary
- **Signal Green** (#3fb950): the one accent. Primary buttons ("Allow this site"), the
  "blocked" numerator and its ratio segment, the online badge, focus rings. Used on ≤10% of a
  screen; its rarity is what makes it read as "good".

### Secondary
- **Signal Red** (#e5534b): destructive and blocked states only (offline badge, "remove",
  the placeholder color of the ratio bar). Never decorative.

### Neutral
- **Deep Slate** (#0d1117): page background and input wells.
- **Panel Slate** (#161b22): cards, the table container, the header bar.
- **Raised Slate** (#1c2128): the one hover layer for table rows and buttons.
- **Hairline** (#30363d): all 1px borders and dividers. Depth comes from these, not shadows.
- **Chalk** (#e6edf3): primary text.
- **Pewter** (#9aa4b2): secondary text, labels, placeholders. Chosen to stay ≥4.5:1 on both
  Deep and Panel Slate (the common dark-UI failure is muted gray that misses 4.5:1).
- **Amber** (#e3b341): reserved for the paused/warning state.

### Named Rules
**The One Accent Rule.** Green is action and "good", red is destructive and "blocked", and
nothing else is colored. No third hue on the screen.

## 3. Typography

**Body Font:** system-ui stack (system-ui, -apple-system, Segoe UI, Roboto, sans-serif)
**Label/Mono Font:** same family; metrics use `font-variant-numeric: tabular-nums`.

**Character:** one family, no display/body pairing. Hierarchy is carried entirely by size and
weight, so the panel reads as instrument labels rather than editorial voice.

### Hierarchy
- **Metric** (700, 24px, 1.1): the summary counts (blocked / allowed / on the list). Tabular figures.
- **Heading** (650, 16px, 1.3): the app title and section headings. Sentence case, never uppercase.
- **Body** (400, 15px, 1.5): table cells, notes, form values.
- **Label** (500, 12.5px, 1.4): field labels, table headers, helper text, badges.

### Named Rules
**The Sentence-Case Rule.** No uppercase headings, no tracked-out eyebrows. Every label is a
word a person would say out loud.

## 4. Elevation

Flat by default. Depth is conveyed by tonal layering (Deep → Panel → Raised Slate) and 1px
hairlines, never by drop shadows on surfaces. A 1px border and a wide soft shadow are never
paired on the same element. The only shadow in the system is on toasts, which float above the
page and need to detach.

### Shadow Vocabulary
- **Toast only** (`box-shadow: 0 4px 14px rgba(0,0,0,.4)`): transient confirmations. Nothing else.

### Named Rules
**The Flat-By-Default Rule.** Cards are flat at rest; a border and a hover tint convey
structure and state. If an element looks like it is floating, it is a bug.

## 5. Components

One vocabulary of controls across every screen: same radius, same border, same hover.

### Buttons
- **Shape:** gently curved (8px radius).
- **Primary:** Signal Green fill, near-black text, used once where the eye should land
  ("Allow this site", the copy-IP action). Everything else is neutral.
- **Neutral:** Raised Slate fill, Hairline border, Chalk text; hover tints to #272e38.
- **Focus:** 2px Signal Green outline, offset 2px, via `:focus-visible`.
- **Disabled / loading:** 55% opacity, no pointer; the label states the action and the result
  lands as a toast.

### Cards / Containers
- **Corner Style:** gently curved (10px).
- **Background:** Panel Slate on Deep Slate.
- **Border:** 1px Hairline.
- **Shadow:** none (see Elevation).
- **Internal Padding:** 16px (md).

### Inputs / Fields
- **Style:** Deep Slate well, 1px Hairline stroke, 8px radius, Chalk text, Pewter placeholder.
- **Focus:** Signal Green outline (2px, offset 2px).
- **Toggles:** native checkboxes with a Pewter label; state is text + position, not color alone.

### Tables
- Rows separated by Hairline; header row in Pewter Label type; row hover with Raised Slate.
- Sortable headers are clickable with an inline ▼/▲ indicator; the whole row, not a chip.

### Advanced Fold
- A single `<details>` ("Advanced settings") holds every configuration surface. It opens to
  inset `h3` sub-headings; it is closed by default so the first screen stays short.

## 6. Do's and Don'ts

### Do:
- **Do** put the DNS address and the blocking state above the fold; everything else can wait.
- **Do** keep the green accent to ≤10% of any screen: primary action and "good" state only.
- **Do** use 1px Hairline borders and tonal layers for structure; no shadows on cards.
- **Do** keep all secondary text at Pewter (#9aa4b2) or lighter, verified ≥4.5:1 on the surface.
- **Do** label buttons with the action and say the outcome ("Allow this site", "Block", "Copy IP").
- **Do** keep sentence case everywhere; the only caps are acronyms (DNS, MAC, MQTT).

### Don't:
- **Don't** build a grid of identical stat cards, or a big number with a tiny label. That is the
  SaaS "hero metric" PRODUCT.md rejects; use the summary strip + ratio bar instead.
- **Don't** put an uppercase, letter-spaced "eyebrow" above sections.
- **Don't** use gradient text, glassmorphism, or colored side-stripe borders.
- **Don't** round cards past 12px, or pair a 1px border with a wide soft shadow (the ghost card).
- **Don't** expose every setting at once; the default screen must stay short.
- **Don't** rely on color alone for state; pair it with a word ("online", "Paused", "blocked").
