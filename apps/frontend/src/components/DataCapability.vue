<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import { useCapability } from '../dashboard/use-capability.js'
import { recoveryOptions } from '../dashboard/data-recovery.js'
const props = defineProps({ request: { type: Object, required: true }, version: String, assets: { type: Array, default: () => [] }, disabled: Boolean })
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
function run() { if (valid()) state.check(props.request, props.version) }
watch(() => JSON.stringify([props.request, props.version]), () => {
  clearTimeout(timer)
  state.invalidate()
  timer = setTimeout(run, 250)
}, { immediate: true })
onBeforeUnmount(() => { clearTimeout(timer); state.dispose() })
</script>
<template>
  <div class="data-capability" :data-state="result?.state || 'unknown'" role="status">
    <strong>本模块数据检查</strong>
    <span>{{ message }}</span>
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
.data-capability { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; margin: 1rem 0; padding: .8rem; border: 1px solid #365269; border-radius: .5rem; color: #c4d5e8; overflow-wrap: anywhere; }
.data-capability[data-state="ready"] { border-color: #3ecdb4; }
.data-capability[data-state="unavailable"] { border-color: #d995b8; }
span, small { flex: 1 1 15rem; }
button { font: inherit; padding: .35rem .6rem; color: #cdf8f2; background: #132638; border: 1px solid #547189; border-radius: .3rem; cursor: pointer; }
.recovery-actions { flex: 1 1 100%; display: flex; flex-wrap: wrap; gap: .6rem; }
.recovery-actions p, .recovery-actions small { flex: 1 1 100%; margin: 0; }
button:disabled { opacity: .55; cursor: default; }
</style>
