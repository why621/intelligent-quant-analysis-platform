// Only visible containers are initialized. Data and interaction state survive theme changes.
export function createChartLifecycle(definitions, { theme, onError = () => {} }) {
  const entries = new Map()
  let disposed = false
  async function sync(tab) {
    if (disposed) return
    await Promise.all(Object.entries(definitions).map(async ([name, def]) => {
      if (def.tab !== tab) return
      const el = def.element.value
      if (!el || !el.clientWidth || !el.clientHeight) return
      let state = entries.get(name)
      if (!state) { state = {}; entries.set(name, state) }
      try {
        // Share a module load across quick tab and theme changes.
        state.loading ||= def.load()
        state.module = await state.loading
        if (disposed || !el.clientWidth || !el.clientHeight) return
        const nextTheme = theme()
        if (!state.chart || state.theme !== nextTheme) {
          const previous = state.chart?.getOption()
          const retained = previous ? {
            ...(Array.isArray(previous.legend) ? { legend: previous.legend.map(l => ({ ...(l.id ? { id: l.id } : {}), selected: l.selected })) } : {}),
            ...(Array.isArray(previous.dataZoom) ? { dataZoom: previous.dataZoom.map(z => ({ ...(z.id ? { id: z.id } : {}), start: z.start, end: z.end, startValue: z.startValue, endValue: z.endValue })) } : {})
          } : null
          state.chart?.dispose()
          state.chart = def.create(state.module).init(el, nextTheme, { renderer: 'svg' })
          state.theme = nextTheme
          state.chart.setOption(def.option())
          if (retained) state.chart.setOption(retained)
        }
        state.chart.resize()
        onError(name, '')
      } catch (error) {
        console.error('Chart render failed:', name, error)
        state.loading = null
        onError(name, '图表暂时无法显示，切换模块可重试；已取得的数据和结果仍可查看。')
      }
    }))
  }
  function update(names) {
    for (const name of names) {
      const entry = entries.get(name)
      if (entry?.chart) entry.chart.setOption(definitions[name].option(), true)
    }
  }
  function dispose() { disposed = true; entries.forEach(s => s.chart?.dispose()); entries.clear() }
  return { sync, update, dispose }
}
