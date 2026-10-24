import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useCorrelation } from '../src/dashboard/use-correlation.js'
import { useAllocation } from '../src/dashboard/use-allocation.js'

for (const kind of ['correlation', 'allocation']) {
  test(`${kind}: failed retry preserves successful result and its request, then recovers`, async t => {
    const scope = effectScope()
    t.after(() => scope.stop())
    const status = ref({ status: 'ready', latestTradeDate: '2026-09-07' })
    let request = async () => ({ marker: 'first success' })
    const state = scope.run(() => kind === 'correlation'
      ? useCorrelation(status, { getCorrelation: payload => request(payload) })
      : useAllocation(ref([{ id: 'momentum_reversal', status: 'available', parameterSchema: {
        type: 'object', properties: { lookback: { type: 'integer', default: 10, minimum: 2 } }
      } }]),
        { getAllocationSuggestion: payload => request(payload) }, status))
    state.startDate.value = '2026-08-10'
    await state.submit()
    assert.equal(state.result.value.marker, 'first success')
    const previous = structuredClone(JSON.parse(JSON.stringify(state.resultRequest.value)))
    state.startDate.value = '2026-08-11'
    let reject
    request = () => new Promise((_, no) => { reject = no })
    const retry = state.submit()
    assert.equal(state.busy.value, true)
    assert.equal(state.result.value.marker, 'first success')
    assert.deepEqual(state.resultRequest.value, previous)
    assert.equal(state.resultStale.value, true)
    reject(new Error('测试网络失败'))
    await retry
    assert.equal(state.busy.value, false)
    assert.match(state.error.value, /测试网络失败/)
    assert.equal(state.result.value.marker, 'first success')
    assert.deepEqual(state.resultRequest.value, previous)
    request = async () => ({ marker: 'recovered' })
    await state.submit()
    assert.equal(state.result.value.marker, 'recovered')
    assert.equal(state.resultRequest.value.startDate, '2026-08-11')
    assert.equal(state.resultStale.value, false)
    assert.equal(state.error.value, '')
  })
}
