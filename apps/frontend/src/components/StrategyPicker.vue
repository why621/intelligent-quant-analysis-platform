<script setup>
import { useId } from 'vue'
defineProps({ modelValue: String, strategies: { type: Array, default: () => [] }, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const name = useId()
const description = id => ({ma_cross:'短长均线交叉，观察趋势变化。',momentum_reversal:'依据近期动量与反转条件生成信号。'}[id] || '选择后查看可用参数。')
</script>
<template><fieldset class="strategy-picker" :disabled="disabled"><legend>选择策略</legend><label v-for="strategy in strategies" :key="strategy.id" class="strategy-choice" :class="{chosen:modelValue === strategy.id}"><input type="radio" :name="name" :value="strategy.id" :checked="modelValue === strategy.id" :disabled="strategy.status !== 'available'" @change="emit('update:modelValue', strategy.id)" /><span><strong>{{ strategy.name }}</strong><small>{{ strategy.status === 'available' ? description(strategy.id) : '暂未开放' }}</small></span><b v-if="modelValue === strategy.id" aria-hidden="true">✓</b></label><p v-if="!strategies.length">策略列表尚未加载</p></fieldset></template>
<style scoped src="../styles/pickers.css"></style>
