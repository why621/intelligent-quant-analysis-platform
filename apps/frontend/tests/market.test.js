import assert from 'node:assert/strict'
import test from 'node:test'
import { useMarket } from '../src/dashboard/use-market.js'

const snapshot = { tradeDate: '2026-09-04', advancing: 42, indices: [] }
const makeClient = () => ({
  getDataStatus: async () => ({ status: 'stale', components: {
    history: { status: 'ready', message: 'complete' },
    overview: { status: 'failed', message: 'unavailable' }
  } }),
  listAssets: async () => ({ items: [{
    symbol: '510300', assetId: 'etf:SSE:510300', assetType: 'etf',
    exchange: 'SSE', name: '沪深300ETF', active: true
  }], total: 1, matchedTotal: 1, offset: 0, nextOffset: null, catalogVersion: 'a'.repeat(64) }),
  getMarketOverview: async () => { throw new Error('503') },
  getStrategies: async () => ({ items: [{ id: 'ma_cross' }] }),
  getStrategyRanking: async () => ({ items: [] })
})

test('overview outage is partial availability, with no fabricated metrics', async () => {
  const state = useMarket(makeClient())
  await state.initialise()
  assert.match(state.connection.message, /部分接口可用/)
  assert.doesNotMatch(state.connection.message, /待接入/)
  assert.equal(state.historyStatusText.value, '更新完成')
  assert.equal(state.overviewStatusText.value, '暂不可用')
  assert.equal(state.market.value.advancing, null)
  assert.match(state.marketNotice.value, /暂不可用/)
})

test('cached snapshot is explicitly labelled stale', async () => {
  const client = makeClient()
  client.getDataStatus = async () => ({ status: 'stale', components: {
    overview: { status: 'stale', message: 'cached' }
  } })
  client.getMarketOverview = async () => snapshot
  const state = useMarket(client)
  await state.initialise()
  assert.equal(state.market.value.advancing, 42)
  assert.match(state.marketNotice.value, /上次成功快照（2026-09-04）/)
  assert.match(state.connection.message, /需关注/)
})

test('recovery clears unavailable notice', async () => {
  const client = makeClient()
  const state = useMarket(client)
  await state.initialise()
  client.getMarketOverview = async () => snapshot
  client.getDataStatus = async () => ({ status: 'ready', components: {
    overview: { status: 'ready', message: 'complete' }
  } })
  await state.initialise()
  assert.equal(state.marketNotice.value, '')
  assert.equal(state.connection.message, '接口数据')
  assert.equal(state.market.value.advancing, 42)
})
test('pending ranking does not block independently resolved data', async () => {
  const client = makeClient()
  let finish
  client.getStrategyRanking = () => new Promise(resolve => { finish = resolve })
  const state = useMarket(client)
  const pending = state.initialise()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.historyStatusText.value, '更新完成')
  assert.match(state.marketNotice.value, /暂不可用/)
  assert.equal(state.connection.loading, true)
  finish({ items: [] })
  await pending
  assert.equal(state.connection.loading, false)
})

test('late responses from an earlier reload never overwrite current state', async () => {
  const client = makeClient()
  let finish
  client.getDataStatus = () => new Promise(resolve => { finish = resolve })
  const state = useMarket(client)
  const first = state.initialise()
  client.getDataStatus = async () => ({ status: 'ready' })
  await state.initialise()
  finish({ status: 'failed' })
  await first
  assert.equal(state.dataStatus.value.status, 'ready')
})

test('failed reload clears old ready status', async () => {
  const client = makeClient()
  client.getDataStatus = async () => ({ status: 'ready' })
  const state = useMarket(client)
  await state.initialise()
  client.getDataStatus = async () => null
  await state.initialise()
  assert.equal(state.dataStatus.value.status, 'stale')
  assert.equal(state.connection.live, false)
})
