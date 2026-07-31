/**
 * Demo 本地数据层 —— 所有数据读写 localStorage（作为本地数据库）
 * 增删查改 API 路由映射
 */

const DEMO_USER = {
  id: 1, username: 'Demo', role: 'user', is_active: true,
  ai_quota: 99, api_credit: 9999, platform_gifted_credit: 0,
  total_effective: 9999, agent_bundle_credit: 0, file_quota_mb: 500,
  has_api_key: false, api_key_last4: '',
  timezone: 'Asia/Shanghai', language: 'zh',
  ui_prefs: {}, avatar_url: null, bio: null,
  status_text: '⚡ Demo', status_color: '#f59e0b',
  setup_completed: true, created_at: '2026-01-01',
  assigned_pool_key_name: null, email: null, email_verified: false,
}

const DEMO_GROUPS = [
  { id: 1, name: 'AI 演示群', type: 'group', avatar_url: null, member_count: 2, is_vector_accelerated: false, owner_type: 'system', created_at: '2026-01-01' },
]

const DEMO_MEMBERS = [
  { id: 1, type: 'human', name: 'Demo', role: 'owner', avatar_url: null },
  { id: 2, type: 'agent', name: 'AI 助手', role: 'member', avatar_url: null },
]

const DEMO_AGENTS = [
  { id: 2, name: 'AI 助手', avatar_url: null, owner_id: 1, ai_type: 'general', is_active: true },
]

const DEMO_WELCOME = {
  id: 1, group_id: 1, sender_type: 'system', sender_id: 0,
  sender_name: '系统', content: '欢迎来到 AIsChat 演示版。\n\n⚙️ 进入「设置 → API 配置」填入你的 DeepSeek API Key 即可与 AI 对话。\n💾 所有数据存储在浏览器本地。',
  created_at: new Date().toISOString(),
}

// ── 读写辅助 ──

export function read<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback } catch { return fallback }
}
export function write(key: string, val: any) { try { localStorage.setItem(key, JSON.stringify(val)) } catch {} }

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = reject
    r.readAsDataURL(blob)
  })
}

// ── 初始化（首次访问时创建默认数据） ──

export function initDemoData() {
  if (!localStorage.getItem('demo_inited')) {
    write('demo_groups', DEMO_GROUPS)
    write('demo_members', { '1': DEMO_MEMBERS })
    write('demo_agents', DEMO_AGENTS)
    write('demo_messages', { '1': [DEMO_WELCOME] })
    write('demo_user', DEMO_USER)
    localStorage.setItem('demo_inited', '1')
  }
}

// ── 用户 ──

export function getDemoUser() {
  const cached = read('demo_user', DEMO_USER)
  const apiKey = read('demo_api_key', '')
  return { ...DEMO_USER, ...cached, has_api_key: !!apiKey, api_key_last4: apiKey.slice(-4) }
}

export function updateDemoUser(data: Record<string, any>) {
  const old = read('demo_user', {})
  write('demo_user', { ...old, ...data })
}

// ── API Key ──

export function getApiKey() { return read('demo_api_key', '') }
export function setApiKey(key: string) {
  write('demo_api_key', key)
  updateDemoUser({ has_api_key: !!key, api_key_last4: key.slice(-4) })
}

// ── 群组 ──

export function getGroups() { return read('demo_groups', DEMO_GROUPS) }
export function getGroup(id: number) { return getGroups().find((g: any) => g.id === id) || DEMO_GROUPS[0] }

// ── 成员 ──

export function getMembers(gid: number) {
  const all = read<Record<number, any[]>>('demo_members', {})
  return all[gid] || DEMO_MEMBERS
}

// ── AI Agent ──

export function getAgents() { return read('demo_agents', DEMO_AGENTS) }

// ── 消息 ──

export function getMessages(gid: number): any[] {
  const all = read<Record<number, any[]>>('demo_messages', { '1': [DEMO_WELCOME] })
  return all[gid] || []
}

let _msgId = Date.now()
export function addMessage(gid: number, msg: any) {
  const all = read<Record<number, any[]>>('demo_messages', {})
  const m = { id: ++_msgId, group_id: gid, created_at: new Date().toISOString(), ...msg }
  all[gid] = [...(all[gid] || []), m]
  write('demo_messages', all)
  // 触发 UI 刷新
  window.dispatchEvent(new CustomEvent('demo_msg_update', { detail: { group_id: gid } }))
  return m
}
