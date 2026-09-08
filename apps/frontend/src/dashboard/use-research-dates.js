import { computed, ref, watch } from 'vue'

export const CALENDAR_START = '2025-01-01'
const CALENDAR_END = '2026-12-31'
const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '')
  && Number.isFinite(Date.parse(value))
  && new Date(value).toISOString().slice(0, 10) === value

export function useResearchDates(dataStatus) {
  const startDate = ref('')
  const endDate = ref('')
  let edited = false
  let initialising = false
  const publishedDate = computed(() => dataStatus?.value?.latestTradeDate || '')
  const maxDate = computed(() => validDate(publishedDate.value)
    ? (publishedDate.value < CALENDAR_END ? publishedDate.value : CALENDAR_END) : '')
  watch([startDate, endDate], () => { if (!initialising) edited = true }, { flush: 'sync' })
  watch(maxDate, cutoff => {
    if (!validDate(cutoff) || edited) return
    initialising = true
    const start = new Date(cutoff)
    start.setUTCFullYear(start.getUTCFullYear() - 1)
    startDate.value = start.toISOString().slice(0, 10) < CALENDAR_START
      ? CALENDAR_START : start.toISOString().slice(0, 10)
    endDate.value = cutoff
    initialising = false
  }, { immediate: true, flush: 'sync' })
  const dateError = computed(() => {
    const status = dataStatus?.value
    const historyState = status?.components?.history?.status || status?.status
    if (!maxDate.value || historyState === 'failed') return '历史数据尚无可用发布状态，请等待数据更新。'
    if (!validDate(startDate.value) || !validDate(endDate.value)) return '请输入有效的开始和结束日期。'
    if (startDate.value > endDate.value) return '开始日期不能晚于结束日期。'
    if (startDate.value < CALENDAR_START || endDate.value > maxDate.value) {
      return `日期须在 ${CALENDAR_START} 至 ${maxDate.value} 内；请修改所选日期。`
    }
    return ''
  })
  const dateNotice = computed(() => publishedDate.value
    ? `历史数据已发布至 ${publishedDate.value}；当前日历从 ${CALENDAR_START} 起。全局截止不保证每只资产完整，提交时仍会校验共同交易日。`
    : '等待历史数据发布截止，暂不能提交。')
  return { startDate, endDate, publishedDate, maxDate, minDate: CALENDAR_START, dateError, dateNotice }
}
