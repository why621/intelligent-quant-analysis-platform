const DEFAULT_API_BASE_URL = '/api'

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL)

export class ApiError extends Error {
  constructor(message, { status, code, details, traceId } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.traceId = traceId
  }
}

function normalizeBaseUrl(baseUrl) {
  return baseUrl.replace(/\/+$/, '') || DEFAULT_API_BASE_URL
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    throw new ApiError(payload?.message || `Request failed with status ${response.status}`, {
      status: response.status,
      code: payload?.code,
      details: payload?.details,
      traceId: payload?.traceId
    })
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

  getMarketOverview() {
    return request('/market/overview')
  },

  getCorrelation(payload) {
    return post('/analytics/correlation', payload)
  },

  runBacktest(payload) {
    return post('/backtests', payload)
  },

  getStrategyRanking() {
    return request('/strategies/ranking')
  },

  getAllocationSuggestion(payload) {
    return post('/allocation/suggestion', payload)
  }
}
