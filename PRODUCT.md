# Product

## Register

product

## Users
Owner/operator of a home or small network who runs an ESP (ESP8266/ESP32) as a DNS
sinkhole. Not a dedicated network engineer: they want to plug it in, point their devices
at the DNS, and see — without jargon — that it is blocking ads. They use it from both a
phone and a desktop.

## Product Purpose
Give local control and visibility over ad/tracker blocking: where to point the DNS, what
is blocked right now, which devices use the network, and the occasional adjustment (allow
a domain, pause blocking, upload a blocklist). Success = the person understands the state
in seconds and needs no SSH/serial for everyday use.

## Brand Personality
Friendly, simple, direct. People-to-people tone: short sentences, imperative verbs,
an explanation where a newcomer gets stuck (e.g. "use the IP, not the name"). Calm and
trustworthy, without needless jargon or ornamentation.

## Anti-references
Generic SaaS: a grid of identical cards, a hero number with a tiny label, a gradient on
the title, an uppercase "eyebrow" on every section, a colored side border, exaggeratedly
rounded corners. A cluttered admin panel: everything exposed at once, washed-out gray,
borders everywhere.

## Design Principles
1. Task first: what to do (point the DNS) and what is happening (blocking) come before
   configuration.
2. Explain what is not obvious; do not repeat the obvious.
3. Show state, don't decorate: color and motion only to indicate state.
4. Hide the advanced behind one step; the default screen is short.
5. Consistency over surprise: a single vocabulary of buttons, fields, and tables.

## Accessibility & Inclusion
Text contrast ≥4.5:1 (muted labels too). Comfortable touch targets on mobile.
`prefers-reduced-motion` respected (transitions become instant). No state depends on
color alone.
