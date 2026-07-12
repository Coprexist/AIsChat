import { memo, useState, useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkBreaks from 'remark-breaks'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { useAuth } from '../context/AuthContext'
import { FileIcon, Download, Globe, ShieldAlert } from 'lucide-react'
import { formatMessageTime } from '../utils/time'
import { formatFileSize } from '../utils/format'
import { avatarGradient } from '../utils/avatar'
import { getChatStyle, chatStyleClasses } from '../utils/providers'
import { useLang, useT } from '../i18n/I18nContext'
import { api } from '../api/client'
import CodeRenderer from './shared/CodeRenderer'
import FilePreviewModal from './FilePreviewModal'
import InvitationCard from './InvitationCard'
import { getBubbleTextClasses } from '../utils/bubbleContrast'

// ── Markdown 基础样式（Katex/pre/img 共用）──
const MD_BASE = [
  '[&_.katex-display]:overflow-x-auto',
  '[&_.katex-display]:-mx-1',
  '[&_.katex-display]:px-1',
  '[&_.katex]:text-inherit',
  '[&_.katex]:max-w-full',
  '[&_.katex]:overflow-x-auto',
  '[&_.katex]:inline-block',
  '[&_pre]:overflow-x-auto',
  '[&_pre]:-mx-1',
  '[&_pre]:px-1',
  '[&_img]:max-w-full',
  '[&_img]:rounded-lg',
].join(' ')

// ── 深色气泡 fallback ──
const STYLES_DARK = [
  '[&_hr]:border-0',
  '[&_hr]:h-px',
  '[&_hr]:bg-white/20',
  '[&_hr]:my-3',
  '[&_a]:break-all',
  '[&_a]:text-white/85',
  '[&_a]:underline',
  '[&_a]:decoration-white/30',
  'hover:[&_a]:text-white',
  '[&_a]:transition-colors',
  '[&_code]:bg-white/15',
  '[&_code]:text-white',
  '[&_code]:px-1',
  '[&_code]:rounded',
  '[&_pre]:bg-black/20',
  '[&_pre_code]:bg-transparent',
  '[&_.markdown-table-wrapper]:my-0',
  '[&_.markdown-table-wrapper]:border-0',
  '[&_.markdown-table-wrapper]:rounded-none',
  '[&_.markdown-table-wrapper]:[scrollbar-color:rgba(255,255,255,0.25)_transparent]',
  '[&_table]:w-full',
  '[&_table]:border-collapse',
  '[&_table]:rounded-lg',
  '[&_table]:overflow-hidden',
  '[&_.markdown-table-wrapper_thead_th]:text-white',
  '[&_.markdown-table-wrapper_tbody_td]:text-white/85',
  '[&_.markdown-table-wrapper_thead_th]:py-1.5',
  '[&_.markdown-table-wrapper_tbody_td]:py-1.5',
  '[&_.markdown-table-wrapper_thead_th]:px-3',
  '[&_.markdown-table-wrapper_tbody_td]:px-3',
  '[&_.markdown-table-wrapper_thead_th]:border',
  '[&_.markdown-table-wrapper_tbody_td]:border',
  '[&_.markdown-table-wrapper_thead_th]:border-white/20',
  '[&_.markdown-table-wrapper_tbody_td]:border-white/20',
  '[&_.markdown-table-wrapper_thead_th]:text-left',
  '[&_.markdown-table-wrapper_thead_th]:font-semibold',
  '[&_.markdown-table-wrapper_table]:bg-primary-700/30',
  '[&_.markdown-table-wrapper_thead_th]:bg-primary-700/40',
  '[&_.markdown-table-wrapper_tbody_tr:nth-child(even)]:bg-primary-700/20',
  // 悬停由 index.css 统一处理
].join(' ')

// ── 浅色气泡 fallback ──
const STYLES_LIGHT = [
  '[&_hr]:border-0',
  '[&_hr]:h-px',
  '[&_hr]:bg-border',
  '[&_hr]:my-3',
  '[&_a]:break-all',
  '[&_a]:text-primary-500',
  'dark:[&_a]:text-primary-400',
  '[&_a]:underline',
  'hover:[&_a]:text-primary-400',
  'dark:hover:[&_a]:text-primary-300',
  '[&_a]:transition-colors',
  '[&_.markdown-table-wrapper]:my-0',
  '[&_.markdown-table-wrapper]:border-0',
  '[&_.markdown-table-wrapper]:rounded-none',
  '[&_table]:w-full',
  '[&_table]:border-collapse',
  '[&_table]:rounded-lg',
  '[&_table]:overflow-hidden',
  '[&_.markdown-table-wrapper_thead_th]:text-textPrimary',
  '[&_.markdown-table-wrapper_tbody_td]:text-textSecondary',
  '[&_.markdown-table-wrapper_thead_th]:py-1.5',
  '[&_.markdown-table-wrapper_tbody_td]:py-1.5',
  '[&_.markdown-table-wrapper_thead_th]:px-3',
  '[&_.markdown-table-wrapper_tbody_td]:px-3',
  '[&_.markdown-table-wrapper_thead_th]:border',
  '[&_.markdown-table-wrapper_tbody_td]:border',
  '[&_.markdown-table-wrapper_thead_th]:border-border',
  '[&_.markdown-table-wrapper_tbody_td]:border-border',
  '[&_.markdown-table-wrapper_thead_th]:text-left',
  '[&_.markdown-table-wrapper_thead_th]:font-semibold',
  '[&_.markdown-table-wrapper_table]:bg-surface',
  '[&_.markdown-table-wrapper_thead_th]:bg-canvas',
  '[&_.markdown-table-wrapper_tbody_tr:nth-child(even)]:bg-elevated',
  // 悬停由 index.css 统一处理
].join(' ')

/** 弹跳三点（思考中/输入中共用） */
const BouncingDots = ({ className = '' }: { className?: string }) => (
  <span className={`inline-flex gap-0.5 ${className}`}>
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
  </span>
);

interface MessageBubbleProps {
  senderName: string
  senderAvatarUrl?: string | null
  content: string
  isMine: boolean
  createdAt: string
  state?: string
  senderType?: string
  senderId?: number
  thinking?: boolean
  isTyping?: boolean
  sourcePublicId?: string | null
  attachments?: Array<{file_id?: number, name?: string, size?: number, mime_type?: string, type?: string, invitation_id?: number, group_name?: string, inviter_name?: string, status?: string}> | null
  messageType?: string
  onAvatarClick?: (type: string, id: number, name: string, state?: string) => void
}


function fileIconColor(mimeType: string): string {
  if (mimeType.startsWith('image/')) return 'text-mint-400'
  if (mimeType.startsWith('video/')) return 'text-rose-400'
  if (mimeType.includes('pdf')) return 'text-rose-400'
  if (mimeType.includes('zip') || mimeType.includes('tar') || mimeType.includes('gz')) return 'text-amber-400'
  return 'text-primary-400'
}

const MessageBubble = memo(function MessageBubble({
  senderName, senderAvatarUrl, content, isMine, createdAt, state,
  senderType, senderId, thinking, isTyping, sourcePublicId, attachments, messageType, onAvatarClick,
}: MessageBubbleProps) {
  const { user } = useAuth()
  const lang = useLang()
  const t = useT()
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!createdAt) return
    const d = new Date(/Z$/i.test(createdAt) ? createdAt : createdAt + 'Z')
    if (isNaN(d.getTime())) return
    const ageMs = Date.now() - d.getTime()
    let interval: number
    if (ageMs < 60_000)           interval = 15_000
    else if (ageMs < 3_600_000)   interval = 300_000
    else if (ageMs < 86_400_000)  interval = 3_600_000
    else return
    const i = setInterval(() => setTick(t => t + 1), interval)
    return () => clearInterval(i)
  }, [createdAt])

  const [previewFile, setPreviewFile] = useState<{ file_id: number; name: string; size: number; mime_type: string } | null>(null)
  const [invStatus, setInvStatus] = useState<string | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [bubbleContrastCls, setBubbleContrastCls] = useState('')

  useEffect(() => {
    if (!contentRef.current) return
    const el = contentRef.current
    const raf = requestAnimationFrame(() => {
      const computed = getComputedStyle(el)
      const rgb = computed.backgroundColor
      const m = rgb.match(/\d+/g)?.map(Number)
      if (m && m.length >= 3) {
        const hex = '#' + m.slice(0, 3).map(c => c.toString(16).padStart(2, '0')).join('')
        setBubbleContrastCls(getBubbleTextClasses(hex))
      } else {
        setBubbleContrastCls('')
      }
    })
    return () => cancelAnimationFrame(raf)
  }, [isMine])

  const invAtt = attachments?.find(a => a.type === 'group_invitation')
  const isInvitation = messageType === 'group_invitation' && invAtt
  const currentStatus = invStatus || invAtt?.status || 'pending'
  const fileAtts = attachments?.filter(a => a.type !== 'group_invitation') || []

  const handleAcceptInvitation = async (invitationId: number) => {
    try {
      await api.post(`/group-invitations/${invitationId}/accept`)
      setInvStatus('accepted')
      window.dispatchEvent(new CustomEvent('groupListRefresh'))
    } catch (_) { /* ignore */ }
  }

  const handleRejectInvitation = async (invitationId: number) => {
    try {
      await api.post(`/group-invitations/${invitationId}/reject`)
      setInvStatus('rejected')
    } catch (_) { /* ignore */ }
  }

  const bubbleBg = isMine
    ? 'bg-primary-500 dark:bg-primary-600 text-white rounded-2xl rounded-tr-md shadow-lg shadow-primary-500/15'
    : senderType === 'system'
      ? 'bg-rose-50 dark:bg-rose-900/20 text-rose-900 dark:text-rose-300 rounded-2xl rounded-tl-md border border-rose-200 dark:border-rose-800'
      : 'bg-surface text-textPrimary rounded-2xl rounded-tl-md border border-border'

  const avatarGradientCls = avatarGradient(senderType, isMine, !!senderAvatarUrl)
  const avatarGradientShadow = isMine ? 'shadow-primary-500/15' : senderType === 'system' ? 'shadow-rose-400/15' : 'shadow-teal-400/10'

  const { gap, mb, avatar: avatarSize, textSize: avatarTextSize } = chatStyleClasses(getChatStyle())

  return (<>
    <div className={`flex ${gap} ${mb} msg-enter ${isMine ? 'flex-row-reverse' : ''}`}>
      <div className="relative shrink-0">
        {!isMine && (thinking || isTyping) && (
          <div className="absolute -inset-px w-10 h-10 rounded-full ai-pulse-active" />
        )}
        {senderAvatarUrl ? (
          <div
            onClick={() => {
              if (onAvatarClick && senderType && senderId && senderType !== 'system') {
                onAvatarClick(senderType, senderId, senderName, state)
              }
            }}
            className={`relative ${avatarSize} rounded-full overflow-hidden ${senderType !== 'system' ? 'cursor-pointer hover:scale-105 transition-transform' : ''} shadow ${avatarGradientShadow}`}
            title={t('chat.viewProfile').replace('{name}', senderName)}
          >
            <div className={`absolute inset-px rounded-full ${avatarGradient(senderType, isMine, true)}`} />
            <img src={senderAvatarUrl} alt={senderName} className="relative w-full h-full rounded-full object-cover" />
          </div>
        ) : (
          <div
            onClick={() => {
              if (onAvatarClick && senderType && senderId && senderType !== 'system') {
                onAvatarClick(senderType, senderId, senderName, state)
              }
            }}
            className={`relative ${avatarSize} rounded-full flex items-center justify-center ${avatarTextSize} font-bold ${avatarGradient(senderType, isMine, false)} ${senderType !== 'system' ? 'cursor-pointer hover:scale-105 transition-transform' : ''} shadow ${avatarGradientShadow} overflow-hidden`}
            title={senderType === 'system' ? '系统通知' : thinking ? t('chat.thinking') : isTyping ? t('chat.typing') : t('chat.viewProfile').replace('{name}', senderName)}
          >
            {senderType === 'system' ? (
              <ShieldAlert size={16} className="text-white" />
            ) : (thinking || isTyping) ? (
              <BouncingDots className="text-white/80" />
            ) : (
              senderName.charAt(0).toUpperCase()
            )}
          </div>
        )}
      </div>

      <div className={`max-w-[72%] ${isMine ? 'items-end' : 'items-start'}`}>
        <div className={`flex items-center gap-2 mb-1 flex-wrap ${isMine ? 'flex-row-reverse' : ''}`}>
          <span className={`text-xs font-medium ${senderType === 'system' ? 'text-rose-500' : 'text-textSecondary'}`}>{senderName}</span>
          {sourcePublicId && (
            <span className="text-[10px] text-primary-400 bg-primary-500/10 px-1.5 py-0.5 rounded-full" title={t('chat.fromInstance').replace('{publicId}', sourcePublicId)}>
              <Globe size={10} className="inline" /> {sourcePublicId.length > 15 ? sourcePublicId.slice(0, 15) + '...' : sourcePublicId}
            </span>
          )}
          <span className="text-[10px] text-textMuted">{formatMessageTime(createdAt, lang)}</span>
          {thinking && (
            <span className="text-[10px] text-primary-400 animate-pulse font-medium">{t('chat.thinking')}</span>
          )}
          {isTyping && (
            <span className="text-[10px] text-mint-400 animate-pulse font-medium">{t('chat.typing')}</span>
          )}
        </div>
        <div ref={contentRef} className={`px-4 py-2.5 text-sm leading-relaxed break-words ${bubbleBg} ${thinking || isTyping ? 'opacity-70' : ''} ${bubbleContrastCls || (isMine ? `${MD_BASE} ${STYLES_DARK}` : `${MD_BASE} ${STYLES_LIGHT}`)} `}>
          {isInvitation && invAtt ? (
            <InvitationCard
              invitationId={invAtt.invitation_id!}
              groupName={invAtt.group_name || ''}
              inviterName={invAtt.inviter_name || ''}
              message={undefined}
              status={currentStatus as 'pending' | 'accepted' | 'rejected'}
              onAccept={handleAcceptInvitation}
              onReject={handleRejectInvitation}
            />
          ) : isTyping ? (
            <BouncingDots className="text-primary-400 align-middle" />
          ) : (
            <Markdown
              children={content
                .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
                .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')}
              remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
              rehypePlugins={[
                rehypeRaw,
                rehypeKatex,
                [rehypeSanitize, {
                  ...defaultSchema,
                  attributes: {
                    ...defaultSchema.attributes,
                    a: [...(defaultSchema.attributes?.a || ['href']), 'class', 'target', 'rel'],
                    code: [...(defaultSchema.attributes?.code || []), 'class'],
                    span: [...(defaultSchema.attributes?.span || []), 'class'],
                    img: [...(defaultSchema.attributes?.img || ['src', 'alt']), 'class'],
                    div: [...(defaultSchema.attributes?.div || []), 'class'],
                  },
                }],
              ]}
              components={{ code: CodeRenderer, table: ({ node, ...props }) => (
                  <div className="markdown-table-wrapper"><table {...props} /></div>
                ), th: ({ node, ...props }) => (<th {...props} />), td: ({ node, ...props }) => (<td {...props} />), }}
            />
          )}
          {fileAtts.length > 0 && (
            <div className={`mt-2 pt-2 border-t flex flex-wrap gap-1.5 ${isMine ? 'border-white/20' : 'border-border'}`}>
              {fileAtts.map((att) => {
                const token = localStorage.getItem('access_token')
                const dlUrl = `/api/fs/download/${att.file_id}?token=${token || ''}`
                const fid = att.file_id!
                const fname = att.name!
                const fsize = att.size!
                const fmime = att.mime_type!

                if (fmime.startsWith('image/')) {
                  return (
                    <button
                      key={fid}
                      onClick={() => setPreviewFile({ file_id: fid, name: fname, size: fsize, mime_type: fmime })}
                      className="block max-w-full"
                    >
                      <img
                        src={dlUrl}
                        alt={fname}
                        className="max-w-[280px] max-h-[200px] rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity border border-white/10"
                        title={fname}
                      />
                    </button>
                  )
                }

                return (
                  <button
                    key={fid}
                    onClick={() => setPreviewFile({ file_id: fid, name: fname, size: fsize, mime_type: fmime })}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-colors ${
                      isMine
                        ? 'bg-white/10 hover:bg-white/20 text-white/90'
                        : 'bg-canvas hover:bg-elevated text-textSecondary hover:text-textPrimary border border-border'
                    }`}
                    title={`${fname} (${formatFileSize(fsize)})`}
                  >
                    <FileIcon size={12} className={fileIconColor(fmime)} />
                    <span className="max-w-[100px] truncate">{fname}</span>
                    <span className="text-[10px] opacity-60">{formatFileSize(fsize)}</span>
                    <Download size={11} className="opacity-60" />
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>

    {previewFile && (
      <FilePreviewModal
        fileId={previewFile.file_id}
        fileName={previewFile.name}
        fileSize={previewFile.size}
        mimeType={previewFile.mime_type}
        onClose={() => setPreviewFile(null)}
      />
    )}
  </>)
})
export default MessageBubble
