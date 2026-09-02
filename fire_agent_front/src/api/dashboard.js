/**
 * 大屏数据 API 服务
 * 通过 Vite proxy 将 /api 请求转发到后端 localhost:8000
 */
import { API_V1 } from '@/utils/config'

const API_BASE = `${API_V1}/dashboard`

async function request(url, params = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.append(k, v)
  })
  const fullUrl = `${API_BASE}${url}${qs.toString() ? '?' + qs.toString() : ''}`
  const res = await fetch(fullUrl)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  const json = await res.json()
  if (json.code !== 200) throw new Error(json.message || 'API error')
  return json.data
}

/**
 * 查询历史火点
 * @param {Object} opts - { start_date, end_date, city, confidence, page, page_size }
 * @returns {Promise<{ total: number, page: number, page_size: number, items: Array }>}
 */
export function fetchHistoryFires(opts = {}) {
  return request('/history-fires', opts)
}

/**
 * 查询预测火险
 * @param {Object} opts - { year, month, day, view_mode, city }
 * @returns {Promise<{ total: number, items: Array }>}
 */
export function fetchPredictRisks(opts = {}) {
  return request('/predict-risks', opts)
}

/**
 * 查询大屏摘要
 * @param {Object} opts - { start_date, end_date }
 * @returns {Promise<Object>}
 */
export function fetchDashboardSummary(opts = {}) {
  return request('/summary', opts)
}