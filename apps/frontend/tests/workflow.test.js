import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useResearchContext, snapshotKey } from '../src/dashboard/use-research-context.js'
import { useBacktest } from '../src/dashboard/use-backtest.js'
import { useCorrelation } from '../src/dashboard/use-correlation.js'
import { useAllocation } from '../src/dashboard/use-allocation.js'
import { equityOption, exposureOption } from '../src/dashboard/charts.js'

function setup(t) {
  const scope = effectScope(); t.after(() => scope.stop())
  const status = ref({ status: 'ready', latestTradeDate: '2026-09-30' })
  const strategies = ref([{ id: 'ma_cross', status: 'available', parameterSchema: {
    type: 'object', required: ['shortWindow', 'longWindow'], properties: {
      shortWindow: { type: 'integer', default: 5, minimum: 2 }, longWindow: { type: 'integer', default: 20, minimum: 3 }
    }, 'x-relations': [{ left: 'shortWindow', operator: 'lt', right: 'longWindow' }]
  } }, { id: 'ppo', status: 'experimental', backtestEnabled: true, modelContext: {
    assetScope: 'training_symbols', symbols: ['510300'], outOfSampleStartDate: '2022-01-01',
    requiredTradingCosts: { commissionPct: 0.03, stampDutyPct: 0, slippagePct: 0.02 }
  }, parameterSchema: { type: 'object', required: ['modelRef'], properties: { modelRef: { type: 'string', enum: ['test'], default: 'test' } } } }])
  const requests = []
  const client = { getCorrelation: async p => { requests.push(p); return { symbols: p.symbols, matrix: [[1]], observationCount: 2 } },
    getAllocationSuggestion: async p => { requests.push(p); return { request: p, positions: [], cashPct: 100 } } }
  return scope.run(() => {
    const correlation = useCorrelation(status, client)
    const backtest = useBacktest(strategies, status, ref([]), client, null)
    const allocation = useAllocation(strategies, client)
    const flow = useResearchContext(correlation, backtest, allocation, status)
    return { correlation, backtest, allocation, flow, status, requests, client }
  })
}

test('one-way asset/date inheritance detaches only edited group and never sends a request', t => {
  const { correlation, backtest, allocation, flow, requests } = setup(t)
  assert.deepEqual(backtest.symbols.value, correlation.symbols.value)
  assert.deepEqual(allocation.symbols.value, correlation.symbols.value)
  correlation.symbols.value = ['600000', '510500']
  assert.deepEqual(backtest.symbols.value, ['600000', '510500'])
  flow.backtestSymbols.value = ['510300']
  correlation.symbols.value = ['600001', '600002']
  correlation.endDate.value = '2026-09-29'
  assert.deepEqual(backtest.symbols.value, ['510300'])
  assert.equal(backtest.endDate.value, '2026-09-29')
  assert.deepEqual(correlation.symbols.value, ['600001', '600002'])
  flow.restoreBacktest()
  assert.deepEqual(backtest.symbols.value, correlation.symbols.value)
  flow.allocationSymbols.value = ['600999']
  flow.backtestSymbols.value = ['510050']
  assert.deepEqual(allocation.symbols.value, ['600999'])
  flow.restoreAllocation()
  assert.deepEqual(allocation.symbols.value, ['510050'])
  assert.equal(requests.length, 0)
})

test('strategy parameters, capital, cash and costs are copied into simulation with no aliases', t => {
  const { backtest, allocation, flow } = setup(t)
  backtest.parameters.value.shortWindow = 7
  backtest.cashPct.value = 25
  backtest.initialCapitalCny.value = 200000
  backtest.tradingCosts.value.commissionPct = 0.08
  assert.equal(allocation.parameters.value.shortWindow, 7)
  assert.equal(allocation.cashPct.value, 25)
  assert.equal(allocation.initialCapitalCny.value, 200000)
  assert.equal(allocation.tradingCosts.value.commissionPct, 0.08)
  flow.allocationConfigLinked.value = false
  allocation.parameters.value.shortWindow = 9
  allocation.tradingCosts.value.commissionPct = 0.2
  assert.equal(backtest.parameters.value.shortWindow, 7)
  assert.equal(backtest.tradingCosts.value.commissionPct, 0.08)
  flow.restoreAllocation()
  assert.equal(allocation.parameters.value.shortWindow, 7)
})

test('running backtest and simulation keep drafts stable then catch up without resubmission', t => {
  const { correlation, backtest, allocation, flow, requests } = setup(t)
  const original = [...backtest.symbols.value]
  backtest.busy.value = true
  allocation.busy.value = true
  correlation.symbols.value = ['600000', '600001']
  flow.backtestSymbols.value = ['510300']
  assert.deepEqual(backtest.symbols.value, original)
  backtest.busy.value = false
  assert.deepEqual(backtest.symbols.value, correlation.symbols.value)
  assert.deepEqual(allocation.symbols.value, original)
  allocation.busy.value = false
  assert.deepEqual(allocation.symbols.value, correlation.symbols.value)
  assert.equal(requests.length, 0)
})

test('AI inheritance blocks unsupported simulation and retains the selected model', async t => {
  const { backtest, allocation, requests } = setup(t)
  backtest.strategyId.value = 'ppo'
  assert.equal(allocation.strategyId.value, 'ppo')
  assert.equal(allocation.canSubmit.value, false)
  assert.match(allocation.validationError.value, /尚不支持模拟配置/)
  await allocation.submit()
  assert.equal(requests.length, 0)
})

test('correlation and simulation result snapshots remain correct after forms change', async t => {
  const { correlation, backtest, allocation, requests } = setup(t)
  await correlation.submit()
  const oldSymbols = [...correlation.resultRequest.value.symbols]
  correlation.symbols.value = ['600000', '600001']
  assert.equal(correlation.resultStale.value, true)
  assert.deepEqual(correlation.resultRequest.value.symbols, oldSymbols)
  await allocation.submit()
  assert.equal(allocation.resultStale.value, false)
  assert.deepEqual(requests.at(-1).parameters, backtest.parameters.value)
  assert.equal(requests.at(-1).tradingCosts.stampDutyMode, 'asset_date')
  assert.equal(requests.at(-1).startDate, backtest.startDate.value)
  backtest.parameters.value.shortWindow = 8
  assert.equal(allocation.resultStale.value, true)
  assert.equal(allocation.resultRequest.value.parameters.shortWindow, 5)
})

test('ranking import requires recorded metadata and loads warmup without claiming equal metrics', t => {
  const { backtest, flow } = setup(t)
  assert.equal(flow.loadRanking({ strategyId: 'ma_cross' }, {}), false)
  const meta = { historyStartDate: '2026-01-01', evaluationStartDate: '2026-09-01', evaluationEndDate: '2026-09-30',
    evaluationSymbols: ['510300'], tradingCosts: { commissionPct: 0.03, stampDutyPct: 0, slippagePct: 0.02, stampDutyMode: 'fixed' } }
  assert.equal(flow.loadRanking({ strategyId: 'ma_cross', parameters: { shortWindow: 10, longWindow: 30 } }, meta), true)
  assert.equal(backtest.startDate.value, '2026-01-01')
  assert.equal(backtest.endDate.value, '2026-09-30')
  assert.equal(backtest.parameters.value.shortWindow, 10)
  assert.equal(flow.backtestAssetsLinked.value, false)
  assert.match(flow.notice.value, /指标不会自动等同/)
})

test('chart buy/sell markers use actual executed dates and holdings use recorded account curve', () => {
  const result = { benchmarkContext: { mode: 'buy_and_hold' }, equityCurve: [
    { date: '2026-09-01', equity: 100, benchmarkEquity: 1 }, { date: '2026-09-02', equity: 90, benchmarkEquity: 0.95 }
  ], trades: [{ date: '2026-09-02', side: 'buy' }, { date: '2026-08-01', side: 'sell' }],
  accountCurve: [{ date: '2026-09-01', exposurePct: 0 }, { date: '2026-09-02', exposurePct: 45 }] }
  const option = equityOption(result)
  assert.deepEqual(option.series.find(s => s.name === '买入成交').data, [['2026-09-02', 0.9]])
  assert.equal(option.series.some(s => s.name === '卖出成交'), false)
  assert.ok(option.legend.data.includes('买入持有基准'))
  assert.deepEqual(exposureOption(result).series[0].data, [0, 45])
  assert.equal(exposureOption({}).series, undefined)
  assert.match(exposureOption({}).title.text, /未记录/)
  assert.equal(snapshotKey({ b: 2, a: 1 }), snapshotKey({ a: 1, b: 2 }))
})

test('market shortcut updates source dates but preserves a manually detached backtest range', t => {
  const { correlation, backtest, flow } = setup(t)
  flow.backtestStartDate.value = '2026-01-01'
  correlation.startDate.value = '2026-06-01'
  flow.usePublishedRange()
  assert.equal(correlation.endDate.value, '2026-09-30')
  assert.equal(correlation.startDate.value, '2025-09-30')
  assert.equal(backtest.startDate.value, '2026-01-01')
})

test('invalid shared fees, capital and cash prevent both calculation requests', async t => {
  const { backtest, allocation, requests } = setup(t)
  backtest.tradingCosts.value.commissionPct = NaN
  assert.equal(backtest.canSubmit.value, false)
  assert.equal(allocation.canSubmit.value, false)
  backtest.tradingCosts.value.commissionPct = 0.03
  backtest.cashPct.value = 101
  assert.equal(backtest.canSubmit.value, false)
  assert.equal(allocation.canSubmit.value, false)
  backtest.cashPct.value = 0
  backtest.initialCapitalCny.value = 0
  assert.equal(backtest.canSubmit.value, false)
  assert.equal(allocation.canSubmit.value, false)
  await allocation.submit()
  assert.equal(requests.length, 0)
})

test('publication change marks recorded result as previous data without overwriting its snapshot', async t => {
  const { correlation, status, client } = setup(t)
  status.value.dataContext = { dataVersion: 'a' }
  client.getCorrelation = async payload => ({ symbols: payload.symbols, matrix: [[1]], dataContext: { dataVersion: 'a' } })
  await correlation.submit()
  status.value.dataContext = { dataVersion: 'b' }
  assert.equal(correlation.resultStale.value, true)
  assert.equal(correlation.result.value.dataContext.dataVersion, 'a')
})
