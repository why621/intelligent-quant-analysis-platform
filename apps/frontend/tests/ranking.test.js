import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useBacktest } from '../src/dashboard/use-backtest.js'
import { useAllocation } from '../src/dashboard/use-allocation.js'
import { useCorrelation } from '../src/dashboard/use-correlation.js'
import { useResearchContext } from '../src/dashboard/use-research-context.js'
import { useRanking } from '../src/dashboard/use-ranking.js'
import { modelScopeLines } from '../src/dashboard/model-disclosure.js'

function setup(t) {
  const scope = effectScope(); t.after(() => scope.stop())
  const status = ref({ status: 'ready', latestTradeDate: '2026-10-14', dataContext: { dataVersion: 'v1' } })
  const assets = ref(Array.from({ length: 10 }, (_, i) => ({ symbol: String(510300 + i), active: true, assetType: i % 2 ? 'stock' : 'etf' })))
  const strategies = ref([{ id: 'ma_cross', name: '均线', status: 'available', parameterSchema: { type: 'object', properties: {
    shortWindow: { type: 'integer', default: 5 }, longWindow: { type: 'integer', default: 20 }
  } } }, { id: 'portfolio_ppo', name: '联合PPO', status: 'experimental', backtestEnabled: true, allocationEnabled: true,
    modelContext: { portfolioMode: 'joint_portfolio', assetScope: 'published_universe', trainingSymbols: ['600000', '600001'],
      symbols: assets.value.map(a => a.symbol), costPolicy: 'request_configurable', outOfSampleStartDate: '2026-08-01' },
    parameterSchema: { type: 'object', properties: { modelRef: { type: 'string', enum: ['wide'], default: 'wide' } } } }])
  const calls = []
  const client = { calculateStrategyRanking: async payload => {
    calls.push(payload)
    return { request: structuredClone(payload), items: [{ strategyId: payload.strategyId, parameters: payload.parameters }],
      unavailableStrategies: [{ strategyId: 'ppo', strategyName: '旧PPO', message: '资产范围不匹配' }], dataContext: { dataVersion: status.value.dataContext.dataVersion } }
  } }
  return scope.run(() => {
    const backtest = useBacktest(strategies, status, assets, client, null)
    const correlation = useCorrelation(status, client)
    const allocation = useAllocation(strategies, client, status, assets)
    const flow = useResearchContext(correlation, backtest, allocation, status)
    flow.backtestSymbols.value = ['510300', '510301']
    flow.backtestStartDate.value = '2026-08-03'
    flow.backtestEndDate.value = '2026-10-14'
    const ranking = useRanking(backtest, status, strategies, client)
    return { backtest, allocation, correlation, flow, ranking, client, calls, status, strategies, assets, scope }
  })
}

test('ranking sends the complete current backtest draft once and retains exclusions and parameters', async t => {
  const { ranking, backtest, calls } = setup(t)
  backtest.initialCapitalCny.value = 230000
  backtest.cashPct.value = 14
  backtest.tradingCosts.value.commissionPct = 0.06
  backtest.parameters.value.shortWindow = 7
  backtest.benchmarkMode.value = 'custom'; backtest.benchmark.value = '510300'
  assert.equal(calls.length, 0)
  await ranking.submit()
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0], backtest.draft.value)
  assert.equal(calls[0].adjust, 'qfq')
  assert.equal(calls[0].portfolioMode, 'shared_account')
  assert.equal(ranking.stale.value, false)
  assert.equal(ranking.items.value[0].parameters.shortWindow, 7)
  assert.equal(ranking.unavailable.value[0].strategyId, 'ppo')
  backtest.parameters.value.shortWindow = 9
  assert.equal(ranking.stale.value, true)
  assert.equal(ranking.result.value.request.parameters.shortWindow, 7)
  assert.equal(calls.length, 1)
})

test('any configuration, data or model change marks existing ranking stale without recalculating', async t => {
  const { ranking, backtest, status, strategies, calls } = setup(t)
  const edits = [
    () => { backtest.symbols.value = ['510301', '510302'] },
    () => { backtest.startDate.value = '2026-08-04' },
    () => { backtest.endDate.value = '2026-10-13' },
    () => { backtest.initialCapitalCny.value += 1000 },
    () => { backtest.tradingCosts.value.slippagePct += 0.01 },
    () => { backtest.cashPct.value += 1 },
    () => { backtest.benchmarkMode.value = 'none' },
    () => { status.value.dataContext.dataVersion = 'v2' },
    () => { strategies.value[1].modelContext.modelRef = 'new-release' }
  ]
  for (const edit of edits) {
    await ranking.submit()
    assert.equal(ranking.stale.value, false)
    const n = calls.length
    edit()
    assert.equal(ranking.stale.value, true)
    assert.equal(calls.length, n)
  }
})

test('late ranking responses cannot overwrite new configuration and duplicate clicks do not compute twice', async t => {
  const { ranking, client, backtest } = setup(t)
  await ranking.submit()
  const saved = ranking.result.value
  let finish; let count = 0
  client.calculateStrategyRanking = payload => { count += 1; return new Promise(resolve => { finish = () => resolve({ request: payload, items: [], unavailableStrategies: [], dataContext: { dataVersion: 'v1' } }) }) }
  const pending = ranking.submit()
  await ranking.submit()
  assert.equal(count, 1)
  backtest.symbols.value = ['510302', '510303']
  assert.match(ranking.notice.value, /旧配置结果将被忽略/)
  finish(); await pending
  assert.equal(ranking.result.value, saved)
  assert.equal(ranking.stale.value, true)
  assert.equal(ranking.busy.value, false)
  const second = ranking.submit(); finish(); await second
  assert.deepEqual(ranking.result.value.request.symbols, ['510302', '510303'])
  assert.equal(ranking.stale.value, false)
})

test('invalid configuration and failed response do not replace a valid ranking snapshot', async t => {
  const { ranking, backtest, calls, client } = setup(t)
  await ranking.submit()
  const saved = ranking.result.value
  backtest.cashPct.value = 101
  await ranking.submit()
  assert.equal(calls.length, 1)
  assert.match(ranking.error.value, /现金/)
  backtest.cashPct.value = 3
  client.calculateStrategyRanking = async () => { throw Error('排行服务暂不可用') }
  await ranking.submit()
  assert.match(ranking.error.value, /暂不可用/)
  assert.equal(ranking.result.value, saved)
  assert.equal(ranking.stale.value, true)
})

test('dispose rejects a late ranking result', async t => {
  const { ranking, client, scope } = setup(t)
  let finish
  client.calculateStrategyRanking = payload => new Promise(resolve => { finish = () => resolve({ request: payload, items: [], unavailableStrategies: [], dataContext: { dataVersion: 'v1' } }) })
  const pending = ranking.submit(); scope.stop(); finish(); await pending
  assert.equal(ranking.result.value, null)
})

test('ranking import restores exact request dates, benchmark, capital and fees then updates linked simulation', async t => {
  const { flow, backtest, allocation } = setup(t)
  const request = { symbols: ['510302', '510303'], startDate: '2026-08-10', endDate: '2026-10-12',
    initialCapitalCny: 321000, cashPct: 13, tradingCosts: { commissionPct: 0.08, stampDutyPct: 0.05, slippagePct: 0.06, stampDutyMode: 'asset_date' },
    benchmarkMode: 'custom', benchmark: '510304', adjust: 'qfq' }
  const item = { strategyId: 'ma_cross', parameters: { shortWindow: 8, longWindow: 30 } }
  assert.equal(flow.loadRanking(item, { request, historyStartDate: '2026-01-01' }), true)
  assert.deepEqual(backtest.symbols.value, request.symbols)
  assert.equal(backtest.startDate.value, request.startDate)
  assert.equal(backtest.initialCapitalCny.value, request.initialCapitalCny)
  assert.equal(backtest.cashPct.value, request.cashPct)
  assert.equal(backtest.benchmark.value, request.benchmark)
  assert.equal(backtest.benchmarkMode.value, request.benchmarkMode)
  assert.deepEqual(backtest.tradingCosts.value, request.tradingCosts)
  assert.deepEqual(allocation.parameters.value, item.parameters)
  assert.deepEqual(allocation.symbols.value, request.symbols)
  assert.deepEqual(allocation.tradingCosts.value, request.tradingCosts)
  assert.equal(allocation.cashPct.value, request.cashPct)
  assert.match(flow.notice.value, /保持一致/)
})

test('published-universe model accepts ten mixed assets outside training pool and configurable costs/cash', t => {
  const { backtest, allocation, assets, strategies } = setup(t)
  backtest.strategyId.value = 'portfolio_ppo'
  backtest.symbols.value = assets.value.map(a => a.symbol)
  backtest.cashPct.value = 12
  backtest.tradingCosts.value.commissionPct = 0.09
  assert.equal(backtest.validationError.value, '')
  assert.equal(allocation.validationError.value, '')
  assert.equal(backtest.draft.value.tradingCosts.commissionPct, 0.09)
  assert.equal(backtest.draft.value.cashPct, 12)
  const text = modelScopeLines(strategies.value[1].modelContext).join(' ')
  assert.match(text, /股票和 ETF/)
  assert.match(text, /共享同一资金账户/)
  assert.doesNotMatch(text, /独立推理/)
  backtest.symbols.value = ['510300', '999999']
  assert.match(backtest.validationError.value, /发布目录/)
  assert.match(allocation.validationError.value, /发布目录/)
  backtest.symbols.value = ['510300', '510300']
  assert.match(backtest.validationError.value, /不同/)
  backtest.symbols.value = ['510300']
  assert.match(backtest.validationError.value, /2–10/)
})

test('legacy joint model still enforces training pool and zero additional cash', t => {
  const { backtest, strategies } = setup(t)
  strategies.value[1].modelContext.assetScope = 'training_symbols'
  strategies.value[1].modelContext.symbols = ['600000', '600001']
  delete strategies.value[1].modelContext.costPolicy
  backtest.strategyId.value = 'portfolio_ppo'
  assert.match(backtest.validationError.value, /旧组合模型仅支持训练池/)
  backtest.symbols.value = ['600000', '600001']
  assert.equal(backtest.validationError.value, '')
  backtest.cashPct.value = 1
  assert.match(backtest.validationError.value, /须显式设为 0/)
})

test('wrong request or publication response cannot masquerade as current ranking', async t => {
  const { ranking, client } = setup(t)
  await ranking.submit()
  const saved = ranking.result.value
  client.calculateStrategyRanking = async payload => ({ request: { ...payload, symbols: ['600000'] }, items: [], unavailableStrategies: [], dataContext: { dataVersion: 'v1' } })
  await ranking.submit()
  assert.match(ranking.error.value, /配置与本次提交不一致/)
  assert.equal(ranking.result.value, saved)
  client.calculateStrategyRanking = async payload => ({ request: payload, items: [], unavailableStrategies: [], dataContext: { dataVersion: 'previous' } })
  await ranking.submit()
  assert.match(ranking.error.value, /数据批次/)
  assert.equal(ranking.result.value, saved)
})

test('over-budget date range is rejected before starting a ranking computation', async t => {
  const { ranking, backtest, calls } = setup(t)
  backtest.startDate.value = '2025-01-01'
  assert.match(ranking.validationError.value, /366 天/)
  await ranking.submit()
  assert.equal(calls.length, 0)
})
