<script setup>
import { computed, ref, useId } from 'vue'
import { ASSET_CATEGORIES, assetCategories, filterAssets } from '../dashboard/asset-filter.js'
const props = defineProps({ modelValue: { type: Array, required: true }, assets: { type: Array, default: () => [] }, label: { type: String, default: '选择资产' }, disabled: Boolean, max: { type: Number, default: 10 } })
const emit = defineEmits(['update:modelValue'])
const query = ref('')
const kind = ref('all')
const categories = ref([])
const hasFilters = computed(() => query.value.trim() || kind.value !== 'all' || categories.value.length)
function resetFilters() {
  query.value = ''
  kind.value = 'all'
  categories.value = []
}
const uid = useId()
const selected = computed(() => props.modelValue.filter(Boolean))
const matches = computed(() => filterAssets(props.assets, { kind: kind.value, query: query.value, categories: categories.value }))
function toggle(symbol) {
  if (props.disabled) return
  emit('update:modelValue', selected.value.includes(symbol) ? selected.value.filter(s => s !== symbol) : selected.value.length < props.max ? [...selected.value, symbol] : [...selected.value])
}
function availabilityLabel(asset) {
  const a = asset.availability
  if (!a) return ''
  const label = a.suspended ? '停牌' : ({ ready: '覆盖完整', stale: '更新未完成', partial: '区间有缺口', unavailable: '暂无行情' }[a.state] || '状态未知')
  const reasons = { rate_limited: '数据源限流', access_denied: '数据源拒绝访问', provider_unavailable: '数据源服务异常', timeout: '请求超时', connection_failed: '连接失败', invalid_response: '响应格式异常', empty_response: '数据源返回空记录', invalid_prices: '价格校验未通过', missing_sessions: '存在未知缺日', not_collected: '本次未完成采集' }
  const update = a.update
  const note = update && update.reason !== 'none' ? `；${reasons[update.reason] || '更新待核实'}${update.outcome === 'retained' ? '，保留历史数据' : ''}` : ''
  const trading = a.tradingState === 'resumed' ? '复牌后已有成交' : label
  return `${trading} · 最后行情 ${a.lastTradeDate || '无'}${note}${a.state !== 'ready' ? '；仅完整历史区间可研究' : ''}`
}
const name = symbol => props.assets.find(a => a.symbol === symbol)?.name || symbol
</script>
<template>
  <fieldset class="asset-picker" :disabled="disabled">
    <legend>{{ label }} <span>{{ selected.length }}/{{ max }}</span></legend>
    <div class="selection-tray" aria-label="已选资产">
      <button v-for="symbol in selected" :key="symbol" type="button" :aria-label="`移除 ${name(symbol)} ${symbol}`" @click="toggle(symbol)">{{ name(symbol) }} <small>{{ symbol }}</small> <span aria-hidden="true">×</span></button>
      <span v-if="!selected.length" class="picker-hint">从下方列表选择资产</span>
    </div>
    <label class="search-label" :for="uid">搜索名称、代码或分类</label>
    <div class="search-row"><input :id="uid" v-model="query" type="search" placeholder="如：半导体 / 芯片 / 600519" autocomplete="off" /><button type="button" :disabled="!selected.length" @click="emit('update:modelValue', [])">清空已选</button></div>
    <div class="filter-row" aria-label="资产类型筛选"><button v-for="item in [{id:'all',name:'全部'},{id:'stock',name:'股票'},{id:'etf',name:'ETF'}]" :key="item.id" type="button" :aria-pressed="kind === item.id" @click="kind = item.id">{{ item.name }}</button><span role="status">{{ matches.length }} 项</span></div>
    <div class="category-filter" role="group" aria-label="常用分类筛选（可多选）">
      <div class="category-heading"><span>常用分类 · 可多选</span><button v-if="hasFilters" type="button" @click="resetFilters">重置筛选</button></div>
      <div class="category-options">
        <label v-for="category in ASSET_CATEGORIES" :key="category.id" class="category-choice" :class="{checked: categories.includes(category.id)}">
          <input v-model="categories" type="checkbox" :value="category.id" />{{ category.label }}
        </label>
      </div>
      <p class="picker-hint">股票按参考指数成分分类，ETF按名称匹配；仅筛选当前资产池，不覆盖全部同行公司。</p>
    </div>
    <p v-if="selected.length >= max" class="picker-hint" role="status">已选满 {{ max }} 个，取消一项后可更换。</p>
    <div class="asset-results">
      <label v-for="asset in matches" :key="asset.symbol" class="asset-option" :class="{selected: selected.includes(asset.symbol)}">
        <input type="checkbox" :checked="selected.includes(asset.symbol)" :disabled="!asset.active || (!selected.includes(asset.symbol) && selected.length >= max)" @change="toggle(asset.symbol)" />
        <span class="asset-name">{{ asset.name }}<small>{{ asset.symbol }} · {{ asset.exchange }}</small><small v-if="assetCategories(asset).length" class="asset-category">{{ assetCategories(asset).map(category => category.label).join(' · ') }}</small><small v-if="asset.availability" class="asset-availability" :data-state="asset.availability.state">{{ availabilityLabel(asset) }}</small></span><span class="asset-type">{{ asset.assetType === 'etf' ? 'ETF' : '股票' }}</span>
      </label>
      <p v-if="!matches.length" class="picker-hint">{{ assets.length ? '没有匹配项，请调整分类、搜索词或重置筛选。' : '资产目录尚不可用，请等待加载或查看连接提示。' }}</p>
    </div>
    <p class="picker-hint">直接勾选，无需按住 Ctrl；筛选后仍保留已选资产。</p>
  </fieldset>
</template>
<style scoped src="../styles/pickers.css"></style>
