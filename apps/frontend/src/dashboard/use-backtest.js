import { computed, onBeforeUnmount, ref } from 'vue'

import { api } from '../services/api'
import { defaultDateRange, displayError } from './common'

export function useBacktest(strategies) {
  const range = defaultDateRange()
  const symbols = ref(['510300'])
  const strategyId = ref('ma_cross')
  const startDate = ref(range.startDate)
  const endDate = ref(range.endDate)
  const job = ref(null)
  const busy = ref(false)
  const error = ref('')
  let pollTimer = null

  const availableStrategies = computed(() =>
    strategies.value.filter((strategy) => strategy.status === 'available')
  )
  const strategyName = computed(() =>
    strategies.value.find((item) => item.id === strategyId.value)?.name || '未选择'
  )
  const canSubmit = computed(() =>
    symbols.value.length > 0
      && availableStrategies.value.some((item) => item.id === strategyId.value)
      && startDate.value <= endDate.value
      && !busy.value
  )

  const poll = async (jobId, attempt = 0) => {
    if (attempt >= 150) {
      busy.value = false
      error.value = '回测等待超时，请稍后使用任务编号重新查询。'
      return
    }
    try {
      job.value = await api.getBacktest(jobId)
      if (['succeeded', 'failed'].includes(job.value.status)) {
        busy.value = false
        if (job.value.status === 'failed') {
          error.value = job.value.error?.error?.message || '回测任务失败'
        }
        return
      }
      pollTimer = window.setTimeout(() => poll(jobId, attempt + 1), 1500)
    } catch (requestError) {
      busy.value = false
      error.value = displayError(requestError)
    }
  }

  const submit = async () => {
    error.value = ''
    job.value = null
    if (!canSubmit.value) {
      error.value = '请选择可用策略、至少一个资产，并检查日期范围。'
      return
    }
    busy.value = true
    try {
      job.value = await api.createBacktest({
        symbols: symbols.value,
        strategyId: strategyId.value,
        parameters: {},
        startDate: startDate.value,
        endDate: endDate.value,
        benchmark: '000300',
        initialCapitalCny: 100000,
        adjust: 'qfq',
        tradingCosts: {
          commissionPct: 0.03,
          stampDutyPct: 0.05,
          slippagePct: 0.02
        }
      })
      await poll(job.value.jobId)
    } catch (requestError) {
      busy.value = false
      error.value = displayError(requestError)
    }
  }

  onBeforeUnmount(() => {
    if (pollTimer) window.clearTimeout(pollTimer)
  })

  return {
    symbols,
    strategyId,
    startDate,
    endDate,
    job,
    busy,
    error,
    availableStrategies,
    strategyName,
    canSubmit,
    submit
  }
}
