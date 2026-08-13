/**
 * 世界 AI 对话 hook — 聊天状态 + 流式发送 + 排队 + 建议按钮 + 斜杠命令
 * 从 WorldDesignPage 拆分（2026-08-06 重构）
 */
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject, type Dispatch, type SetStateAction, type UIEvent } from 'react'
import { api } from '../api/client'

// 世界 AI 对话消息（世界级会话，非 DM；reasoning = 思考过程；tool = 工具执行结果；note = 中间叙述）
export interface ChatMsg {
  id: number
  role: 'user' | 'ai' | 'tool' | 'note'
  content: string
  reasoning?: string
  error?: boolean
  /** 排队中（AI 处理时发送，尚未真正发出；流结束后自动发送并刷新为正式消息） */
  pending?: boolean
  created_at?: string
  /** 工具状态事件（2026-08-13）：tool_id 定位气泡，多状态原地更新 */
  tool_id?: string
  tool_name?: string
  tool_status?: 'running' | 'update' | 'done'
  tool_args?: string
  /** 工具执行失败（落库后刷新保持红色；2026-08-13） */
  is_error?: boolean
}

// SSE 事件前缀（与后端 world_chat_service 的 yield 格式一一对应；解析用常量避免魔法数字）
const EV = {
  INSERTED: '[INSERTED]',  // 信号：排队消息已插入（不计历史）→ 清排队弹窗
  INSERT: '[INSERT]',      // 消息：已落库（记历史）→ 画用户气泡
} as const

/** 解析 `[PREFIX]{json}` 事件体；前缀不匹配/JSON 坏返回 null */
function parseEvent<T>(payload: string, prefix: string): T | null {
  if (!payload.startsWith(prefix)) return null
  try {
    return JSON.parse(payload.slice(prefix.length)) as T
  } catch {
    return null
  }
}

// 斜杠命令列表（输入 / 弹出，像 @ 提及；仅世界设计页——主站保持人性化不加）
export const WORLD_COMMANDS = [
  { cmd: '/new', desc: '开新对话（旧对话保存，可切回）' },
  { cmd: '/sessions', desc: '列出所有会话（id + 时间 + 收藏）' },
  { cmd: '/use <id>', desc: '切回指定会话继续对话' },
  { cmd: '/pin', desc: '收藏当前会话（最多 16 个，不被清理）' },
  { cmd: '/unpin', desc: '取消收藏当前会话' },
  { cmd: '/clear', desc: '清空当前会话上下文（保留长期记忆）' },
  { cmd: '/compact', desc: '压缩当前会话上下文为摘要' },
]

interface UseWorldChatOptions {
  wid: number
  /** 世界信息刷新（AI 工具可能改过世界，回复结束后调用） */
  onRefresh: () => void
  /** 顶部提示消息 */
  onMsg: (msg: string) => void
}

export interface UseWorldChatReturn {
  chatMsgs: ChatMsg[]
  chatInput: string
  setChatInput: (v: string) => void
  chatSending: boolean
  chatProcessing: boolean
  chatHasMore: boolean
  chatLoadingOlder: boolean
  chatListRef: (el: HTMLDivElement | null) => void
  chatInputRef: RefObject<HTMLTextAreaElement | null>
  pendingItems: { kind: 'msg' | 'cmd'; text: string }[]
  setPendingItems: Dispatch<SetStateAction<{ kind: 'msg' | 'cmd'; text: string }[]>>
  suggestions: string[]
  cmdActive: boolean
  setCmdActive: (v: boolean) => void
  cmdQuery: string
  setCmdQuery: (v: string) => void
  cmdIdx: number
  setCmdIdx: Dispatch<SetStateAction<number>>
  cmdFiltered: { cmd: string; desc: string }[]
  submitText: (text: string) => void
  insertSuggestion: (q: string) => void
  isAtBottom: boolean
  chatCanScroll: boolean
  currentSession: string
  sessionList: { id: string; last_active_at?: string; pinned?: boolean }[]
  switchSession: (sid: string) => Promise<boolean>
  togglePin: () => Promise<boolean>
  scrollToBottom: (force?: boolean) => void
  forceScrollToBottom: () => void
  unreadCount: number
}

export function useWorldChat({ wid, onRefresh, onMsg }: UseWorldChatOptions) {
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const [chatProcessing, setChatProcessing] = useState(false)  // 刷新后恢复：后台轮次仍在执行
  const [pendingItems, setPendingItems] = useState<{ kind: 'msg' | 'cmd'; text: string }[]>([])  // AI 处理中排队消息（msg 一起发；cmd 串行执行）
  const [suggestions, setSuggestions] = useState<string[]>([])  // "你可以"建议（AI 生成 / 兜底 / 预设）
  // 会话（/new 开新对话、可切回；展示当前会话 id + 列表）
  const [currentSession, setCurrentSession] = useState<string>('default')
  const [sessionList, setSessionList] = useState<{ id: string; last_active_at?: string; pinned?: boolean }[]>([])
  const currentSessionRef = useRef(currentSession)
  currentSessionRef.current = currentSession
  // 供 WS 回调（onMessage 闭包）引用组件级滚动函数——[INSERT] 插入消息后滚到底部
  const forceScrollToBottomRef = useRef<() => void>(() => {})
  const sessionListRef = useRef(sessionList)
  sessionListRef.current = sessionList
  const chatProcessingRef = useRef(false)
  const [chatHasMore, setChatHasMore] = useState(false)
  const [chatLoadingOlder, setChatLoadingOlder] = useState(false)
  // 移动/桌面双面板都渲染 renderChatInner → ref 收集所有实例，滚动作用在全部（否则只滚到隐藏的那个）
  const listElsRef = useRef<HTMLDivElement[]>([])
  const chatListRef = useCallback((el: HTMLDivElement | null) => {
    if (el) {
      if (!listElsRef.current.includes(el)) listElsRef.current.push(el)
    } else {
      listElsRef.current = listElsRef.current.filter((x) => x.isConnected)
    }
  }, [])
  const eachList = useCallback((fn: (el: HTMLDivElement, i: number) => void) => {
    listElsRef.current.forEach((el, i) => { if (el.isConnected) fn(el, i) })
  }, [])
  const msgSeqRef = useRef(0)  // 本地临时消息 id（负数，避免与 DB id 碰撞）
  const chatInputRef = useRef<HTMLTextAreaElement>(null)
  // 工具执行完 → 世界文件可能被改 → 节流刷新（文件树/世界信息动态更新，不打断聊天流）
  const refreshTimerRef = useRef<number | null>(null)
  const onRefreshRef = useRef(onRefresh)
  onRefreshRef.current = onRefresh
  // 滚动跟随：在底部 = 新消息自动滚到最新；不在底部 = 显示 ↓ 按钮
  const [isAtBottom, setIsAtBottom] = useState(true)
  const isAtBottomRef = useRef(true)
  // 列表是否可滚动（内容溢出）：不可滚动时永远算"在底部"，但按钮入口仍要显示（没消息也要能直达底部）
  const [chatCanScroll, setChatCanScroll] = useState(false)
  const chatCanScrollRef = useRef(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const unreadCountRef = useRef(0)
  const loadingHistoryRef = useRef(false)  // 标记是否在加载历史（prepend），不增加未读

  // 斜杠命令列表（输入 / 弹出）
  const [cmdActive, setCmdActive] = useState(false)
  const [cmdQuery, setCmdQuery] = useState('')
  const [cmdIdx, setCmdIdx] = useState(0)
  const cmdFiltered = useMemo(() =>
    cmdQuery ? WORLD_COMMANDS.filter((c) => c.cmd.startsWith('/' + cmdQuery)) : WORLD_COMMANDS
  , [cmdQuery])

  // ── 历史加载 ──
  const loadChat = useCallback(async (opts?: { before_id?: number; append?: boolean }) => {
    try {
      const q = opts?.before_id ? `?before_id=${opts.before_id}&limit=30` : '?limit=30'
      // 翻页时记录原滚动位置（prepend 后补回，作用于所有面板实例）
      const heights = listElsRef.current.map((el) => el.scrollHeight)
      const r = await api.get<{ messages: ChatMsg[]; has_more: boolean; current_session?: string; sessions?: { id: string; last_active_at?: string; pinned?: boolean }[] }>(`/worlds/${wid}/chat${q}`)
      if (r.current_session) setCurrentSession(r.current_session)
      if (Array.isArray(r.sessions)) setSessionList(r.sessions)
      if (opts?.append && opts.before_id) {
        setChatMsgs((msgs) => [...(r.messages || []), ...msgs])
        requestAnimationFrame(() => {
          eachList((el, i) => { el.scrollTop = el.scrollHeight - (heights[i] ?? 0) })
        })
      } else {
        setChatMsgs(r.messages || [])
        // 在底部（跟随模式）才滚到消息末尾；用户往上翻时不打扰
        // ⚠️ 2026-08-13 修复：实时读位置（isAtBottomRef 由 rAF 节流更新可能延迟——
        // 用户刚往上翻时 ref 还是 true，工具 done 后 loadChat 误滚到底部）
        const el = listElsRef.current.find((x) => x.isConnected)
        const atBottomNow = el ? el.scrollHeight - el.scrollTop - el.clientHeight < 80 : false
        if (atBottomNow) {
          forceScrollToBottom()
        }
      }
      setChatHasMore(!!r.has_more)
    } catch { /* 历史拉不到不阻塞 */ }
  }, [wid])

  useEffect(() => { loadChat() }, [loadChat])

  // 挂载时拉取建议（持久化的 AI 建议；无历史 → 预设随机 4；有历史无存储 → 空等 AI 回复）
  useEffect(() => {
    if (!wid) return
    let cancelled = false
    api.get<{ suggestions: string[] }>(`/worlds/${wid}/chat/suggest`)
      .then((r) => { if (!cancelled && Array.isArray(r?.suggestions)) setSuggestions(r.suggestions) })
      .catch(() => { /* 失败静默 */ })
    return () => { cancelled = true }
  }, [wid])

  // 滚到顶 → 加载更早消息（主聊天同款无限滚动）
  const loadOlder = useCallback(async () => {
    if (chatLoadingOlder || !chatHasMore || chatMsgs.length === 0) return
    const oldest = chatMsgs[0].id
    // 历史消息来自 DB，id 为正数；本地临时负数消息跳过
    if (!oldest || oldest < 0) return
    setChatLoadingOlder(true)
    loadingHistoryRef.current = true  // 标记是历史加载，不增加未读
    try {
      await loadChat({ before_id: oldest, append: true })
    } finally {
      loadingHistoryRef.current = false
      setChatLoadingOlder(false)
    }
  }, [chatLoadingOlder, chatHasMore, chatMsgs, loadChat])

  // 滚动状态统一处理（rAF 节流）：capture 监听 window scroll（scroll 不冒泡但经捕获阶段，覆盖列表/页面任何滚动）
  // ⚠️ 每帧最多一次布局读取 + 状态更新：滚动事件高频触发，若每次都读 scrollHeight/clientHeight（reflow）会卡
  const loadOlderRef = useRef(loadOlder)
  loadOlderRef.current = loadOlder
  const scrollRafRef = useRef<number | null>(null)
  const updateScrollState = useCallback(() => {
    scrollRafRef.current = null
    const el = listElsRef.current.find((x) => x.isConnected)
    if (!el) return
    if (el.scrollTop < 30) loadOlderRef.current()
    // 只看列表元素滚动位置（不用 window.scrollY——列表占满视口时恒 0，误判在底部）
    const listCanScroll = el.scrollHeight - el.clientHeight > 4
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    isAtBottomRef.current = atBottom
    setIsAtBottom(atBottom)
    chatCanScrollRef.current = listCanScroll
    setChatCanScroll(listCanScroll)
    if (atBottom) {
      unreadCountRef.current = 0
      setUnreadCount(0)
    }
  }, [])
  const onAnyScroll = useCallback(() => {
    if (scrollRafRef.current !== null) return
    scrollRafRef.current = requestAnimationFrame(updateScrollState)
  }, [updateScrollState])
  useEffect(() => {
    window.addEventListener('scroll', onAnyScroll, true)
    return () => {
      window.removeEventListener('scroll', onAnyScroll, true)
      if (scrollRafRef.current !== null) cancelAnimationFrame(scrollRafRef.current)
    }
  }, [onAnyScroll])

  // 消息/布局变化后重新测量可滚性（列表不可滚动时按钮仍显示入口）
  // ⚠️ 依赖 chatMsgs.length 而非 chatMsgs：气泡内容流式更新（每 token 一次）不触发测量，
  // 否则流式输出期间高频读取 scrollHeight/clientHeight 强制 reflow，底部滑动时卡顿
  useEffect(() => {
    const el = listElsRef.current.find((x) => x.isConnected)
    if (!el) return
    const can = el.scrollHeight - el.clientHeight > 4
    chatCanScrollRef.current = can
    setChatCanScroll(can)
  }, [chatMsgs.length])

  // 新消息到达时，如果不在底部，增加未读计数（历史加载时不增加）
  // ⚠️ 2026-08-13 修复：原来依赖 chatMsgs 变化——流式每 chunk 更新都触发（思考气泡逐字、
  // 正文逐字），一秒加几十个未读。改为只在「完整 AI 回复」或「插入消息」到达时计数一次。
  // 实际计数点：subscribeTurnStream 收到 [DONE] 后（完整一轮）+
  // 轮询恢复发现新消息时（check 兜底）——见下方计数组件。
  const countUnreadIfAway = useCallback(() => {
    if (loadingHistoryRef.current) return
    if (!isAtBottomRef.current && chatMsgs.length > 0) {
      unreadCountRef.current += 1
      setUnreadCount(unreadCountRef.current)
    }
  }, [chatMsgs])

  // 滚到底部并校验：double rAF 等布局稳定 → 延时后仍不在底部再滚一次（兜底时序问题）
  const forceScrollToBottom = useCallback(() => {
    const settle = () => {
      eachList((el) => { el.scrollTop = el.scrollHeight })
      // 兜底：内容可能还在渲染（图片/代码块），稍后不在底部再滚一次
      window.setTimeout(() => {
        eachList((el) => {
          if (el.scrollHeight - el.scrollTop - el.clientHeight > 10) el.scrollTop = el.scrollHeight
        })
      }, 250)
    }
    requestAnimationFrame(() => requestAnimationFrame(settle))
  }, [eachList])
  forceScrollToBottomRef.current = forceScrollToBottom

  // 新消息到达：跟随模式（在底部）自动滚到最新——首次瞬时（等布局稳定），后续新消息平滑，流式内容更新瞬时
  const prevLenRef = useRef(0)
  const loadedOnceRef = useRef(false)
  useEffect(() => {
    if (chatMsgs.length === 0) return
    // ⚠️ 2026-08-13 修复：滚动前实时读取位置（不依赖可能延迟的 isAtBottomRef）——
    // 用户往上翻后 rAF 节流未及更新 ref，AI 新消息到达会误滚到底部。
    const el = listElsRef.current.find((x) => x.isConnected)
    if (!el) return
    // ⚠️ 2026-08-13 修复2：只看列表元素本身的滚动位置（不用 window.scrollY）——
    // 列表占满视口时 window.scrollY 恒 0，误判"在底部"导致每次新消息都跳底。
    const atBottomNow = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (!atBottomNow) {
      // 用户不在底部：不滚动，未读由 countUnreadIfAway 计数
      return
    }
    const first = !loadedOnceRef.current
    loadedOnceRef.current = true
    const lenChanged = chatMsgs.length !== prevLenRef.current
    prevLenRef.current = chatMsgs.length
    if (first) {
      forceScrollToBottom()
    } else if (lenChanged) {
      // 流式输出中（chatSending）用瞬时滚动：smooth 动画在快速连续输出时会堆积打架导致卡顿
      eachList((el) => { el.scrollTo({ top: el.scrollHeight, behavior: chatSending ? 'auto' : 'smooth' }) })
    }
  }, [chatMsgs, chatSending])

  const scrollToBottom = useCallback((smooth = true) => {
    isAtBottomRef.current = true
    setIsAtBottom(true)
    eachList((el) => { el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' }) })
  }, [eachList])

  // ── 订阅 turn 直播（SSE）：发消息后 / 刷新恢复 共用 ──
  // 断开自动重连（最多 2 次）；返回是否收到 [DONE]（false = 连接失败/重连耗尽，调用方拉历史收尾）
  const subscribeTurnStream = useCallback(async (turnId: string): Promise<boolean> => {
    let full = ''
    let reasoning = ''
    // 2026-08-13：正文/思考独立气泡（顺序递增 id）——思考一个气泡、正文一个气泡，
    // 没有正文就没有正文气泡（不再用占位）；[TOOL_UPDATE] 后都封存开新
    let contentTargetId: number | null = null
    let reasoningTargetId: number | null = null
    const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
    const authHeaders = {
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      'Content-Type': 'application/json',
    }
    let gotDone = false
    for (let attempt = 0; attempt < 2 && !gotDone; attempt++) {
      const streamResp = await fetch(`${base}/worlds/${wid}/chat/stream?turn_id=${turnId}`, { headers: authHeaders })
      if (!streamResp.ok || !streamResp.body) return false
      const reader = streamResp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      // 流式气泡：函数式更新（存在则更新、不存在则创建），同一 id 永不重复——
      // ⚠️ 根本修复：React 18 setState 异步提交，气泡创建未提交时 msgs.map 找不到 id → 更新被吞 → 气泡永远空。
      // 用函数式 setState：无论提交时序，最终 state 里气泡必带最新内容（创建即带内容，更新不丢）。
      const updateBubble = (id: number, patch: Partial<ChatMsg>) => {
        setChatMsgs((msgs) => {
          const idx = msgs.findIndex((m) => m.id === id)
          if (idx >= 0) {
            const next = msgs.slice()
            next[idx] = { ...next[idx], ...patch }
            return next
          }
          return [...msgs, { id, role: 'ai' as const, content: '', ...patch }]
        })
      }
      // 更新思考（2026-08-13 简化：不维护 preview——折叠截断在渲染层做，一个对象）
      const updateBubbleReasoning = (id: number, reasoningText: string) => {
        updateBubble(id, { reasoning: reasoningText })
      }
      // 正文气泡（首次正文到达时创建；id 顺序递增保证时间线）
      const ensureContentBubble = () => {
        if (contentTargetId !== null) return
        contentTargetId = -(++msgSeqRef.current)
        updateBubble(contentTargetId, { content: full })
      }
      // 思考气泡（首次思考到达时创建；独立 id）
      const ensureReasoningBubble = () => {
        if (reasoningTargetId !== null) return
        reasoningTargetId = -(++msgSeqRef.current)
        updateBubble(reasoningTargetId, { reasoning })
      }
      // rAF 节流渲染（每帧最多一次函数式更新）
      let renderPending = false
      const scheduleRender = () => {
        if (renderPending) return
        renderPending = true
        requestAnimationFrame(() => {
          renderPending = false
          if (contentTargetId !== null) updateBubble(contentTargetId, { content: full })
          if (reasoningTargetId !== null) updateBubbleReasoning(reasoningTargetId, reasoning)
        })
      }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') {
            gotDone = true
            // 完整一轮结束：若用户不在底部，未读 +1（不是每 chunk 都加）
            window.setTimeout(() => countUnreadIfAway(), 0)
            break
          }
          if (payload.startsWith('[SUGGEST]')) {
            try { setSuggestions(JSON.parse(payload.slice(9))) } catch { /* ignore */ }
            continue
          }
          if (payload.startsWith(EV.INSERTED)) {
            // 信号（不计入历史）：后端已把排队消息真正插入工具轮（FIFO）——
            // 从排队弹窗移除 count 条成功的消息，弹窗只留还没发出的
            const sig = parseEvent<{ count?: number }>(payload, EV.INSERTED)
            if (sig) setPendingItems((items) => items.slice(sig.count || 0))
            continue
          }
          if (payload.startsWith(EV.INSERT)) {
            // 排队消息已插入工具轮并落库（记入历史）：画用户气泡（用真实 msg_id，
            // 与历史一致，loadChat 后不会重复/错位）
            const ins = parseEvent<{ msg_id: number; content: string }>(payload, EV.INSERT)
            if (ins) {
              setChatMsgs((msgs) => [...msgs, { id: ins.msg_id, role: 'user', content: ins.content }])
              requestAnimationFrame(() => forceScrollToBottomRef.current?.())
            }
            continue
          }
          if (payload.startsWith('[ERROR]')) throw new Error(payload.slice(7))
          if (payload.startsWith('[TOOL_UPDATE]')) {
            // 工具状态事件（2026-08-13：同 tool_id 多状态更新）——
            // running（正在执行 XX）→ update（进度）→ done（完成，同 id 原地更新气泡）
            try {
              const tu = JSON.parse(payload.slice(13))
              const tId = tu.tool_id
              // 先把当前正文/思考气泡同步封存（函数式更新：存在则更新；即使创建未提交也会带内容创建，不丢）
              if (contentTargetId !== null) updateBubble(contentTargetId, { content: full })
              if (reasoningTargetId !== null) updateBubbleReasoning(reasoningTargetId, reasoning)
              // 后续内容开新气泡；full/reasoning 重置避免拼接
              contentTargetId = null
              reasoningTargetId = null
              full = ''
              reasoning = ''
              renderPending = false
              if (tId) {
                // 按 tool_id 定位：有则更新（status 变化原地替换），无则创建
                const base = {
                  role: 'tool' as const, tool_id: tId,
                  tool_name: tu.name, tool_status: tu.status as any,
                  tool_args: tu.args_summary,
                  error: tu.status === 'done' ? !tu.success : false,
                }
                setChatMsgs((msgs) => {
                  const idx = msgs.findIndex((m) => m.role === 'tool' && m.tool_id === tId)
                  if (idx >= 0) {
                    const next = msgs.slice()
                    next[idx] = { ...next[idx], ...base, content: tu.summary || next[idx].content }
                    return next
                  }
                  return [...msgs, { id: -(++msgSeqRef.current), ...base, content: tu.summary || '' }]
                })
              } else {
                // 无 tool_id（旧格式兜底）：独立气泡
                setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'tool', content: tu.summary || tu.name, error: tu.status === 'done' ? !tu.success : false }])
              }
              // 工具完成 → 世界文件/配置可能被改 → 节流刷新（文件树动态更新；400ms 内多个工具合并一次）
              if (tu.status === 'done') {
                if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
                refreshTimerRef.current = window.setTimeout(() => onRefreshRef.current(), 400)
              }
            } catch { /* 解析失败忽略 */ }
            continue
          }
          if (payload.startsWith('[REASONING]')) {
            reasoning += payload.slice(11).replace(/\{NL\}/g, '\n')
            ensureReasoningBubble()
          } else if (payload.startsWith('[TOOL]')) {
            // 旧格式工具事件（无 _UPDATE）已废弃：忽略，不当作正文显示（2026-08-13）
          } else {
            full += payload.replace(/\{NL\}/g, '\n')
            ensureContentBubble()
          }
          scheduleRender()
        }
        if (gotDone) break
      }
      if (gotDone) break
      // 连接断开且未完成：稍等重连（间隔 1s/2s）
      await new Promise((res) => setTimeout(res, 1000 * (attempt + 1)))
    }
    return gotDone
  }, [wid])

  // 刷新后恢复「思考中」状态：world_turn 在服务器端继续执行，前端状态丢失后订阅直播 + 轮询恢复
  useEffect(() => {
    if (!wid) return
    let timer: number | undefined
    let cancelled = false
    const check = async () => {
      try {
        const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
        const r = await fetch(`${base}/worlds/${wid}/chat/status`, {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
        })
        const s = await r.json()
        if (s && s.processing) {
          chatProcessingRef.current = true
          setChatProcessing(true)
          // 有进行中的 turn → 订阅 SSE 直播，实时看到流式内容（不用等整轮跑完才一次性更新）
          if (s.turn_id && !cancelled) {
            try {
              const done = await subscribeTurnStream(s.turn_id)
              if (cancelled) return
              if (done) {
                // 直播正常结束：拉权威历史收尾 + 刷新用量（缓存命中率）
                chatProcessingRef.current = false
                setChatProcessing(false)
                loadChat()
                onRefreshRef.current()
                return
              }
            } catch { /* 直播失败/中断：继续轮询兜底 */ }
          }
          timer = window.setTimeout(check, 4000)
        } else {
          if (chatProcessingRef.current) {
            chatProcessingRef.current = false
            setChatProcessing(false)
            loadChat()  // 处理完成：拉最新历史（含 AI 回复）
            onRefreshRef.current()  // 刷新用量（缓存命中率）——普通对话也要更新，不只工具场景
          }
        }
      } catch { /* 失败静默重试 */ if (!cancelled) timer = window.setTimeout(check, 8000) }
    }
    chatProcessingRef.current = false
    check()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [wid, loadChat, subscribeTurnStream])

  // 卸载清理（节流刷新定时器）
  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    }
  }, [])

  // ── 会话切换 / 收藏（/new /use /pin 的前端等价操作，走 API 不占对话轮次）──
  const switchSession = useCallback(async (sid: string): Promise<boolean> => {
    try {
      const r = await api.post<{ messages: ChatMsg[]; current_session: string; sessions: { id: string; last_active_at?: string; pinned?: boolean }[] }>(
        `/worlds/${wid}/chat/session`, { session_id: sid },
      )
      setCurrentSession(r.current_session)
      if (Array.isArray(r.sessions)) setSessionList(r.sessions)
      if (Array.isArray(r.messages)) setChatMsgs(r.messages)
      setChatHasMore(false)
      forceScrollToBottom()
      return true
    } catch { return false }
  }, [wid, forceScrollToBottom])

  const togglePin = useCallback(async (): Promise<boolean> => {
    try {
      const cur = currentSessionRef.current
      const isPinned = sessionListRef.current.find((s) => s.id === cur)?.pinned
      const r = await api.post<{ pinned: boolean; count: number }>(`/worlds/${wid}/chat/session/pin`, { pin: !isPinned })
      setSessionList((prev) => prev.map((s) => s.id === cur ? { ...s, pinned: r.pinned } : s))
      return r.pinned
    } catch { return false }
  }, [wid])

  // ── 发送 ──
  const sendMessages = async (texts: string[]) => {
    const list = texts.map((t) => t.trim()).filter(Boolean)
    if (!list.length) return
    setChatSending(true)
    setChatInput('')
    setCmdActive(false)
    // 斜杠命令：立即给执行中反馈（后端压缩/清空需要时间，等 [TOOL] 正式结果到达后 loadChat 会清掉这个临时气泡）
    const singleCmd = list.length === 1 ? list[0] : ''
    if (singleCmd.startsWith('/compact') || singleCmd.startsWith('/clear')) {
      setChatMsgs((msgs) => [...msgs, {
        id: -(++msgSeqRef.current), role: 'tool',
        content: singleCmd.startsWith('/compact') ? '⏳ 正在压缩上下文（可能需要一点时间）…' : '⏳ 正在清空上下文…',
      }])
    }

    // 服务器端轮次（不依赖本页面）：入队 → 订阅直播（断开自动重连，逻辑见 subscribeTurnStream）
    try {
      // 1. 入队（返回 turn_id；若前面有消息在跑会排队）
      const r = await api.post<{ turn_id: string; queued: boolean; position: number }>(`/worlds/${wid}/chat`, { messages: list })
      if (r.queued) {
        setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'tool', content: `⏳ 已排队（前面还有 ${r.position} 条在跑）` }])
      }

      // 2. 订阅直播（SSE）；断连自动重连最多 2 次，耗尽后拉权威历史收尾
      await subscribeTurnStream(r.turn_id)
      // 用权威历史收尾（含断开期间漏掉的工具气泡/最终回复）；世界信息可能被工具改过，一并刷新
      await loadChat()
      onRefresh()
    } catch (e: any) {
      // 出错：独立错误气泡（已流式显示的内容保留，不抹掉）
      const errText = e?.message || '未知错误'
      setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'ai', content: errText, error: true }])
      onMsg(`发送失败: ${errText}`)
    } finally {
      setChatSending(false)
    }
  }

  const submitText = (text: string) => {
    const t = text.trim()
    if (!t) return
    // AI 忙（本条发送中 / 后台轮次执行中）：进队列——不画占位气泡（位置不对，
    // 且会被 loadChat 冲掉），只显示在排队弹窗；真正插入后（[INSERT] 回执）才进对话流
    if (chatSending || chatProcessing) {
      setPendingItems((items) => [...items, { kind: t.startsWith('/') ? 'cmd' : 'msg', text: t }])
      setChatInput('')
      setCmdActive(false)
      setSuggestions([])  // 开始新工作流 → 旧建议隐藏，等新回复生成新的
      return
    }
    // 直接发送：也先画用户气泡，再由 sendMessages 发送
    setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'user', content: t }])
    setSuggestions([])  // 用户发送（点了预设等）→ 建议收起
    sendMessages([t])
  }

  // 插入建议到输入框（追加不覆盖）；输入框 ref 在聊天面板 textarea 上
  const insertSuggestion = (q: string) => {
    setChatInput((prev) => (prev ? prev + ' ' + q : q))
    requestAnimationFrame(() => {
      chatInputRef.current?.focus()
      const ta = chatInputRef.current
      if (ta) {
        const pos = ta.value.length
        ta.setSelectionRange(pos, pos)
      }
    })
  }

  // 流结束后按队列顺序自动处理：连续普通消息一批（一次 API 一起发，逐条气泡）；命令单独（等前一个完成再下一个）
  useEffect(() => {
    if (chatSending || chatProcessing || pendingItems.length === 0) return
    const items = pendingItems
    const firstCmd = items.findIndex((i) => i.kind === 'cmd')
    if (firstCmd === 0) {
      setPendingItems(items.slice(1))
      sendMessages([items[0].text])
    } else {
      const n = firstCmd === -1 ? items.length : firstCmd
      setPendingItems(items.slice(n))
      sendMessages(items.slice(0, n).map((i) => i.text))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatSending, chatProcessing, pendingItems])

  return {
    chatMsgs, chatInput, setChatInput,
    chatSending, chatProcessing, chatHasMore, chatLoadingOlder,
    chatListRef, chatInputRef, pendingItems, setPendingItems, suggestions,
    cmdActive, setCmdActive, cmdQuery, setCmdQuery, cmdIdx, setCmdIdx, cmdFiltered,
    submitText, insertSuggestion, isAtBottom, chatCanScroll, scrollToBottom, forceScrollToBottom,
    currentSession, sessionList, switchSession, togglePin, unreadCount,
  }
}

// vite-transform-cache-bump: 2026-08-10 14:16
