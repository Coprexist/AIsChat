/**
 * Demo 模式初始化
 * 自动注册演示账号 → 获取真实 token → API 请求代理到 i.datongai.top
 */

const BACKEND = 'https://i.datongai.top'
const API = '/api'

const MOCK_USER = { /* same as before */
  id: 1, username: 'Demo', role: 'user', is_active: true,
  ai_quota: 99, api_credit: 9999, platform_gifted_credit: 0,
  total_effective: 9999, agent_bundle_credit: 0, file_quota_mb: 500,
  has_api_key: false, api_key_last4: '',
  timezone: 'Asia/Shanghai', language: 'zh', ui_prefs: {},
  avatar_url: null, bio: null, status_text: '⚡ Demo',
  status_color: '#f59e0b', setup_completed: true,
  created_at: '2026-01-01', assigned_pool_key_name: null,
  email: null, email_verified: false,
}

export async function setupDemo() {
  // 1. 注册/登录演示账号，获取真实 token
  let token = localStorage.getItem('demo_real_token')
  if (!token) {
    try {
      const r = await fetch(`${BACKEND}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: `demo_${Date.now()}`, password: 'demo123456' }),
      })
      const d = await r.json()
      token = d.access_token
    } catch {
      // 注册失败时用 mock token 兜底
      token = 'demo_mock_token'
    }
    if (token) localStorage.setItem('demo_real_token', token)
  }

  localStorage.setItem('access_token', token || 'demo_mock_token')

  // 2. 拦截 fetch：API 请求代理到真实后端
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.replace(/^https?:\/\/[^\/]+/, '').replace(/\?.*$/, '')

    // 认证相关 → mock（不暴露真实用户）
    if (path === `${API}/auth/me` || path === `${API}/user/me`) {
      const cached = localStorage.getItem('demo_user')
      return jsonRes(cached ? { ...MOCK_USER, ...JSON.parse(cached) } : { ...MOCK_USER })
    }
    if (path === `${API}/auth/login` || path === `${API}/auth/register`) {
      return jsonRes({ access_token: token, user_id: 1, username: 'Demo' })
    }
    if (path === `${API}/auth/has-users`) {
      return jsonRes({ has_users: true })
    }

    // 用户设置 → 本地缓存
    if (path === `${API}/user/settings`) {
      if (init?.method === 'PUT' || init?.method === 'POST') {
        try {
          const body = JSON.parse(init.body as string || '{}')
          const old = JSON.parse(localStorage.getItem('demo_user') || '{}')
          localStorage.setItem('demo_user', JSON.stringify({ ...old, ...body }))
        } catch {}
      }
      return jsonRes({ status: 'ok' })
    }

    // 其他 /api 请求 → 代理到真实后端
    if (path.startsWith(API)) {
      const realUrl = `${BACKEND}${path}${url.includes('?') ? '?' + url.split('?')[1] : ''}`
      const headers: Record<string, string> = { ...init?.headers as any }
      if (!headers['Authorization']) {
        headers['Authorization'] = `Bearer ${token || 'demo_mock_token'}`
      }
      try {
        const resp = await original(realUrl, { ...init, headers })
        return resp
      } catch {
        return jsonRes({ error: 'backend unreachable' }, 502)
      }
    }

    // 非 API 请求（静态资源、DeepSeek 等）→ 正常走
    return original(input, init)
  }

  // 3. 拦截 WebSocket
  class DemoWS {
    url: string
    onopen: ((e: Event) => void) | null = null
    onclose: ((e: CloseEvent) => void) | null = null
    onerror: ((e: Event) => void) | null = null
    onmessage: ((e: MessageEvent) => void) | null = null
    readyState = 3
    constructor(url: string) {
      this.url = url
      console.log('[Demo] WS 已拦截:', url)
      queueMicrotask(() => this.onclose?.(new CloseEvent('close')))
    }
    close() {}
    send() {}
  }
  window.WebSocket = DemoWS as any

  // 4. logo 修正
  new MutationObserver(() => {
    document.querySelectorAll('img[src="/logo.png"]').forEach(el => {
      if (el instanceof HTMLImageElement) el.src = '/AIsChat/logo.png'
    })
  }).observe(document.body || document.documentElement, { childList: true, subtree: true })
}

function jsonRes(data: any, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
