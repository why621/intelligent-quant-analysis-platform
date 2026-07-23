import { init, use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

let registered = false

export const getLineEcharts = () => {
  if (!registered) {
    use([
      LineChart,
      TooltipComponent,
      GridComponent,
      SVGRenderer
    ])
    registered = true
  }

  return { init }
}
