/**
 * AIsChat 嵌入桥（Embed Bridge）
 *
 * 当 AIsChat 以 `?embed=1` 被宿主（如 DeepSeek Harness / DSH）嵌入时，
 * 通过 postMessage 与宿主页面通信：
 *
 *   AIsChat → 宿主（source: 'aischat-embed'）
 *     - { type: 'ready',   loggedIn }      页面加载完成（含登录态）
 *     - { type: 'contacts', loggedIn, groups, dmSessions }  联系人列表（复用现有 API）
 *   AIsChat ← 宿主（source: 'ds-aischat'）
 *     - { type: 'navigate', path }         导航到站内路径（如 /chat/gm/3）
 *     - { type: 'refresh' }                重新上报联系人列表
 *
 * 安全边界：本窗口的 access_token 绝不跨窗口传输；只交换联系人元数据与
 * 导航路径。宿主侧同样校验 event.origin 与本消息 source。
 */
import { api } from '../api/client'

/** AIsChat 发出的消息标识 */
export const EMBED_SOURCE = 'aischat-embed'
/** 宿主（DSH）发来的消息标识 */
export const HOST_SOURCE = 'ds-aischat'

/** 与 ChatSidebar 的 Group / DMSession 结构保持一致（接口字段可增减，序列化取原始 JSON） */
export interface EmbedGroup {
  id: number
  name: string
  unread_count: number
  has_mention?: boolean
  last_message_preview?: string | null
  last_message_at?: string | null
  is_pinned?: boolean
  [k: string]: unknown
}

export interface EmbedDMSession {
  session_id: string
  partner?: {
    id: number
    name: string
    type?: string
    state?: string | null
    avatar_url?: string | null
    [k: string]: unknown
  }
  last_message_preview?: string | null
  last_message_at?: string | null
  unread_count?: number
  is_pinned?: boolean
  [k: string]: unknown
}

export interface EmbedContacts {
  groups: EmbedGroup[]
  dmSessions: EmbedDMSession[]
}

let embedded: boolean | null = null

/** 当前是否处于嵌入模式（URL 带 embed 参数）。惰性求值，避免 SSR/测试环境问题。 */
export function isEmbedded(): boolean {
  if (embedded === null) {
    try {
      embedded = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('embed')
    } catch {
      embedded = false
    }
  }
  return embedded
}

type NavigateHandler = (path: string) => void

let navigateHandler: NavigateHandler | null = null

/** 宿主设置站内导航器（App 挂载 router 后调用）；未登录时导航会被路由守卫转到登录页，属预期行为 */
export function setEmbedNavigator(fn: NavigateHandler) {
  navigateHandler = fn
}

/** 向宿主页面发送一条消息（仅嵌入模式） */
function post(payload: Record<string, unknown>) {
  if (!isEmbedded()) return
  try {
    window.parent?.postMessage({ source: EMBED_SOURCE, ...payload }, '*')
  } catch {
    /* 宿主不可达时静默 */
  }
}

/** 拉取联系人列表并上报宿主。失败静默：宿主面板打开时会再次请求。 */
export async function reportContacts(): Promise<void> {
  if (!isEmbedded()) return
  // 未登录时不上报空列表之外的请求：client.ts 的 401 处理会整页跳转 /login，
  // 在 embed iframe 中会造成刷新死循环（同时避免无效请求）
  if (!localStorage.getItem('access_token')) {
    post({ type: 'contacts', loggedIn: false, groups: [], dmSessions: [] })
    return
  }
  try {
    const [groups, dmSessions] = await Promise.all([
      api.get<EmbedGroup[]>('/groups').catch(() => [] as EmbedGroup[]),
      api.get<EmbedDMSession[]>('/dm/sessions').catch(() => [] as EmbedDMSession[]),
    ])
    post({
      type: 'contacts',
      loggedIn: true,
      groups,
      dmSessions,
    })
  } catch {
    /* 静默 */
  }
}

/**
 * 初始化嵌入桥：监听宿主消息并上报初始状态。
 * 返回清理函数；非嵌入模式直接返回 noop。
 */
export function initEmbedBridge(): () => void {
  if (!isEmbedded()) return () => {}

  const onMessage = (event: MessageEvent) => {
    const data = event.data
    if (!data || typeof data !== 'object') return
    if (data.source !== HOST_SOURCE) return
    switch (data.type) {
      case 'navigate':
        if (typeof data.path === 'string') navigateHandler?.(data.path)
        break
      case 'refresh':
        reportContacts()
        break
      default:
        break
    }
  }

  window.addEventListener('message', onMessage)
  // 初始上报：登录态 + 联系人列表
  post({ type: 'ready', loggedIn: !!localStorage.getItem('access_token') })
  reportContacts()

  return () => window.removeEventListener('message', onMessage)
}
