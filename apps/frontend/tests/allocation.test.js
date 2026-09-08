import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useAllocation } from '../src/dashboard/use-allocation.js'
import { allocationOption } from '../src/dashboard/charts.js'

const cashResult = { positions: [], cashPct: 100, strategyId: 'momentum_reversal' }
const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}
function setup(t) {
  const requests = []
  const client = { getAllocationSuggestion: async payload => {
    requests.push(payload)
    return cashResult
  } }
  const scope = effectScope()
  t.after(() => scope.stop())
  const strategies = ref([{ id: 'momentum_reversal', status: 'available' }])
  const state = scope.run(() => useAllocation(strategies, client))
  return { state, requests, client, scope, strategies }
}

test('allocation rejects empty, nonfinite and out-of-range cash without POST', async t => {
  const { state, requests } = setup(t)
  for (const value of ['', null, undefined, '10', true, NaN, Infinity, -1, 101]) {
    state.cashPct.value = value
    assert.equal(state.canSubmit.value, false, String(value))
    await state.submit()
    assert.match(state.error.value, /现金/)
  }
  assert.equal(requests.length, 0)
})

test('allocation requires one to ten unique valid symbols and an available strategy', async t => {
  const { state, requests, strategies } = setup(t)
  for (const values of [[], ['510300', '510300'], ['bad'], ['510300', ''],
    Array.from({ length: 11 }, (_, i) => String(510300 + i))]) {
    state.symbols.value = values
    assert.equal(state.canSubmit.value, false)
    await state.submit()
  }
  state.symbols.value = ['510300']
  strategies.value = []
  assert.equal(state.canSubmit.value, false)
  assert.equal(requests.length, 0)
})

test('allocation accepts explicit zero, fractional and all-cash requests', async t => {
  const { state, requests } = setup(t)
  for (const cash of [0, 10.5, 100]) {
    state.cashPct.value = cash
    await state.submit()
    assert.equal(requests.at(-1).cashPct, cash)
    assert.equal(state.error.value, '')
    assert.deepEqual(state.result.value, cashResult)
  }
})

test('allocation duplicate submission preserves in-flight state and snapshots inputs', async t => {
  const { state, requests, client } = setup(t)
  const pending = deferred()
  client.getAllocationSuggestion = payload => { requests.push(payload); return pending.promise }
  const first = state.submit()
  state.symbols.value.push('159915')
  state.cashPct.value = 50
  await state.submit()
  assert.equal(requests.length, 1)
  assert.deepEqual(requests[0].symbols, ['510300', '510500'])
  assert.equal(requests[0].cashPct, 10)
  assert.equal(state.busy.value, true)
  assert.equal(state.error.value, '')
  pending.resolve(cashResult)
  await first
  assert.deepEqual(state.result.value, cashResult)
})

test('allocation disposal ignores late response and blocks further requests', async t => {
  const { state, client, scope, requests } = setup(t)
  const pending = deferred()
  client.getAllocationSuggestion = payload => { requests.push(payload); return pending.promise }
  const first = state.submit()
  scope.stop()
  pending.resolve(cashResult)
  await first
  assert.equal(state.result.value, null)
  assert.equal(state.canSubmit.value, false)
  await state.submit()
  assert.equal(requests.length, 1)
})

test('allocation server errors stay visible and permit a subsequent retry', async t => {
  const { state, client } = setup(t)
  client.getAllocationSuggestion = async () => { throw Error('controlled outage') }
  await state.submit()
  assert.match(state.error.value, /controlled outage/)
  assert.equal(state.busy.value, false)
  assert.equal(state.canSubmit.value, true)
  client.getAllocationSuggestion = async () => cashResult
  await state.submit()
  assert.equal(state.error.value, '')
  assert.deepEqual(state.result.value, cashResult)
})

test('allocation chart renders a cash-only result rather than a waiting placeholder', () => {
  const option = allocationOption(cashResult)
  assert.deepEqual(option.series?.[0]?.data, [{ name: '现金', value: 100 }])
  assert.deepEqual(allocationOption({ positions: [{ symbol: '510300', weightPct: 0 }], cashPct: 100 })
    .series[0].data, [{ name: '现金', value: 100 }])
  assert.match(allocationOption(null).title.text, /生成/)
  assert.deepEqual(allocationOption({ positions: [{ symbol: '510300', weightPct: 90 }], cashPct: 10 })
    .series[0].data, [{ name: '510300', value: 90 }, { name: '现金', value: 10 }])
})
