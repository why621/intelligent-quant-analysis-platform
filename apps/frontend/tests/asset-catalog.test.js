import assert from 'node:assert/strict'
import test from 'node:test'
import { loadAssetCatalog } from '../src/dashboard/asset-catalog.js'
import { useMarket } from '../src/dashboard/use-market.js'

// Deliberately synthetic, never published as a CSI300 list.
const assets = Array.from({ length: 301 }, (_, n) => ({
  symbol: String(600000 + n), assetType: n === 300 ? 'etf' : 'stock',
  exchange: 'SSE', name: `合成资产${n}`, active: true,
  assetId: `${n === 300 ? 'etf' : 'stock'}:SSE:${600000 + n}`
}))
function clientFor(mutate = page => page) {
  const calls = []
  return {
    calls,
    listAssets: async ({ limit, offset }) => {
      calls.push(offset)
      const items = assets.slice(offset, offset + limit)
      return mutate({ items, total: items.length, matchedTotal: assets.length,
        offset, nextOffset: offset + items.length < assets.length ? offset + items.length : null,
        catalogVersion: 'a'.repeat(64) })
    }
  }
}

test('300 synthetic stocks plus ETF load exactly once across four pages', async () => {
  const client = clientFor()
  const result = await loadAssetCatalog(client)
  assert.deepEqual(client.calls, [0, 100, 200, 300])
  assert.deepEqual(result.items, assets)
})

for (const [name, mutate] of [
  ['version change', page => ({ ...page, catalogVersion: 'b'.repeat(64) })],
  ['changed count', page => ({ ...page, matchedTotal: 302 })],
  ['duplicate item', page => ({ ...page, items: [assets[0], ...page.items.slice(1)] })],
  ['early last page', page => ({ ...page, nextOffset: null })],
  ['non-progress offset', page => ({ ...page, nextOffset: page.offset })],
  ['wrong offset', page => ({ ...page, offset: 0 })],
  ['wrong page count', page => ({ ...page, total: 99 })],
  ['invalid identity', page => ({ ...page, items: [{ ...page.items[0], assetId: 'index:CSI:000300' }, ...page.items.slice(1)] })],
]) {
  test(`rejects ${name} instead of returning partial catalog`, async () => {
    const client = clientFor(page => page.offset ? mutate(page) : page)
    await assert.rejects(loadAssetCatalog(client), /目录不完整/)
    assert.deepEqual(client.calls, [0, 100])
  })
}

test('outage is propagated and obsolete load stops before next page', async () => {
  const client = clientFor(page => {
    if (page.offset) throw new Error('503')
    return page
  })
  await assert.rejects(loadAssetCatalog(client), /503/)
  const superseded = clientFor()
  await assert.rejects(loadAssetCatalog(superseded, () => superseded.calls.length === 0), /替代/)
  assert.deepEqual(superseded.calls, [0])
})

test('legacy contract and over-budget catalog fail explicitly', async () => {
  await assert.rejects(loadAssetCatalog({ listAssets: async () => ({ items: assets.slice(0, 50) }) }), /旧后端/)
  const oversized = clientFor(page => ({ ...page, matchedTotal: 1001 }))
  await assert.rejects(loadAssetCatalog(oversized), /目录不完整/)
  assert.deepEqual(oversized.calls, [0])
})

test('empty catalog is valid at loader boundary', async () => {
  const result = await loadAssetCatalog({ listAssets: async () => ({
    items: [], total: 0, matchedTotal: 0, offset: 0, nextOffset: null, catalogVersion: 'a'.repeat(64)
  }) })
  assert.deepEqual(result.items, [])
})

test('market publishes no partial catalog and exposes a clear error', async () => {
  const client = {
    ...clientFor(page => {
      if (page.offset) throw new Error('503')
      return page
    }),
    getDataStatus: async () => ({ status: 'ready' }),
    getMarketOverview: async () => ({ tradeDate: '2026-09-07' }),
    getStrategies: async () => ({ items: [{ id: 'ma_cross' }] }),
    getStrategyRanking: async () => ({ items: [] })
  }
  const state = useMarket(client)
  await state.initialise()
  assert.deepEqual(state.assetCatalog.value, [])
  assert.match(state.assetCatalogError.value, /目录加载失败/)
  assert.equal(state.connection.live, false)
  client.listAssets = clientFor().listAssets
  await state.initialise()
  assert.equal(state.assetCatalog.value.length, 301)
  assert.equal(state.assetCatalogError.value, '')
})
