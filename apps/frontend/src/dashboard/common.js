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
