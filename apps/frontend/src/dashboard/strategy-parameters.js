import { computed, ref, watch } from 'vue'

export function useStrategyParameters(strategy) {
  const parameters = ref({})
  const schema = computed(() => strategy.value?.parameterSchema)
  const fields = computed(() => Object.entries(schema.value?.properties || {}).map(([key, rule]) => ({
    key, ...rule, label: rule.title || rule.description || key
  })))
  const metadataReady = computed(() => schema.value?.type === 'object'
    && fields.value.length > 0
    && fields.value.every(field => ['number', 'integer'].includes(field.type)))
  watch(schema, value => {
    parameters.value = Object.fromEntries(Object.entries(value?.properties || {})
      .map(([key, rule]) => [key, rule.default ?? '']))
  }, { immediate: true, flush: 'sync' })
  const parameterError = computed(() => {
    if (!metadataReady.value) return '等待服务端策略参数定义，暂不能提交。'
    for (const field of fields.value) {
      const value = parameters.value[field.key]
      const missing = value === '' || value == null
      if (missing && !(schema.value.required || []).includes(field.key)) continue
      if (missing) return `请填写 ${field.label}。`
      if (typeof value !== 'number' || !Number.isFinite(value)) return `${field.label} 必须是有限数值。`
      if (field.type === 'integer' && !Number.isInteger(value)) return `${field.label} 必须为整数。`
      if (field.minimum != null && value < field.minimum) return `${field.label} 不能小于 ${field.minimum}。`
      if (field.maximum != null && value > field.maximum) return `${field.label} 不能大于 ${field.maximum}。`
      if (field.exclusiveMinimum != null && value <= field.exclusiveMinimum) return `${field.label} 必须大于 ${field.exclusiveMinimum}。`
      if (field.exclusiveMaximum != null && value >= field.exclusiveMaximum) return `${field.label} 必须小于 ${field.exclusiveMaximum}。`
    }
    for (const relation of schema.value['x-relations'] || []) {
      if (relation.operator !== 'lt') return '策略参数关系暂不支持，请更新客户端。'
      if (!(parameters.value[relation.left] < parameters.value[relation.right])) {
        const label = key => fields.value.find(field => field.key === key)?.label || key
        return `${label(relation.left)} 必须小于 ${label(relation.right)}。`
      }
    }
    return ''
  })
  return { parameters, parameterFields: fields, parameterError, metadataReady }
}
