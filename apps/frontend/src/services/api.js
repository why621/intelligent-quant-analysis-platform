const DEFAULT_API_BASE_URL = '/api'
let researchVersion = null
let statusGeneration = 0

export const API_BASE_URL = normalizeBaseUrl(
  import.meta.env?.VITE_API_BASE_URL || DEFAULT_API_BASE_URL
)

export class ApiError extends Error {
  constructor(message, { status, code, details } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function normalizeBaseUrl(baseUrl) {
  return baseUrl.replace(/\/+$/, '') || DEFAULT_API_BASE_URL
}

function toQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  const result = query.toString()
  return result ? `?${result}` : ''
}

export async function request(path, options = {}) {
  const { timeoutMs = 15000, headers, research = false, ...fetchOptions } = options
  const version = research ? researchVersion : null
  const controller = new AbortController()
  let timer
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new ApiError('请求超时，请稍后重试', { code: 'REQUEST_TIMEOUT' }))
      controller.abort()
    }, timeoutMs)
  })
  try {
    return await Promise.race([deadline, (async () => {
      let response
      try {
        response = await fetch(`${API_BASE_URL}${path}`, {
          ...fetchOptions, signal: controller.signal,
          headers: {
            Accept: 'application/json',
            ...(fetchOptions.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
            ...(version ? { 'X-Research-Version': version } : {}),
            ...headers
          }
        })
      } catch (error) {
        if (error instanceof TypeError) {
          throw new ApiError('无法连接数据服务，请检查网络、HTTPS 证书或跨域配置', {
            code: 'NETWORK_ERROR'
          })
        }
        throw error
      }
      const contentType = response.headers.get('content-type') || ''
      let payload = null
      if (contentType.includes('application/json')) {
        try { payload = await response.json() } catch { /* Reject invalid JSON below. */ }
      }
      if (!response.ok) {
        const error = payload?.error || payload
        throw new ApiError(error?.message || `请求失败（HTTP ${response.status}）`, {
          status: response.status, code: error?.code, details: error?.details
        })
      }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new ApiError('接口返回格式不正确，请检查后端地址', {
          status: response.status, code: 'INVALID_RESPONSE'
        })
      }
      return payload
    })()])
  } finally {
    clearTimeout(timer)
  }
}

// Fetch deliberately does not distinguish TLS/CORS/DNS failures. Never guess.
export function describeApiFailure(error) {
  if (error?.code === 'NETWORK_ERROR') return '连接未建立：可能是网络、HTTPS 证书或跨域限制。'
  if (error?.code === 'REQUEST_TIMEOUT') return '响应超时，请稍后重试。'
  if (error?.status === 401 || error?.status === 403) return `访问被拒绝（HTTP ${error.status}），请检查接口权限。`
  if (error?.code === 'INVALID_RESPONSE') return '接口返回的内容格式不符合要求，请检查 API 地址及前后端版本。'
  if (error?.code === 'INVALID_CATALOG') return '资产目录不完整或版本不一致，请检查前后端版本。'
  if (error?.status) return `接口返回 HTTP ${error.status}，请检查服务状态。`
  return '数据加载失败，请检查服务响应或重试。'
}

function post(path, body) {
  return request(path, {
    method: 'POST', research: true,
    body: JSON.stringify(body)
  })
}

export const api = {
  getHealth() {
    return request('/health')
  },

  async getDataStatus() {
    const current = ++statusGeneration
    researchVersion = null
    const result = await request('/data/status')
    if (current === statusGeneration) researchVersion = result.dataContext?.dataVersion || null
    return result
  },

  listAssets(params = {}) {
    return request(`/assets${toQuery(params)}`)
  },

  getAssetHistory(symbol, params) {
    return request(`/assets/${encodeURIComponent(symbol)}/history${toQuery(params)}`, { research: true })
  },

  getMarketOverview(tradeDate) {
    return request(`/market/overview${toQuery({ tradeDate })}`)
  },

  checkDataCapability(payload) {
    return post('/data/capability', payload)
  },

  getCorrelation(payload) {
    return post('/analytics/correlation', payload)
  },

  getStrategies() {
    return request('/strategies')
  },

  getStrategyRanking(period = '30d') {
    return request(`/strategies/ranking${toQuery({ period })}`, { research: true })
  },

  calculateStrategyRanking(payload) {
    return request('/strategies/ranking', {
      method: 'POST', research: true, timeoutMs: 45000, body: JSON.stringify(payload)
    })
  },

  createBacktest(payload) {
    return post('/backtests', payload)
  },

  getBacktest(jobId) {
    return request(`/backtests/${encodeURIComponent(jobId)}`)
  },

  getAllocationSuggestion(payload) {
    return post('/allocation/suggestion', payload)
  }
}
