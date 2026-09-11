import assert from 'node:assert/strict'
import test from 'node:test'
import { ref } from 'vue'
import { useBacktest } from '../src/dashboard/use-backtest.js'
import { useCorrelation } from '../src/dashboard/use-correlation.js'

const published = () => ref({ status: 'stale', latestTradeDate: '2026-09-07',
  components: { history: { status: 'ready' }, overview: { status: 'failed' } } })

test('page backtest defaults use published cutoff', () => {
  const state = useBacktest(ref([]), published(), ref([]))
  assert.equal(state.endDate.value, '2026-09-07')
})

test('correlation screenshot defaults use published cutoff', () => {
  const state = useCorrelation(published())
  assert.equal(state.endDate.value, '2026-09-07')
})
import { effectScope } from 'vue'

const metadata = [
  { id: 'ma_cross', name: '均线交叉', status: 'available', parameterSchema: {
    type: 'object', required: ['shortWindow', 'longWindow'],
    properties: { shortWindow: { type: 'integer', minimum: 2, default: 5 },
      longWindow: { type: 'integer', minimum: 3, maximum: 200, default: 20 } },
    'x-relations': [{ left: 'shortWindow', operator: 'lt', right: 'longWindow' }]
  } },
  { id: 'momentum_reversal', name: '动量反转', status: 'available', parameterSchema: {
    type: 'object', required: ['lookback', 'overboughtThreshold', 'oversoldThreshold'],
    properties: { lookback: { type: 'integer', minimum: 3, default: 10 },
      overboughtThreshold: { type: 'number', default: 5 },
      oversoldThreshold: { type: 'number', default: -5 } },
    'x-relations': [{ left: 'oversoldThreshold', operator: 'lt', right: 'overboughtThreshold' }]
  } }
]
const jobId = '12345678-1234-1234-1234-123456789012'
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
function setup(t, storage = null) {
  const requests = []
  const client = {
    createBacktest: async payload => { requests.push(payload); return { jobId, status: 'queued', request: payload } },
    getBacktest: async () => ({ jobId, status: 'succeeded', request: requests.at(-1) }),
    getCorrelation: async payload => { requests.push(payload); return { observationCount: 242, matrix: [] } }
  }
  const scope = effectScope()
  t.after(() => scope.stop())
  const status = published()
  const strategies = ref(structuredClone(metadata))
  const assets = ref([{ symbol: '510300', name: '沪深300ETF', assetType: 'etf', active: true }])
  const state = scope.run(() => useBacktest(strategies, status, assets, client, storage))
  const correlation = scope.run(() => useCorrelation(status, client))
  return { state, correlation, scope, requests, client, status, strategies, assets }
}

test('actual submit consumes server defaults and omits implicit benchmark', async t => {
  const { state, requests, strategies } = setup(t)
  strategies.value[0].parameterSchema = { ...strategies.value[0].parameterSchema,
    properties: { ...strategies.value[0].parameterSchema.properties,
      shortWindow: { type: 'integer', minimum: 2, default: 7 } } }
  await state.submit()
  assert.deepEqual(requests[0].parameters, { shortWindow: 7, longWindow: 20 })
  assert.equal(requests[0].endDate, '2026-09-07')
  assert.equal('benchmark' in requests[0], false)
  assert.match(state.benchmarkLabel.value, /无基准/)
})

test('switching strategies resets schema parameters and accepts decimal thresholds', async t => {
  const { state, requests } = setup(t)
  state.parameters.value.shortWindow = 8
  state.strategyId.value = 'momentum_reversal'
  assert.deepEqual(state.parameters.value, { lookback: 10, overboughtThreshold: 5, oversoldThreshold: -5 })
  state.parameters.value.overboughtThreshold = 5.5
  await state.submit()
  assert.equal(requests[0].parameters.overboughtThreshold, 5.5)
  state.strategyId.value = 'ma_cross'
  assert.deepEqual(state.parameters.value, { shortWindow: 5, longWindow: 20 })
  assert.equal(state.strategyName.value, '动量反转')
})

test('missing metadata, required values, types, boundaries and relationships block POST', async t => {
  const { state, requests, strategies } = setup(t)
  for (const value of ['', '5', true, NaN, Infinity, 1, 2.5, 20]) {
    state.parameters.value.shortWindow = value
    assert.equal(state.canSubmit.value, false, String(value))
    await state.submit()
  }
  state.parameters.value.shortWindow = 5
  state.parameters.value.longWindow = 201
  assert.equal(state.canSubmit.value, false)
  strategies.value[0].parameterSchema = {}
  assert.match(state.validationError.value, /等待/)
  assert.equal(requests.length, 0)
})

test('momentum relation blocks equal/reversed thresholds', t => {
  const { state } = setup(t)
  state.strategyId.value = 'momentum_reversal'
  state.parameters.value.oversoldThreshold = 5
  assert.equal(state.canSubmit.value, false)
  state.parameters.value.oversoldThreshold = 6
  assert.equal(state.canSubmit.value, false)
})

test('late status initializes once and refresh never changes edited values', async t => {
  const { state, status, requests } = setup(t)
  status.value = { status: 'failed', latestTradeDate: null }
  assert.equal(state.canSubmit.value, false)
  state.startDate.value = '2026-01-01'
  status.value = { status: 'ready', latestTradeDate: '2026-09-04' }
  assert.equal(state.startDate.value, '2026-01-01')
  assert.equal(state.endDate.value, '2026-09-07')
  await state.submit()
  assert.equal(requests.length, 0)
  assert.match(state.validationError.value, /2026-09-04/)
})

test('empty date status never falls back to browser clock; late ready fills dates', t => {
  const { scope } = setup(t)
  const status = ref(null)
  const state = scope.run(() => useCorrelation(status))
  assert.equal(state.endDate.value, '')
  assert.equal(state.canSubmit.value, false)
  status.value = published().value
  assert.equal(state.endDate.value, '2026-09-07')
})

test('date bounds, invalid dates and unavailable history block both forms', async t => {
  const { state, correlation, requests, status } = setup(t)
  for (const form of [state, correlation]) {
    form.endDate.value = '2026-09-08'
    await form.submit()
    assert.equal(form.canSubmit.value, false)
    form.endDate.value = '2026-09-07'
    form.startDate.value = '2024-01-01'
    assert.equal(form.canSubmit.value, false)
    form.startDate.value = '2026-02-30'
    assert.equal(form.canSubmit.value, false)
    form.startDate.value = '2026-09-08'
    assert.equal(form.canSubmit.value, false)
  }
  status.value = { status: 'stale', latestTradeDate: '2026-09-07', components: { history: { status: 'failed' } } }
  assert.equal(state.canSubmit.value, false)
  assert.equal(requests.length, 0)
})

test('correlation sends screenshot symbols and does not silently discard bad inputs', async t => {
  const { correlation, requests } = setup(t)
  await correlation.submit()
  assert.deepEqual(requests[0].symbols, ['510300', '510500', '159915'])
  assert.equal(requests[0].endDate, '2026-09-07')
  for (const values of [['510300', '510300'], ['510300', '510500', ''], ['510300', 'bad'], Array(11).fill('510300')]) {
    correlation.symbols.value = values
    await correlation.submit()
    assert.equal(correlation.canSubmit.value, false)
  }
  assert.equal(requests.length, 1)
})

test('explicit ETF is submitted, unsupported benchmark and unavailable catalog are blocked', async t => {
  const { state, requests, assets } = setup(t)
  state.benchmark.value = '000300'
  assert.equal(state.canSubmit.value, false)
  state.benchmark.value = '510300'
  await state.submit()
  assert.equal(requests[0].benchmark, '510300')
  assert.match(state.benchmarkLabel.value, /ETF.*510300/)
  assets.value = []
  assert.equal(state.canSubmit.value, false)
})

test('double clicks produce only one POST and preserve the in-flight job', async t => {
  const { state, client, requests } = setup(t)
  const pending = deferred()
  client.getBacktest = () => pending.promise
  const first = state.submit()
  await Promise.resolve()
  assert.equal(state.job.value.jobId, jobId)
  await state.submit()
  assert.equal(state.job.value.jobId, jobId)
  assert.equal(requests.length, 1)
  pending.resolve({ jobId, status: 'succeeded', request: requests[0] })
  await first
})

test('correlation double clicks and disposal ignore late results', async t => {
  const { correlation, client, scope } = setup(t)
  const pending = deferred()
  let calls = 0
  client.getCorrelation = () => { calls += 1; return pending.promise }
  const first = correlation.submit()
  await correlation.submit()
  assert.equal(calls, 1)
  scope.stop()
  pending.resolve({ matrix: [[1]] })
  await first
  assert.equal(correlation.result.value, null)
})

test('poll error preserves ID, blocks duplicate active jobs, and resumes saved request', async t => {
  const { state, client, requests } = setup(t)
  client.getBacktest = async () => { throw Error('temporary failure') }
  await state.submit()
  assert.equal(state.recoveryId.value, jobId)
  assert.equal(state.canSubmit.value, false)
  assert.equal(state.busy.value, false)
  client.getBacktest = async () => ({ jobId, status: 'succeeded', request: requests[0] })
  await state.resume()
  assert.equal(requests.length, 1)
  assert.equal(state.job.value.status, 'succeeded')
})

test('saved ID survives a new component and recovers without POST', async t => {
  const saved = new Map()
  const storage = { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value) }
  const first = setup(t, storage)
  await first.state.submit()
  first.scope.stop()
  const second = setup(t, storage)
  assert.equal(second.state.recoveryId.value, jobId)
  second.client.getBacktest = async () => first.state.job.value
  await second.state.resume()
  assert.equal(second.state.job.value.request.strategyId, 'ma_cross')
  assert.equal(second.requests.length, 0)
})

test('unmount during polling prevents late updates and scheduled polls', async t => {
  const { state, client, scope } = setup(t)
  const pending = deferred()
  let polls = 0
  client.getBacktest = () => { polls += 1; return pending.promise }
  const submit = state.submit()
  await Promise.resolve()
  scope.stop()
  pending.resolve({ jobId, status: 'running' })
  await submit
  assert.equal(state.job.value.status, 'queued')
  assert.equal(polls, 1)
})


test('missing recovered task releases new submission without losing the ID', async t => {
  const { state, client } = setup(t)
  state.recoveryId.value = jobId
  client.getBacktest = async () => { throw Object.assign(Error('missing'), { code: 'JOB_NOT_FOUND' }) }
  await state.resume()
  assert.equal(state.job.value, null)
  assert.equal(state.recoveryId.value, jobId)
  assert.equal(state.canSubmit.value, true)
})

test('polling timeout retains active job and can resume without resubmitting', async t => {
  const { state, client, requests } = setup(t)
  t.mock.timers.enable({ apis: ['setTimeout'] })
  client.getBacktest = async () => ({ jobId, status: 'running', request: requests[0] })
  await state.submit()
  for (let i = 0; i < 150; i += 1) {
    t.mock.timers.tick(1500)
    await Promise.resolve()
  }
  assert.equal(state.busy.value, false)
  assert.equal(state.canSubmit.value, false)
  assert.match(state.error.value, /等待超时/)
  assert.equal(state.recoveryId.value, jobId)
  client.getBacktest = async () => ({ jobId, status: 'succeeded', request: requests[0] })
  await state.resume()
  assert.equal(requests.length, 1)
  assert.equal(state.canSubmit.value, true)
})


test('nullable correlation cells stay absent without throwing or fabricating zero', async () => {
  const { correlationOption } = await import('../src/dashboard/charts.js')
  const option = correlationOption({ symbols: ['510300', '510500'], matrix: [[1, null], [null, null]] })
  assert.deepEqual(option.series[0].data, [[0, 0, 1]])
})


test('equity chart compares returns at the same base despite different source units', async () => {
  const { equityOption } = await import('../src/dashboard/charts.js')
  const option = equityOption({ equityCurve: [
    { date: '2026-09-04', equity: 100000, benchmarkEquity: 1 },
    { date: '2026-09-07', equity: 110000, benchmarkEquity: 1.2 }
  ] })
  assert.deepEqual(option.series[0].data, [1, 1.1])
  assert.deepEqual(option.series[1].data, [1, 1.2])
  assert.equal(option.yAxis.name, '净值（首日=1）')
  const noBenchmark = equityOption({ equityCurve: [
    { date: '2026-09-07', equity: 100000, benchmarkEquity: null }
  ] })
  assert.equal(noBenchmark.series.length, 1)
  assert.deepEqual(noBenchmark.legend.data, ['策略净值'])
})


test('chart formatters retain raw precision and exclude invalid baselines', async () => {
  const { equityOption, correlationOption } = await import('../src/dashboard/charts.js')
  const raw = 1.123456789
  const option = equityOption({ equityCurve: [
    { date: '2026-09-04', equity: 1, benchmarkEquity: 0 },
    { date: '2026-09-07', equity: raw, benchmarkEquity: 2 }
  ] })
  assert.equal(option.series[0].data[1], raw)
  assert.equal(option.series.length, 1)
  assert.equal(option.tooltip.valueFormatter(raw), '1.1235')
  assert.equal(option.tooltip.valueFormatter(0), '0.0000')
  for (const invalid of [null, undefined, NaN, Infinity]) {
    assert.equal(option.tooltip.valueFormatter(invalid), '—')
  }
  const heatmap = correlationOption({ symbols: ['510300'], matrix: [[1]] })
  assert.equal(heatmap.visualMap.calculable, false)
  assert.equal(heatmap.visualMap.min, -1)
  assert.equal(heatmap.visualMap.max, 1)
})
