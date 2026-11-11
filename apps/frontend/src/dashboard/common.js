import { ApiError } from '../services/api.js'

export const SYMBOL_PATTERN = /^\d{6}$/

export function displayError(error) {
  if (error instanceof ApiError && error.code) {
    return `${error.message}（${error.code}）`
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—'
  }
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })
}

export function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—'
  }
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`
}

const PARAMETER_LABELS = Object.freeze({
  shortWindow: '短期均线',
  longWindow: '长期均线',
  lookback: '回看周期',
  overboughtThreshold: '超买阈值',
  oversoldThreshold: '超卖阈值',
  modelRef: '模型版本'
})

function formatParameterValue(value) {
  if (value === null || value === undefined || value === '') return '未设置'
  if (Array.isArray(value)) return value.map(formatParameterValue).join('、')
  if (typeof value === 'object') {
    return Object.entries(value).map(([key, item]) => `${key}：${formatParameterValue(item)}`).join('，')
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

// 仅格式化界面文本；提交和计算仍使用原始参数对象。
export function formatParameters(parameters) {
  if (parameters === null || parameters === undefined) return '未记录'
  const entries = Object.entries(parameters)
  if (!entries.length) return '默认参数'
  return entries.map(([key, value]) => `${PARAMETER_LABELS[key] || key}：${formatParameterValue(value)}`).join(' · ')
}
