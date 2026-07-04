import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, MessageSquare, UserPlus, Bot, User } from 'lucide-react'
import { api } from '../api/client'
import { getStateDotColor } from '../constants'
import { useT } from '../i18n/I18nContext'
import { getStatusTextStyle, BG_ELEVATED_LIGHT, BG_ELEVATED_DARK } from '../utils/statusColor'
import { useTheme } from '../context/ThemeContext'

interface ProfileCardProps {
  entityType: 'human' | 'ai'
  entityId: number
  entityName: string
  state?: string
  onClose: () => void
}

interface ProfileData {
  entity_type: string
  entity_id: number
  name: string
  avatar_url: string | null
  bio: string | null
  status_text: string | null
  status_color: string | null
  state?: string
  created_at: string | null
  owner_name: string | null
  is_friend: boolean
}

export default function ProfileCard({ entityType, entityId, entityName, state, onClose }: ProfileCardProps) {
  const t = useT()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  // 加好友
  const [showAddFriend, setShowAddFriend] = useState(false)
  const [friendMessage, setFriendMessage] = useState('')
  const [addingFriend, setAddingFriend] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.get<ProfileData>(`/user/profile/${entityType}/${entityId}`)
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
  }, [entityType, entityId])

  const handleSendDM = async () => {
    setSending(true)
    try {
      const dm = await api.post<{ session_id: string }>(`/dm/${entityId}`)
      if (dm.session_id) {
        onClose()
        navigate(`/chat/dm/${dm.session_id}`)
      }
    } catch (err: any) {
      alert(err.message || t('error.startDmFailed'))
    } finally {
      setSending(false)
    }
  }

  const handleAddFriend = async () => {
    setAddingFriend(true)
    try {
      await api.post('/friends/requests', {
        target_type: entityType,
        target_id: entityId,
        message: friendMessage.trim() || undefined,
      })
      setProfile(prev => prev ? { ...prev, is_friend: true } : null)
      setShowAddFriend(false)
      setFriendMessage('')
      alert(t('search.addFriendSuccess'))
    } catch (err: any) {
      alert(err.message || t('search.addFriendFailed'))
    } finally {
      setAddingFriend(false)
    }
  }

  const getStateText = (s?: string) => {
    switch (s) {
      case 'active': return t('dm.online')
      case 'dnd': return t('dm.dnd')
      case 'offline': return t('dm.offline')
      case 'blocked': return t('profileCard.blocked')
      default: return ''
    }
  }

  const displayState = profile?.state || state

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
        <div
          className="bg-elevated border border-border rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl shadow-black/30"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full" />
          </div>
        </div>
      </div>
    )
  }

  const name = profile?.name || entityName
  const avatarUrl = profile?.avatar_url
  const bio = profile?.bio
  const statusText = profile?.status_text
  const statusColor = profile?.status_color
  const ownerName = profile?.owner_name
  const createdAt = profile?.created_at
  const isFriend = profile?.is_friend ?? false

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-elevated border border-border rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl shadow-black/30 pb-[var(--safe-bottom)] md:pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* 头像 */}
            <div className={`relative w-14 h-14 rounded-full flex items-center justify-center shrink-0 overflow-hidden ${
              entityType === 'human'
                ? 'from-primary-500 to-primary-700'
                : 'from-teal-400 to-teal-600'
            }`}>
              {avatarUrl ? (
                <>
                  <div className={`absolute inset-0.5 rounded-full bg-gradient-to-bl ${
                    entityType === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
                  }`} />
                  <img src={avatarUrl} alt={name} className="relative w-full h-full rounded-full object-cover" />
                </>
              ) : (
                <div className={`w-full h-full rounded-full bg-gradient-to-bl flex items-center justify-center ${
                  entityType === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
                }`}>
                  <span className="text-xl font-bold text-white">{name.charAt(0).toUpperCase()}</span>
                </div>
              )}
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-textPrimary text-base truncate">{name}</h3>
              <div className="flex items-center gap-1.5 text-sm text-textSecondary">
                <span className={`w-2 h-2 rounded-full shrink-0 ${getStateDotColor(displayState)}`} />
                <span>{entityType === 'ai' ? `AI · ${getStateText(displayState)}` : t('profileCard.human')}</span>
                {statusText && (
                  <span className="font-medium truncate" style={statusColor
                    ? getStatusTextStyle(statusColor, theme === 'dark' ? BG_ELEVATED_DARK : BG_ELEVATED_LIGHT)
                    : undefined}>
                    · {statusText}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-canvas rounded-lg text-textMuted hover:text-textSecondary shrink-0">
            <X size={20} />
          </button>
        </div>

        {/* 简介 */}
        {bio && (
          <div className="mb-3">
            <p className="text-sm text-textSecondary leading-relaxed">{bio}</p>
          </div>
        )}

        {/* 详细信息 */}
        <div className="mb-4 space-y-1 text-xs text-textMuted">
          {entityType === 'ai' && ownerName && (
            <div className="flex items-center gap-1.5">
              <User size={12} />
              <span>{t('profileCard.creator')}: {ownerName}</span>
            </div>
          )}
          {createdAt && (
            <div className="flex items-center gap-1.5">
              {entityType === 'ai' ? <Bot size={12} /> : <User size={12} />}
              <span>{t('profileCard.registeredOn')}: {new Date(createdAt).toLocaleDateString('zh-CN')}</span>
            </div>
          )}
          {entityType === 'ai' && (
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${getStateDotColor(displayState)}`} />
              <span>{getStateText(displayState) || displayState}</span>
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="space-y-2">
          {/* 加好友区域 */}
          {!isFriend && (
            showAddFriend ? (
              <div className="space-y-2">
                <textarea
                  value={friendMessage}
                  onChange={(e) => setFriendMessage(e.target.value)}
                  placeholder={t('profileCard.friendMessagePlaceholder')}
                  rows={2}
                  maxLength={200}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => { setShowAddFriend(false); setFriendMessage('') }}
                    className="flex-1 py-2 text-xs border border-border rounded-lg hover:bg-canvas text-textSecondary transition-colors"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    onClick={handleAddFriend}
                    disabled={addingFriend}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs rounded-lg bg-mint-400 text-white hover:bg-mint-500 disabled:opacity-40 transition-colors"
                  >
                    <UserPlus size={12} />
                    {addingFriend ? '...' : t('profileCard.sendRequest')}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowAddFriend(true)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-mint-400/10 border border-mint-400/20 text-mint-400 hover:bg-mint-400/20 transition-colors text-sm font-medium"
              >
                <UserPlus size={16} />
                {t('profileCard.addFriend')}
              </button>
            )
          )}

          {/* 发消息 */}
          <button
            onClick={handleSendDM}
            disabled={sending}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-400 disabled:opacity-30 transition-all text-sm font-medium shadow-lg shadow-primary-500/20"
          >
            <MessageSquare size={16} />
            {sending ? t('profileCard.sending') : isFriend ? t('profileCard.sendDM') : t('profileCard.sendDM')}
          </button>
        </div>
      </div>
    </div>
  )
}
