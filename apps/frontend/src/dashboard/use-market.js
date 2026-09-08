import { computed, reactive, ref } from 'vue'

import { fallbackAssets, fallbackMarket, fallbackStrategies } from '../data/application-fixtures.js'
import { api } from '../services/api.js'
import { loadAssetCatalog } from './asset-catalog.js'

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
  const assetCatalog = ref([])
  const assetCatalogError = ref('')
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
    const labels = { limitUp: '涨停数', limitDown: '跌停数', turnoverCny: '成交额',
      northboundNetCny: '北向资金' }
    const missing = (market.value.unavailableMetrics || []).map(key =>
      labels[key] || (key.startsWith('index:') ? `指数 ${key.slice(6)}` : key))
    const coverage = market.value.coverage
    if (coverage && coverage.priced < coverage.total) missing.push('部分股票涨跌幅')
    const notice = missing.length ? `部分指标暂不可用：${missing.join('、')}；缺失值显示为 —。` : ''
    return component?.status === 'ready' ? notice : (component?.message || '等待市场概览状态确认')
  })

  let generation = 0
  const initialise = async () => {
    const current = ++generation
    connection.loading = true
    connection.live = false
    connection.message = '正在连接后端接口'
    dataStatus.value = { ...dataStatus.value, status: 'stale', components: {},
      latestTradeDate: null, updatedAt: null, message: '等待后端数据接口' }
    assetCatalog.value = []
    assetCatalogError.value = ''
    strategies.value = fallbackStrategies
    market.value = { ...fallbackMarket }
    ranking.value = []
    marketError.value = ''
    let completed = 0
    const jobs = [
      [() => client.getDataStatus(), value => {
        if (!value || !['ready', 'stale', 'updating', 'failed'].includes(value.status)) throw Error()
        dataStatus.value = value
      }],
      [() => loadAssetCatalog(client, () => current === generation), value => {
        if (!Array.isArray(value?.items) || !value.items.length) throw Error()
        assetCatalog.value = value.items
      }],
      [() => client.getMarketOverview(), value => {
        if (typeof value?.tradeDate !== 'string') throw Error()
        market.value = value
      }],
      [() => client.getStrategies(), value => {
        if (!Array.isArray(value?.items) || !value.items.length) throw Error()
        strategies.value = value.items
      }],
      [() => client.getStrategyRanking('30d'), value => {
        if (!Array.isArray(value?.items)) throw Error()
        ranking.value = value.items
      }]
    ]
    const results = await Promise.allSettled(jobs.map(async ([fetchValue, applyValue], index) => {
      try {
        const value = await fetchValue()
        if (current === generation) applyValue(value)
      } catch (error) {
        if (current === generation && index === 1) {
          assetCatalogError.value = '资产目录加载失败：未取得完整且一致的目录，请重新加载；若持续失败请核对前后端版本。'
        }
        if (current === generation && index === 2) marketError.value = '市场概览读取失败'
        throw error
      } finally {
        if (current === generation) {
          completed += 1
          connection.message = `已收到 ${completed}/${jobs.length} 个接口响应，可用数据已显示`
        }
      }
    }))
    if (current !== generation) return
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
    assetCatalogError,
    market,
    strategies,
    ranking,
    historyStatusText,
    overviewStatusText,
    marketNotice,
    initialise
  }
}
