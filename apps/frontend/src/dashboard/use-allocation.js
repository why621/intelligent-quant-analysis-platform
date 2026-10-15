import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'

import { api } from '../services/api.js'
import { displayError, SYMBOL_PATTERN } from './common.js'
import { useStrategyParameters } from './strategy-parameters.js'
import { snapshotKey } from './use-research-context.js'
import { modelAssetError } from './model-disclosure.js'

export function useAllocation(strategies, client = api, dataStatus, assetCatalog) {
  const symbols = ref(['510300', '510500'])
  const strategyId = ref('momentum_reversal')
  const cashPct = ref(10)
  const startDate = ref('')
  const initialCapitalCny = ref(100000)
  const tradingCosts = ref({ commissionPct: 0.03, stampDutyPct: 0.05, slippagePct: 0.02, stampDutyMode: 'asset_date' })
  const selectedStrategy = computed(() => strategies.value.find(item => item.id === strategyId.value))
  const parameterForm = useStrategyParameters(selectedStrategy)
  const resultRequest = ref(null)
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')
  const disposed = ref(false)

  const availableStrategies = computed(() =>
    strategies.value.filter((strategy) => strategy.status === 'available' || strategy.allocationEnabled === true)
  )
  const validationError = computed(() => {
    if (!symbols.value.length || symbols.value.length > 10
      || symbols.value.some(value => !SYMBOL_PATTERN.test(value))
      || new Set(symbols.value).size !== symbols.value.length) return '请选择 1–10 个不同的六位资产代码。'
    if (!availableStrategies.value.some(item => item.id === strategyId.value)) return '当前策略尚不支持模拟配置；现有 AI 模型仅支持实验回测。请显式选择传统策略。'
    if (parameterForm.parameterError.value) return parameterForm.parameterError.value
    if (typeof initialCapitalCny.value !== 'number' || !Number.isFinite(initialCapitalCny.value) || initialCapitalCny.value <= 0) return '初始资金必须为正数。'
    if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate.value) || !Number.isFinite(Date.parse(startDate.value))
      || new Date(startDate.value).toISOString().slice(0, 10) !== startDate.value) return '请设置有效的历史重放开始日期。'
    if (dataStatus?.value?.latestTradeDate && startDate.value > dataStatus.value.latestTradeDate) return '重放开始日期不能晚于最新发布交易日。'
    if (!['asset_date', 'fixed'].includes(tradingCosts.value.stampDutyMode)
      || ['commissionPct', 'stampDutyPct', 'slippagePct'].some(key => typeof tradingCosts.value[key] !== 'number' || !Number.isFinite(tradingCosts.value[key]) || tradingCosts.value[key] < 0)) return '费用必须为非负有限数值。'
    if (typeof cashPct.value !== 'number' || !Number.isFinite(cashPct.value)
      || cashPct.value < 0 || cashPct.value > 100) return '现金比例必须填写 0–100 之间的有限数值。'
    const model = selectedStrategy.value?.modelContext
    if (model?.portfolioMode === 'joint_portfolio') {
      const scopeError = modelAssetError(model, symbols.value, assetCatalog?.value || [])
      if (scopeError) return scopeError
      if (model.costPolicy !== 'request_configurable' && cashPct.value !== 0) return '组合模型自行决定现金权重，额外预留现金须显式设为 0%。'
      if (startDate.value < model.outOfSampleStartDate) return `组合模拟起始日须从 ${model.outOfSampleStartDate} 起，不能与训练或验证区间重叠。`
    }
    return ''
  })
  const canSubmit = computed(() => !disposed.value && !busy.value && !validationError.value)
  const draft = computed(() => ({ symbols: [...symbols.value], strategyId: strategyId.value,
    cashPct: cashPct.value, parameters: { ...parameterForm.parameters.value }, adjust: 'qfq',
    tradingCosts: { ...tradingCosts.value }, initialCapitalCny: initialCapitalCny.value, startDate: startDate.value }))
  const resultStale = computed(() => Boolean(result.value && resultRequest.value && (snapshotKey(draft.value) !== snapshotKey(
    Object.fromEntries(Object.keys(draft.value).map(key => [key, resultRequest.value[key]]))))
    || (result.value?.dataContext?.dataVersion && dataStatus?.value?.dataContext?.dataVersion
      && result.value.dataContext.dataVersion !== dataStatus.value.dataContext.dataVersion)))

  const submit = async () => {
    if (busy.value || disposed.value) return
    if (!canSubmit.value) {
      error.value = validationError.value
      return
    }
    error.value = ''
    result.value = null
    busy.value = true
    const payload = JSON.parse(JSON.stringify(draft.value))
    try {
      const response = await client.getAllocationSuggestion(payload)
      if (!disposed.value) { result.value = response; resultRequest.value = response.request || payload }
    } catch (requestError) {
      if (!disposed.value) error.value = displayError(requestError)
    } finally {
      if (!disposed.value) busy.value = false
    }
  }

  if (getCurrentScope()) onScopeDispose(() => { disposed.value = true })

  return {
    symbols,
    ...parameterForm, startDate, initialCapitalCny, tradingCosts, selectedStrategy, resultRequest, resultStale,
    strategyId,
    cashPct,
    result,
    busy,
    error,
    availableStrategies,
    validationError,
    canSubmit,
    submit
  }
}
