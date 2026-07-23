import { init, use } from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

let registered = false

export const getHeatmapEcharts = () => {
  if (!registered) {
    use([
      HeatmapChart,
      TooltipComponent,
      GridComponent,
      VisualMapComponent,
      SVGRenderer
    ])
    registered = true
  }

  return { init }
}
