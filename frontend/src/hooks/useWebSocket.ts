import { useEffect, useRef, useState, useCallback } from 'react'
import { getInstanceUrl } from '../utils/platform'
import { safeParse } from '../utils/result'

export interface WebSocketMessage {
  type: string
  data?: any
  code?: string
  message?: string
  tool_call_id?: string
  conversation_type?: string
}

interface WsError {
  code: string
  message: string
  tool_call_id?: string
  timestamp: number
}

/** 重连参数 */
const RECONNECT_BASE_MS = 1000      // 首次重连等待 1s
const RECONNECT_MAX_MS = 30_000     // 最大 30s
const RECONNECT_MULTIPLIER = 2      // 每次翻倍

/** 计算重连延迟：指数退避 + ±30% 抖动 */
function calcReconnectDelay(retryCount: number): number {
  const base = Math.min(
    RECONNECT_BASE_MS * Math.pow(RECONNECT_MULTIPLIER, retryCount),
    RECONNECT_MAX_MS,
  )
  const jitter = base * 0.3 * (Math.random() * 2 - 1)
  return Math.round(base + jitter)
}

export function useWebSocket(
  conversationType: 'group' | 'dm',
  conversationId: number | string | null,
  opts?: { onMessage?: (msg: WebSocketMessage) => void },
) {
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [errors, setErrors] = useState<WsError[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  // 消息回调 ref — 由消费者设置，WebSocket onmessage 时调用
  // 用 ref 而非直接依赖，避免 connect useCallback 随回调变化而重建
  const onMessageRef = useRef<((msg: WebSocketMessage) => void) | undefined>(opts?.onMessage)
  onMessageRef.current = opts?.onMessage

  // 重连控制 ref
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  /** 建立 WebSocket 连接，返回清理函数 */
  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token')
    if (!token) return () => {}

    const instanceUrl = getInstanceUrl()
    const protocol = instanceUrl.startsWith('https') ? 'wss:' : 'ws:'
    const host = instanceUrl.replace(/^https?:\/\//, '')
    const url = `${protocol}//${host}/ws?token=${token}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close()
        return
      }
      setConnected(true)
      setReconnecting(false)
      retryCountRef.current = 0

      // 订阅当前对话
      if (conversationType === 'group') {
        ws.send(JSON.stringify({ type: 'subscribe', group_id: conversationId }))
      } else {
        ws.send(JSON.stringify({ type: 'subscribe', session_id: conversationId }))
      }
    }

    ws.onmessage = (event) => {
      const result = safeParse<WebSocketMessage>(event.data)
      if (!result.ok) {
        console.warn('WebSocket 收到无效 JSON:', (event.data as string).slice(0, 100))
        return
      }
      const msg = result.value

        // 错误事件：自动消失的 toast
        if (msg.type === 'error') {
          const wsError: WsError = {
            code: msg.code || 'UNKNOWN',
            message: msg.message || 'Unknown error',
            tool_call_id: msg.tool_call_id,
            timestamp: Date.now(),
          }
          setErrors((prev) => [...prev.slice(-9), wsError])
          setTimeout(() => {
            setErrors((prev) => prev.filter((e) => e.timestamp !== wsError.timestamp))
          }, 5000)
        }

        // v0.9.0: 余额弹窗 → 全局自定义事件（BalancePromptModal 监听）
        if (msg.type === 'balance_prompt' && msg.data) {
          window.dispatchEvent(new CustomEvent('balance-prompt', { detail: msg.data }))
        }

        // 分发给消费者回调（ChatView 注册）
        // 无需 flushSync：消费者内部全部使用函数式 setState(prev => ...)，
        // 即使 React 18 批处理合并多次调用，prev 链式叠加也不会丢失消息。
        onMessageRef.current?.(msg)
    }

    ws.onclose = (event) => {
      // 1000=正常关闭, 1001=离开页面 → 不重连
      const cleanClose = event.code === 1000 || event.code === 1001
      if (!mountedRef.current || cleanClose) {
        setConnected(false)
        setReconnecting(false)
        return
      }
      // 非正常关闭 → 调度重连
      setConnected(false)
      scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose 会紧接着触发，连接状态由 onclose 统一处理
    }

    return () => {
      // 清理：干净关闭，不触发重连
      ws.onclose = null
      ws.close(1000)
      wsRef.current = null
    }
  }, [conversationType, conversationId])

  // ── 调度重连 ──
  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return

    // 取消已有重连定时器
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }

    setReconnecting(true)
    retryCountRef.current += 1

    const delay = calcReconnectDelay(retryCountRef.current)
    console.log(
      `🔌 WebSocket 将在 ${(delay / 1000).toFixed(1)}s 后重连（第 ${retryCountRef.current} 次）`,
    )

    retryTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return
      connect()
      // 如果 connect 同步失败（如 token 丢失），清除重连状态
      if (!wsRef.current) setReconnecting(false)
    }, delay)
  }, [connect])

  // ── 浏览器恢复在线时立即重连 ──
  useEffect(() => {
    const handleOnline = () => {
      if (!mountedRef.current) return
      if (
        wsRef.current?.readyState !== WebSocket.OPEN &&
        wsRef.current?.readyState !== WebSocket.CONNECTING
      ) {
        console.log('🌐 浏览器恢复在线，立即重连 WebSocket')
        // 取消正在等待的重连定时器
        if (retryTimerRef.current !== null) {
          clearTimeout(retryTimerRef.current)
          retryTimerRef.current = null
        }
        retryCountRef.current = 0
        connect()
        if (!wsRef.current) setReconnecting(false)
      }
    }

    window.addEventListener('online', handleOnline)
    return () => window.removeEventListener('online', handleOnline)
  }, [connect])

  // ── 主 effect：对话参数变化时重连 ──
  useEffect(() => {
    mountedRef.current = true

    // 对话切换 → 重置状态
    clearRetryTimer()
    retryCountRef.current = 0
    setConnected(false)
    setReconnecting(false)

    if (!conversationId) {
      return () => { mountedRef.current = false }
    }

    const token = localStorage.getItem('access_token')
    if (!token) {
      return () => { mountedRef.current = false }
    }

    const cleanup = connect()

    return () => {
      mountedRef.current = false
      clearRetryTimer()
      if (cleanup) cleanup()
    }
  }, [conversationType, conversationId, connect])

  const sendMessage = useCallback((content: string, replyTo?: number, attachments?: Array<{file_id: number, name: string, size: number, mime_type: string}>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload: any = {
        type: 'send',
        content,
        reply_to: replyTo ?? null,
      }
      if (attachments && attachments.length > 0) {
        payload.attachments = attachments
      }
      if (conversationType === 'group') {
        payload.group_id = conversationId
      } else {
        payload.session_id = conversationId
      }
      wsRef.current.send(JSON.stringify(payload))
    }
  }, [conversationType, conversationId])

  const sendTyping = useCallback((isTyping: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload: any = {
        type: 'typing',
        is_typing: isTyping,
      }
      if (conversationType === 'group') {
        payload.group_id = conversationId
      } else {
        payload.session_id = conversationId
      }
      wsRef.current.send(JSON.stringify(payload))
    }
  }, [conversationType, conversationId])

  const clearErrors = useCallback(() => setErrors([]), [])

  // 内联工具函数（仅操作 ref，不需要 useCallback）
  function clearRetryTimer() {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }

  return {
    connected,
    reconnecting,
    errors,
    sendMessage,
    sendTyping,
    clearErrors,
  }
}
