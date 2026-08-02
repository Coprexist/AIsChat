import { memo, useState, useMemo } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkBreaks from 'remark-breaks'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { useAuth } from '../context/AuthContext'
import { FileIcon, Download, Globe, ShieldAlert, Reply } from 'lucide-react'
import { formatMessageTime } from '../utils/time'
import { formatFileSize } from '../utils/format'
import { avatarGradient } from '../utils/avatar'
import { getChatStyle, chatStyleClasses } from '../utils/providers.tsx'
import { scrollToInContainer } from '../utils/scroll'
import { useLang, useT } from '../i18n/I18nContext'
import { api } from '../api/client'
import CodeRenderer from './shared/CodeRenderer'
import FilePreviewModal from './FilePreviewModal'
import InvitationCard from './InvitationCard'
import { useTimeTick } from '../hooks/useTimeTick'
// CSS 变量：isMine 直接决定配色（不用 getComputedStyle，性能快）
const DARK_VARS = [
  '--b-link-r:255', '--b-link-g:255', '--b-link-b:255', '--b-link-a:0.85',
  '--b-code-r:255', '--b-code-g:255', '--b-code-b:255', '--b-code-a:0.15',
  '--b-pre-r:0',    '--b-pre-g:0',    '--b-pre-b:0',    '--b-pre-a:0.2',
  '--b-hr-r:255',   '--b-hr-g:255',   '--b-hr-b:255',   '--b-hr-a:0.2',
  '--b-thead-r:55', '--b-thead-g:45', '--b-thead-b:70', '--b-thead-a:1',
  '--b-zebra-r:48', '--b-zebra-g:40', '--b-zebra-b:60', '--b-zebra-a:0.5',
  '--b-hover-r:55', '--b-hover-g:45', '--b-hover-b:70', '--b-hover-a:0.8',
  '--b-scrollbar-r:255_255_255', '--b-scrollbar-a:0.3',
  /* 气泡彩色文字（深色底用亮色） */
  '--b-text-red:255 100 100', '--b-text-orange:255 180 50', '--b-text-gold:255 215 0',
  '--b-text-green:80 220 120', '--b-text-blue:100 150 255', '--b-text-purple:180 130 255',
  '--b-text-pink:255 130 200', '--b-text-gray:180 180 180',
]

const LIGHT_VARS = [
  '--b-link-r:initial',
  '--b-thead-r:237', '--b-thead-g:233', '--b-thead-b:254', '--b-thead-a:1',
  '--b-zebra-r:243', '--b-zebra-g:240', '--b-zebra-b:255', '--b-zebra-a:1',
  /* 气泡彩色文字（浅色底用标准色） */
  '--b-text-red:220 50 50', '--b-text-orange:220 130 0', '--b-text-gold:180 140 0',
  '--b-text-green:20 150 60', '--b-text-blue:50 100 220', '--b-text-purple:130 80 200',
  '--b-text-pink:220 80 150', '--b-text-gray:100 100 100',
]

/** 弹跳三点 */
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
  messageId?: number
  replyTo?: { id: number; sender: string; content: string } | null
  onAvatarClick?: (type: string, id: number, name: string, state?: string) => void
  onReply?: (messageId: number, senderName: string, content: string) => void
}

function fileIconColor(mimeType: string): string {
  if (mimeType.startsWith('image/')) return 'text-mint-400'
  if (mimeType.startsWith('video/')) return 'text-rose-400'
  if (mimeType.includes('pdf')) return 'text-rose-400'
  if (mimeType.includes('zip') || mimeType.includes('tar') || mimeType.includes('gz')) return 'text-amber-400'
  return 'text-primary-400'
}

// 将行内代码重定向到独立组件，避免和代码块共用同一个 code 组件
import { visit } from 'unist-util-visit'
function remarkInlineCode() {
  return (tree) => { visit(tree, 'inlineCode', (node) => {
    node.data = { hName: 'inlinecode' }
  }) }
}

const MessageBubble = memo(function MessageBubble({
  senderName, senderAvatarUrl, content, isMine, createdAt, state,
  senderType, senderId, thinking, isTyping, sourcePublicId, attachments, messageType, onAvatarClick, messageId, replyTo, onReply,
}: MessageBubbleProps) {
  const { user } = useAuth()
  const lang = useLang()
  const t = useT()
  useTimeTick()  // 全局 tick，驱动相对时间更新（不需要返回值）

  const [previewFile, setPreviewFile] = useState<{ file_id: number; name: string; size: number; mime_type: string } | null>(null)
  const [invStatus, setInvStatus] = useState<string | null>(null)

  // 表格昼夜适配：将 DARK_VARS / LIGHT_VARS 转换为 inline style 挂到气泡上
  //（DARK_VARS/LIGHT_VARS 定义了但从未被使用，这里修复）
  const tableVars = useMemo(() => {
    const isPageDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
    const vars = (isMine || isPageDark) ? DARK_VARS : LIGHT_VARS
    const obj: Record<string, string> = {}
    for (const v of vars) {
      const idx = v.indexOf(':')
      if (idx !== -1) obj[v.slice(0, idx).trim()] = v.slice(idx + 1).trim()
    }
    return obj
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

  // 气泡样式拆两层：背景层（上色+圆角边框+阴影，参与魔视界旋转）与内容层（文字颜色+布局）
  // 背景层 absolute inset-0 铺满外层，尺寸由内容层撑起，圆角边框天然对齐
  const bubbleBg = isMine
    ? 'bg-primary-500 dark:bg-[#5a3a99] rounded-2xl rounded-tr-md shadow-lg shadow-primary-500/15'
    : senderType === 'system'
      ? 'bg-rose-50 dark:bg-rose-900/20 rounded-2xl rounded-tl-md border border-rose-200 dark:border-rose-800'
      : 'bg-surface rounded-2xl rounded-tl-md border border-border'
  const bubbleText = isMine
    ? 'text-white'
    : senderType === 'system'
      ? 'text-rose-900 dark:text-rose-300'
      : 'text-textPrimary'

  const avatarGradientCls = avatarGradient(senderType, isMine, !!senderAvatarUrl)
  const avatarGradientShadow = isMine ? 'shadow-primary-500/15' : senderType === 'system' ? 'shadow-rose-400/15' : 'shadow-teal-400/10'
  const { gap, mb, avatar: avatarSize, textSize: avatarTextSize } = chatStyleClasses(getChatStyle())

  // Katex/表格/pre 溢出等不适合用 CSS 变量的样式继续用 Tailwind
  const layoutCls = [
    '[&_.katex-display]:overflow-x-auto',
    '[&_.katex-display]:-mx-1',
    '[&_.katex-display]:px-1',
    '[&_.katex]:text-inherit',
    '[&_.katex]:max-w-full',
    '[&_.katex]:overflow-x-auto',
    '[&_.katex]:overflow-y-hidden',
    '[&_.katex]:align-middle',
    '[&_pre]:overflow-x-auto',
    '[&_pre]:-mx-1',
    '[&_pre]:px-1',
    '[&_img]:max-w-full',
    '[&_img]:rounded-lg',
    // 表格圆角（overflow 由 index.css overflow-x-auto 控制）
    '[&_.markdown-table-wrapper]:rounded-lg',
    '[&_.markdown-table-wrapper]:border',
    '[&_.markdown-table-wrapper]:border-border',
    // 移除 wrapper 额外间距
    '[&_.markdown-table-wrapper]:my-0',
  ].join(' ')

  return (<>
    <div id={messageId ? `msg-${messageId}` : undefined} className={`flex ${gap} ${mb} msg-enter group ${isMine ? 'flex-row-reverse' : ''}`}>
      <div className="relative shrink-0">
        {!isMine && (thinking || isTyping) && (
          <div className="absolute -inset-px w-10 h-10 rounded-full ai-pulse-active" />
        )}
        {senderAvatarUrl ? (
          <div
            onClick={() => { if (onAvatarClick && senderType && senderId && senderType !== 'system') onAvatarClick(senderType, senderId, senderName, state) }}
            className={`relative ${avatarSize} rounded-full overflow-hidden ${senderType !== 'system' ? 'cursor-pointer hover:scale-105 transition-transform' : ''} shadow ${avatarGradientShadow}`}
            title={t('chat.viewProfile').replace('{name}', senderName)}
          >
            <div className={`absolute inset-px rounded-full ${avatarGradient(senderType, isMine, true)}`} />
            <img src={senderAvatarUrl} alt={senderName} className="relative w-full h-full rounded-full object-cover" loading="lazy" decoding="async" />
          </div>
        ) : (
          <div
            onClick={() => { if (onAvatarClick && senderType && senderId && senderType !== 'system') onAvatarClick(senderType, senderId, senderName, state) }}
            className={`relative ${avatarSize} rounded-full flex items-center justify-center ${avatarTextSize} font-bold ${avatarGradient(senderType, isMine, false)} ${senderType !== 'system' ? 'cursor-pointer hover:scale-105 transition-transform' : ''} shadow ${avatarGradientShadow} overflow-hidden`}
            title={senderType === 'system' ? '系统通知' : thinking ? t('chat.thinking') : isTyping ? t('chat.typing') : t('chat.viewProfile').replace('{name}', senderName)}
          >
            {senderType === 'system' ? <ShieldAlert size={16} className="text-white" />
              : (thinking || isTyping) ? <BouncingDots className="text-white/80" />
              : senderName.charAt(0).toUpperCase()}
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
          {thinking && <span className="text-[10px] text-primary-400 animate-pulse font-medium">{t('chat.thinking')}</span>}
          {isTyping && <span className="text-[10px] text-mint-400 animate-pulse font-medium">{t('chat.typing')}</span>}
        </div>
        <div className={`relative ${thinking || isTyping ? 'opacity-70' : ''}`}>
          {/* 背景层：只上色/圆角/边框/阴影，不含图片 → 天然被魔视界选中旋转；尺寸由外层决定 */}
          <div data-mv-force className={`absolute inset-0 ${bubbleBg}`} aria-hidden="true" />
          {/* 内容层：文字/图片/布局，不参与旋转（图片保持清晰） */}
          <div className={`bubble-content relative px-4 py-2.5 text-sm leading-relaxed break-words ${bubbleText} ${layoutCls}`} style={tableVars}>
          {replyTo != null && (
            <div className={`flex items-start gap-1.5 mb-1.5 pb-1.5 border-b ${isMine ? 'border-white/20' : 'border-border'} cursor-pointer hover:opacity-80 transition-opacity`}
              onClick={() => {
                // 只滚动消息列表容器本身（scrollIntoView 会连带滚动外层 main/Layout，把标题栏滚出视口）
                const target = document.getElementById(`msg-${replyTo.id}`)
                const list = target?.closest('.overflow-y-auto') as HTMLElement | null
                if (target && list) {
                  scrollToInContainer(list, target, { smooth: true, offset: -list.clientHeight / 2 })
                }
              }}>
              <div className="w-0.5 h-full min-h-[1.5em] bg-primary-400 rounded-full shrink-0" />
              <div className="text-[11px] leading-relaxed line-clamp-2">
                <span className={`font-medium ${isMine ? 'text-white/80' : 'text-primary-400'}`}>@{replyTo.sender}</span>
                <span className={`${isMine ? 'text-white/50' : 'text-textMuted'}`}> {replyTo.content}</span>
              </div>
            </div>
          )}
          {isInvitation && invAtt ? (
            <InvitationCard invitationId={invAtt.invitation_id!} groupName={invAtt.group_name || ''} inviterName={invAtt.inviter_name || ''} message={undefined} status={currentStatus as 'pending' | 'accepted' | 'rejected'} onAccept={handleAcceptInvitation} onReject={handleRejectInvitation} isMine={isMine} />
          ) : isTyping ? (
            <BouncingDots className="text-primary-400 align-middle" />
          ) : (
            <Markdown
              children={content
                .replace(/<span\s+class=['"]text-red['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '255 100 100' : '220 50 50') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-orange['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '255 180 50' : '220 130 0') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-gold['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '255 215 0' : '180 140 0') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-green['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '80 220 120' : '20 150 60') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-blue['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '100 150 255' : '50 100 220') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-purple['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '180 130 255' : '130 80 200') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-pink['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '255 130 200' : '220 80 150') + ')">$1</span>')
                .replace(/<span\s+class=['"]text-gray['"][^>]*>([\s\S]*?)<\/span>/gi, '<span style="color:rgb(' + (isMine ? '180 180 180' : '100 100 100') + ')">$1</span>')
                .replace(/\[red\]([\s\S]*?)\[\/red\]/g, '<span style="color:rgb(' + (isMine ? '255 100 100' : '220 50 50') + ')">$1</span>')
                .replace(/\[orange\]([\s\S]*?)\[\/orange\]/g, '<span style="color:rgb(' + (isMine ? '255 180 50' : '220 130 0') + ')">$1</span>')
                .replace(/\[gold\]([\s\S]*?)\[\/gold\]/g, '<span style="color:rgb(' + (isMine ? '255 215 0' : '180 140 0') + ')">$1</span>')
                .replace(/\[green\]([\s\S]*?)\[\/green\]/g, '<span style="color:rgb(' + (isMine ? '80 220 120' : '20 150 60') + ')">$1</span>')
                .replace(/\[blue\]([\s\S]*?)\[\/blue\]/g, '<span style="color:rgb(' + (isMine ? '100 150 255' : '50 100 220') + ')">$1</span>')
                .replace(/\[purple\]([\s\S]*?)\[\/purple\]/g, '<span style="color:rgb(' + (isMine ? '180 130 255' : '130 80 200') + ')">$1</span>')
                .replace(/\[pink\]([\s\S]*?)\[\/pink\]/g, '<span style="color:rgb(' + (isMine ? '255 130 200' : '220 80 150') + ')">$1</span>')
                .replace(/\[gray\]([\s\S]*?)\[\/gray\]/g, '<span style="color:rgb(' + (isMine ? '180 180 180' : '100 100 100') + ')">$1</span>')
                .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
                .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')}
              remarkPlugins={[remarkGfm, remarkMath, remarkBreaks,
                // 标记行内代码，让 CodeRenderer 能区分 inline vs block
                remarkInlineCode]}
              rehypePlugins={[rehypeRaw, [rehypeSanitize, {
                ...defaultSchema,
                tagNames: [...(defaultSchema.tagNames || []), 'inlinecode'],
                attributes: {
                  ...defaultSchema.attributes,
                  a: [...(defaultSchema.attributes?.a || ['href']), 'class', 'target', 'rel'],
                  code: [...(defaultSchema.attributes?.code || []), 'class'],
                  span: [...(defaultSchema.attributes?.span || []), 'style'],
                  img: [...(defaultSchema.attributes?.img || ['src', 'alt']), 'class'],
                  div: [...(defaultSchema.attributes?.div || []), 'class'],
                },
              }], rehypeKatex]}
              components={{
                code: CodeRenderer,
                inlinecode: ({ children }) => (
                  <code className="bg-black/5 dark:bg-white/10 rounded px-1 py-0.5 text-[0.85em] inline-block max-w-full break-words">{children}</code>
                ),
                table: ({ node, ...props }) => <div className="markdown-table-wrapper"><table {...props} /></div>,
                th: ({ node, ...props }) => <th {...props} />,
                td: ({ node, ...props }) => <td {...props} />,
              }}
            />
          )}
          {fileAtts.length > 0 && (
            <div className={`${content ? 'mt-2 pt-2 border-t' : ''} flex flex-wrap gap-1.5 ${isMine ? 'border-white/20' : 'border-border'}`}>
              {fileAtts.map(att => {
                const token = localStorage.getItem('access_token')
                const dlUrl = `/api/fs/download/${att.file_id}?token=${token || ''}`
                const fid = att.file_id!
                const fname = att.name!
                const fsize = att.size!
                const fmime = att.mime_type!
                if (fmime.startsWith('image/')) return (
                  <button key={fid} onClick={() => setPreviewFile({ file_id: fid, name: fname, size: fsize, mime_type: fmime })} className="block max-w-full">
                    <img src={dlUrl} alt={fname} className="max-w-[280px] max-h-[200px] rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity border border-white/10" title={fname} loading="lazy" />
                  </button>
                )
                return (
                  <button key={fid} onClick={() => setPreviewFile({ file_id: fid, name: fname, size: fsize, mime_type: fmime })}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-colors ${isMine ? 'bg-white/10 hover:bg-white/20 text-white/90' : 'bg-canvas hover:bg-elevated text-textSecondary hover:text-textPrimary border border-border'}`}
                    title={`${fname} (${formatFileSize(fsize)})`}>
                    <FileIcon size={12} className={fileIconColor(fmime)} />
                    <span className="max-w-[100px] truncate">{fname}</span>
                    <span className="text-[10px] opacity-60">{formatFileSize(fsize)}</span>
                    <Download size={11} className="opacity-60" />
                  </button>
                )
              })}
            </div>
          )}

          {/* 回复按钮 */}
          {messageId != null && onReply && (
            <button
              onClick={() => onReply(messageId, senderName, content)}
              className={`absolute ${isMine ? '-left-[9px]' : '-right-[9px]'} top-0 md:opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg bg-elevated border border-border shadow-lg hover:bg-surface text-textMuted hover:text-primary-400`}
              title="回复"
            >
              <Reply size={12} />
            </button>
          )}
        </div>
        </div>
      </div>
    </div>
    {previewFile && <FilePreviewModal fileId={previewFile.file_id} fileName={previewFile.name} fileSize={previewFile.size} mimeType={previewFile.mime_type} onClose={() => setPreviewFile(null)} />}
  </>)
})
export default MessageBubble
