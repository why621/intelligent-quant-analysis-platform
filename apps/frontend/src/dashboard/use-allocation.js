import { computed, ref } from 'vue'

import { api } from '../services/api'
import { displayError } from './common'

export function useAllocation(strategies) {
  const symbols = ref(['510300', '510500'])
  const strategyId = ref('momentum_reversal')
  const cashPct = ref(10)
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')

  const availableStrategies = computed(() =>
    strategies.value.filter((strategy) => strategy.status === 'available')
  )
  const canSubmit = computed(() =>
    symbols.value.length > 0
      && availableStrategies.value.some((item) => item.id === strategyId.value)
      && !busy.value
  )

  const submit = async () => {
    error.value = ''
    result.value = null
    if (!canSubmit.value) {
      error.value = '请选择至少一个资产和一个已实现策略。'
      return
    }
    busy.value = true
    try {
      result.value = await api.getAllocationSuggestion({
        symbols: symbols.value,
        strategyId: strategyId.value,
        cashPct: Number(cashPct.value)
      })
    } catch (requestError) {
      error.value = displayError(requestError)
    } finally {
      busy.value = false
    }
  }

  return {
    symbols,
    strategyId,
    cashPct,
    result,
    busy,
    error,
    availableStrategies,
    canSubmit,
    submit
  }
}
