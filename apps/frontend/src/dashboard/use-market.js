import { computed, reactive, ref } from 'vue'

import { fallbackMarket } from '../data/application-fixtures.js'
import { api, API_BASE_URL, ApiError, describeApiFailure } from '../services/api.js'
import { loadAssetCatalog } from './asset-catalog.js'

export function useMarket(client = api) {
  const marketError = ref('')
  const interfaceDefinitions = [
    { id: 'status', label: '数据发布状态', path: '/data/status' },
    { id: 'assets', label: '资产目录', path: '/assets' },
    { id: 'overview', label: '市场概览', path: '/market/overview' },
    { id: 'strategies', label: '策略目录', path: '/strategies' }
  ]
  const interfaceStatus = ref([])
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
    source: null,
    assetCount: null,
    latestTradeDate: null,
    updatedAt: null,
    message: '等待后端数据接口'
  })
  const assetCatalog = ref([])
  const assetCatalogError = ref('')
  const market = ref({ ...fallbackMarket })
  const strategies = ref([])
  const historyStatusText = computed(() => dataStatus.value.availability
    ? `${dataStatus.value.availability.readyCount}/327 覆盖完整，其余见资产状态`
    : statusLabel(dataStatus.value.components?.history?.status))
  const overviewStatusText = computed(() => statusLabel(dataStatus.value.components?.overview?.status))
  const marketNotice = computed(() => {
    if (marketError.value) return '市场概览暂不可用；历史行情、分析和回测可独立验证。'
    const component = dataStatus.value.components?.overview
    if (market.value.partial) {
      return `当前批次部分可用：有效比较 ${market.value.coverage?.priced ?? 0}/300，停牌等已知非交易 ${market.value.suspended ?? 0}，数据缺失 ${market.value.unavailable ?? 0}。缺失数据不计为平盘；指数缺失时不使用旧值冒充。`
    }
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
    interfaceStatus.value = interfaceDefinitions.map(item => ({ ...item, state: 'loading', message: '正在加载' }))
    dataStatus.value = { ...dataStatus.value, status: 'stale', components: {},
      availability: undefined, latestTradeDate: null, updatedAt: null, message: '等待后端数据接口' }
    assetCatalog.value = []
    assetCatalogError.value = ''
    strategies.value = []
    market.value = { ...fallbackMarket }
    marketError.value = ''
    let completed = 0
    const statusRequest = Promise.resolve().then(client.getDataStatus.bind(client))
    const jobs = [
      [() => statusRequest, value => {
        if (!value || !['ready', 'stale', 'updating', 'failed'].includes(value.status)) throw new ApiError('发布状态格式无效', { code: 'INVALID_RESPONSE' })
        dataStatus.value = value
      }],
      [() => loadAssetCatalog(client, () => current === generation), value => {
        if (!Array.isArray(value?.items) || !value.items.length) throw new ApiError('资产目录为空或无效', { code: 'INVALID_CATALOG' })
        assetCatalog.value = value.items
      }],
      [() => client.getMarketOverview(), value => {
        if (typeof value?.tradeDate !== 'string') throw new ApiError('概览格式无效', { code: 'INVALID_RESPONSE' })
        market.value = value
      }],
      [() => client.getStrategies(), value => {
        if (!Array.isArray(value?.items) || !value.items.length) throw new ApiError('策略目录格式无效', { code: 'INVALID_RESPONSE' })
        strategies.value = value.items
      }]
    ]
    const results = await Promise.allSettled(jobs.map(async ([fetchValue, applyValue], index) => {
      try {
        const value = await fetchValue()
        if (current === generation) {
          applyValue(value)
          interfaceStatus.value[index] = {
            ...interfaceDefinitions[index], state: 'ready', message: '读取成功'
          }
        }
      } catch (error) {
        if (current === generation) {
          const message = describeApiFailure(error)
          interfaceStatus.value[index] = {
            ...interfaceDefinitions[index], state: 'failed', message, code: error?.code
          }
          if (index === 1) assetCatalogError.value = `资产目录加载失败。${message}`
          if (index === 2) marketError.value = '市场概览读取失败'
        }
        throw error
      } finally {
        if (current === generation) {
          completed += 1
          connection.message = `已完成 ${completed}/${jobs.length} 项连接检查`
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
        : '未能读取数据服务'
  }

  return {
    interfaceStatus,
    apiBaseUrl: API_BASE_URL,
    connection,
    dataStatus,
    assetCatalog: computed(() => assetCatalog.value.map(asset => ({
      ...asset, availability: dataStatus.value.availability?.assets?.[asset.symbol]
    }))),
    assetCatalogError,
    market,
    strategies,
    historyStatusText,
    overviewStatusText,
    marketNotice,
    initialise
  }
}
