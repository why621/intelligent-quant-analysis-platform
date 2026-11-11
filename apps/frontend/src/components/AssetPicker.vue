<script setup>
import { computed, ref, useId } from 'vue'
import { assetCategories } from '../dashboard/asset-filter.js'
import { useAssetDirectory } from '../dashboard/use-asset-directory.js'
const props = defineProps({ modelValue: { type: Array, required: true }, assets: { type: Array, default: () => [] }, label: { type: String, default: '选择资产' }, disabled: Boolean, loading: Boolean, error: { type: String, default: '' }, max: { type: Number, default: 10 } })
const emit = defineEmits(['update:modelValue'])

const industryOpen = ref(false)
const directory = useAssetDirectory(computed(() => props.assets))
const { query, kind, categoryId, searchScope, notice, allSearch, kindOptions, categoryOptions, matches, inKind, currentPath, hasFilter, resetFilters } = directory
function pickKind(id) { notice.value = ''; kind.value = id }
function pickCategory(id) { notice.value = ''; categoryId.value = categoryId.value === id ? null : id }

const uid = useId()
const selected = computed(() => props.modelValue.filter(Boolean))
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
const namesBySymbol = computed(() => new Map(props.assets.map(asset => [asset.symbol, asset.name])))
const selectedAssets = computed(() => selected.value.map(symbol => ({
  symbol,
  name: namesBySymbol.value.get(symbol) || symbol
})))
</script>
<template>
  <fieldset class="asset-picker" :disabled="disabled">
    <legend>{{ label }} <span>{{ selected.length }}/{{ max }}</span></legend>

    <div class="selection-tray" aria-label="已选资产">
      <button v-for="{ symbol, name } in selectedAssets" :key="symbol" type="button" :aria-label="`移除 ${name === symbol ? symbol : `${name} ${symbol}`}`" @click="toggle(symbol)">
        {{ name }} <small v-if="name !== symbol">{{ symbol }}</small> <span aria-hidden="true">×</span>
      </button>
      <button v-if="selected.length" class="link-btn" type="button" @click="emit('update:modelValue', [])">清空已选</button>
      <span v-if="!selected.length && assets.length" class="picker-hint">从资产列表勾选</span>
    </div>

    <div v-show="assets.length" class="search-row">
      <input :id="uid" v-model="query" type="search" placeholder="搜索资产名称或代码" :aria-label="`${label}搜索`" autocomplete="off" />
      <select :id="`${uid}-scope`" v-model="searchScope" aria-label="搜索范围"><option value="filtered">当前筛选</option><option value="all">全部资产</option></select>
      <button v-if="hasFilter" type="button" class="search-reset" @click="resetFilters">重置筛选</button>
    </div>
    <p v-if="allSearch && assets.length" class="picker-hint">本次搜索暂不应用类型和行业筛选。</p>
    <p v-if="notice" class="picker-hint" role="status">{{ notice }}</p>
    <div class="picker-body">
      <template v-if="assets.length">
        <div class="picker-filters">
          <div class="kind-filters" role="group" aria-label="资产类型">
            <button v-for="item in kindOptions" :key="item.id" type="button" class="dir-item" :class="{ on: !allSearch && kind === item.id }" :aria-pressed="!allSearch && kind === item.id" @click="pickKind(item.id)">
              <span>{{ item.label }}</span><small>{{ item.count }}</small>
            </button>
          </div>
          <button class="dir-group-toggle" type="button" :aria-expanded="industryOpen" :aria-controls="`${uid}-industry`" @click="industryOpen = !industryOpen">
            行业 / 主题 <span aria-hidden="true">{{ industryOpen ? '−' : '+' }}</span>
          </button>
        </div>
        <div v-show="industryOpen" :id="`${uid}-industry`" class="industry-filters" role="group" aria-label="行业或主题">
          <button type="button" class="dir-item" :class="{ on: !allSearch && !categoryId }" :aria-pressed="!allSearch && !categoryId" @click="pickCategory(null)">
            <span>不限行业</span><small>{{ inKind.length }}</small>
          </button>
          <button v-for="item in categoryOptions" :key="item.id" type="button" class="dir-item" :class="{ on: !allSearch && categoryId === item.id }" :aria-pressed="!allSearch && categoryId === item.id" @click="pickCategory(item.id)">
            <span>{{ item.label }}</span><small>{{ item.count }}</small>
          </button>
          <p v-if="!categoryOptions.length" class="dir-empty">该类型下暂无行业分类</p>
        </div>
      </template>

      <div class="picker-results">
        <p v-if="assets.length" class="results-head"><span>{{ currentPath }}</span><small>{{ matches.length }} 只</small></p>
        <p v-if="selected.length >= max" class="picker-hint" role="status">已选满 {{ max }} 只，先取消一只再换。</p>
        <div class="asset-results">
          <label v-for="asset in matches" :key="asset.symbol" class="asset-option" :class="{selected: selected.includes(asset.symbol)}">
            <input type="checkbox" :checked="selected.includes(asset.symbol)" :disabled="!asset.active || (!selected.includes(asset.symbol) && selected.length >= max)" @change="toggle(asset.symbol)" />
            <span class="asset-name">
              {{ asset.name }} <small class="asset-code">{{ asset.symbol }} · {{ asset.exchange }}</small>
              <small v-if="asset.availability" class="asset-availability" :data-state="asset.availability.state">{{ availabilityLabel(asset) }}</small>
              <small v-if="assetCategories(asset).length" class="asset-category">{{ assetCategories(asset).map(category => category.label).join(' · ') }}</small>
            </span>
            <span class="asset-type">{{ asset.assetType === 'etf' ? 'ETF' : '股票' }}</span>
          </label>
          <p v-if="!matches.length" class="picker-hint" :role="error ? 'alert' : 'status'">{{ loading ? '正在加载资产目录…' : error ? '资产目录加载失败，请使用页面上方的重新连接。' : assets.length ? '当前范围没有匹配资产，可调整筛选或切换为全部资产搜索。' : '暂无可用资产，请检查数据状态。' }}</p>
        </div>
      </div>
    </div>
  </fieldset>
</template>
<style scoped src="../styles/pickers.css"></style>
