/**
 * 世界 AI 对话 hook — 聊天状态 + 流式发送 + 排队 + 建议按钮 + 斜杠命令
 * 从 WorldDesignPage 拆分（2026-08-06 重构）
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
}

// 斜杠命令列表（输入 / 弹出，像 @ 提及；仅世界设计页——主站保持人性化不加）
const WORLD_COMMANDS = [
  { cmd: '/clear', desc: '清空对话上下文（保留长期记忆）' },
  { cmd: '/compact', desc: '压缩对话上下文为摘要' },
]

interface UseWorldChatOptions {
  wid: number
  /** 世界信息刷新（AI 工具可能改过世界，回复结束后调用） */
  onRefresh: () => void
  /** 顶部提示消息 */
  onMsg: (msg: string) => void
}

export function useWorldChat({ wid, onRefresh, onMsg }: UseWorldChatOptions) {
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const [chatProcessing, setChatProcessing] = useState(false)  // 刷新后恢复：后台轮次仍在执行
  const [pendingItems, setPendingItems] = useState<{ kind: 'msg' | 'cmd'; text: string }[]>([])  // AI 处理中排队消息（msg 一起发；cmd 串行执行）
  const [suggestions, setSuggestions] = useState<string[]>([])  // "你可以"建议（AI 生成 / 兜底 / 预设）
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
  // 滚动跟随：在底部 = 新消息自动滚到最新；不在底部 = 显示 ↓ 按钮
  const [isAtBottom, setIsAtBottom] = useState(true)
  const isAtBottomRef = useRef(true)

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
      const r = await api.get<{ messages: ChatMsg[]; has_more: boolean }>(`/worlds/${wid}/chat${q}`)
      if (opts?.append && opts.before_id) {
        setChatMsgs((msgs) => [...(r.messages || []), ...msgs])
        requestAnimationFrame(() => {
          eachList((el, i) => { el.scrollTop = el.scrollHeight - (heights[i] ?? 0) })
        })
      } else {
        setChatMsgs(r.messages || [])
        // 在底部（跟随模式）才滚到消息末尾；用户往上翻时不打扰
        if (isAtBottomRef.current) {
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

  // 刷新后恢复「思考中」状态：world_turn 在服务器端继续执行，前端状态丢失后轮询恢复
  useEffect(() => {
    if (!wid) return
    let timer: number | undefined
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
          timer = window.setTimeout(check, 4000)
        } else {
          if (chatProcessingRef.current) {
            chatProcessingRef.current = false
            setChatProcessing(false)
            loadChat()  // 处理完成：拉最新历史（含 AI 回复）
          }
        }
      } catch { /* 失败静默重试 */ timer = window.setTimeout(check, 8000) }
    }
    chatProcessingRef.current = false
    check()
    return () => { if (timer) clearTimeout(timer) }
  }, [wid])

  // 滚到顶 → 加载更早消息（主聊天同款无限滚动）
  const loadOlder = useCallback(async () => {
    if (chatLoadingOlder || !chatHasMore || chatMsgs.length === 0) return
    const oldest = chatMsgs[0].id
    // 历史消息来自 DB，id 为正数；本地临时负数消息跳过
    if (!oldest || oldest < 0) return
    setChatLoadingOlder(true)
    try {
      await loadChat({ before_id: oldest, append: true })
    } finally {
      setChatLoadingOlder(false)
    }
  }, [chatLoadingOlder, chatHasMore, chatMsgs, loadChat])

  const handleChatScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollTop < 30) loadOlder()
    // 底部判定（rAF 节流由 React 事件天然节流；80px 阈值与主界面一致）
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    isAtBottomRef.current = atBottom
    setIsAtBottom(atBottom)
  }, [loadOlder])

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

  // 新消息到达：跟随模式（在底部）自动滚到最新——首次瞬时（等布局稳定），后续新消息平滑，流式内容更新瞬时
  const prevLenRef = useRef(0)
  const loadedOnceRef = useRef(false)
  useEffect(() => {
    if (!isAtBottomRef.current || chatMsgs.length === 0) return
    const first = !loadedOnceRef.current
    loadedOnceRef.current = true
    const lenChanged = chatMsgs.length !== prevLenRef.current
    prevLenRef.current = chatMsgs.length
    if (first) {
      forceScrollToBottom()
    } else if (lenChanged) {
      eachList((el) => { el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }) })
    }
  }, [chatMsgs])

  const scrollToBottom = useCallback((smooth = true) => {
    isAtBottomRef.current = true
    setIsAtBottom(true)
    eachList((el) => { el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' }) })
  }, [eachList])

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

    // 服务器端轮次（不依赖本页面）：入队 → 订阅直播（断开自动重连）
    let full = ''
    let reasoning = ''
    let streamTargetId: number | null = null  // 当前流式气泡（[TOOL] 后封存、开新气泡）
    const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
    const authHeaders = {
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      'Content-Type': 'application/json',
    }
    try {
      // 1. 入队（返回 turn_id；若前面有消息在跑会排队）
      const r = await api.post<{ turn_id: string; queued: boolean; position: number }>(`/worlds/${wid}/chat`, { messages: list })
      if (r.queued) {
        setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'tool', content: `⏳ 已排队（前面还有 ${r.position} 条在跑）` }])
      }

      // 2. 订阅直播（SSE）；断开自动重连加入直播，最多 5 次
      let gotDone = false
      for (let attempt = 0; attempt < 5 && !gotDone; attempt++) {
        const streamResp = await fetch(`${base}/worlds/${wid}/chat/stream?turn_id=${r.turn_id}`, { headers: authHeaders })
        if (!streamResp.ok || !streamResp.body) throw new Error(`直播连接失败(${streamResp.status})`)
        const reader = streamResp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        // 首次内容/思考到达时开气泡（不在发消息时预建，避免空气泡）
        const ensureBubble = () => {
          if (streamTargetId !== null) return
          const id = -(++msgSeqRef.current)
          streamTargetId = id
          setChatMsgs((msgs) => [...msgs, { id, role: 'ai', content: '', reasoning: '' }])
        }
        // rAF 节流渲染（只更新当前流式气泡）
        let renderPending = false
        const scheduleRender = () => {
          if (renderPending) return
          renderPending = true
          requestAnimationFrame(() => {
            renderPending = false
            if (streamTargetId === null) return
            setChatMsgs((msgs) => msgs.map((m) => m.id === streamTargetId ? { ...m, content: full, reasoning } : m))
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
            if (payload === '[DONE]') { gotDone = true; break }
            if (payload.startsWith('[SUGGEST]')) {
              try { setSuggestions(JSON.parse(payload.slice(9))) } catch { /* ignore */ }
              continue
            }
            if (payload.startsWith('[ERROR]')) throw new Error(payload.slice(7))
            if (payload.startsWith('[TOOL]')) {
              try {
                const t = JSON.parse(payload.slice(6))
                // 封存当前叙述气泡（内容已渲染），后续内容开新气泡；full/reasoning 重置避免拼接
                streamTargetId = null
                full = ''
                reasoning = ''
                setChatMsgs((msgs) => [...msgs, {
                  id: -(++msgSeqRef.current),
                  role: 'tool',
                  content: t.summary || `${t.name} ${t.success ? '执行成功' : '执行失败'}`,
                  error: !t.success,
                }])
              } catch { /* 解析失败忽略 */ }
              continue
            }
            if (payload.startsWith('[REASONING]')) {
              reasoning += payload.slice(11).replace(/\{NL\}/g, '\n')
            } else {
              full += payload.replace(/\{NL\}/g, '\n')
            }
            ensureBubble()
            scheduleRender()
          }
          if (gotDone) break
        }
        if (gotDone) break
        // 连接断开且未完成：稍等重连（重新订阅直播）
        await new Promise((res) => setTimeout(res, 1500 * (attempt + 1)))
      }
      // 用权威历史收尾（含断开期间漏掉的工具气泡/最终回复）；世界信息可能被工具改过，一并刷新
      await loadChat()
      onRefresh()
    } catch (e: any) {
      // 出错：独立错误气泡
      const errText = e?.message || '未知错误'
      setChatMsgs((msgs) => streamTargetId === null ? msgs : msgs.map((m) => m.id === streamTargetId ? { ...m, content: '', reasoning: '' } : m))
      setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'ai', content: errText, error: true }])
      onMsg(`发送失败: ${errText}`)
    } finally {
      setChatSending(false)
    }
  }

  const submitText = (text: string) => {
    const t = text.trim()
    if (!t) return
    // AI 忙（本条发送中 / 后台轮次执行中）：进队列——普通消息等流结束一起发；/ 命令等流结束按顺序逐个执行
    if (chatSending || chatProcessing) {
      // 排队：消息直接画进对话流（用户气泡 + 排队中标记），流结束后一起发送——输入框上方不再弹列表
      setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'user', content: t, pending: true }])
      setPendingItems((items) => [...items, { kind: t.startsWith('/') ? 'cmd' : 'msg', text: t }])
      setChatInput('')
      setCmdActive(false)
      return
    }
    // 直接发送：也先画用户气泡，再由 sendMessages 发送
    setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'user', content: t }])
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
    handleChatScroll, submitText, insertSuggestion, isAtBottom, scrollToBottom, forceScrollToBottom,
  }
}
