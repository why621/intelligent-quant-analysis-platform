const colors = {
  blue: '#2563eb',
  amber: '#f59e0b',
  red: '#e11d48',
  grid: '#e2e8f0',
  muted: '#64748b'
}

export function emptyChartOption(message) {
  return {
    title: {
      text: message,
      left: 'center',
      top: 'middle',
      textStyle: { color: colors.muted, fontSize: 13, fontWeight: 500 }
    }
  }
}

export function correlationOption(result) {
  if (!result?.symbols?.length || !result?.matrix?.length) {
    return emptyChartOption('提交 2–10 个资产后显示真实相关矩阵')
  }
  const data = []
  result.matrix.forEach((row, y) => {
    row.forEach((value, x) => {
      if (typeof value === 'number' && Number.isFinite(value)) data.push([x, y, Number(value.toFixed(3))])
    })
  })
  return {
    tooltip: {
      formatter: ({ data: item }) =>
        `${result.symbols[item[1]]} / ${result.symbols[item[0]]}<br>${item[2]}`
    },
    grid: { left: 64, right: 22, top: 20, bottom: 84 },
    xAxis: { type: 'category', data: result.symbols, splitArea: { show: true } },
    yAxis: { type: 'category', data: result.symbols, splitArea: { show: true } },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      inRange: { color: [colors.red, '#ffffff', colors.blue] }
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true }
    }]
  }
}

export function equityOption(result) {
  const points = result?.equityCurve || []
  if (!points.length) return emptyChartOption('回测完成后显示净值曲线')
  const normalised = field => {
    const baseline = points[0][field]
    return points.map(point => typeof point[field] === 'number' && Number.isFinite(point[field])
      && typeof baseline === 'number' && baseline > 0 ? point[field] / baseline : null)
  }
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 4, data: ['策略净值', '基准净值'] },
    grid: { left: 52, right: 18, top: 64, bottom: 38 },
    xAxis: { type: 'category', data: points.map((item) => item.date) },
    yAxis: { name: '净值（首日=1）', type: 'value', scale: true, splitLine: { lineStyle: { color: colors.grid } } },
    series: [
      {
        name: '策略净值',
        type: 'line',
        showSymbol: false,
        data: normalised('equity'),
        lineStyle: { color: colors.blue, width: 2 }
      },
      {
        name: '基准净值',
        type: 'line',
        showSymbol: false,
        data: normalised('benchmarkEquity'),
        lineStyle: { color: colors.amber, width: 2, type: 'dashed' }
      }
    ]
  }
}

export function allocationOption(result) {
  if (!result) return emptyChartOption('生成后显示下一交易日模拟权重')
  const positions = result?.positions || []
  // Zero-weight exits remain in the textual details, not as empty pie slices.
  const data = positions.filter(item => item.weightPct > 0)
    .map((item) => ({ name: item.symbol, value: item.weightPct }))
  if (result.cashPct > 0) data.push({ name: '现金', value: result.cashPct })
  if (!data.length) return emptyChartOption('没有可展示的持仓或现金权重')
  return {
    animation: false,
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['44%', '70%'],
      center: ['50%', '44%'],
      data,
      label: { formatter: '{b}\n{d}%' }
    }]
  }
}
