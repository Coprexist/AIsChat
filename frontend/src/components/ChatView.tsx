import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useWebSocket, type WebSocketMessage } from '../hooks/useWebSocket'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import MessageBubble from './MessageBubble'
import ActivityBar, { type ActivityUser } from './ActivityBar'
import ProfileCard from './ProfileCard'
import { Send, Loader2, AlertTriangle, X, ArrowDown, ArrowUp, Paperclip, FileIcon, Bot, User } from 'lucide-react'
import { getStateDotColor, CHAT_REFRESH_EVENT } from '../constants'
import { useT } from '../i18n/I18nContext'

interface Message {
  id: number
  group_id?: number
  session_id?: string
  sender_type: string
  sender_id: number
  sender_name: string | null
  sender_avatar_url?: string | null
  content: string
  reply_to: number | null
  read_at?: string | null
  attachments?: Array<{file_id?: number, name?: string, size?: number, mime_type?: string, type?: string, invitation_id?: number, group_name?: string, inviter_name?: string, status?: string}> | null
  source_public_id?: string | null
  message_type?: string
  created_at: string
}

interface ChatViewProps {
  conversationType: 'group' | 'dm'
  conversationId: number | string
}

const PAGE_SIZE = 20

// ── 模块级工具函数 ──

/** 检查 WebSocket 消息是否属于当前对话 */
function isMessageForThisConversation(
  data: { group_id?: number; session_id?: string },
  convType: 'group' | 'dm',
  convId: number | string,
): boolean {
  return (convType === 'group' && (data as any).group_id === convId) ||
         (convType === 'dm' && (data as any).session_id === convId)
}

/** 从 Map state setter 中移除指定 id */
function removeFromMap<K, V>(
  setter: React.Dispatch<React.SetStateAction<Map<K, V>>>,
  id: K,
) {
  setter((prev) => {
    const next = new Map(prev)
    next.delete(id)
    return next
  })
}

/** 向 Map state setter 中添加指定键值对 */
function addToMap<K, V>(
  setter: React.Dispatch<React.SetStateAction<Map<K, V>>>,
  id: K,
  value: V,
) {
  setter((prev) => {
    const next = new Map(prev)
    next.set(id, value)
    return next
  })
}

export default function ChatView({ conversationType, conversationId }: ChatViewProps) {
  const t = useT()
  const { user } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loadingState, setLoadingState] = useState<'initial' | 'older' | 'newer' | null>(null)
  const [hasMoreBefore, setHasMoreBefore] = useState(false)
  const [hasMoreAfter, setHasMoreAfter] = useState(false)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [firstUnreadId, setFirstUnreadId] = useState<number | null>(null)
  const [showJumpToUnread, setShowJumpToUnread] = useState(false)
  const [profileCard, setProfileCard] = useState<{
    type: string; id: number; name: string; state?: string
  } | null>(null)
  const [thinkingAgents, setThinkingAgents] = useState<Map<number, { name: string; avatarUrl: string | null }>>(new Map())
  const [typingAgents, setTypingAgents] = useState<Map<number, { name: string; avatarUrl: string | null }>>(new Map())
  // 人类打字状态: userId → {name, avatarUrl}
  const [humanTyping, setHumanTyping] = useState<Map<number, { name: string; avatarUrl: string | null }>>(new Map())

  // 合并所有活动用户（AI 思考 + AI 输入中 + 人类打字）
  const activityUsers: ActivityUser[] = useMemo(() => {
    const map = new Map<number, ActivityUser>()

    thinkingAgents.forEach((info, id) => {
      map.set(id, { id, name: info.name, avatarUrl: info.avatarUrl, status: 'thinking' })
    })
    typingAgents.forEach((info, id) => {
      const existing = map.get(id)
      if (existing) existing.status = 'typing'
      else map.set(id, { id, name: info.name, avatarUrl: info.avatarUrl, status: 'typing' })
    })
    humanTyping.forEach(({ name, avatarUrl }, id) => {
      map.set(id, { id, name, avatarUrl, status: 'typing' })
    })

    return Array.from(map.values())
  }, [thinkingAgents, typingAgents, humanTyping])

  // @提及 自动补全（仅群聊）
  const [groupMembers, setGroupMembers] = useState<Array<{ type: string; id: number; name: string; state?: string }>>([])
  const [mentionActive, setMentionActive] = useState(false)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionIdx, setMentionIdx] = useState(0)

  // 文件附件
  interface PendingAttachment {
    id: string        // 临时前端 ID（用于删除/去重）
    file: File | null // null=上传完成，有值=上传中
    file_id?: number  // 服务端返回的 ID
    path?: string     // 服务端返回的存储路径
    name: string
    size: number
    mime_type: string
    uploading: boolean
    error?: string
  }
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingCount, setUploadingCount] = useState(0)

  // Refs
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const inputRef = useRef(input)
  inputRef.current = input // 保持同步，供 effect cleanup 闭包读取最新值
  const containerRef = useRef<HTMLDivElement>(null)
  const topSentinelRef = useRef<HTMLDivElement>(null)
  const bottomSentinelRef = useRef<HTMLDivElement>(null)
  const firstUnreadRef = useRef<HTMLDivElement>(null)
  const prevMessageCount = useRef(0)
  const isAutoScrolling = useRef(false)
  const prevScrollHeight = useRef(0)
  const isAtBottomRef = useRef(true)
  const newestIdRef = useRef<number | null>(null)       // 离开时保存已读位置
  const oldestIdRef = useRef<number | null>(null)        // 供哨兵读取，避免 messages 依赖
  const typingRef = useRef(false)                       // 当前是否正在输入中，避免重复发送 typing 消息
  const showJumpToUnreadRef = useRef(false)              // 避免 scroll 中高频 setState

  // 离开对话时保存已读位置（通过 newestIdRef，无需额外的 messages 同步 effect）
  useEffect(() => {
    return () => {
      if (newestIdRef.current && conversationId) {
        const key = `lastRead_${conversationType}_${conversationId}`
        localStorage.setItem(key, String(newestIdRef.current))
      }
    }
  }, [conversationType, conversationId])

  // 输入框草稿缓存：切换对话时保存旧草稿、恢复新草稿；页面刷新/崩溃后内容不丢
  useEffect(() => {
    if (!conversationId) return
    const draftKey = `draft_${conversationType}_${conversationId}`
    const draft = localStorage.getItem(draftKey)
    setInput(draft || '')
    return () => {
      if (inputRef.current.trim()) {
        localStorage.setItem(draftKey, inputRef.current)
      } else {
        localStorage.removeItem(draftKey)
      }
    }
  }, [conversationType, conversationId])

  // 输入中自动保存草稿（500ms 防抖，防止崩溃/掉线丢失）
  useEffect(() => {
    if (!conversationId) return
    const draftKey = `draft_${conversationType}_${conversationId}`
    const timer = setTimeout(() => {
      if (input.trim()) {
        localStorage.setItem(draftKey, input)
      } else {
        localStorage.removeItem(draftKey)
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [input, conversationType, conversationId])

  const handleMessage = useCallback((msg: WebSocketMessage) => {
    if (msg.type === 'message') {
      const m = msg.data
      setMessages((prev) => {
        // 去重：防止 WebSocket 与 HTTP fetch 竞态导致同 ID 消息重复
        if (prev.some((existing) => existing.id === m.id)) return prev
        const next = [...prev, m]
        newestIdRef.current = m.id
        return next
      })
      if (isAtBottomRef.current) {
        setTimeout(() => scrollToBottom(true), 50)
      }
      // 新消息到达 → 通知侧栏刷新排序和未读
      window.dispatchEvent(new CustomEvent(CHAT_REFRESH_EVENT, { detail: {
        type: 'unread_update',
        conversation_type: conversationType,
        conversation_id: conversationId,
      } }))
      if (m.sender_type === 'ai' && m.sender_id) {
        removeFromMap(setThinkingAgents, m.sender_id)
        removeFromMap(setTypingAgents, m.sender_id)
      }
    } else if (msg.type === 'ai_thinking') {
      const d = msg.data
      if (d.trigger === 'auto') return
      if (!isMessageForThisConversation(d, conversationType, conversationId)) return
      addToMap(setThinkingAgents, d.agent_id, { name: d.agent_name, avatarUrl: d.agent_avatar_url || null })
    } else if (msg.type === 'ai_thinking_end') {
      const d = msg.data
      if (d.trigger === 'auto') return
      if (!isMessageForThisConversation(d, conversationType, conversationId)) return
      removeFromMap(setThinkingAgents, d.agent_id)
      removeFromMap(setTypingAgents, d.agent_id)
    } else if (msg.type === 'ai_typing') {
      const d = msg.data
      if (d.trigger === 'auto') return
      if (!isMessageForThisConversation(d, conversationType, conversationId)) return
      setTimeout(() => removeFromMap(setThinkingAgents, d.agent_id), 1500)
      addToMap(setTypingAgents, d.agent_id, { name: d.agent_name, avatarUrl: d.agent_avatar_url || null })
    } else if (msg.type === 'typing') {
      // 人类打字状态
      const d = msg.data
      if (!isMessageForThisConversation(d, conversationType, conversationId)) return
      if (d.is_typing) {
        setHumanTyping(prev => {
          const next = new Map(prev)
          next.set(d.sender_id, { name: d.username, avatarUrl: d.avatar_url || null })
          return next
        })
      } else {
        setHumanTyping(prev => {
          const next = new Map(prev)
          next.delete(d.sender_id)
          return next
        })
      }
    } else if (msg.type === 'announcement') {
      const d = msg.data
      if (d.group_id !== conversationId) return
      setMessages((prev) => [...prev, {
        id: -Date.now(),
        sender_type: 'system',
        sender_id: 0,
        sender_name: t('groupSettings.announcement'),
        content: d.content,
        reply_to: null,
        created_at: new Date().toISOString(),
      } as Message])
    } else if (msg.type === 'avatar_updated') {
      const d = msg as any
      const etype = d.entity_type
      const eid = d.entity_id
      const newUrl = d.avatar_url
      if (etype && eid && newUrl) {
        setMessages((prev) =>
          prev.map((m) =>
            m.sender_type === etype && m.sender_id === eid
              ? { ...m, sender_avatar_url: newUrl }
              : m,
          ),
        )
      }
    } else if (msg.type === 'dm_notification' || msg.type === 'unread_update') {
      window.dispatchEvent(new CustomEvent(CHAT_REFRESH_EVENT, { detail: msg }))
    }
  }, [conversationType, conversationId, t])

  const { connected, reconnecting, errors, sendMessage, sendTyping, clearErrors } = useWebSocket(
    conversationType, conversationId, { onMessage: handleMessage },
  )

  // 获取上传大小限制（缓存 5 分钟）
  useEffect(() => {
    const cached = sessionStorage.getItem('upload_limits')
    if (cached) {
      const parsed = JSON.parse(cached)
      if (Date.now() - parsed.ts < 300000) return // 缓存有效
    }
    api.get('/user/config/upload-limits').then((limits: any) => {
      sessionStorage.setItem('upload_limits', JSON.stringify({ ...limits, ts: Date.now() }))
    }).catch(() => {})
  }, [])

  // 切换对话 / 卸载时：清除输入中状态，避免对方看到残留的 typing 指示
  useEffect(() => {
    return () => {
      if (typingRef.current) {
        typingRef.current = false
        sendTyping(false)
      }
    }
  }, [conversationType, conversationId, sendTyping])

  // 稳定引用，配合 MessageBubble 的 React.memo 避免输入时重渲染消息列表
  const handleAvatarClick = useCallback((type: string, id: number, name: string, state?: string) => {
    setProfileCard({ type, id, name, state })
  }, [])

  // ============================================================
  // 消息加载器
  // ============================================================

  const loadMessages = useCallback(async (params: {
    before_id?: number
    after_id?: number
    mode: 'initial' | 'older' | 'newer'
  }) => {
    const { before_id, after_id, mode } = params
    // 避免 initial 模式重复设值（调用方已设过）
    if (mode !== 'initial') setLoadingState(mode)

    // 加载旧消息前记录当前滚动高度
    if (mode === 'older' && containerRef.current) {
      prevScrollHeight.current = containerRef.current.scrollHeight
    }

    try {
      const queryParams = new URLSearchParams()
      queryParams.set('limit', String(PAGE_SIZE))
      if (before_id) queryParams.set('before_id', String(before_id))
      if (after_id) queryParams.set('after_id', String(after_id))

      let fetched: Message[]
      if (conversationType === 'group') {
        fetched = await api.get<Message[]>(
          `/groups/${conversationId}/messages?${queryParams.toString()}`
        )
      } else {
        fetched = await api.get<Message[]>(
          `/dm/${conversationId}/messages?${queryParams.toString()}`
        )
      }

      const gotFullPage = fetched.length >= PAGE_SIZE

      // 更新 refs（避免 IntersectionObserver 依赖 messages 数组）
      if (fetched.length > 0) {
        newestIdRef.current = fetched[fetched.length - 1].id
        oldestIdRef.current = fetched[0].id
      }

      setMessages((prev) => {
        if (mode === 'older') {
          // 去重：fetched 可能在 prev 中已存在（竞态）
          const existingIds = new Set(prev.map((m) => m.id))
          const unique = fetched.filter((m) => !existingIds.has(m.id))
          return [...unique, ...prev]
        } else if (mode === 'newer') {
          // 游标 after_id 保证不重叠，但以防万一也去重
          const existingIds = new Set(prev.map((m) => m.id))
          const unique = fetched.filter((m) => !existingIds.has(m.id))
          return [...prev, ...unique]
        } else {
          return fetched
        }
      })

      if (mode === 'older') {
        setHasMoreBefore(gotFullPage)
        if (!gotFullPage) setFirstUnreadId(null)
        // 恢复滚动位置：旧消息插入头部后，补偿新增高度
        requestAnimationFrame(() => {
          if (containerRef.current && prevScrollHeight.current > 0) {
            const newHeight = containerRef.current.scrollHeight
            containerRef.current.scrollTop += (newHeight - prevScrollHeight.current)
            prevScrollHeight.current = 0
          }
        })
      } else if (mode === 'newer') {
        setHasMoreAfter(gotFullPage)
      } else {
        // initial
        setHasMoreBefore(gotFullPage)
        setHasMoreAfter(false)

        if (fetched.length > 0) {
          const key = `lastRead_${conversationType}_${conversationId}`
          const stored = localStorage.getItem(key)
          const lastReadId = stored ? parseInt(stored) : null

          if (lastReadId && lastReadId > 0) {
            // 上次已读过的对话：找第一条 > lastReadId 的消息作为"首个未读"
            const firstUnread = fetched.find(m => m.id > lastReadId)
            if (firstUnread) {
              setFirstUnreadId(firstUnread.id)
            }
            // 所有消息都已读 → firstUnreadId 保持 null
          } else if (gotFullPage) {
            // 首次访问且有更多历史消息 → 最旧那条作为未读边界
            setFirstUnreadId(fetched[0].id)
          }
          // 首次访问且消息 ≤ PAGE_SIZE → 全部可见，无需未读标记
        }
      }
    } catch (err) {
      console.error('加载消息失败:', err)
    } finally {
      setLoadingState(null)
    }
  }, [conversationId, conversationType])

  // ============================================================
  // 滚动辅助
  // ============================================================

  const scrollToBottom = useCallback((smooth = true) => {
    const el = containerRef.current
    if (!el) return
    isAutoScrolling.current = true
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
    setTimeout(() => { isAutoScrolling.current = false }, 500)
  }, [])

  const scrollToMessage = useCallback((messageId: number) => {
    const el = containerRef.current
    if (!el) return
    const msgEl = el.querySelector(`[data-message-id="${messageId}"]`)
    if (msgEl) {
      isAutoScrolling.current = true
      msgEl.scrollIntoView({ block: 'start', behavior: 'smooth' })
      setTimeout(() => { isAutoScrolling.current = false }, 500)
    }
  }, [])

  const handleJumpToUnread = useCallback(async () => {
    if (!firstUnreadId) return
    // 加载 firstUnreadId 之前的一页消息
    await loadMessages({ before_id: firstUnreadId, mode: 'older' })
    // 滚动到原来的 firstUnreadId 位置
    setTimeout(() => scrollToMessage(firstUnreadId), 200)
  }, [firstUnreadId, loadMessages, scrollToMessage])

  // ============================================================
  // 初始加载
  // ============================================================

  useEffect(() => {
    if (!conversationId) return
    setThinkingAgents(new Map())
    setTypingAgents(new Map())
    setMessages([])
    setHasMoreBefore(false)
    setHasMoreAfter(false)
    setFirstUnreadId(null)
    setShowJumpToUnread(false)
    setIsAtBottom(true)
    prevMessageCount.current = 0
    setLoadingState('initial')

    const init = async () => {
      try {
        if (conversationType === 'group') {
          api.post(`/groups/${conversationId}/read`)
            .then(() => {
              window.dispatchEvent(new CustomEvent(CHAT_REFRESH_EVENT, { detail: { type: 'unread_update' } }))
            })
            .catch(() => {})
          const membersData = await api.get(`/groups/${conversationId}/members`)
          setGroupMembers(membersData)
        }
        await loadMessages({ mode: 'initial' })
        // DM 消息加载同时标记已读，触发 sidebar 刷新未读计数
        if (conversationType === 'dm') {
          window.dispatchEvent(new CustomEvent(CHAT_REFRESH_EVENT, { detail: { type: 'unread_update' } }))
        }
      } catch (err) {
        console.error('初始化失败:', err)
      }
    }
    init()
  }, [conversationId, conversationType])

  // 初始加载后定位 + 立即保存已读位置（不等卸载，防止刷新时红线残留）
  useEffect(() => {
    if (loadingState === null && messages.length > 0 && prevMessageCount.current === 0) {
      prevMessageCount.current = messages.length
      // 立即保存已读位置：初始加载完成即视为用户已看到最新消息
      if (newestIdRef.current && conversationId) {
        const key = `lastRead_${conversationType}_${conversationId}`
        localStorage.setItem(key, String(newestIdRef.current))
      }
      setTimeout(() => {
        const container = containerRef.current
        if (!container) return
        if (firstUnreadId) {
          // 有更早的未读消息 → 将首个未读定位到视口顶部
          const msgEl = container.querySelector(`[data-message-id="${firstUnreadId}"]`)
          if (msgEl) {
            isAutoScrolling.current = true
            const containerRect = container.getBoundingClientRect()
            const msgRect = msgEl.getBoundingClientRect()
            container.scrollTop = container.scrollTop + msgRect.top - containerRect.top
            setTimeout(() => { isAutoScrolling.current = false }, 500)
          }
        } else if (container.scrollHeight > container.clientHeight) {
          // 无旧消息但内容溢出 → 滚到底部
          scrollToBottom(false)
        }
        // 内容不溢出 → 不滚动
      }, 100)
    }
  }, [loadingState, messages.length, firstUnreadId])

  // ============================================================
  // 共享哨兵 Hook：IntersectionObserver 用 ref 读取消息 ID，避免 messages 数组依赖
  // ============================================================

  function useSentinel(
    sentinelRef: React.RefObject<HTMLDivElement | null>,
    hasMore: boolean,
    direction: 'older' | 'newer',
  ) {
    useEffect(() => {
      const sentinel = sentinelRef.current
      if (!sentinel) return
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting && hasMore && !loadingState) {
            const cursorId = direction === 'older' ? oldestIdRef.current : newestIdRef.current
            if (cursorId) {
              loadMessages(
                direction === 'older'
                  ? { before_id: cursorId, mode: 'older' }
                  : { after_id: cursorId, mode: 'newer' }
              )
            }
          }
        },
        { root: containerRef.current, threshold: 0.1 }
      )
      observer.observe(sentinel)
      return () => observer.disconnect()
    }, [hasMore, loadingState, direction])
  }

  useSentinel(topSentinelRef, hasMoreBefore, 'older')
  useSentinel(bottomSentinelRef, hasMoreAfter, 'newer')

  // ============================================================
  // 滚动监听：isAtBottom + showJumpToUnread（使用 rAF 节流 DOM 查询）
  // ============================================================

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let rafId = 0
    const handleScroll = () => {
      if (isAutoScrolling.current) return
      if (rafId) return // 上一帧的 DOM 查询尚未执行，跳过
      rafId = requestAnimationFrame(() => {
        rafId = 0
        const { scrollTop, scrollHeight, clientHeight } = container
        const atBottom = scrollHeight - scrollTop - clientHeight < 80
        setIsAtBottom(atBottom)
        isAtBottomRef.current = atBottom

        if (firstUnreadId) {
          const msgEl = container.querySelector(`[data-message-id="${firstUnreadId}"]`)
          const visible = msgEl
            ? msgEl.getBoundingClientRect().bottom >= container.getBoundingClientRect().top
            : false
          // 仅值变化时才触发渲染
          if (visible !== showJumpToUnreadRef.current) {
            showJumpToUnreadRef.current = !visible
            setShowJumpToUnread(!visible)
          }
        }
      })
    }
    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      container.removeEventListener('scroll', handleScroll)
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [firstUnreadId])

  // ============================================================
  // @提及逻辑（仅群聊）
  // ============================================================

  const mentionFiltered = mentionQuery
    ? groupMembers.filter((m) => m.name.toLowerCase().includes(mentionQuery.toLowerCase()))
    : groupMembers

  const detectMention = (value: string, cursorPos: number) => {
    if (conversationType === 'dm') return
    const beforeCursor = value.slice(0, cursorPos)
    const atIdx = beforeCursor.lastIndexOf('@')
    if (atIdx === -1) { setMentionActive(false); return }
    const prev = atIdx > 0 ? beforeCursor[atIdx - 1] : ''
    const allowed = prev === '' || prev === ' ' || /[，。！？、；：""【】（）]/.test(prev)
    if (!allowed) { setMentionActive(false); return }
    const query = beforeCursor.slice(atIdx + 1, cursorPos)
    if (query.includes(' ')) { setMentionActive(false); return }
    setMentionQuery(query)
    setMentionIdx(0)
    setMentionActive(true)
  }

  const insertMention = (name: string) => {
    const ta = textareaRef.current
    if (!ta) return
    const value = input
    const cursorPos = ta.selectionStart
    const beforeCursor = value.slice(0, cursorPos)
    const atIdx = beforeCursor.lastIndexOf('@')
    if (atIdx === -1) return
    const newBefore = beforeCursor.slice(0, atIdx) + '@' + name + ' '
    const newValue = newBefore + value.slice(cursorPos)
    setInput(newValue)
    setMentionActive(false)
    requestAnimationFrame(() => {
      ta.focus()
      const newPos = newBefore.length
      ta.setSelectionRange(newPos, newPos)
    })
  }

  // 文件上传处理
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    // 从后端获取上传大小限制（缓存 5 分钟）
    let MAX_FILE_MB = 32
    try {
      const cached = sessionStorage.getItem('upload_limits')
      if (cached) {
        const parsed = JSON.parse(cached)
        if (Date.now() - parsed.ts < 300000) {
          MAX_FILE_MB = parsed.upload_max_size_mb || 32
        }
      }
    } catch {}

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      if (file.size > MAX_FILE_MB * 1024 * 1024) {
        alert(`文件「${file.name}」超出 ${MAX_FILE_MB}MB 上传限制`)
        continue
      }
      const tempId = `att_${Date.now()}_${i}`
      const newAtt: PendingAttachment = {
        id: tempId,
        file,
        name: file.name,
        size: file.size,
        mime_type: file.type || 'application/octet-stream',
        uploading: true,
      }
      setPendingAttachments(prev => [...prev, newAtt])
      setUploadingCount(c => c + 1)

      try {
        const result = await api.upload('/fs/upload-attachment', file)
        setPendingAttachments(prev =>
          prev.map(a => a.id === tempId
            ? { ...a, file: null, file_id: result.file_id, path: result.path, uploading: false }
            : a
          )
        )
        setUploadingCount(c => c - 1)
      } catch (err: any) {
        setPendingAttachments(prev =>
          prev.map(a => a.id === tempId
            ? { ...a, uploading: false, error: err.message || t('chat.uploadFailed') }
            : a
          )
        )
        setUploadingCount(c => c - 1)
      }
    }
    // 清空 input 以便重复选择同一文件
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeAttachment = (tempId: string) => {
    setPendingAttachments(prev => prev.filter(a => a.id !== tempId))
  }

  const handleSend = () => {
    if (!input.trim() && pendingAttachments.length === 0) return
    if (!conversationId) return

    // 检查是否有未上传完的文件
    const stillUploading = pendingAttachments.some(a => a.uploading)
    if (stillUploading) return

    // 检查是否有上传失败的文件
    const hasErrors = pendingAttachments.some(a => a.error)
    if (hasErrors) return

    // 收集已上传完成的附件
    const readyAttachments = pendingAttachments
      .filter(a => a.file_id)
      .map(a => ({
        file_id: a.file_id!,
        path: a.path || '',
        name: a.name,
        size: a.size,
        mime_type: a.mime_type,
      }))

    sendMessage(input.trim(), undefined, readyAttachments.length > 0 ? readyAttachments : undefined)
    setInput('')
    // 发送后清除输入中状态
    if (typingRef.current) {
      typingRef.current = false
      sendTyping(false)
    }
    localStorage.removeItem(`draft_${conversationType}_${conversationId}`)
    setPendingAttachments([])
    setMentionActive(false)
    window.dispatchEvent(new CustomEvent(CHAT_REFRESH_EVENT, { detail: { type: 'message_sent' } }))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (mentionActive && mentionFiltered.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setMentionIdx((prev) => (prev + 1) % mentionFiltered.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setMentionIdx((prev) => (prev - 1 + mentionFiltered.length) % mentionFiltered.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); insertMention(mentionFiltered[mentionIdx].name); return }
      if (e.key === 'Escape') { e.preventDefault(); setMentionActive(false); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const isOwnMessage = (msg: Message) => {
    return msg.sender_type === 'human' && msg.sender_id === user?.id
  }

  // ============================================================
  // 渲染
  // ============================================================

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
      {/* 重连提示条 */}
      {reconnecting && (
        <div className="absolute top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-amber-500/15 border-b border-amber-500/20 text-amber-400 px-4 py-1.5 text-xs font-medium backdrop-blur-sm">
          <Loader2 size={12} className="animate-spin" />
          {t('chat.reconnecting')}
        </div>
      )}

      {/* 错误 Toast */}
      {errors.length > 0 && (
        <div className="absolute top-4 right-4 z-50 space-y-1 max-w-sm">
          {errors.map((err) => (
            <div
              key={err.timestamp}
              className="flex items-start gap-2 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl px-3 py-2 text-sm shadow-lg shadow-black/20"
            >
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <span className="flex-1">{err.message}</span>
              <button onClick={clearErrors} className="shrink-0 text-rose-400/60 hover:text-rose-400">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ↑ 跳至首个未读消息 */}
      {showJumpToUnread && firstUnreadId && (
        <button
          onClick={handleJumpToUnread}
          className="absolute top-3 right-4 z-40 flex items-center gap-1.5 px-3 py-1.5 bg-primary-500/90 hover:bg-primary-500 text-white text-xs font-medium rounded-full shadow-lg shadow-primary-500/30 backdrop-blur-sm transition-all duration-200"
        >
          <ArrowUp size={14} />
          {t('chat.jumpToFirstUnread')}
        </button>
      )}

      {/* 消息列表 */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-4 py-4 bg-canvas relative"
      >
        {/* 顶部哨兵（加载更旧消息的触发器） */}
        <div ref={topSentinelRef} className="h-1" />

        {/* 顶部加载指示器 */}
        {loadingState === 'older' && (
          <div className="flex items-center justify-center py-3">
            <Loader2 className="animate-spin text-textMuted" size={16} />
          </div>
        )}

        {/* 无更多旧消息提示 */}
        {!hasMoreBefore && messages.length > 0 && (
          <div className="text-center text-[10px] text-textMuted py-2 select-none">
            {t('chat.beginningOfChat')}
          </div>
        )}

        {/* 初始加载 */}
        {loadingState === 'initial' ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="animate-spin text-textMuted" size={24} />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-textMuted text-sm">
            {conversationType === 'dm' ? t('chat.startDMConversation') : t('chat.startGroupConversation')}
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              data-message-id={msg.id}
              ref={msg.id === firstUnreadId ? firstUnreadRef : undefined}
            >
              {/* 未读分隔线（在 firstUnreadId 消息上方） */}
              {msg.id === firstUnreadId && hasMoreBefore && (
                <div className="flex items-center gap-2 my-3 select-none">
                  <div className="flex-1 h-px bg-rose-500/30" />
                  <span className="text-[10px] font-medium text-rose-400 whitespace-nowrap">{t('chat.newMessages')}</span>
                  <div className="flex-1 h-px bg-rose-500/30" />
                </div>
              )}
              <MessageBubble
                senderName={msg.sender_name || `${msg.sender_type}:${msg.sender_id}`}
                senderAvatarUrl={msg.sender_avatar_url}
                content={msg.content}
                isMine={isOwnMessage(msg)}
                createdAt={msg.created_at}
                senderType={msg.sender_type}
                senderId={msg.sender_id}
                state={msg.sender_state}
                sourcePublicId={msg.source_public_id}
                attachments={msg.attachments}
                messageType={msg.message_type}
                onAvatarClick={handleAvatarClick}
              />
            </div>
          ))
        )}

        {/* 底部活动状态栏：合并 AI 思考/输入 + 人类打字 */}
        <ActivityBar users={activityUsers} />

        {/* 底部加载指示器 */}
        {loadingState === 'newer' && (
          <div className="flex items-center justify-center py-3">
            <Loader2 className="animate-spin text-textMuted" size={16} />
          </div>
        )}

        {/* 底部哨兵（加载更新消息的触发器） */}
        <div ref={bottomSentinelRef} className="h-1" />
      </div>

      {/* ↓ 回到底部浮动按钮 */}
      {!isAtBottom && messages.length > 0 && (
        <div className="absolute bottom-20 right-6 z-40">
          <button
            onClick={() => scrollToBottom(true)}
            className="flex items-center justify-center w-9 h-9 bg-elevated border border-border rounded-full shadow-lg shadow-black/20 text-textSecondary hover:text-textPrimary hover:bg-surface transition-all duration-200"
            title={t('chat.scrollToBottom')}
          >
            <ArrowDown size={16} />
          </button>
        </div>
      )}

      {/* 输入框 */}
      <div className="p-3 bg-surface border-t border-border relative">
        {/* 附件预览列表 */}
        {pendingAttachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {pendingAttachments.map((att) => (
              <div
                key={att.id}
                className={`relative group flex items-center gap-2 pl-3 pr-1 py-1.5 rounded-xl text-xs border transition-colors ${
                  att.error
                    ? 'bg-rose-500/10 border-rose-500/30'
                    : att.uploading
                    ? 'bg-canvas border-border animate-pulse'
                    : 'bg-canvas border-border hover:bg-elevated'
                }`}
              >
                <FileIcon size={14} className={att.error ? 'text-rose-400' : att.uploading ? 'text-textMuted' : 'text-primary-400'} />
                <span className={`max-w-[120px] truncate ${att.error ? 'text-rose-400' : 'text-textSecondary'}`}>
                  {att.name}
                </span>
                {att.uploading && (
                  <Loader2 size={12} className="animate-spin text-textMuted shrink-0" />
                )}
                {att.error && (
                  <span className="text-rose-400 text-[10px] shrink-0" title={att.error || t('chat.uploadFailed')}>{t('chat.uploadFailed')}</span>
                )}
                <span className="text-textMuted text-[10px] shrink-0">
                  {(att.size / 1024).toFixed(0)}KB
                </span>
                <button
                  onClick={() => removeAttachment(att.id)}
                  className="p-0.5 rounded-lg hover:bg-rose-500/10 text-textMuted hover:text-rose-400 transition-colors"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* @提及 自动补全下拉 */}
        {mentionActive && mentionFiltered.length > 0 && (
          <div className="absolute bottom-full left-3 right-3 mb-1 bg-elevated border border-border rounded-xl shadow-2xl shadow-black/20 z-50 max-h-48 overflow-y-auto">
            {mentionFiltered.map((m, i) => (
              <button
                key={`${m.type}:${m.id}`}
                onClick={() => insertMention(m.name)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                  i === mentionIdx
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300'
                    : 'text-textPrimary hover:bg-elevated'
                }`}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${getStateDotColor(m.state)}`} />
                <span className="font-medium">{m.name}</span>
                <span className="text-textMuted text-xs ml-auto">
                  {m.type === 'ai' ? <><Bot size={12} className="inline" /> AI</> : <User size={12} className="inline" />}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* 文件上传按钮 */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
            accept="image/*,.pdf,.doc,.docx,.txt,.md,.json,.csv,.zip,.tar,.gz"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2.5 rounded-xl border border-border bg-canvas text-textMuted hover:text-textPrimary hover:border-primary-500/30 hover:bg-elevated transition-colors"
            title={t('chat.addAttachment')}
          >
            <Paperclip size={18} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              const pos = e.target.selectionStart
              detectMention(e.target.value, pos)
              // 只在 空→非空 / 非空→空 时发送 typing 状态变更
              const nowTyping = e.target.value.length > 0
              if (nowTyping !== typingRef.current) {
                typingRef.current = nowTyping
                sendTyping(nowTyping)
              }
            }}
            onKeyUp={(e) => {
              if (mentionActive && ['ArrowUp','ArrowDown','Enter','Tab','Escape'].includes(e.key)) return
              if (['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) {
                const ta = e.currentTarget
                detectMention(ta.value, ta.selectionStart)
              }
            }}
            onClick={(e) => {
              const ta = e.currentTarget
              setTimeout(() => detectMention(ta.value, ta.selectionStart), 0)
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              // 仅手机端：键盘弹出时确保输入框紧贴在键盘上方
              if (window.innerWidth >= 768) return
              const timer = setTimeout(() => {
                textareaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
              }, 400)
              // 失焦时清除未触发的定时器，防止累积
              const onBlur = () => {
                clearTimeout(timer)
                textareaRef.current?.removeEventListener('blur', onBlur)
              }
              textareaRef.current?.addEventListener('blur', onBlur, { once: true })
            }}
            placeholder={conversationType === 'dm' ? t('chat.dmInputPlaceholder') : t('chat.groupInputPlaceholder')}
            rows={1}
            className="flex-1 min-w-0 resize-none rounded-xl border border-border bg-canvas px-4 py-2.5 text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/30 transition-shadow"
          />
          <button
            onClick={handleSend}
            disabled={(!input.trim() && pendingAttachments.length === 0) || uploadingCount > 0 || pendingAttachments.some(a => a.error)}
            title={
              uploadingCount > 0
                ? t('chat.uploadingFiles').replace('{count}', String(uploadingCount))
                : pendingAttachments.some(a => a.error)
                ? t('chat.uploadErrorRemove')
                : pendingAttachments.length > 0 && !input.trim()
                ? t('chat.sendAttachment')
                : ''
            }
            className="p-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg shadow-primary-500/20"
          >
            <Send size={18} />
          </button>
        </div>
      </div>

      {/* 资料卡 */}
      {profileCard && (
        <ProfileCard
          entityType={profileCard.type as 'human' | 'ai'}
          entityId={profileCard.id}
          entityName={profileCard.name}
          state={profileCard.state}
          onClose={() => setProfileCard(null)}
        />
      )}
    </div>
  )
}
