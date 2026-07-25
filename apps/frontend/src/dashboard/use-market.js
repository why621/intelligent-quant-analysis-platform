import { reactive, ref } from 'vue'

import { fallbackAssets, fallbackMarket, fallbackStrategies } from '../data/application-fixtures'
import { api } from '../services/api'

export function useMarket() {
  const connection = reactive({
    loading: true,
    live: false,
    message: '正在连接后端接口'
  })
  const dataStatus = ref({
    status: 'stale',
    timezone: 'Asia/Shanghai',
    source: 'AkShare',
    assetCount: fallbackAssets.length,
    latestTradeDate: null,
    updatedAt: null,
    message: '等待后端数据接口'
  })
  const assetCatalog = ref(fallbackAssets)
  const market = ref({ ...fallbackMarket })
  const strategies = ref(fallbackStrategies)
  const ranking = ref([])

  const initialise = async () => {
    connection.loading = true
    const results = await Promise.allSettled([
      api.getDataStatus(),
      api.listAssets({ limit: 50 }),
      api.getMarketOverview(),
      api.getStrategies(),
      api.getStrategyRanking('30d')
    ])

    if (results[0].status === 'fulfilled') dataStatus.value = results[0].value
    if (results[1].status === 'fulfilled' && results[1].value.items?.length) {
      assetCatalog.value = results[1].value.items
    }
    if (results[2].status === 'fulfilled') market.value = results[2].value
    if (results[3].status === 'fulfilled' && results[3].value.items?.length) {
      strategies.value = results[3].value.items
    }
    if (results[4].status === 'fulfilled') ranking.value = results[4].value.items || []

    const fulfilledCount = results.filter((result) => result.status === 'fulfilled').length
    connection.live = fulfilledCount === results.length
    connection.loading = false
    connection.message = connection.live
      ? '接口数据'
      : `后端待接入：目录为演示占位（${fulfilledCount}/${results.length} 个读取接口可用）`
  }

  return {
    connection,
    dataStatus,
    assetCatalog,
    market,
    strategies,
    ranking,
    initialise
  }
}
