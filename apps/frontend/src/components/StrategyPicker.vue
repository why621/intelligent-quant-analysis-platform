<script setup>
import { computed, useId } from 'vue'
const props = defineProps({ modelValue: String, strategies: { type: Array, default: () => [] }, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const name = useId()
import { strategyDescription } from '../dashboard/model-disclosure.js'
const category = strategy => strategy.id.startsWith('portfolio_masked_') ? 'enhanced'
  : strategy.modelContext?.portfolioMode === 'joint_portfolio' || strategy.id.startsWith('portfolio_') ? 'portfolio'
    : ['ma_cross', 'momentum_reversal'].includes(strategy.id) ? 'traditional' : 'single'
const groups = computed(() => [
  { id: 'traditional', label: '传统规则', description: '可解释的趋势与反转基线' },
  { id: 'portfolio', label: '联合组合模型', description: '2–10 资产 · 共享资金账户' },
  { id: 'enhanced', label: '掩码注意力组合', description: '2–10 资产 · 增强表示，未证明收益优势' },
  { id: 'single', label: '单资产实验', description: '适用资产以模型说明为准' }
].map(group => ({ ...group, items: props.strategies.filter(strategy => category(strategy) === group.id) }))
  .filter(group => group.items.length))
const selected = computed(() => props.strategies.find(strategy => strategy.id === props.modelValue))
</script>
<template>
  <fieldset class="strategy-picker" :disabled="disabled">
    <legend>选择策略</legend>
    <p class="picker-hint strategy-selection" role="status">当前选择：{{ selected?.name || '尚未选择可用策略' }}</p>
    <details v-for="group in groups" :key="group.id" class="strategy-group"
      :open="group.id === 'traditional' || (selected && category(selected) === group.id)">
      <summary><strong>{{ group.label }} · {{ group.items.length }}</strong><small>{{ group.description }}</small></summary>
      <div class="strategy-options">
        <label v-for="strategy in group.items" :key="strategy.id" class="strategy-choice" :class="{chosen: modelValue === strategy.id}">
          <input type="radio" :name="name" :value="strategy.id" :checked="modelValue === strategy.id"
            :disabled="strategy.status !== 'available' && !(strategy.status === 'experimental' && strategy.backtestEnabled === true)"
            @change="emit('update:modelValue', strategy.id)" />
          <span><strong>{{ strategy.name }}</strong><small>{{ strategyDescription(strategy) }}</small></span>
          <b v-if="modelValue === strategy.id" aria-hidden="true">✓</b>
        </label>
      </div>
    </details>
    <p v-if="!strategies.length">策略列表尚未加载</p>
  </fieldset>
</template>
<style scoped src="../styles/pickers.css"></style>
