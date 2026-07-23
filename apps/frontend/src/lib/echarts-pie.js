import { init, use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

let registered = false

export const getPieEcharts = () => {
  if (!registered) {
    use([
      PieChart,
      TooltipComponent,
      LegendComponent,
      SVGRenderer
    ])
    registered = true
  }

  return { init }
}
