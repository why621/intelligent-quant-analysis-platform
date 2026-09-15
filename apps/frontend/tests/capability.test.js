import assert from 'node:assert/strict'
import test from 'node:test'
import { useCapability } from '../src/dashboard/use-capability.js'
const response = (state = 'ready', version = 'v1') => ({ state, issues: [], message: state, dataContext: { dataVersion: version } })
test('later selection wins even when old request finishes last', async () => {
  const pending = []
  const state = useCapability({ checkDataCapability: () => new Promise(resolve => pending.push(resolve)) })
  const a = state.check({ symbols: ['a'] }, 'v1')
  const b = state.check({ symbols: ['b'] }, 'v1')
  pending[1](response('unavailable')); await b
  pending[0](response()); await a
  assert.equal(state.result.value.state, 'unavailable')
})
test('input change invalidates in-flight result immediately', async () => {
  let resolve
  const state = useCapability({ checkDataCapability: () => new Promise(r => { resolve = r }) })
  const pending = state.check({}, 'v1')
  state.invalidate(); resolve(response()); await pending
  assert.equal(state.result.value, null)
})
test('different publication never appears ready', async () => {
  const state = useCapability({ checkDataCapability: async () => response('ready', 'v2') })
  await state.check({}, 'v1')
  assert.equal(state.result.value, null)
  assert.match(state.message.value, /版本已变化/)
})
test('failure or missing old endpoint is advisory and clears old result', async () => {
  const state = useCapability({ checkDataCapability: async () => { throw new Error('503') } })
  await state.check({}, 'v1')
  assert.equal(state.result.value, null)
  assert.equal(state.busy.value, false)
  assert.match(state.message.value, /实际提交仍会检查/)
})
test('disposed component ignores response', async () => {
  let resolve
  const state = useCapability({ checkDataCapability: () => new Promise(r => { resolve = r }) })
  const pending = state.check({}, 'v1')
  state.dispose(); resolve(response()); await pending
  assert.equal(state.result.value, null)
})
