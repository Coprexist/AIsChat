import { memo, useState, useRef, useCallback, useMemo, forwardRef, useImperativeHandle, useEffect } from 'react'
import { Send, Plus, X, ChevronRight, Brain, ArrowDown, FileText, Search, Globe, Terminal, Package, Clock, Wrench, Eraser, Pin, ChevronDown } from 'lucide-react'
import MarkdownContent from './shared/MarkdownContent'
import { useWorldChat, WORLD_COMMANDS } from '../hooks/useWorldChat'
import { useT } from '../i18n/I18nContext'

// 工具气泡图标：按摘要内容关键词映射（后端文本不带 emoji，图标由前端渲染）
function toolIcon(content: string) {
  const s = content || ''
  if (s.includes('接口文档')) return <FileText size={12} />
  if (s.includes('记住') || s.includes('记忆') || s.includes('检索')) return <Brain size={12} />
  if (s.includes('搜索')) return <Search size={12} />
  if (s.includes('获取') || s.includes('http')) return <Globe size={12} />
  if (s.includes('世界代码')) return <Terminal size={12} />
  if (s.includes('压缩')) return <Package size={12} />
  if (s.includes('清空')) return <Eraser size={12} />
  if (s.includes('排队')) return <Clock size={12} />
  return <Wrench size={12} />
}

/** 工具气泡（2026-08-13）：running/update 单行状态；done 的 summary 过长时默认 2 行 + 展开/收起 */
function ToolBubble({ label, error, icon }: { label: string; error?: boolean; icon: React.ReactNode }) {
  const [expanded, setExpanded] = useState(false)
  // 长判定：字符多或有换行（多行摘要）才折叠
  const long = label.length > 90 || label.includes('\n')
  const collapsible = long && !expanded
  return (
    <div className={`world-msg max-w-[90%] mx-auto text-[11px] rounded-lg overflow-hidden ${error ? 'text-rose-400 bg-rose-500/10 border border-rose-500/20' : 'text-mint-400 bg-mint-400/10 border border-mint-400/20'}`}>
      <div
        className={`px-2 py-1 text-center ${collapsible ? 'cursor-pointer select-none' : ''}`}
        onClick={() => collapsible && setExpanded(true)}
      >
        {collapsible ? (
          <div>
            {/* 折叠：2 行 + 渐变淡化，与思考气泡一致 */}
            <div className="relative">
              <div className="flex items-start justify-center gap-1.5">
                <span className="shrink-0 mt-0.5">{icon}</span>
                <span className="min-w-0 line-clamp-2 text-left whitespace-pre-wrap">{label}</span>
              </div>
              <div className="absolute inset-x-0 bottom-0 h-5 bg-gradient-to-t from-mint-400/10 to-transparent pointer-events-none" />
            </div>
            <span className="inline-flex items-center gap-0.5 text-[10px] opacity-70">
              <ChevronDown size={10} /> 展开
            </span>
          </div>
        ) : (
          <div className="flex items-start justify-center gap-1.5">
            <span className="shrink-0 mt-0.5">{icon}</span>
            <span className="min-w-0 whitespace-pre-wrap text-left">{label}</span>
            {long && (
              <button
                className="shrink-0 text-[10px] opacity-70 hover:opacity-100 flex items-center gap-0.5"
                onClick={(e) => { e.stopPropagation(); setExpanded(false) }}
              >
                <ChevronDown size={10} className="rotate-180" /> 收起
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** 思考气泡（2026-08-13）：独立展示，默认 2 行 + 底部渐变淡化，点击展开看全部 */
function ReasoningBubble({ text, preview }: { text: string; preview?: string }) {
  const [expanded, setExpanded] = useState(false)
  const t = useT()
  const bodyRef = useRef<HTMLDivElement>(null)
  // 展开时滚动到气泡顶部（内容开头）——否则视口停在底部，用户看到的是末尾，误以为折叠没消失
  const handleToggle = () => {
    setExpanded((v) => {
      if (!v) {
        requestAnimationFrame(() => bodyRef.current?.scrollTo({ top: 0 }))
      }
      return !v
    })
  }
  return (
    <div
      className="world-msg max-w-[90%] mx-auto cursor-pointer select-none text-[11px] text-textMuted bg-elevated/40 border border-border/50 rounded-lg overflow-hidden"
      onClick={handleToggle}
    >
      <div className="flex items-center gap-1 px-2 py-1 border-b border-border/30">
        <Brain size={11} className="shrink-0 text-textMuted" />
        <span className="shrink-0 text-[10px] text-textMuted">{t('world.reasoning') || '思考'}</span>
        <ChevronDown size={11} className={`ml-auto shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </div>
      {expanded ? (
        <div ref={bodyRef} className="px-2 py-1.5 whitespace-pre-wrap max-h-72 overflow-y-auto">{text}</div>
      ) : (
        <div className="relative">
          <div className="px-2 py-1.5 whitespace-pre-wrap">{preview || text.split('\n').slice(0, 2).join('\n')}</div>
          <div className="absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-elevated/90 to-transparent pointer-events-none" />
        </div>
      )}
    </div>
  )
}

export interface WorldChatHandle {
  forceScrollToBottom: () => void
  unreadCount: number
  isInterrupted: boolean
  lastAiMsgId: number | null
}

interface WorldChatPanelProps {
  wid: number
  onRefresh: () => void
  onMsg: (msg: string) => void
  /** 未读计数变化回调（父组件需要响应式更新标题栏徽章等） */
  onUnreadCountChange?: (count: number) => void
  /** 群视界机器人昵称（气泡标签用；缺省回退「世界 AI」） */
  creatorName?: string
}

/**
 * 世界聊天面板（独立自包含组件）
 * - 内部调用 useWorldChat 管理所有聊天状态
 * - 所有聊天相关 UI 逻辑集中在此
 * - 通过 forwardRef 暴露 forceScrollToBottom 等接口给父组件
 * - 通过 onUnreadCountChange 回调通知父组件未读变化
 * - 打字/消息更新仅重渲染此组件，不触发父组件
 */
const WorldChatPanel = memo(forwardRef<WorldChatHandle, WorldChatPanelProps>(({ wid, onRefresh, onMsg, onUnreadCountChange, creatorName }, ref) => {
  const t = useT()
  // ── 内部管理所有聊天状态 ──
  const chat = useWorldChat({ wid, onRefresh, onMsg })

  // ── 计算派生状态 ──
  const isInterrupted = useMemo(() => {
    for (let i = chat.chatMsgs.length - 1; i >= 0; i--) {
      const m = chat.chatMsgs[i]
      if (m.role === 'ai') return String(m.content || '').includes('对话中断')
      if (m.role === 'user') continue
    }
    return false
  }, [chat.chatMsgs])

  const lastAiMsgId = useMemo(() => {
    for (let i = chat.chatMsgs.length - 1; i >= 0; i--) {
      if (chat.chatMsgs[i].role === 'ai') return chat.chatMsgs[i].id
    }
    return null
  }, [chat.chatMsgs])

  // ── 暴露给父组件的接口 ──
  useImperativeHandle(ref, () => ({
    forceScrollToBottom: chat.forceScrollToBottom,
    unreadCount: chat.unreadCount,
    isInterrupted,
    lastAiMsgId,
  }), [chat.forceScrollToBottom, chat.unreadCount, isInterrupted, lastAiMsgId])

  // ── 通知父组件未读计数变化 ──
  useEffect(() => {
    onUnreadCountChange?.(chat.unreadCount)
  }, [chat.unreadCount, onUnreadCountChange])

  // ── 会话列表下拉 ──
  const [sessionOpen, setSessionOpen] = useState(false)

  // ── 本地输入状态（打字时只有此组件重渲染） ──
  const [localInput, setLocalInput] = useState('')
  const localInputRef = useRef('')

  // ── 本地命令检测状态 ──
  const [localCmdActive, setLocalCmdActive] = useState(false)
  const [localCmdQuery, setLocalCmdQuery] = useState('')
  const [localCmdIdx, setLocalCmdIdx] = useState(0)
  const localCmdFiltered = useMemo(() =>
    localCmdQuery ? WORLD_COMMANDS.filter((c) => c.cmd.startsWith('/' + localCmdQuery)) : WORLD_COMMANDS
  , [localCmdQuery])

  const clearLocalInput = useCallback(() => {
    setLocalInput('')
    localInputRef.current = ''
    setLocalCmdActive(false)
  }, [])

  const handleSubmit = useCallback((text: string) => {
    const t = text.trim()
    if (!t) return
    chat.submitText(t)
    clearLocalInput()
  }, [chat, clearLocalInput])

  const handleCmdSelect = useCallback((cmd: string) => {
    chat.submitText(cmd)
    clearLocalInput()
  }, [chat, clearLocalInput])

  const handleInsertSuggestion = useCallback((q: string) => {
    const next = localInputRef.current ? localInputRef.current + ' ' + q : q
    localInputRef.current = next
    setLocalInput(next)
    requestAnimationFrame(() => {
      const ta = chat.chatInputRef.current
      if (ta) {
        ta.focus()
        const pos = next.length
        ta.setSelectionRange(pos, pos)
      }
    })
  }, [chat])

  // ── 渲染消息列表 ──
  const renderMessage = (m: typeof chat.chatMsgs[number], msgIndex: number) => {
    const isLastAi = m.role === 'ai' && m.id === lastAiMsgId
    // 正文上方紧跟思考气泡（上一条 note 且无正文）→ 省略「世界 AI」标签（思考已标识 AI 身份）
    const prevIsReasoning = msgIndex > 0
      && chat.chatMsgs[msgIndex - 1].role === 'note'
      && !chat.chatMsgs[msgIndex - 1].content
      && !!chat.chatMsgs[msgIndex - 1].reasoning

    if (m.role === 'tool') {
      // 工具状态气泡：running（正在执行 XX）→ update（进度）→ done（完成）
      // 结构化字段走 i18n（tool:toolName.{name} + tool:tool.{status} 模板插值）；旧格式直接显示 content
      let label = m.content
      if (m.tool_name) {
        const nameKey = `tool:toolName.${m.tool_name}`
        const nameLabel = t(nameKey)
        const toolName = nameLabel !== nameKey ? nameLabel : m.tool_name
        if (m.tool_status === 'running') {
          label = t('tool:tool.running', { name: `${toolName}${m.tool_args ? `：${m.tool_args}` : ''}` })
        } else if (m.tool_status === 'update') {
          label = m.content || t('tool:tool.update', { summary: `${toolName}…` })
        } else {
          label = m.content || t('tool:tool.done', { summary: `${toolName} ${m.error ? '执行失败' : '执行完成'}` })
        }
      }
      return (
        <ToolBubble
          key={m.id}
          label={label}
          error={m.error ?? m.is_error}
          icon={toolIcon(m.content)}
        />
      )
    }

    // 思考独立气泡（2026-08-13）：只有思考没正文（note 且 content 空）——
    // 默认显示 2 行 + 底部渐变淡化，点击展开看全部
    if (m.role === 'note' && !m.content && m.reasoning) {
      return <ReasoningBubble key={m.id} text={m.reasoning} preview={m.reasoning_preview} />
    }

    return (
      <div key={m.id} className="space-y-2">
        <div className={`world-msg text-sm max-w-[90%] p-2 rounded-lg ${m.error ? 'bg-rose-500/10 border border-rose-500/30 text-rose-400' : m.role === 'user' ? 'bg-primary-500/20 ml-auto' : 'bg-elevated/80'}`}>
          <div className="text-[10px] text-textMuted mb-0.5">{m.error ? '错误' : m.role === 'user' ? (m.pending ? '我（排队中，发送后生效）' : '我') : (prevIsReasoning ? '' : (creatorName || '世界 AI'))}</div>
          {!m.error && (m.role === 'ai' || m.role === 'note') && !!m.reasoning && (
            <details className="group/details mb-1.5">
              <summary className="flex items-center gap-1 text-[10px] text-textMuted cursor-pointer select-none hover:text-textSecondary list-none [&::-webkit-details-marker]:hidden">
                <ChevronRight size={11} className="transition-transform group-open/details:rotate-90" />
                <Brain size={11} className="text-textMuted" />
                思考过程
              </summary>
              <div className="text-xs text-textMuted mt-1 whitespace-pre-wrap bg-elevated/70 rounded p-2">{m.reasoning}</div>
            </details>
          )}
          {m.content ? <MarkdownContent content={m.content} /> : m.role === 'ai' ? (
            m.reasoning ? (
              <span className="opacity-50 text-xs italic">
                {(() => { const r = m.reasoning.trim(); return r.length > 60 ? r.slice(-60) + '…' : r || '思考中…' })()}
              </span>
            ) : (
              <span className="inline-flex gap-0.5">
                <span className="w-1 h-1 bg-primary-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1 h-1 bg-primary-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1 h-1 bg-primary-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            )
          ) : null}
        </div>

        {/* 中断 → "你可以：继续" */}
        {isLastAi && isInterrupted && !chat.chatSending && !chat.chatProcessing && (
          <div className="space-y-1.5 pl-1 w-full max-w-[420px]">
            <div className="text-[10px] text-textMuted">你可以：</div>
            <div className="flex items-stretch rounded-lg bg-elevated border border-border overflow-hidden w-full">
              <button
                onClick={() => handleSubmit('继续')}
                className="flex-1 min-w-0 px-2.5 py-1.5 text-left text-xs text-textSecondary hover:bg-primary-500/20 hover:text-primary-300 transition-colors truncate"
                title="继续之前的工作"
              >继续之前的工作</button>
              <div className="w-px bg-border shrink-0" />
              <button
                onClick={(e) => { e.stopPropagation(); handleSubmit('继续') }}
                className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                title="发送"
              ><Send size={11} /></button>
            </div>
          </div>
        )}

        {/* 建议列表 */}
        {(isLastAi || chat.chatMsgs.length === 0) && !isInterrupted && chat.suggestions.length > 0 && !chat.chatSending && !chat.chatProcessing && (
          <div className="space-y-1.5 pl-1 w-full max-w-[420px]">
            <div className="text-[10px] text-textMuted">你可以：</div>
            {chat.suggestions.map((q, i) => (
              <div key={i} className="flex items-stretch rounded-lg bg-elevated border border-border overflow-hidden w-full">
                <button
                  onClick={() => handleSubmit(q)}
                  className="flex-1 min-w-0 px-2.5 py-1.5 text-left text-xs text-textSecondary hover:bg-primary-500/20 hover:text-primary-300 transition-colors truncate"
                  title={q}
                >{q}</button>
                <div className="w-px bg-border shrink-0" />
                <button
                  onClick={(e) => { e.stopPropagation(); handleSubmit(q) }}
                  className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                  title="发送这条"
                ><Send size={11} /></button>
                <div className="w-px bg-border shrink-0" />
                <button
                  onClick={(e) => { e.stopPropagation(); handleInsertSuggestion(q) }}
                  className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                  title="插入到输入框（追加，不覆盖）"
                ><Plus size={12} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // ── 空状态建议 ──
  const renderEmptySuggestions = () => (
    <div className="text-center mt-8 space-y-3">
      <div className="text-xs text-textMuted">暂无消息，从下面开始探索：</div>
      {chat.suggestions.length > 0 && !chat.chatSending && !chat.chatProcessing && (
        <div className="flex flex-col items-center gap-1.5 w-full max-w-[420px]">
          {chat.suggestions.map((q, i) => (
            <div key={i} className="flex items-stretch rounded-lg bg-elevated border border-border overflow-hidden w-full">
              <button
                onClick={() => handleSubmit(q)}
                className="flex-1 min-w-0 px-2.5 py-1.5 text-left text-xs text-textSecondary hover:bg-primary-500/20 hover:text-primary-300 transition-colors truncate"
                title={q}
              >{q}</button>
              <div className="w-px bg-border shrink-0" />
              <button
                onClick={(e) => { e.stopPropagation(); handleSubmit(q) }}
                className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                title="发送这条"
              ><Send size={11} /></button>
              <div className="w-px bg-border shrink-0" />
              <button
                onClick={(e) => { e.stopPropagation(); handleInsertSuggestion(q) }}
                className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                title="插入到输入框（追加，不覆盖）"
              ><Plus size={12} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  // ── 命令下拉菜单 ──
  const renderCmdMenu = () => (
    <div className="absolute bottom-full left-3 mb-1 w-64 max-h-40 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
      {localCmdFiltered.map((c, i) => (
        <button
          key={c.cmd}
          className={`w-full text-left px-3 py-2 transition-colors ${i === localCmdIdx ? 'bg-primary-500/20 text-primary-400' : 'text-textPrimary hover:bg-hover'}`}
          onMouseDown={(e) => { e.preventDefault(); handleCmdSelect(c.cmd) }}
        >
          <span className="font-mono text-xs">{c.cmd}</span>
          <span className="block text-[10px] text-textMuted">{c.desc}</span>
        </button>
      ))}
    </div>
  )

  return (
    <>
      {/* 消息列表 */}
      <div ref={chat.chatListRef} className="flex-1 overflow-y-auto p-3 space-y-2 relative">
        {chat.chatLoadingOlder && <div className="text-[10px] text-textMuted text-center py-1">加载更早消息…</div>}
        {chat.chatMsgs.length === 0 ? renderEmptySuggestions() : chat.chatMsgs.map((m, i) => renderMessage(m, i))}

        {/* 回到底部 / 新消息按钮：不在底部（或未读>0，或列表不可滚动时给入口）才显示；可滚动且在底部隐藏
            sticky 固定在聊天列表视口右下角（输入区正上方）：列表滚动时不动，不随消息内容滚 */}
        {(!chat.isAtBottom || !chat.chatCanScroll || chat.unreadCount > 0) && (
          <div className="sticky bottom-3 flex justify-end pointer-events-none z-40">
            <button
              onClick={() => chat.scrollToBottom(true)}
              className={`pointer-events-auto flex items-center justify-center gap-1 px-3 h-8 rounded-full shadow-lg transition-all ${
                chat.unreadCount > 0
                  ? 'bg-rose-500 hover:bg-rose-400 text-white border border-rose-400 animate-bounce'
                  : 'bg-elevated border border-border text-textSecondary hover:text-textPrimary hover:bg-surface'
              }`}
              title="回到底部"
            >
              {chat.unreadCount > 0 ? (
                <>
                  <ArrowDown size={14} />
                  <span className="text-xs font-semibold">{chat.unreadCount} 条新消息</span>
                </>
              ) : (
                <ArrowDown size={14} />
              )}
            </button>
          </div>
        )}
      </div>

      {/* 会话工具条：当前会话 + 收藏 + 新对话 + 会话列表（/new 后对话保存可切回） */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-t border-border bg-surface/60 text-[10px] text-textMuted relative">
        <span className="truncate font-mono max-w-[180px] shrink-0" title={chat.currentSession}>{chat.currentSession === 'default' ? '默认会话' : chat.currentSession}</span>
        <button
          onClick={async () => { const p = await chat.togglePin(); if (!p && onMsg) onMsg('已取消收藏（收藏的会话不会被自动清理）') }}
          className={`shrink-0 p-1 rounded transition-colors ${chat.sessionList.find((s) => s.id === chat.currentSession)?.pinned ? 'text-amber-400 bg-amber-400/10' : 'hover:bg-elevated hover:text-textSecondary'}`}
          title={chat.sessionList.find((s) => s.id === chat.currentSession)?.pinned ? '取消收藏' : '收藏此会话（不被自动清理）'}
        >
          <Pin size={11} className={chat.sessionList.find((s) => s.id === chat.currentSession)?.pinned ? 'fill-current' : ''} />
        </button>
        <button
          onClick={() => chat.submitText('/new')}
          className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-elevated hover:text-textSecondary transition-colors"
          title="开新对话（旧对话保存）"
        ><Plus size={11} /> 新对话</button>
        <div className="flex-1" />
        <button
          onClick={() => setSessionOpen((v) => !v)}
          className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-elevated hover:text-textSecondary transition-colors"
        ><ChevronDown size={11} /> 会话列表（{chat.sessionList.length}）</button>
        {sessionOpen && chat.sessionList.length > 0 && (
          <div className="absolute bottom-full right-3 mb-1 w-72 max-h-56 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
            <div className="px-3 py-1.5 text-[10px] text-textMuted border-b border-border flex items-center gap-1">会话列表（点击切换；<Pin size={9} className="text-amber-400 fill-current" />=已收藏，不会被自动清理）</div>
            {chat.sessionList.map((s) => (
              <button
                key={s.id}
                onClick={async () => { if (await chat.switchSession(s.id)) setSessionOpen(false) }}
                className={`w-full flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-left border-b border-border/40 last:border-b-0 transition-colors ${s.id === chat.currentSession ? 'bg-primary-500/15 text-primary-300' : 'hover:bg-surface text-textSecondary'}`}
              >
                <span className="truncate flex-1 font-mono" title={s.id}>{s.id === 'default' ? '默认会话' : s.id}</span>
                <span className="shrink-0 flex items-center gap-1 text-textMuted">{s.pinned ? <Pin size={10} className="text-amber-400 fill-current" /> : ''}{s.id === chat.currentSession ? '当前' : ''}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="p-3 border-t border-border relative">
        {/* 排队消息（AI 处理中，输入框上方弹窗展示） */}
        {chat.pendingItems.length > 0 && (
          <div className="absolute bottom-full left-3 right-3 mb-1 max-h-32 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
            <div className="px-3 py-1.5 text-[10px] text-textMuted border-b border-border">
              AI 处理中，以下 {chat.pendingItems.length} 条排队（普通消息将插入下一轮 AI 思考，命令等本轮结束执行）
            </div>
            {chat.pendingItems.map((it, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-border/40 last:border-b-0">
                <span className={`truncate flex-1 ${it.kind === 'cmd' ? 'font-mono text-primary-400' : 'text-textPrimary'}`}>{it.text}</span>
                <span className="shrink-0 text-[10px] text-textMuted">{it.kind === 'cmd' ? '命令' : '消息'}</span>
                <button
                  onClick={() => chat.setPendingItems((items) => items.filter((_, j) => j !== i))}
                  className="shrink-0 text-textMuted hover:text-rose-400 transition-colors"
                  title="移除这条"
                ><X size={12} /></button>
              </div>
            ))}
          </div>
        )}
        {localCmdActive && localCmdFiltered.length > 0 && renderCmdMenu()}
        <textarea
          ref={chat.chatInputRef}
          value={localInput}
          onChange={(e) => {
            const val = e.target.value
            localInputRef.current = val
            setLocalInput(val)
            const before = val.slice(0, e.target.selectionStart)
            const m = before.match(/^\/\w*$/)
            if (m) { setLocalCmdQuery(before.slice(1)); setLocalCmdActive(true); setLocalCmdIdx(0) }
            else if (localCmdActive) setLocalCmdActive(false)
          }}
          onKeyDown={(e) => {
            if (localCmdActive && localCmdFiltered.length > 0) {
              if (e.key === 'ArrowDown') { e.preventDefault(); setLocalCmdIdx((i) => (i + 1) % localCmdFiltered.length); return }
              if (e.key === 'ArrowUp') { e.preventDefault(); setLocalCmdIdx((i) => (i - 1 + localCmdFiltered.length) % localCmdFiltered.length); return }
              if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); handleCmdSelect(localCmdFiltered[localCmdIdx].cmd); return }
              if (e.key === 'Escape') { e.preventDefault(); setLocalCmdActive(false); return }
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              const text = localInputRef.current
              if (!text.trim()) return
              handleSubmit(text)
            }
          }}
          rows={2}
          placeholder={(chat.chatSending || chat.chatProcessing) ? 'AI 处理中，消息将排队…' : '和世界 AI 对话…（输入 / 查看命令）'}
          className="w-full bg-elevated text-sm p-2 rounded border border-border outline-none resize-none focus:border-primary-500/50"
        />
        <button
          onClick={() => { const t = localInputRef.current.trim(); if (t) handleSubmit(t) }}
          disabled={!localInput.trim()}
          className="w-full mt-2 py-1.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded transition-colors disabled:opacity-40"
        >
          {(chat.chatSending || chat.chatProcessing) ? '排队发送' : (chat.chatSending ? '思考中...' : '发送')}
        </button>
        {chat.chatProcessing && (
          <div className="text-[10px] text-textMuted mt-2 text-center">
            上一轮还在执行（刷新不影响），完成后自动显示
          </div>
        )}
        <div className="text-[10px] text-textMuted mt-2 text-center">
          世界级会话（非 DM）：账单走世界主人，让它改界面、加功能
        </div>
      </div>
    </>
  )
}))

WorldChatPanel.displayName = 'WorldChatPanel'

export default WorldChatPanel
