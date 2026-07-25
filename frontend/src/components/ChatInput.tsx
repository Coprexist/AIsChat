import { useState, useCallback, useEffect, useRef, useMemo, forwardRef, useImperativeHandle } from 'react'
import { Send, Paperclip } from 'lucide-react'

interface ChatInputProps {
  conversationType: string
  conversationId: number | string
  t: (key: string) => string
  onSend: (text: string) => void
  onSendFile?: () => void
  groupMembers?: Array<{ type: string; id: number; name: string; state?: string }>
  inputHeight?: number | null
  /** 自动高度变化时通知父组件（用于补偿拖拽高度） */
  onAutoHeight?: (ah: number) => void
}

/**
 * 独立输入框。管理自身 value 和 @mention 状态，打字不触发父组件重渲染。
 */
const ChatInputFunc = ({ conversationType, conversationId, t, onSend, onSendFile, groupMembers, inputHeight, onAutoHeight }: ChatInputProps, ref: React.ForwardedRef<HTMLTextAreaElement>) => {
  const [value, setValue] = useState('')
  const [autoHeight, setAutoHeight] = useState(0)
  const valueRef = useRef('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(ref, () => textareaRef.current!, [])
  const LINE_H = 23

  // @mention 检测
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionActive, setMentionActive] = useState(false)
  const [mentionIdx, setMentionIdx] = useState(0)
  const mentionFiltered = useMemo(() =>
    mentionQuery ? (groupMembers || []).filter(m => m.name.toLowerCase().includes(mentionQuery.toLowerCase())) : (groupMembers || [])
  , [mentionQuery, groupMembers])

  useEffect(() => { valueRef.current = value }, [value])

  // 拖拽高度或自动高度变化时同步到 textarea DOM
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = Math.max(44, (inputHeight || 0) + autoHeight) + 'px'
  }, [inputHeight, autoHeight])

  // 草稿恢复 & 离开保存
  useEffect(() => {
    const key = `draft_${conversationType}_${conversationId}`
    const saved = localStorage.getItem(key)
    if (saved) setValue(saved)
    return () => {
      const v = valueRef.current.trim()
      if (v) localStorage.setItem(key, v)
      else localStorage.removeItem(key)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationType, conversationId])

  // @ 检测
  const detectMention = useCallback((val: string, cursorPos: number) => {
    const before = val.slice(0, cursorPos)
    const atIdx = before.lastIndexOf('@')
    if (atIdx >= 0) {
      const after = val.slice(atIdx + 1, cursorPos)
      if (/^[\w\u4e00-\u9fff]*$/.test(after)) {
        setMentionQuery(after)
        setMentionActive(true)
        setMentionIdx(0)
        return
      }
    }
    setMentionActive(false)
  }, [])

  // 插入 @ 名字
  const insertMention = useCallback((name: string) => {
    const ta = textareaRef.current
    if (!ta) return
    const cursorPos = ta.selectionStart
    const before = value.slice(0, cursorPos)
    const atIdx = before.lastIndexOf('@')
    if (atIdx === -1) return
    const newBefore = before.slice(0, atIdx) + '@' + name + ' '
    const newValue = newBefore + value.slice(cursorPos)
    setValue(newValue)
    setMentionActive(false)
    requestAnimationFrame(() => {
      ta.focus()
      const newPos = newBefore.length
      ta.setSelectionRange(newPos, newPos)
    })
  }, [value])

  // 发送
  const doSend = useCallback(() => {
    const v = value.trim()
    if (!v) return
    onSend(v)
    setValue('')
  }, [value, onSend])

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const ta = e.target
    setValue(ta.value)
    detectMention(ta.value, ta.selectionStart)
    // 自动缩放：超出基础高度的部分最多 3 行
    ta.style.height = 'auto'
    const scrollH = ta.scrollHeight
    const base = inputHeight || 44
    const maxAuto = 3 * LINE_H
    const ah = Math.max(0, Math.min(scrollH - base, maxAuto))
    setAutoHeight(ah)
    ta.dataset.autoHeight = String(ah)
    onAutoHeight?.(ah)
    ta.style.height = Math.max(44, (inputHeight || 0) + ah) + 'px'
  }, [detectMention, inputHeight])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // @mention 导航
    if (mentionActive && mentionFiltered.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setMentionIdx(i => (i + 1) % mentionFiltered.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setMentionIdx(i => (i - 1 + mentionFiltered.length) % mentionFiltered.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); insertMention(mentionFiltered[mentionIdx].name); return }
      if (e.key === 'Escape') { e.preventDefault(); setMentionActive(false); return }
    }
    // Enter 发送
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSend()
    }
  }, [mentionActive, mentionFiltered, mentionIdx, insertMention, doSend])

  return (
    <div className="flex items-end gap-2 px-4 py-3 shrink-0">
      {/* @mention 弹出列表 */}
      {mentionActive && mentionFiltered.length > 0 && (
        <div className="absolute bottom-full left-4 mb-1 w-56 max-h-40 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
          {mentionFiltered.map((m, i) => (
            <button
              key={`${m.type}:${m.id}`}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                i === mentionIdx ? 'bg-primary-500/20 text-primary-400' : 'text-textPrimary hover:bg-hover'
              }`}
              onMouseDown={(e) => { e.preventDefault(); insertMention(m.name) }}
            >
              {m.name}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => onSendFile?.()}
        className="p-2.5 rounded-xl border border-border bg-canvas text-textMuted hover:text-textPrimary hover:border-primary-500/30 hover:bg-elevated transition-colors shrink-0"
        title={t('chat.addAttachment')}
      >
        <Paperclip size={18} />
      </button>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={conversationType === 'dm' ? t('chat.dmInputPlaceholder') : t('chat.groupInputPlaceholder')}
        rows={1}
        className="flex-1 min-w-0 resize-none rounded-xl border border-border bg-canvas px-4 py-2.5 text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/30 transition-shadow min-h-[42px]"
      />
      <button
        onClick={doSend}
        disabled={!value.trim()}
        className="p-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all shrink-0"
        title={t('chat.send')}
      >
        <Send size={16} />
      </button>
    </div>
  )
}

const ChatInput = forwardRef(ChatInputFunc)
export default ChatInput
