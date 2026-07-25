import { ApiError } from '../services/api'

export const SYMBOL_PATTERN = /^\d{6}$/

export function isoDate(value) {
  return value.toISOString().slice(0, 10)
}

export function defaultDateRange() {
  const end = new Date()
  const start = new Date(end)
  start.setFullYear(start.getFullYear() - 1)
  return { startDate: isoDate(start), endDate: isoDate(end) }
}

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
