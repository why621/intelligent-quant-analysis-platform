// Each task starts independently; unavailable charts cannot block API reads.
export async function initialiseDashboard(initialise, chartTasks, onChartError) {
  return Promise.allSettled([
    Promise.resolve().then(initialise),
    ...Object.entries(chartTasks).map(([name, start]) =>
      Promise.resolve().then(start).catch(error => onChartError(name, error)))
  ])
}
