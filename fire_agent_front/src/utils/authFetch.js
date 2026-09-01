/**
 * 带认证的 fetch 封装
 *
 * - 自动附加 Authorization: Bearer <token>
 * - 401（token 失效/未登录）时自动登出并跳转登录页
 * - 其余与原生 fetch 一致（返回 Response）
 */
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

export default async function authFetch(url, options = {}) {
  const auth = useAuthStore()
  const headers = new Headers(options.headers || {})
  if (auth.token) {
    headers.set('Authorization', `Bearer ${auth.token}`)
  }
  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    auth.logout()
    const current = router.currentRoute.value
    if (current.path !== '/login') {
      router.replace({
        path: '/login',
        query: current.path === '/' ? {} : { redirect: current.fullPath },
      })
    }
    throw new Error('登录已过期，请重新登录')
  }
  return res
}

/** 解析 JSON 响应，code!==200 时抛错 */
export async function parseJson(res, fallbackMsg = '请求失败') {
  let json
  try {
    json = await res.json()
  } catch {
    throw new Error(fallbackMsg)
  }
  if (!res.ok || json.code !== 200) {
    throw new Error(json?.detail || json?.message || fallbackMsg)
  }
  return json
}
