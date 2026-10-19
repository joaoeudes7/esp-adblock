#!/usr/bin/env node
// Runnable check for the dashboard's auth/offline messaging (web/index.html).
// It extracts the REAL source of unauth()/showOffline()/load() and drives the branches,
// so a regression in the 401 handling fails here. Run: node tools/test_dashboard_auth.mjs
import { readFileSync } from 'node:fs'
import assert from 'node:assert'

const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8')
const script = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].pop()[1]

// brace-matched slice of `(async) function <name>(` .. its closing brace
function sliceFn(src, name) {
  let i = src.indexOf(`async function ${name}(`)
  if (i < 0) i = src.indexOf(`function ${name}(`)
  if (i < 0) throw new Error(`function ${name} not found`)
  let d = 0
  for (let j = src.indexOf('{', i); j < src.length; j++) {
    if (src[j] === '{') d++
    else if (src[j] === '}' && --d === 0) return src.slice(i, j + 1)
  }
  throw new Error(`unbalanced braces in ${name}`)
}

const body = ['unauth', 'showOffline', 'load'].map((n) => sliceFn(script, n)).join('\n')

// Minimal stubs for the globals load() touches (state/LU/etc. are no-ops).
const PREAMBLE = `
const el=()=>({style:{},dataset:{},classList:{add(){},remove(){}},replaceChildren(){},textContent:'',innerHTML:''})
const boot=el(), loadbar=el()
const state={s:null,ev:[],conn:'connecting',pauseIn:0,renderGeo(){}}
const loadRulesFile=()=>{}, LU=()=>{}
let lastOk=0, lastErr=false, bootSeen=null, evLast=0, rulesInit=1`

function harness(fetchImpl, store = {}) {
  const state = { reloads: 0 }
  const location = { reload: () => state.reloads++ }
  const sessionStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => (store[k] = String(v)),
    removeItem: (k) => delete store[k],
  }
  const factory = new Function(
    'fetch',
    'document',
    'sessionStorage',
    'location',
    `${PREAMBLE}\n${body}\nreturn {load, boot, err:()=>lastErr}`,
  )
  return {
    api: factory(fetchImpl, { getElementById: () => null, createTextNode: () => ({}) }, sessionStorage, location),
    state,
    store,
  }
}

// 1. fresh origin with no credentials: force exactly one reload (that navigation opens the prompt)
{
  const { api, state, store } = harness(async () => ({ status: 401, ok: false }))
  await api.load()
  assert.equal(state.reloads, 1, '401 must trigger exactly one reload')
  assert.equal(store.auth401, '1', '401 must be remembered across the reload')
}

// 2. after that reload (authRL set) the hint must be "login required", not "offline"
{
  const { api, state } = harness(async () => ({ status: 401, ok: false }), { authRL: '1' })
  await api.load()
  assert.equal(state.reloads, 0, 'no reload loop')
  assert.match(api.boot.innerHTML, /Login required/, 'must ask for login, not claim offline')
}

// 3. a thrown fetch is a real network error
{
  const { api } = harness(async () => {
    throw new Error('boom')
  })
  await api.load()
  assert.match(api.boot.innerHTML, /Can not reach the device/)
}

// 4. sticky: once a 401 was seen, a later flaky fetch still shows the login hint
{
  const { api } = harness(
    async () => {
      throw new Error('boom')
    },
    { authRL: '1', auth401: '1' },
  )
  await api.load()
  assert.match(api.boot.innerHTML, /Login required/)
}

// 5. success clears both flags, hides the overlay and shows no error
{
  const { api, store } = harness(async () => ({ status: 200, ok: true, json: async () => ({ boot: 1, ev: [] }) }), {
    authRL: '1',
    auth401: '1',
  })
  await api.load()
  assert.equal(store.authRL, undefined, 'authRL cleared on success')
  assert.equal(store.auth401, undefined, 'auth401 cleared on success')
  assert.equal(api.boot.innerHTML, '', 'no message on success')
  assert.equal(api.err(), false, 'lastErr false on success')
}

console.log('dashboard auth/offline messaging: all assertions passed')
