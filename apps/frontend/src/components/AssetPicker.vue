<script setup>
import { computed, ref, useId } from 'vue'
const props = defineProps({ modelValue: { type: Array, required: true }, assets: { type: Array, default: () => [] }, label: { type: String, default: '选择资产' }, disabled: Boolean, max: { type: Number, default: 10 } })
const emit = defineEmits(['update:modelValue'])
const query = ref('')
const kind = ref('all')
const uid = useId()
const selected = computed(() => props.modelValue.filter(Boolean))
const matches = computed(() => props.assets.filter(a => (kind.value === 'all' || a.assetType === kind.value) && `${a.symbol} ${a.name}`.toLowerCase().includes(query.value.trim().toLowerCase())))
function toggle(symbol) {
  if (props.disabled) return
  emit('update:modelValue', selected.value.includes(symbol) ? selected.value.filter(s => s !== symbol) : selected.value.length < props.max ? [...selected.value, symbol] : [...selected.value])
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
    <label class="search-label" :for="uid">搜索名称或代码</label>
    <div class="search-row"><input :id="uid" v-model="query" type="search" placeholder="如：贵州茅台 / 600519" autocomplete="off" /><button type="button" :disabled="!selected.length" @click="emit('update:modelValue', [])">清空已选</button></div>
    <div class="filter-row" aria-label="资产类型筛选"><button v-for="item in [{id:'all',name:'全部'},{id:'stock',name:'股票'},{id:'etf',name:'ETF'}]" :key="item.id" type="button" :aria-pressed="kind === item.id" @click="kind = item.id">{{ item.name }}</button><span role="status">{{ matches.length }} 项</span></div>
    <p v-if="selected.length >= max" class="picker-hint" role="status">已选满 {{ max }} 个，取消一项后可更换。</p>
    <div class="asset-results">
      <label v-for="asset in matches" :key="asset.symbol" class="asset-option" :class="{selected: selected.includes(asset.symbol)}">
        <input type="checkbox" :checked="selected.includes(asset.symbol)" :disabled="!asset.active || (!selected.includes(asset.symbol) && selected.length >= max)" @change="toggle(asset.symbol)" />
        <span class="asset-name">{{ asset.name }}<small>{{ asset.symbol }} · {{ asset.exchange }}</small></span><span class="asset-type">{{ asset.assetType === 'etf' ? 'ETF' : '股票' }}</span>
      </label>
      <p v-if="!matches.length" class="picker-hint">{{ assets.length ? '没有匹配项，请尝试名称或六位代码。' : '资产目录尚不可用，请等待加载或查看连接提示。' }}</p>
    </div>
    <p class="picker-hint">直接勾选，无需按住 Ctrl；筛选后仍保留已选资产。</p>
  </fieldset>
</template>
<style scoped src="../styles/pickers.css"></style>
