import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, MessageSquare, UserPlus, Bot, User, Star } from 'lucide-react'
import { api } from '../api/client'
import { getStateDotColor } from '../constants'
import { useT, useLang } from '../i18n/I18nContext'
import { getStatusTextStyle, BG_ELEVATED_LIGHT, BG_ELEVATED_DARK } from '../utils/statusColor.tsx'
import { formatMessageTime } from '../utils/time'
import { useTheme } from '../context/ThemeContext'

interface ProfileCardProps {
  entityType: 'human' | 'ai' | 'group'
  entityId: number
  entityName: string
  state?: string
  avatar_url?: string | null
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
  friendship_id: number | null
  is_priority: boolean
  last_active_at: string | null
}

export default function ProfileCard({ entityType, entityId, entityName, state, avatar_url, onClose }: ProfileCardProps) {
  const t = useT()
  const lang = useLang()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [fullImg, setFullImg] = useState<string | null>(null)
  const isActive = profile?.state === 'active' || state === 'active'
  const [loading, setLoading] = useState(entityType === 'group' ? false : true)
  const [sending, setSending] = useState(false)
  const [showAddFriend, setShowAddFriend] = useState(false)
  const [friendMessage, setFriendMessage] = useState('')
  const [addingFriend, setAddingFriend] = useState(false)
  const [isPriority, setIsPriority] = useState(false)
  const [togglingPriority, setTogglingPriority] = useState(false)

  // 群聊不需要加载 profile（数据直接从 props 来）
  useEffect(() => {
    if (entityType === 'group') return
    setLoading(true)
    api.get<ProfileData>(`/user/profile/${entityType}/${entityId}`)
      .then((data) => { setProfile(data); setIsPriority(data.is_priority || false) })
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
  }, [entityType, entityId])

  const handleTogglePriority = async () => {
    const fid = profile?.friendship_id
    if (!fid) return
    setTogglingPriority(true)
    try {
      const r = await api.post<{ is_priority: boolean }>(`/friends/${fid}/toggle-priority`)
      setIsPriority(r.is_priority)
    } catch { /* ignore */ }
    finally { setTogglingPriority(false) }
  }

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
      case 'inactive': return t('dm.offline')
      case 'blocked': return t('profileCard.blocked')
      default: return ''
    }
  }

  const displayState = profile?.state || state

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
        <div
          className="bg-elevated border border-border rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl shadow-black/30"
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
  const avatarUrl = entityType === 'group' ? (avatar_url || profile?.avatar_url) : profile?.avatar_url
  const bio = profile?.bio
  const statusText = profile?.status_text
  const statusColor = profile?.status_color
  const ownerName = profile?.owner_name
  const createdAt = profile?.created_at
  const isFriend = profile?.is_friend ?? false
  const isGroup = entityType === 'group'
  const avatarShape = isGroup ? 'rounded-xl' : 'rounded-full'

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-elevated border border-border rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl shadow-black/30 pb-[var(--safe-bottom)] md:pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* 头像 */}
            <button
              onClick={() => avatarUrl && setFullImg(avatarUrl)}
              className={`relative w-14 h-14 ${avatarShape} flex items-center justify-center shrink-0 overflow-hidden ${
                isGroup ? 'bg-elevated' : entityType === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
              }`}>
              {avatarUrl ? (
                <img src={avatarUrl} alt={name} className={`w-full h-full ${avatarShape} object-cover hover:opacity-80 transition-opacity`} />
              ) : (
                <div className={`w-full h-full ${avatarShape} bg-gradient-to-bl flex items-center justify-center ${
                  isGroup ? 'bg-primary-500/10' : entityType === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
                }`}>
                  <span className="text-xl font-bold text-white">{name.charAt(0).toUpperCase()}</span>
                </div>
              )}
            </button>
            <div className="min-w-0">
              <h3 className="font-semibold text-textPrimary text-base truncate">{name}</h3>
              <div className="flex items-center gap-1.5 text-sm text-textSecondary">
                {entityType === 'ai' && <span>{t('profileCard.aiPrefix')}</span>}
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
        <div className="mb-3">
          <p className="text-sm text-textMuted leading-relaxed italic">{bio || t('profileCard.bioEmpty')}</p>
        </div>

        {/* 详细信息 */}
        <div className="mb-4 space-y-1 text-xs text-textMuted">
          {entityType === 'ai' && ownerName && (
            <div>{t('profileCard.creator')}: {ownerName}</div>
          )}
          <div className="flex flex-wrap gap-x-2">
            {createdAt && (
              <span>{t('profileCard.registeredOn')}: {new Date(createdAt).toLocaleDateString('zh-CN')}</span>
            )}
            {isActive ? (
              <span className="text-green-500">{t('dm.online')}</span>
            ) : profile?.last_active_at ? (
              <span>{t('dm.lastActive')} {formatMessageTime(profile.last_active_at, lang)}</span>
            ) : null}
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="space-y-2">
            {/* 发消息（群聊跳过好友操作） */}
          {isGroup ? null : (
            <>
          {isFriend && profile?.friendship_id && (
            <button
              onClick={handleTogglePriority}
              disabled={togglingPriority}
              className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl border text-sm font-medium transition-colors ${
                isPriority
                  ? 'bg-amber-400/10 border-amber-400/30 text-amber-400 hover:bg-amber-400/20'
                  : 'bg-canvas border-border text-textSecondary hover:bg-elevated'
              }`}
            >
              <Star size={16} fill={isPriority ? 'currentColor' : 'none'} />
              {isPriority ? t('profileCard.priorityOn') || '已特别关心' : t('profileCard.priorityOff') || '设为特别关心'}
            </button>
          )}

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
          </>
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

          {/* 群聊信息 */}
          {isGroup && (
            <div className="text-[11px] text-textMuted text-center pt-2">
              {createdAt && <span>{t('profileCard.createdOn') || '创建于'} {new Date(createdAt).toLocaleDateString('zh-CN')}</span>}
            </div>
          )}

          {/* 用于群聊时隐藏发消息按钮上方的好友相关操作 */}
          {isGroup ? null : (
            <>
              {isFriend && profile?.friendship_id && (
                <button
                  onClick={handleTogglePriority}
                  disabled={togglingPriority}
                  className={`w-full flex items-center justify-center gap-2 py-2 rounded-xl border text-sm font-medium transition-colors ${
                    isPriority
                      ? 'bg-amber-400/10 border-amber-400/30 text-amber-400 hover:bg-amber-400/20'
                      : 'bg-canvas border-border text-textSecondary hover:bg-elevated'
                  }`}
                >
                  <Star size={16} fill={isPriority ? 'currentColor' : 'none'} />
                  {isPriority ? t('profileCard.priorityOn') || '已特别关心' : t('profileCard.priorityOff') || '设为特别关心'}
                </button>
              )}
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
            </>
          )}
        </div>
      </div>

      {/* 查看大图 */}
      {fullImg && (
        <div className="fixed inset-0 bg-black/90 z-[60] flex items-center justify-center" onClick={() => setFullImg(null)}>
          <img src={fullImg} alt="" className="max-w-[90vw] max-h-[90vh] object-contain" />
          <button onClick={() => setFullImg(null)} className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white hover:bg-black/70">
            <X size={24} />
          </button>
        </div>
      )}
    </div>
  )
}
