<script setup>
import { useId } from 'vue'
defineProps({ modelValue: String, strategies: { type: Array, default: () => [] }, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const name = useId()
import { strategyDescription } from '../dashboard/model-disclosure.js'
</script>
<template><fieldset class="strategy-picker" :disabled="disabled"><legend>选择策略</legend><label v-for="strategy in strategies" :key="strategy.id" class="strategy-choice" :class="{chosen:modelValue === strategy.id}"><input type="radio" :name="name" :value="strategy.id" :checked="modelValue === strategy.id" :disabled="strategy.status !== 'available' && !(strategy.status === 'experimental' && strategy.backtestEnabled === true)" @change="emit('update:modelValue', strategy.id)" /><span><strong>{{ strategy.name }}</strong><small>{{ strategyDescription(strategy) }}</small></span><b v-if="modelValue === strategy.id" aria-hidden="true">✓</b></label><p v-if="!strategies.length">策略列表尚未加载</p></fieldset></template>
<style scoped src="../styles/pickers.css"></style>
