import { Check, X, Users } from 'lucide-react'
import { useT } from '../i18n/I18nContext'

interface InvitationCardProps {
  invitationId: number
  groupName: string
  inviterName: string
  message?: string
  status: 'pending' | 'accepted' | 'rejected'
  onAccept: (invitationId: number) => void
  onReject: (invitationId: number) => void
}

export default function InvitationCard({
  invitationId, groupName, inviterName, message, status,
  onAccept, onReject,
}: InvitationCardProps) {
  const t = useT()

  const isResolved = status !== 'pending'

  return (
    <div className={`
      rounded-xl border-2 overflow-hidden transition-all
      ${isResolved
        ? 'border-border bg-canvas/50'
        : 'border-mint-400/40 bg-mint-50/30 dark:bg-mint-900/10'}
    `}>
      {/* 头部 */}
      <div className="flex items-center gap-2 px-4 pt-3 pb-2">
        <div className={`
          w-8 h-8 rounded-full flex items-center justify-center
          ${isResolved
            ? 'bg-border text-textMuted'
            : 'bg-mint-400/20 text-mint-500'}
        `}>
          {status === 'accepted' ? <Check size={16} /> :
           status === 'rejected' ? <X size={16} /> :
           <Users size={16} />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-textPrimary truncate">
            {t('invitation.title').replace('{inviter}', inviterName)}
          </p>
          <p className="text-xs text-textSecondary truncate">
            {t('invitation.groupLabel')}：<span className="text-textPrimary font-medium">{groupName}</span>
          </p>
        </div>
        {/* 状态标签 */}
        {isResolved && (
          <span className={`
            shrink-0 text-xs px-2 py-0.5 rounded-full font-medium
            ${status === 'accepted'
              ? 'bg-mint-100 dark:bg-mint-900/30 text-mint-600 dark:text-mint-400'
              : 'bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400'}
          `}>
            {status === 'accepted' ? t('invitation.accepted') : t('invitation.rejected')}
          </span>
        )}
      </div>

      {/* 附言 */}
      {message && (
        <div className="px-4 pb-1">
          <p className="text-xs text-textSecondary italic">"{message}"</p>
        </div>
      )}

      {/* 按钮区（仅 pending） */}
      {!isResolved && (
        <div className="flex gap-2 px-4 pb-3 pt-1">
          <button
            onClick={(e) => { e.stopPropagation(); onAccept(invitationId) }}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5
              bg-mint-500 hover:bg-mint-600 text-white text-sm font-medium
              rounded-lg transition-colors"
          >
            <Check size={14} />
            {t('invitation.accept')}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onReject(invitationId) }}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5
              bg-canvas hover:bg-hover text-textSecondary hover:text-textPrimary text-sm
              rounded-lg border border-border transition-colors"
          >
            <X size={14} />
            {t('invitation.reject')}
          </button>
        </div>
      )}
    </div>
  )
}
