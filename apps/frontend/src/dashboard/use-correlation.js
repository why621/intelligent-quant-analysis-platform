import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'

import { api } from '../services/api.js'
import { displayError, SYMBOL_PATTERN } from './common.js'
import { useResearchDates } from './use-research-dates.js'

export function useCorrelation(dataStatus, client = api) {
  const dates = useResearchDates(dataStatus)
  const symbols = ref(['510300', '510500', '159915'])
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')
  let disposed = false
  const validSymbols = computed(() => symbols.value.filter(value => SYMBOL_PATTERN.test(value)))
  const symbolError = computed(() => {
    const values = symbols.value
    return values.length < 2 || values.length > 10
      || values.some(value => !SYMBOL_PATTERN.test(value))
      || new Set(values).size !== values.length
      ? '请输入 2–10 个不同的六位资产代码；空白、重复或非法代码不能提交。' : ''
  })
  const validationError = computed(() => symbolError.value || dates.dateError.value)
  const canSubmit = computed(() => !disposed && !busy.value && !validationError.value)
  const addSymbol = () => { if (symbols.value.length < 10) symbols.value.push('') }
  const removeSymbol = index => { if (symbols.value.length > 2) symbols.value.splice(index, 1) }
  const submit = async () => {
    if (disposed || busy.value) return
    if (!canSubmit.value) { error.value = validationError.value; return }
    error.value = ''
    result.value = null
    busy.value = true
    try {
      const response = await client.getCorrelation({
        symbols: [...symbols.value], startDate: dates.startDate.value, endDate: dates.endDate.value,
        adjust: 'qfq', returnType: 'simple'
      })
      if (!disposed) result.value = response
    } catch (requestError) {
      if (!disposed) error.value = displayError(requestError)
    } finally {
      if (!disposed) busy.value = false
    }
  }
  if (getCurrentScope()) onScopeDispose(() => { disposed = true })
  return { ...dates, symbols, result, busy, error, validSymbols, validationError,
    canSubmit, addSymbol, removeSymbol, submit }
}
