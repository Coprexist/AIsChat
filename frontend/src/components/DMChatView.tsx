import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import ChatView from './ChatView'
import DMSettingsPanel from './DMSettingsPanel'
import ProfileCard from './ProfileCard'
import { ArrowLeft, Bell, BellOff, Settings, Bot, User, Globe, ShieldAlert } from 'lucide-react'
import { getStateDotColor } from '../constants'
import { useT } from '../i18n/I18nContext'

interface DMChatViewProps {
  sessionId: string
  onMobileBack?: () => void
}

export default function DMChatView({ sessionId, onMobileBack }: DMChatViewProps) {
  const t = useT()
  const [partner, setPartner] = useState<{ id: number; name: string; type: string; state: string | null; is_federated?: boolean; avatar_url?: string | null } | null>(null)
  const [myDndUntil, setMyDndUntil] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!sessionId) return
    api.get(`/dm/${sessionId}`).then((data) => {
      setPartner(data.partner)
      setMyDndUntil(data.my_dnd_until || null)
    }).catch(console.error)
  }, [sessionId])

  const handleToggleDnd = async () => {
    try {
      if (myDndUntil) {
        await api.post(`/dm/${sessionId}/dnd/cancel`)
        setMyDndUntil(null)
      } else {
        await api.post(`/dm/${sessionId}/dnd`, { duration_minutes: null })
        setMyDndUntil('permanent')
      }
    } catch { /* ignore */ }
  }

  const stateColor = getStateDotColor(partner?.state)

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 私信头部 — 与群聊头部布局对齐 */}
      <div className="px-4 h-14 border-b border-border bg-surface flex items-center gap-2 shrink-0">
        {/* 移动端：打开会话列表 */}
        <button
          onClick={() => navigate('/chat')}
          className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
          title={t('dm.sessionList')}
        >
          <ArrowLeft size={20} />
        </button>

        {/* 对方头像（可点击 → 资料卡） */}
        <button
          onClick={() => partner && setShowProfile(true)}
          className="shrink-0"
          title={t('profileCard.viewProfile')}
        >
          {partner?.avatar_url ? (
            <div className="relative w-8 h-8 rounded-full overflow-hidden shrink-0">
              <div className={`absolute inset-0.5 rounded-full bg-gradient-to-bl ${
                partner?.type === 'system' ? 'from-rose-400 to-rose-600' : 'from-teal-400 to-teal-600'
              }`} />
              <img src={partner.avatar_url} alt={partner.name || ''} className="relative w-full h-full rounded-full object-cover" />
            </div>
          ) : (
            <div className={`w-8 h-8 rounded-full bg-gradient-to-bl flex items-center justify-center text-xs font-bold text-white overflow-hidden ${
              partner?.type === 'system' ? 'from-rose-400 to-rose-600' : 'from-teal-400 to-teal-600'
            }`}>
          {partner?.type === 'system' ? (
            <ShieldAlert size={14} className="text-white" />
          ) : (
            partner?.name?.charAt(0)?.toUpperCase() || '?'
          )}
        </div>
          )}
        </button>

        {/* 对方信息 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-textPrimary text-sm truncate">
              {partner?.name || t('dm.loading')}
            </span>
          </div>
          <span className="text-[10px] text-textMuted">
            {partner?.type === 'system' ? <><ShieldAlert size={12} className="inline text-rose-400" /> 系统通知</>
            : partner?.type === 'ai' ? <><Bot size={12} className="inline" /> {t('dm.ai')}</>
            : <><User size={12} className="inline" /> {t('dm.user')}</>}
            {partner?.type !== 'system' && partner?.state === 'active' && ` · ${t('dm.online')}`}
            {partner?.type !== 'system' && partner?.state === 'dnd' && ` · ${t('dm.dnd')}`}
            {partner?.type !== 'system' && (!partner?.state || partner?.state === 'offline') && ` · ${t('dm.offline')}`}
          </span>
        </div>

        {/* 联邦标签 */}
        {partner?.is_federated && (
          <span className="inline-flex items-center gap-1 text-[10px] text-primary-400 bg-primary-500/10 px-1.5 py-0.5 rounded-full shrink-0"
                title={t('chat.federatedGroup')}>
            <Globe size={11} />
            {t('chat.federated')}
          </span>
        )}

        {/* 在线状态指示 */}
        <span className={`inline-flex items-center gap-1 text-[10px] font-medium ${partner?.state === 'active' ? 'text-mint-400' : partner?.state === 'dnd' ? 'text-rose-400' : 'text-textMuted'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${stateColor}`} />
          {partner?.state === 'active' ? t('dm.online') : partner?.state === 'dnd' ? t('dm.shortDnd') : t('dm.offline')}
        </span>

        {/* 免打扰按钮 */}
        <button
          onClick={handleToggleDnd}
          className={`p-1 rounded-lg transition-colors ${
            myDndUntil
              ? 'text-rose-400 hover:bg-rose-400/10'
              : 'text-textMuted hover:text-rose-400 hover:bg-elevated'
          }`}
          title={myDndUntil ? t('dm.unmute') : t('dm.mute')}
        >
          {myDndUntil ? <BellOff size={14} /> : <Bell size={14} />}
        </button>

        {/* 设置按钮（与群聊头部的 Settings 对齐） */}
        <button
          onClick={() => setShowSettings(true)}
          className="p-1 rounded-lg hover:bg-elevated text-textMuted hover:text-textSecondary transition-colors"
          title={t('dm.dmSettings')}
        >
          <Settings size={14} />
        </button>
      </div>

      {/* 共享对话框 */}
      <ChatView conversationType="dm" conversationId={sessionId} />

      {/* 私信设置面板 */}
      {showSettings && (
        <DMSettingsPanel
          sessionId={sessionId}
          partner={partner}
          myDndUntil={myDndUntil}
          onClose={() => setShowSettings(false)}
          onDndChange={(dndUntil) => setMyDndUntil(dndUntil)}
        />
      )}

      {/* 资料卡 */}
      {showProfile && partner && (
        <ProfileCard
          entityType={partner.type as 'human' | 'ai'}
          entityId={partner.id}
          entityName={partner.name}
          state={partner.state || undefined}
          onClose={() => setShowProfile(false)}
        />
      )}
    </div>
  )
}
