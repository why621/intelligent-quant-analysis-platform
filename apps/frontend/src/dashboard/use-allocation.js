import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'

import { api } from '../services/api.js'
import { displayError, SYMBOL_PATTERN } from './common.js'

export function useAllocation(strategies, client = api) {
  const symbols = ref(['510300', '510500'])
  const strategyId = ref('momentum_reversal')
  const cashPct = ref(10)
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')
  const disposed = ref(false)

  const availableStrategies = computed(() =>
    strategies.value.filter((strategy) => strategy.status === 'available')
  )
  const validationError = computed(() => {
    if (!symbols.value.length || symbols.value.length > 10
      || symbols.value.some(value => !SYMBOL_PATTERN.test(value))
      || new Set(symbols.value).size !== symbols.value.length) return '请选择 1–10 个不同的六位资产代码。'
    if (!availableStrategies.value.some(item => item.id === strategyId.value)) return '请选择已实现的可用策略。'
    if (typeof cashPct.value !== 'number' || !Number.isFinite(cashPct.value)
      || cashPct.value < 0 || cashPct.value > 100) return '现金比例必须填写 0–100 之间的有限数值。'
    return ''
  })
  const canSubmit = computed(() => !disposed.value && !busy.value && !validationError.value)

  const submit = async () => {
    if (busy.value || disposed.value) return
    if (!canSubmit.value) {
      error.value = validationError.value
      return
    }
    error.value = ''
    result.value = null
    busy.value = true
    const payload = {
      symbols: [...symbols.value],
      strategyId: strategyId.value,
      cashPct: cashPct.value
    }
    try {
      const response = await client.getAllocationSuggestion(payload)
      if (!disposed.value) result.value = response
    } catch (requestError) {
      if (!disposed.value) error.value = displayError(requestError)
    } finally {
      if (!disposed.value) busy.value = false
    }
  }

  if (getCurrentScope()) onScopeDispose(() => { disposed.value = true })

  return {
    symbols,
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
