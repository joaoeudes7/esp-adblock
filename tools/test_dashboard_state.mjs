#!/usr/bin/env node
// Runnable check for the dashboard's derived state (web/index.html).
// Evaluates the REAL inline script with DOM/fetch stubs and asserts the getters that
// replaced the old imperative render(). Run: node tools/test_dashboard_state.mjs
import { readFileSync } from 'node:fs'
import assert from 'node:assert'

const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8')
const src = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].pop()[1]

const STATS = {
  boot: 1,
  ip: '192.168.0.2',
  ver: '1.0',
  blocked: 750,
  allowed: 250,
  domains: 1000,
  gafam: [40, 10, 20, 10, 10, 10],
  dnss: [90, 100],
  pl: 2,
  ph: 6,
  pht: 10,
  php: 42,
  psv: 70,
  rssi: -50,
  dns: 20,
  geo: [
    ['US', 100],
    ['BR', 50],
  ],
  geoMapped: 150,
  clients: [
    { ip: '10.0.0.3', mac: 'aa:aa', name: 'TV', blocked: 5, allowed: 50, ps: 0 },
    { ip: '10.0.0.2', mac: 'bb:bb', name: '', blocked: 9, allowed: 1, ps: 120 },
  ],
  evSeq: 2,
  custom: ['a.example'],
  wild: [],
  hosts: [],
}

// /stats.json no longer carries the ring: the dashboard fetches it by cursor from /events.
const EVENTS = {
  last: 2,
  ev: [
    { seq: 1, host: 'track.example', cip: '10.0.0.3' },
    { seq: 2, host: 'ads.example', cip: '10.0.0.2' },
  ], // ascending, like the firmware's cursor page; the UI unshifts to newest-first
  more: false,
}

const el = () => ({
  classList: { add() {}, remove() {} },
  innerHTML: '',
  textContent: '',
  style: {},
  querySelectorAll: () => [],
})
const document = {
  getElementById: () => el(),
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ style: {}, setAttribute() {}, select() {}, remove() {} }),
  createElementNS: () => ({ setAttribute() {} }),
  addEventListener() {},
  body: { appendChild() {} },
}
const storage = () => ({ getItem: () => null, setItem() {}, removeItem() {} })
const fetchStub = async (url) => {
  if (url === '/stats.json') return { status: 200, ok: true, json: async () => STATS }
  if (url.startsWith('/events?')) return { status: 200, ok: true, json: async () => EVENTS }
  return { status: 200, ok: true, text: async () => '' }
}

const factory = new Function(
  'window',
  'document',
  'localStorage',
  'sessionStorage',
  'location',
  'fetch',
  'setInterval',
  'setTimeout',
  'MutationObserver',
  'navigator',
  `${src}\nreturn { state, load, fmt, fmtc }`,
)
const app = factory(
  { addEventListener() {} },
  document,
  storage(),
  storage(),
  { reload() {} },
  fetchStub,
  () => 0,
  (fn, d) => (d === 0 ? queueMicrotask(fn) : 0),
  class {
    observe() {}
  },
  {},
)

await app.load()
await new Promise((r) => setImmediate(r))
const { state, fmt, fmtc } = app

assert.equal(state.s.ip, '192.168.0.2', 'stats snapshot stored')
assert.equal(state.conn, 'online', 'connection goes online on success')

// KPI / bar percentages
assert.equal(state.pct, 75)
assert.equal(state.hPct, 60)
assert.equal(state.allPct, 68)
assert.equal(state.gf[0].pct, 40, 'provider share')
assert.equal(state.gafTotal, 90, 'GAFM share ignores "other"')
assert.equal(state.dnssPct, 90)
assert.equal(state.privText, '6/10 security headers served')
assert.equal(state.plLine, 'standard · 42 pages shielded')

// destination map: sorted by count, share of mapped lookups
assert.equal(state.geoTop[0].cc, 'US')
assert.equal(state.geoTop[0].pct, 67)
assert.equal(state.geoTop[1].cc, 'BR')
assert.ok(state.geoFoot.includes('150'), 'footer reports mapped lookups')

// elenco derivado: sort default blocked desc, then filter
assert.deepEqual(
  state.shownClients.map((c) => c.ip),
  ['10.0.0.2', '10.0.0.3'],
)
state.qc = 'tv'
assert.deepEqual(
  state.shownClients.map((c) => c.ip),
  ['10.0.0.3'],
  'filter by name, case-insensitive',
)
state.qc = ''
state.setSort('blocked')
assert.equal(state.sortDir, 1, 'clicking the active column flips direction')
assert.deepEqual(
  state.shownClients.map((c) => c.ip),
  ['10.0.0.3', '10.0.0.2'],
)
assert.equal(state.sortAria('blocked'), 'ascending')
assert.equal(state.arrow('blocked'), '▲')

// eventos recentes: filtro + ordem
assert.deepEqual(
  state.shownEvents.map((e) => e.seq),
  [2, 1],
  'newest first',
)
state.qe = 'ads'
assert.deepEqual(
  state.shownEvents.map((e) => e.host),
  ['ads.example'],
)
state.qe = ''

// status / formatação
assert.equal(state.statusText, 'Blocking active')
assert.equal(fmt(1234), (1234).toLocaleString())
assert.equal(fmtc(999), '999')
assert.equal(fmtc(1500), '1.5k')

console.log('dashboard derived state: all assertions passed')
