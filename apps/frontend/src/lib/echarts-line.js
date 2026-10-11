import { init, use } from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, TitleComponent, LegendComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

let registered = false

export const getLineEcharts = () => {
  if (!registered) {
    use([
      LineChart,
      ScatterChart,
      TooltipComponent,
      TitleComponent,
      LegendComponent,
      GridComponent,
      SVGRenderer
    ])
    registered = true
  }

  return { init }
}
