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

/** 弹跳三点（思考中/输入中共用） */
const BouncingDots = ({ className = '' }: { className?: string }) => (
  <span className={`inline-flex gap-0.5 ${className}`}>
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
    <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
  </span>
);

// ChatCodeRenderer ——已迁移到 components/shared/CodeRenderer.tsx

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
  // 智能刷新相对时间：越近越频繁，越远越少刷
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!createdAt) return
    const d = new Date(/Z$/i.test(createdAt) ? createdAt : createdAt + 'Z')
    if (isNaN(d.getTime())) return
    const ageMs = Date.now() - d.getTime()
    let interval: number
    if (ageMs < 60_000)           interval = 15_000   // < 1分钟：每15秒
    else if (ageMs < 3_600_000)   interval = 300_000  // < 1小时：每5分钟
    else if (ageMs < 86_400_000)  interval = 3_600_000 // < 1天：每小时
    else return // 超过1天不刷
    const i = setInterval(() => setTick(t => t + 1), interval)
    return () => clearInterval(i)
  }, [createdAt])

  const [previewFile, setPreviewFile] = useState<{ file_id: number; name: string; size: number; mime_type: string } | null>(null)
  const [invStatus, setInvStatus] = useState<string | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [bubbleContrastCls, setBubbleContrastCls] = useState('')

  // 运行时读取气泡背景色，动态调对比度
  useEffect(() => {
    if (!contentRef.current) return
    const el = contentRef.current
    // 等一帧让浏览器渲染完成，拿到计算后的背景色
    const raf = requestAnimationFrame(() => {
      const computed = getComputedStyle(el)
      const rgb = computed.backgroundColor  // "rgb(99, 102, 241)" 格式
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

  // 检测邀请卡片
  const invAtt = attachments?.find(a => a.type === 'group_invitation')
  const isInvitation = messageType === 'group_invitation' && invAtt
  const currentStatus = invStatus || invAtt?.status || 'pending'
  // 普通文件附件（排除邀请卡片）
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
      {/* 头像 — 思考/输入中时带脉动光环 */}
      <div className="relative shrink-0">
        {/* 仅在 AI 思考中/输入中显示脉动 */}
        {!isMine && (thinking || isTyping) && (
          <div className="absolute -inset-px w-10 h-10 rounded-full ai-pulse-active" />
        )}
        {/* 头像 */}
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

      {/* 消息内容 */}
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
        <div ref={contentRef} className={`px-4 py-2.5 text-sm leading-relaxed break-words ${bubbleBg} ${thinking || isTyping ? 'opacity-70' : ''} ${bubbleContrastCls || (
          isMine
            ? `[&_.katex-display]:overflow-x-auto [&_.katex-display]:-mx-1 [&_.katex-display]:px-1
               [&_.katex]:text-inherit [&_.katex]:max-w-full [&_.katex]:overflow-x-auto [&_.katex]:inline-block
               [&_pre]:overflow-x-auto [&_pre]:-mx-1 [&_pre]:px-1
               [&_.markdown-table-wrapper]:my-0 [&_.markdown-table-wrapper]:border-0 [&_.markdown-table-wrapper]:rounded-none [&_table]:w-full [&_table]:border-collapse [&_table]:rounded-lg [&_table]:overflow-hidden [&_table_th]:text-white [&_table_td]:text-white/85 [&_table_th]:py-1.5 [&_table_td]:py-1.5 [&_table_th]:px-3 [&_table_td]:px-3 [&_table_th]:border [&_table_td]:border [&_table_th]:border-white/20 [&_table_td]:border-white/20 [&_table_th]:text-left [&_table_th]:font-semibold [&_table]:bg-primary-700/30 [&_table_th]:bg-primary-700/40 [&_table_tr:nth-child(even)]:bg-primary-700/20 [&_table_tr]:hover:bg-primary-700/50 [&_table_tr]:transition-colors
               [&_img]:max-w-full [&_img]:rounded-lg
               [&_a]:break-all [&_a]:text-white/85 [&_a]:underline [&_a]:decoration-white/30 hover:[&_a]:text-white [&_a]:transition-colors
               [&_code]:bg-white/15 [&_code]:text-white [&_code]:px-1 [&_code]:rounded
               [&_pre]:bg-black/20 [&_pre_code]:bg-transparent`
            : `[&_.katex-display]:overflow-x-auto [&_.katex-display]:-mx-1 [&_.katex-display]:px-1
               [&_.katex]:text-inherit [&_.katex]:max-w-full [&_.katex]:overflow-x-auto [&_.katex]:inline-block
               [&_pre]:overflow-x-auto [&_pre]:-mx-1 [&_pre]:px-1
               [&_.markdown-table-wrapper]:my-0 [&_.markdown-table-wrapper]:border-0 [&_.markdown-table-wrapper]:rounded-none [&_table]:w-full [&_table]:border-collapse [&_table]:rounded-lg [&_table]:overflow-hidden [&_table_th]:text-textPrimary [&_table_td]:text-textSecondary [&_table_th]:py-1.5 [&_table_td]:py-1.5 [&_table_th]:px-3 [&_table_td]:px-3 [&_table_th]:border [&_table_td]:border [&_table_th]:border-border [&_table_td]:border-border [&_table_th]:text-left [&_table_th]:font-semibold [&_table]:bg-surface [&_table_th]:bg-canvas [&_table_tr:nth-child(even)]:bg-elevated [&_table_tr]:hover:bg-elevated/80 [&_table_tr]:transition-colors
               [&_img]:max-w-full [&_img]:rounded-lg
               [&_a]:break-all [&_a]:text-primary-500 dark:[&_a]:text-primary-400 [&_a]:underline hover:[&_a]:text-primary-400 dark:hover:[&_a]:text-primary-300 [&_a]:transition-colors`
        )}
        `}>
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
              // 预处理：\(...\) → $...$，\[...\] → $$...$$，兼容 LaTeX 风格数学公式
              children={content
                .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
                .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')}
              remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
              rehypePlugins={[
                rehypeRaw,
                rehypeKatex,
                // sanitize 放最后，并配置 allowlist 确保 <a> 标签的 class 不被剥离
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
          {/* 附件列表（跳过邀请类型附件） */}
          {fileAtts.length > 0 && (
            <div className={`mt-2 pt-2 border-t flex flex-wrap gap-1.5 ${isMine ? 'border-white/20' : 'border-border'}`}>
              {fileAtts.map((att) => {
                const token = localStorage.getItem('access_token')
                const dlUrl = `/api/fs/download/${att.file_id}?token=${token || ''}`
                // 文件附件必有这些字段（来自 API），断言为非可选
                const fid = att.file_id!
                const fname = att.name!
                const fsize = att.size!
                const fmime = att.mime_type!

                // 图片类型：缩略图，点击弹窗查看
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

                // 其他文件：点击预览（不可预览时自动下载）
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

    {/* 文件预览弹窗 */}
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
