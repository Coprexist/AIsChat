/**
 * Demo 模式初始化：拦截 fetch 请求，返回 mock 数据
 * 直发消息到 DeepSeek API，不走后端
 */

const API = '/api'
const FAKE_TOKEN = 'demo_token_abc123'

const MOCK_USER = {
  id: 1,
  username: 'Demo',
  role: 'user',
  is_active: true,
  ai_quota: 99,
  api_credit: 9999,
  platform_gifted_credit: 0,
  total_effective: 9999,
  agent_bundle_credit: 0,
  file_quota_mb: 500,
  has_api_key: false,
  api_key_last4: '',
  timezone: 'Asia/Shanghai',
  language: 'zh',
  ui_prefs: {},
  avatar_url: null,
  bio: null,
  status_text: '⚡ Demo 体验用户',
  status_color: '#f59e0b',
  setup_completed: true,
  created_at: '2026-01-01',
  assigned_pool_key_name: null,
  email: null,
  email_verified: false,
}

const MOCK_GROUPS = [
  { id: 1, name: 'AIsChat 演示群', type: 'group', avatar_url: null, member_count: 3, is_vector_accelerated: false, owner_type: 'system' },
  { id: 2, name: 'AI 闲聊室',      type: 'group', avatar_url: null, member_count: 5, is_vector_accelerated: false, owner_type: 'system' },
  { id: 3, name: '技术交流',       type: 'group', avatar_url: null, member_count: 2, is_vector_accelerated: false, owner_type: 'system' },
]

const MOCK_AGENTS = [
  { id: 1, name: 'AI 助手', avatar_url: null, owner_id: 1, ai_type: 'general', is_active: true },
]

const MOCK_MESSAGES = [
  { id: 1, group_id: 1, sender_type: 'system', sender_id: 0, sender_name: '系统', content: '欢迎来到 AIsChat 演示版。发送消息与 AI 对话。', created_at: new Date().toISOString() },
]

const MOCK_MEMBERS = [
  { id: 1, type: 'human', name: 'Demo', role: 'owner', avatar_url: null },
  { id: 2, type: 'agent', name: 'AI 助手', role: 'member', avatar_url: null },
]

export function setupDemo() {
  localStorage.setItem('access_token', FAKE_TOKEN)
  localStorage.setItem('instance_url', 'https://coprexist.github.io')

  const original = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.replace(/^https?:\/\/[^\/]+/, '').replace(/\?.*$/, '')

    // 认证相关
    if (path === `${API}/auth/me` || path === `${API}/user/me`) {
      return jsonRes({ ...MOCK_USER })
    }
    if (path === `${API}/auth/login` || path === `${API}/auth/register`) {
      return jsonRes({ access_token: FAKE_TOKEN, user_id: 1, username: 'Demo' })
    }
    if (path === `${API}/auth/has-users`) {
      return jsonRes({ has_users: true })
    }

    // 群组列表
    if (path === `${API}/groups`) {
      return jsonRes(MOCK_GROUPS)
    }
    if (path.match(/^\/api\/groups\/\d+$/)) {
      const g = MOCK_GROUPS.find(g => g.id === parseInt(path.split('/')[3]))
      return jsonRes(g || MOCK_GROUPS[0])
    }

    // 群成员
    if (path.match(/^\/api\/groups\/\d+\/members$/)) {
      return jsonRes(MOCK_MEMBERS)
    }

    // 消息列表
    if (path.match(/^\/api\/groups\/\d+\/messages$/)) {
      return jsonRes(MOCK_MESSAGES)
    }

    // AI agent 列表
    if (path === `${API}/agents` || path === `${API}/agents/available`) {
      return jsonRes(MOCK_AGENTS)
    }

    // 用户设置
    if (path === `${API}/user/settings` || path === `${API}/settings`) {
      return jsonRes({ status: 'ok' })
    }

    // 系统设置
    if (path === `${API}/system/settings`) {
      return jsonRes({ registration_enabled: false })
    }

    // 维护信息
    if (path.match(/maintenance-msg/)) {
      return jsonRes({})
    }

    // DM / 好友
    if (path.includes('/friends') || path.includes('/dm') || path.includes('/friendship')) {
      return jsonRes([])
    }

    // 文件上传
    if (path.includes('/upload') || path.includes('/avatar') || path.includes('/file')) {
      return jsonRes({ url: '' })
    }

    // 其他未匹配路径 → 返回空
    if (url.includes(API) || url.includes('/user/') || url.includes('/groups/') || url.includes('/agents/')) {
      console.log(`[Demo] Mock: ${path}`)
      return jsonRes({})
    }

    // 非 API 请求 → 走原始 fetch
    return original(input, init)
  }

  // 拦截 WebSocket，防止无限重连
  const OrigWS = window.WebSocket
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
}

function jsonRes(data: any, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
