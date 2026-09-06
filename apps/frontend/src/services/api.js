const DEFAULT_API_BASE_URL = '/api'

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

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    const error = payload?.error || payload
    throw new ApiError(
      error?.message || `请求失败（HTTP ${response.status}）`,
      {
        status: response.status,
        code: error?.code,
        details: error?.details
      }
    )
  }

  return payload
}

function post(path, body) {
  return request(path, {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export const api = {
  getHealth() {
    return request('/health')
  },

  getDataStatus() {
    return request('/data/status')
  },

  listAssets(params = {}) {
    return request(`/assets${toQuery(params)}`)
  },

  getAssetHistory(symbol, params) {
    return request(`/assets/${encodeURIComponent(symbol)}/history${toQuery(params)}`)
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
    return request(`/strategies/ranking${toQuery({ period })}`)
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
