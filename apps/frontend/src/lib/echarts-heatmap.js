import { init, use } from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent, TitleComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

let registered = false

export const getHeatmapEcharts = () => {
  if (!registered) {
    use([
      HeatmapChart,
      TooltipComponent,
      TitleComponent,
      GridComponent,
      VisualMapComponent,
      SVGRenderer
    ])
    registered = true
  }

  return { init }
}
