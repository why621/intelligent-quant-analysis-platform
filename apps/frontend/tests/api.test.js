import assert from 'node:assert/strict'
import test from 'node:test'
import { api, request } from '../src/services/api.js'

function stub(t, fn) {
  const original = globalThis.fetch
  globalThis.fetch = fn
  t.after(() => { globalThis.fetch = original })
}

test('GET avoids unnecessary preflight; POST keeps JSON content type', async t => {
  const calls = []
  stub(t, async (_, options) => {
    calls.push(options)
    return Response.json({ status: 'ok' })
  })
  await api.getHealth()
  await api.createBacktest({ test: true })
  assert.equal(calls[0].headers['Content-Type'], undefined)
  assert.equal(calls[1].headers['Content-Type'], 'application/json')
  assert.ok(calls[0].signal instanceof AbortSignal)
})

for (const body of ['<html>SPA fallback</html>', 'null', '{bad']) {
  test(`invalid success body is rejected: ${body}`, async t => {
    stub(t, async () => new Response(body, { headers: {
      'content-type': body.startsWith('<') ? 'text/html' : 'application/json'
    } }))
    await assert.rejects(api.getHealth(), { code: 'INVALID_RESPONSE' })
  })
}

test('structured 503 remains actionable', async t => {
  stub(t, async () => Response.json({ error: { code: 'UPSTREAM_UNAVAILABLE' } }, { status: 503 }))
  await assert.rejects(api.getMarketOverview(), { code: 'UPSTREAM_UNAVAILABLE', status: 503 })
})

test('deadline bounds connection and response-body waits', async t => {
  let signal
  stub(t, async (_, options) => { signal = options.signal; return new Promise(() => {}) })
  await assert.rejects(request('/health', { timeoutMs: 10 }), { code: 'REQUEST_TIMEOUT' })
  assert.equal(signal.aborted, true)
  globalThis.fetch = async () => ({ ok: true, status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => new Promise(() => {}) })
  await assert.rejects(request('/health', { timeoutMs: 10 }), { code: 'REQUEST_TIMEOUT' })
})


test('research requests pin the loaded version; job recovery stays independent', async t => {
  const calls = []
  stub(t, async (url, options) => {
    calls.push([url, options.headers])
    return Response.json(url.endsWith('/data/status')
      ? { dataContext: { dataVersion: 'a'.repeat(64) } } : { items: [] })
  })
  await api.getDataStatus()
  await api.getCorrelation({ symbols: ['510300', '510500'] })
  await api.getStrategyRanking()
  await api.getAllocationSuggestion({ symbols: ['510300'] })
  await api.getBacktest('old-task')
  assert.equal(calls[1][1]['X-Research-Version'], 'a'.repeat(64))
  assert.equal(calls[2][1]['X-Research-Version'], 'a'.repeat(64))
  assert.equal(calls[3][1]['X-Research-Version'], 'a'.repeat(64))
  assert.equal(calls[4][1]['X-Research-Version'], undefined)
})
