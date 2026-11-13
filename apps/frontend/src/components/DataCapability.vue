<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import { useCapability } from '../dashboard/use-capability.js'
import { recoveryOptions } from '../dashboard/data-recovery.js'
const props = defineProps({ request: { type: Object, required: true }, version: String, active: Boolean, assets: { type: Array, default: () => [] }, disabled: Boolean })
const emit = defineEmits(['recover', 'checked'])
const state = useCapability()
const { result, message, busy } = state
const options = computed(() => recoveryOptions(props.request, result.value, props.assets))
watch(result, value => emit('checked', value?.state || 'unknown'), { flush: 'sync', immediate: true })
let timer
function valid() {
  const p = props.request
  if (['correlation', 'backtest', 'allocation'].includes(p.module)
      && (!Array.isArray(p.symbols) || p.symbols.length < (p.module === 'correlation' ? 2 : 1))) return false
  return !['correlation', 'backtest'].includes(p.module) || Boolean(p.startDate && p.endDate)
}
function run() {
  clearTimeout(timer)
  if (props.active && props.version && valid()) void state.check(props.request, props.version)
}
const requestKey = computed(() => JSON.stringify([props.request, props.version]))
watch([requestKey, () => props.active], ([key, active], [previousKey]) => {
  clearTimeout(timer)
  if (key !== previousKey) state.invalidate()
  if (active && props.version && valid() && !result.value && !busy.value) {
    timer = setTimeout(run, 250)
  }
}, { immediate: true })
onBeforeUnmount(() => { clearTimeout(timer); state.dispose() })
</script>
<template>
  <div class="data-capability" :data-state="result?.state || 'unknown'" role="status">
    <strong>本模块数据检查</strong>
    <span>{{ version ? message : '等待数据批次' }}</span>
    <small v-if="result?.issues.length">涉及 {{ [...new Set(result.issues.map(i => i.symbol).filter(Boolean))].join('、') || '模块所需日期或共同样本' }}</small>
    <button type="button" :disabled="busy || !version || !valid()" @click="run">{{ busy ? '检查中…' : '重新检查' }}</button>
    <div v-if="options.length" class="recovery-actions">
      <p>只影响当前所选组合，其他资产仍可使用。选择一种调整方式：</p>
      <button v-for="option in options" :key="option.label" type="button" :disabled="disabled || busy" @click="emit('recover', option.patch)">{{ option.label }}</button>
      <small>调整后重新校验区间内缺日和共同样本，最后行情日期不保证整段完整。</small>
    </div>
  </div>
</template>
<style scoped>
.data-capability { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin: 0 0 12px; padding: 6px 10px; background: var(--field); border: 1px solid var(--line); border-radius: 7px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.data-capability[data-state="ready"] { border-left: 3px solid var(--accent); }
.data-capability[data-state="unavailable"] { border-left: 3px solid var(--danger); }
span { flex: 1 1 140px; }
.data-capability > small { flex: 1 1 100%; }
.data-capability > button { min-height: 32px; }
.recovery-actions { flex: 1 1 100%; display: flex; flex-wrap: wrap; gap: 10px; }
.recovery-actions p, .recovery-actions small { flex: 1 1 100%; margin: 0; }
</style>
