import assert from 'node:assert/strict'
import test from 'node:test'
import { ASSET_CATEGORIES, assetCategories, filterAssets } from '../src/dashboard/asset-filter.js'

const stock = (symbol, name, exchange = 'SSE') => ({ symbol, name, exchange, assetType: 'stock', assetId: `stock:${exchange}:${symbol}`, active: true })
const smic = stock('688981', '中芯国际')
const bank = stock('600036', '招商银行')
const chip = { symbol: '516510', name: '芯片ETF', assetType: 'etf', exchange: 'SSE', active: true }
const broad = { ...chip, symbol: '510300', name: '沪深300ETF' }
const unknown = stock('999999', '测试公司')
const assets = [smic, bank, chip, broad, unknown]

test('category and alias search finds a stock without the category in its name', () => {
  assert.deepEqual(filterAssets(assets, { query: ' 半导体 ' }), [smic, chip])
  assert.deepEqual(filterAssets(assets, { query: '芯片', kind: 'stock' }), [smic])
  assert.deepEqual(filterAssets(assets, { query: 'SEMICONDUCTOR 688981' }), [smic])
  assert.deepEqual(filterAssets(assets, { query: '６８８９８１' }), [smic])
})
test('category union intersects asset type and search; clearing filters preserves catalog', () => {
  assert.deepEqual(filterAssets(assets, { categories: ['semiconductor', 'bank'], kind: 'stock' }), [smic, bank])
  assert.deepEqual(filterAssets(assets, { categories: ['bank'], query: '芯片' }), [])
  assert.deepEqual(filterAssets(assets, { categories: ['semiconductor'], kind: 'etf' }), [chip])
  assert.deepEqual(filterAssets(assets, { query: '招商' }), [bank])
  assert.deepEqual(filterAssets(assets), assets)
  assert.deepEqual(filterAssets([], { query: '半导体' }), [])
})
test('unknown identities and broad ETFs are never assigned unrelated sectors', () => {
  assert.deepEqual(assetCategories(unknown), [])
  assert.deepEqual(assetCategories(broad), [])
  assert.deepEqual(assetCategories({ ...smic, exchange: 'SZSE' }), [])
  assert.deepEqual(assetCategories({ ...smic, assetId: 'stock:SSE:600036' }), [])
  assert.deepEqual(filterAssets([unknown], { categories: ['semiconductor'] }), [])
  assert.deepEqual(filterAssets([unknown], { query: '测试公司' }), [unknown])
})
test('filter does not mutate assets, reorder results or discard inactive records', () => {
  const inactive = Object.freeze({ ...smic, active: false })
  const input = Object.freeze([inactive, Object.freeze(bank)])
  assert.deepEqual(filterAssets(input, { categories: ['semiconductor'] }), [inactive])
  assert.equal(inactive.active, false)
})
test('classification data has traceable sources and unique qualified member identities', () => {
  assert.equal(new Set(ASSET_CATEGORIES.map(x => x.id)).size, ASSET_CATEGORIES.length)
  for (const category of ASSET_CATEGORIES) {
    assert.match(category.sourceUrl, /^https:\/\/oss-ch\.csindex\.com\.cn\//)
    assert.match(category.sourceSha256, /^[a-f0-9]{64}$/)
    assert.match(category.sourceDate, /^\d{4}-\d{2}-\d{2}$/)
    assert.equal(new Set(category.members).size, category.members.length)
    assert.ok(category.members.length > 0)
    for (const member of category.members) assert.match(member, /^stock:(SSE|SZSE|BSE):[0-9]{6}$/)
  }
})
