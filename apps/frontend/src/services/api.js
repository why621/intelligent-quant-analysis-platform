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
      const response = await fetch(`${API_BASE_URL}${path}`, {
        ...fetchOptions, signal: controller.signal,
        headers: { Accept: 'application/json',
          ...(fetchOptions.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(version ? { 'X-Research-Version': version } : {}),
          ...headers }
      })
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

  getCorrelation(payload) {
    return post('/analytics/correlation', payload)
  },

  getStrategies() {
    return request('/strategies')
  },

  getStrategyRanking(period = '30d') {
    return request(`/strategies/ranking${toQuery({ period })}`, { research: true })
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
