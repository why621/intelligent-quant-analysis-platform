import { computed, reactive, ref } from 'vue'

import { fallbackAssets, fallbackMarket, fallbackStrategies } from '../data/application-fixtures.js'
import { api } from '../services/api.js'

export function useMarket(client = api) {
  const marketError = ref('')
  const statusLabel = (state) => ({ ready: '更新完成', updating: '更新中',
    stale: '更新不完整或已过期', failed: '暂不可用' }[state] || '待确认')
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
  const historyStatusText = computed(() => statusLabel(dataStatus.value.components?.history?.status))
  const overviewStatusText = computed(() => statusLabel(dataStatus.value.components?.overview?.status))
  const marketNotice = computed(() => {
    if (marketError.value) return '市场概览暂不可用；历史行情、分析和回测可独立验证。'
    const component = dataStatus.value.components?.overview
    if (component?.status === 'stale') {
      return `显示上次成功快照（${market.value.tradeDate || '日期未知'}），本次未完成更新。`
    }
    return component?.status === 'ready' ? '' : (component?.message || '等待市场概览状态确认')
  })

  const initialise = async () => {
    connection.loading = true
    const results = await Promise.allSettled([
      client.getDataStatus(),
      client.listAssets({ limit: 50 }),
      client.getMarketOverview(),
      client.getStrategies(),
      client.getStrategyRanking('30d')
    ])

    if (results[0].status === 'fulfilled') dataStatus.value = results[0].value
    if (results[1].status === 'fulfilled' && results[1].value.items?.length) {
      assetCatalog.value = results[1].value.items
    }
    if (results[2].status === 'fulfilled') {
      market.value = results[2].value
      marketError.value = ''
    } else {
      market.value = { ...fallbackMarket }
      marketError.value = '市场概览读取失败'
    }
    if (results[3].status === 'fulfilled' && results[3].value.items?.length) {
      strategies.value = results[3].value.items
    }
    if (results[4].status === 'fulfilled') ranking.value = results[4].value.items || []

    const fulfilledCount = results.filter((result) => result.status === 'fulfilled').length
    connection.live = fulfilledCount === results.length
    connection.loading = false
    connection.message = connection.live
      ? (dataStatus.value.status === 'ready' ? '接口数据' : '后端已连接，数据更新需关注')
      : fulfilledCount > 0
        ? `后端部分接口可用（${fulfilledCount}/${results.length}），请查看分项状态`
        : '后端暂不可用，资产和策略目录为演示占位'
  }

  return {
    connection,
    dataStatus,
    assetCatalog,
    market,
    strategies,
    ranking,
    historyStatusText,
    overviewStatusText,
    marketNotice,
    initialise
  }
}
