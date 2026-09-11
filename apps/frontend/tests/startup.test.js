import assert from 'node:assert/strict'
import test from 'node:test'
import { initialiseDashboard } from '../src/dashboard/startup.js'

test('blocked chart download does not delay data initialization or other charts', async () => {
  let finish, loaded = false, other = false
  const pending = new Promise(resolve => { finish = resolve })
  const run = initialiseDashboard(async () => { loaded = true }, {
    correlation: () => pending, equity: async () => { other = true }
  }, () => assert.fail('unexpected error'))
  await Promise.resolve(); await Promise.resolve()
  assert.equal(loaded, true)
  assert.equal(other, true)
  finish(); await run
})

test('chart rejection is reported without losing data or other charts', async () => {
  const errors = []; let loaded = false, other = false
  await initialiseDashboard(async () => { loaded = true }, {
    correlation: async () => { throw Error('chunk failed') },
    equity: async () => { other = true }
  }, (name, error) => errors.push([name, error.message]))
  assert.equal(loaded, true); assert.equal(other, true)
  assert.deepEqual(errors, [['correlation', 'chunk failed']])
})

test('data rejection does not prevent chart initialization', async () => {
  let rendered = false
  const results = await initialiseDashboard(async () => { throw Error('API failed') }, {
    correlation: () => { rendered = true }
  }, () => assert.fail('unexpected chart error'))
  assert.equal(rendered, true)
  assert.equal(results[0].status, 'rejected')
})
