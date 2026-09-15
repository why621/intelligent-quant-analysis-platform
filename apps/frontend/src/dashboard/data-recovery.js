// Recovery proposals change inputs only after an explicit click; preflight runs again.
export function recoveryOptions(request, result, assets = []) {
  if (result?.state !== 'unavailable') return []
  const issues = result.issues || []
  const symbols = request.symbols || []
  const bad = new Set(issues.map(i => i.symbol).filter(Boolean))
  const options = []
  const minimum = request.module === 'correlation' ? 2 : 1
  const retained = symbols.filter(s => !bad.has(s))
  if (!issues.some(i => !i.symbol) && retained.length >= minimum && retained.length < symbols.length) {
    options.push({ label: `移除缺数资产 ${symbols.filter(s => bad.has(s)).join('、')}，保留 ${retained.length} 只并重新检查`, patch: { symbols: retained } })
  }
  if (request.module === 'backtest' && request.benchmark && bad.has(request.benchmark)) {
    options.push({ label: '取消缺数比较基准（Alpha / Beta 不适用）', patch: { benchmark: null } })
  }
  if (['correlation', 'backtest'].includes(request.module)) {
    const dependencies = [...new Set([...symbols, ...(request.benchmark ? [request.benchmark] : [])])]
    const dates = dependencies.map(s => assets.find(a => a.symbol === s)?.availability?.lastTradeDate)
    if (dates.length && dates.every(d => /^\d{4}-\d{2}-\d{2}$/.test(d || ''))) {
      const endDate = [...dates].sort()[0]
      if (endDate < request.endDate && endDate > request.startDate) {
        options.push({ label: `保留所选资产，结束日期改为 ${endDate} 并重新检查`, patch: { endDate } })
      }
    }
  }
  return options
}
