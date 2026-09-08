import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'

import { api, API_BASE_URL } from '../services/api.js'
import { displayError, SYMBOL_PATTERN } from './common.js'
import { useResearchDates } from './use-research-dates.js'
import { useStrategyParameters } from './strategy-parameters.js'

const JOB_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const STORAGE_KEY = `quant:last-backtest:${API_BASE_URL}`

export function useBacktest(strategies, dataStatus, assetCatalog, client = api, storage) {
  const dates = useResearchDates(dataStatus)
  const symbols = ref(['510300'])
  const strategyId = ref('ma_cross')
  const benchmark = ref('')
  const job = ref(null)
  const busy = ref(false)
  const error = ref('')
  const recoveryId = ref('')
  let pollTimer = null
  let generation = 0
  let disposed = false
  try { if (storage === undefined) storage = globalThis.localStorage } catch { storage = null }
  try { recoveryId.value = storage?.getItem(STORAGE_KEY) || '' } catch { /* Storage may be disabled. */ }

  const availableStrategies = computed(() => strategies.value.filter(item => item.status === 'available'))
  const selectedStrategy = computed(() => availableStrategies.value.find(item => item.id === strategyId.value))
  const parameterForm = useStrategyParameters(selectedStrategy)
  const benchmarkOptions = computed(() => (assetCatalog?.value || []).filter(item => item.assetType === 'etf' && item.active))
  const activeJob = computed(() => ['queued', 'running'].includes(job.value?.status))
  const strategyName = computed(() => {
    const id = job.value ? job.value.request?.strategyId : strategyId.value
    return strategies.value.find(item => item.id === id)?.name || '历史任务（策略待确认）'
  })
  const benchmarkLabel = computed(() => {
    const code = job.value?.request?.benchmark
    if (job.value && !job.value.request) return '历史任务未返回请求快照，基准待确认'
    if (!code) return '无基准；Alpha / Beta 不适用'
    const asset = benchmarkOptions.value.find(item => item.symbol === code)
    return asset ? `${asset.name}（ETF · ${code}）` : `历史基准 ${code}（身份未验证）`
  })
  const validationError = computed(() => {
    if (!symbols.value.length || symbols.value.length > 10
      || symbols.value.some(value => !SYMBOL_PATTERN.test(value))
      || new Set(symbols.value).size !== symbols.value.length) return '请选择 1–10 个不同的六位资产代码。'
    if (!selectedStrategy.value) return '请选择可用策略。'
    if (parameterForm.parameterError.value) return parameterForm.parameterError.value
    if (benchmark.value && !benchmarkOptions.value.some(item => item.symbol === benchmark.value)) return '请选择目录中的 ETF 或无基准。'
    return dates.dateError.value
  })
  const canSubmit = computed(() => !busy.value && !activeJob.value && !disposed && !validationError.value)
  const current = token => !disposed && token === generation
  const saveId = value => {
    recoveryId.value = value
    try { storage?.setItem(STORAGE_KEY, value) } catch { /* ID remains visible in the page. */ }
  }
  const stopTimer = () => { if (pollTimer !== null) clearTimeout(pollTimer); pollTimer = null }
  const poll = async (jobId, token, attempt = 0) => {
    if (!current(token)) return
    if (attempt >= 150) {
      busy.value = false
      error.value = '回测等待超时，任务仍可能运行；请使用任务编号恢复查询。'
      return
    }
    try {
      const response = await client.getBacktest(jobId)
      if (!current(token)) return
      if (response.jobId !== jobId) throw Error('返回的任务编号不匹配。')
      job.value = response
      if (['succeeded', 'failed'].includes(response.status)) {
        busy.value = false
        if (response.status === 'failed') error.value = response.error?.error?.message || '回测任务失败'
      } else {
        pollTimer = setTimeout(() => poll(jobId, token, attempt + 1), 1500)
      }
    } catch (requestError) {
      if (current(token)) {
        busy.value = false
        if (requestError.code === 'JOB_NOT_FOUND') job.value = null
        error.value = `${displayError(requestError)}；保留任务编号，可恢复查询。`
      }
    }
  }
  const resume = async () => {
    if (busy.value || disposed) return
    const id = recoveryId.value.trim()
    if (!JOB_PATTERN.test(id)) { error.value = '请输入有效的 UUID 任务编号。'; return }
    stopTimer()
    const token = ++generation
    busy.value = true
    error.value = ''
    job.value = { jobId: id, status: 'queued' }
    saveId(id)
    await poll(id, token)
  }
  const submit = async () => {
    if (busy.value || disposed || activeJob.value) return
    if (!canSubmit.value) { error.value = validationError.value; return }
    stopTimer()
    const token = ++generation
    busy.value = true
    error.value = ''
    job.value = null
    const payload = {
      symbols: [...symbols.value], strategyId: strategyId.value,
      parameters: Object.fromEntries(Object.entries(parameterForm.parameters.value)
        .filter(([, value]) => value !== '' && value != null)),
      startDate: dates.startDate.value, endDate: dates.endDate.value,
      ...(benchmark.value ? { benchmark: benchmark.value } : {}),
      initialCapitalCny: 100000, adjust: 'qfq',
      tradingCosts: { commissionPct: 0.03, stampDutyPct: 0.05, slippagePct: 0.02 }
    }
    try {
      const response = await client.createBacktest(payload)
      // Save an accepted ID even if navigation occurred while the POST was in flight.
      if (JOB_PATTERN.test(response.jobId)) {
        try { storage?.setItem(STORAGE_KEY, response.jobId) } catch { /* Optional persistence. */ }
      }
      if (!current(token)) return
      if (!JOB_PATTERN.test(response.jobId)) throw Error('服务器未返回有效任务编号。')
      job.value = { ...response, request: response.request || payload }
      saveId(response.jobId)
      await poll(response.jobId, token)
    } catch (requestError) {
      if (current(token)) { busy.value = false; error.value = displayError(requestError) }
    }
  }
  if (getCurrentScope()) onScopeDispose(() => { disposed = true; generation += 1; stopTimer() })
  return { ...dates, ...parameterForm, symbols, strategyId, benchmark, benchmarkOptions,
    benchmarkLabel, job, busy, error, recoveryId, activeJob, availableStrategies, strategyName,
    validationError, canSubmit, submit, resume }
}
