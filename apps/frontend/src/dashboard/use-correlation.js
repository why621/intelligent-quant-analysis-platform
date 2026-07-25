import { computed, ref } from 'vue'

import { api } from '../services/api'
import { defaultDateRange, displayError, SYMBOL_PATTERN } from './common'

export function useCorrelation() {
  const range = defaultDateRange()
  const symbols = ref(['510300', '510500', '159915'])
  const startDate = ref(range.startDate)
  const endDate = ref(range.endDate)
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')

  const validSymbols = computed(() => {
    const values = symbols.value
      .map((value) => value.trim())
      .filter((value) => SYMBOL_PATTERN.test(value))
    return [...new Set(values)].slice(0, 10)
  })

  const canSubmit = computed(() =>
    validSymbols.value.length >= 2
      && startDate.value
      && endDate.value
      && startDate.value <= endDate.value
  )

  const addSymbol = () => {
    if (symbols.value.length < 10) symbols.value.push('')
  }

  const removeSymbol = (index) => {
    if (symbols.value.length > 2) symbols.value.splice(index, 1)
  }

  const submit = async () => {
    error.value = ''
    result.value = null
    if (!canSubmit.value) {
      error.value = '请输入 2–10 个不同的六位资产代码，并检查日期范围。'
      return
    }
    busy.value = true
    try {
      result.value = await api.getCorrelation({
        symbols: validSymbols.value,
        startDate: startDate.value,
        endDate: endDate.value,
        adjust: 'qfq',
        returnType: 'simple'
      })
    } catch (requestError) {
      error.value = displayError(requestError)
    } finally {
      busy.value = false
    }
  }

  return {
    symbols,
    startDate,
    endDate,
    result,
    busy,
    error,
    validSymbols,
    canSubmit,
    addSymbol,
    removeSymbol,
    submit
  }
}
