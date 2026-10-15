import { computed, ref, watch } from 'vue'

const copy = value => JSON.parse(JSON.stringify(value))
export const snapshotKey = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item)

// Flow is strictly correlation -> backtest -> allocation. Editing a downstream
// draft detaches that field group; existing results and running requests are immutable.
export function useResearchContext(correlation, backtest, allocation, dataStatus) {
  const backtestAssetsLinked = ref(true)
  const backtestDatesLinked = ref(true)
  const allocationAssetsLinked = ref(true)
  const allocationConfigLinked = ref(true)
  const notice = ref('')
  const backtestLocked = computed(() => backtest.busy.value || backtest.activeJob.value)
  const allocationLocked = computed(() => allocation.busy.value)
  const syncBacktest = () => {
    if (backtestLocked.value) return
    if (backtestAssetsLinked.value) backtest.symbols.value = [...correlation.symbols.value]
    if (backtestDatesLinked.value) {
      backtest.startDate.value = correlation.startDate.value
      backtest.endDate.value = correlation.endDate.value
    }
  }
  const syncAllocation = () => {
    if (allocationLocked.value) return
    if (allocationAssetsLinked.value) allocation.symbols.value = [...backtest.symbols.value]
    if (allocationConfigLinked.value) {
      allocation.strategyId.value = backtest.strategyId.value
      allocation.parameters.value = copy(backtest.parameters.value)
      allocation.tradingCosts.value = copy(backtest.effectiveTradingCosts.value)
      allocation.initialCapitalCny.value = backtest.initialCapitalCny.value
      allocation.cashPct.value = backtest.cashPct.value
      allocation.startDate.value = backtest.startDate.value
    }
  }
  watch(() => [correlation.symbols.value, correlation.startDate.value, correlation.endDate.value,
    backtestAssetsLinked.value, backtestDatesLinked.value, backtestLocked.value], syncBacktest,
  { immediate: true, deep: true, flush: 'sync' })
  watch(() => [backtest.symbols.value, backtest.strategyId.value, backtest.parameters.value,
    backtest.effectiveTradingCosts.value, backtest.initialCapitalCny.value, backtest.cashPct.value, backtest.startDate.value,
    allocationAssetsLinked.value, allocationConfigLinked.value, allocationLocked.value], syncAllocation,
  { immediate: true, deep: true, flush: 'sync' })
  const editable = (field, linked, locked) => computed({ get: () => field.value, set: value => {
    if (locked.value) return
    linked.value = false
    field.value = copy(value)
  } })
  const backtestSymbols = editable(backtest.symbols, backtestAssetsLinked, backtestLocked)
  const backtestStartDate = editable(backtest.startDate, backtestDatesLinked, backtestLocked)
  const backtestEndDate = editable(backtest.endDate, backtestDatesLinked, backtestLocked)
  const allocationSymbols = editable(allocation.symbols, allocationAssetsLinked, allocationLocked)
  const allocationStrategyId = editable(allocation.strategyId, allocationConfigLinked, allocationLocked)
  function restoreBacktest() {
    if (backtestLocked.value) return
    backtestAssetsLinked.value = true; backtestDatesLinked.value = true; syncBacktest()
  }
  function restoreAllocation() {
    if (allocationLocked.value) return
    allocationAssetsLinked.value = true; allocationConfigLinked.value = true; syncAllocation()
  }
  function usePublishedRange() {
    const end = dataStatus.value.latestTradeDate
    if (!end || correlation.busy.value) return
    const start = new Date(`${end}T00:00:00Z`); start.setUTCDate(start.getUTCDate() - 365)
    correlation.startDate.value = [start.toISOString().slice(0, 10), correlation.minDate].sort().at(-1)
    correlation.endDate.value = end
    notice.value = '已设置最近一年研究区间。请检查各模块数据覆盖后手动计算。'
  }
  function loadRanking(item, metadata) {
    if (backtestLocked.value) { notice.value = '请等待当前回测结束后再载入排行配置。'; return false }
    if (metadata?.request) {
      const request = metadata.request
      if (!request.symbols?.length || !request.startDate || !request.endDate || !request.tradingCosts || !item.parameters) {
        notice.value = '该排行缺少完整研究配置，不能载入。'; return false
      }
      backtestAssetsLinked.value = false; backtestDatesLinked.value = false
      backtest.symbols.value = [...request.symbols]
      backtest.strategyId.value = item.strategyId
      backtest.parameters.value = copy(item.parameters)
      backtest.startDate.value = request.startDate
      backtest.endDate.value = request.endDate
      backtest.initialCapitalCny.value = request.initialCapitalCny
      backtest.cashPct.value = request.cashPct
      backtest.tradingCosts.value = copy(request.tradingCosts)
      backtest.benchmarkMode.value = request.benchmarkMode
      backtest.benchmark.value = request.benchmark || ''
      notice.value = `已载入该策略在排行榜中的完整配置：${request.startDate} 至 ${request.endDate}；资金、费用、现金与基准保持一致。请手动提交回测。`
      return true
    }
    if (!metadata?.evaluationStartDate || !metadata?.evaluationEndDate || !metadata?.historyStartDate || !item.parameters || !metadata.tradingCosts) {
      notice.value = '该排行未提供完整评价区间、预热起点或配置，不能猜测后载入。'; return false
    }
    backtestAssetsLinked.value = false; backtestDatesLinked.value = false
    backtest.symbols.value = [...(metadata.evaluationSymbols || ['510300'])]
    backtest.strategyId.value = item.strategyId
    backtest.parameters.value = copy(item.parameters)
    // Include the recorded warmup history. The leaderboard's metric window is
    // explicitly narrower; do not label a full backtest as the same comparison.
    backtest.startDate.value = metadata.historyStartDate
    backtest.endDate.value = metadata.evaluationEndDate
    backtest.tradingCosts.value = copy(metadata.tradingCosts)
    notice.value = `已载入排行配置及预热历史；排行评价区间为 ${metadata.evaluationStartDate} 至 ${metadata.evaluationEndDate}。回测展示全请求区间，指标不会自动等同于排行。`
    return true
  }
  return { backtestAssetsLinked, backtestDatesLinked, allocationAssetsLinked, allocationConfigLinked,
    backtestSymbols, backtestStartDate, backtestEndDate, allocationSymbols, allocationStrategyId,
    restoreBacktest, restoreAllocation, usePublishedRange, loadRanking, notice, backtestLocked }
}
