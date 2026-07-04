import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Plus, BellOff, Menu, UserPlus, Users, Bot, Globe, ShieldAlert } from 'lucide-react'
import { getStateDotColor, CHAT_REFRESH_EVENT } from '../constants'
import { formatRelativeTime } from '../utils/time'
import { getStatusTextStyle, BG_SURFACE_LIGHT, BG_SURFACE_DARK } from '../utils/statusColor'
import { useTheme } from '../context/ThemeContext'
import { useLang, useT } from '../i18n/I18nContext'

interface Group {
  id: number
  name: string
  unread_count: number
  has_mention: boolean
  last_message_preview: string | null
  last_message_at: string | null
  dnd_until: string | null
  member_avatars: string[]  // v0.6.0: 前 4 个成员头像
  is_federated?: boolean
}

interface DMSession {
  session_id: string
  partner: { id: number; name: string; type: string; state: string | null; avatar_url: string | null; status_text: string | null; status_color: string | null }
  last_message_preview: string | null
  last_message_at: string | null
  unread_count: number
  is_federated?: boolean
}

interface ChatSidebarProps {
  activeGroupId: number | null
  activeSessionId: string | null
  onCreateGroup: () => void
  onAddFriend: () => void
  openDrawer: () => void
  /** 移动端选中对话后隐藏侧边栏 */
  hideOnMobile: boolean
  /** 移动端返回当前对话（侧边栏作为 overlay 时） */
  onMobileBack?: () => void
  /** 移动端全屏覆盖模式 */
  mobileFullscreen?: boolean
}

export default function ChatSidebar({
  activeGroupId,
  activeSessionId,
  onCreateGroup,
  onAddFriend,
  openDrawer,
  hideOnMobile,
  onMobileBack,
  mobileFullscreen,
}: ChatSidebarProps) {
  const [groups, setGroups] = useState<Group[]>([])
  const [dmSessions, setDmSessions] = useState<DMSession[]>([])
  const [showPlusMenu, setShowPlusMenu] = useState(false)
  const navigate = useNavigate()

  const loadGroups = () => api.get('/groups').then(setGroups).catch(() => {})
  const loadDMSessions = () => api.get('/dm/sessions').then(setDmSessions).catch(() => {})

  // 初始加载
  useEffect(() => {
    loadGroups()
    loadDMSessions()
  }, [])

  // 活跃对话变化时刷新（延迟等 mark-as-read 完成）
  useEffect(() => {
    const timer = setTimeout(() => {
      loadGroups()
      loadDMSessions()
    }, 300)
    return () => clearTimeout(timer)
  }, [activeGroupId, activeSessionId])

  // 用 ref 持有最新 active ID，避免 chat-refresh 事件监听器随对话切换而重建
  const activeGroupIdRef = useRef(activeGroupId)
  activeGroupIdRef.current = activeGroupId
  const activeSessionIdRef = useRef(activeSessionId)
  activeSessionIdRef.current = activeSessionId

  // 去抖 ref：防止高频 chat-refresh 导致请求风暴
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reloadDebounced = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      loadGroups()
      loadDMSessions()
    }, 500)
  }

  // chat-refresh 事件 — 监听器只注册一次（[] 依赖），通过 ref 读取最新 ID
  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const t = e.detail?.type
      if (t === 'dm_notification' || t === 'unread_update' || t === 'message_sent') {
        reloadDebounced()
      }
    }
    window.addEventListener(CHAT_REFRESH_EVENT, handler as EventListener)
    return () => {
      window.removeEventListener(CHAT_REFRESH_EVENT, handler as EventListener)
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  // 排序：按 last_message_at 降序（最新在前），无时间戳的排末尾
  const sortByTime = (a: any, b: any) => {
    const ta = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
    const tb = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
    return tb - ta
  }

  // 只显示普通群聊，按最后消息时间排序
  const regularGroups = groups
    .filter((g: any) => !g.name?.startsWith('DM:'))
    .sort(sortByTime)

  // DM 会话按最后消息时间排序
  const sortedDMSessions = [...dmSessions].sort(sortByTime)

  const lang = useLang()
  const t = useT()
  const { theme } = useTheme()

  // 群聊头像组：4 个头像的 2×2 网格或默认图标
  const GroupAvatarGroup = ({ avatars }: { avatars: string[] }) => {
    if (avatars.length === 0) {
      return (
        <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0">
          <Users size={14} className="text-primary-400/70" />
        </div>
      )
    }
    return (
      <div className="w-9 h-9 rounded-lg bg-elevated grid grid-cols-2 grid-rows-2 gap-px overflow-hidden shrink-0">
        {avatars.slice(0, 4).map((url, i) => (
          <div key={i} className="bg-canvas flex items-center justify-center">
            <img src={url} alt="" className="w-full h-full object-cover" />
          </div>
        ))}
        {avatars.length < 4 && Array.from({ length: 4 - avatars.length }).map((_, i) => (
          <div key={`empty-${i}`} className="bg-canvas flex items-center justify-center">
            <Users size={8} className="text-textMuted/40" />
          </div>
        ))}
      </div>
    )
  }

  const nothingSelected = !activeGroupId && !activeSessionId

  return (
    <div className={`w-full bg-surface border-r border-border shrink-0 flex-col flex h-full ${
      hideOnMobile && !nothingSelected ? 'hidden' : 'flex'
    } md:flex`}>
      {/* 标题 */}
      <div className="px-3 h-14 border-b border-border font-medium text-sm flex items-center justify-between text-textPrimary shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={openDrawer}
            className="md:hidden p-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
            title={t('chatlist.menu')}
          >
            <Menu size={18} />
          </button>
          <span>{t('chatlist.chat')}</span>
        </div>
        <div className="relative">
          <button
            onClick={() => setShowPlusMenu(!showPlusMenu)}
            className="p-1 rounded-lg hover:bg-elevated text-textMuted hover:text-primary-400 transition-colors"
            title={t('chatlist.createNewGroup')}
          >
            <Plus size={16} />
          </button>
          {showPlusMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowPlusMenu(false)} />
              <div className="absolute right-0 top-full mt-1 w-36 bg-elevated border border-border rounded-xl shadow-xl z-50 py-1 overflow-hidden">
                <button
                  onClick={() => { setShowPlusMenu(false); onCreateGroup() }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-textSecondary hover:bg-canvas hover:text-textPrimary transition-colors"
                >
                  <Users size={15} />
                  {t('chatlist.createGroup')}
                </button>
                <button
                  onClick={() => { setShowPlusMenu(false); onAddFriend() }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-textSecondary hover:bg-canvas hover:text-textPrimary transition-colors"
                >
                  <UserPlus size={15} />
                  {t('friends.add')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {/* ── 群聊 ── */}
        <div className="px-3 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-textMuted">
          {t('chatlist.chat')}
        </div>
        {regularGroups.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-textMuted">
            {t('chatlist.createFirstGroup')}
          </div>
        ) : (
          regularGroups.map((g) => (
            <button
              key={`group-${g.id}`}
              onClick={() => {
                if (g.id === activeGroupId && mobileFullscreen) {
                  onMobileBack?.()
                } else {
                  navigate(`/chat/gm/${g.id}`)
                }
              }}
              className={`w-full text-left px-3 py-2 text-sm transition-all duration-150 ${
                g.id === activeGroupId
                  ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300 border-l-2 border-primary-400'
                  : 'hover:bg-elevated text-textSecondary border-l-2 border-transparent'
              }`}
            >
              <div className="flex items-center gap-2.5">
                {/* 群聊头像组 */}
                <GroupAvatarGroup avatars={g.member_avatars || []} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="font-medium flex items-center gap-1 min-w-0">
                      {g.is_federated && <Globe size={11} className="text-primary-400 shrink-0" />}
                      <span className="truncate block">{g.name}</span>
                    </div>
                    {g.unread_count > 0 && (
                      <span className={`shrink-0 ml-1 min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-bold text-white ${
                        g.has_mention
                          ? 'bg-rose-500 shadow-sm shadow-rose-500/30'
                          : 'bg-primary-500/80'
                      }`}>
                        {g.unread_count > 99 ? '99+' : g.unread_count}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-textMuted mt-0.5 flex items-center gap-1 min-w-0">
                    {g.dnd_until && <BellOff size={10} className="text-rose-400 shrink-0" />}
                    {g.has_mention && !g.dnd_until && (
                      <span className="text-rose-400 font-medium shrink-0">{t('chatlist.atYou')}</span>
                    )}
                    <span className="min-w-0 flex-1" style={{ display: 'block' }}>
                      <span className="truncate block">{g.last_message_preview || t('chatlist.noMessages')}</span>
                    </span>
                    {g.last_message_at && (
                      <span className="shrink-0">{formatRelativeTime(g.last_message_at, lang)}</span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))
        )}

        {/* ── 私信 ── */}
        {sortedDMSessions.length > 0 && (
          <>
            <div className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-textMuted">
              {t('chatlist.dm')}
            </div>
            {sortedDMSessions.map((s) => (
              <button
                key={`dm-${s.session_id}`}
                onClick={() => {
                  if (s.session_id === activeSessionId && mobileFullscreen) {
                    onMobileBack?.()
                  } else {
                    navigate(`/chat/dm/${s.session_id}`)
                  }
                }}
                className={`w-full text-left px-3 py-2 text-sm transition-all duration-150 ${
                  s.session_id === activeSessionId
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300 border-l-2 border-primary-400'
                    : 'hover:bg-elevated text-textSecondary border-l-2 border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  {/* 对方头像 */}
                  <div className="w-9 h-9 rounded-full relative shrink-0 overflow-hidden">
                    {s.partner.avatar_url ? (
                      <>
                        <div className={`absolute inset-0.5 rounded-full bg-gradient-to-bl ${
                          s.partner.type === 'system' ? 'from-rose-400 to-rose-600' : 'from-teal-400 to-teal-600'
                        }`} />
                        <img src={s.partner.avatar_url} alt="" className="relative w-full h-full rounded-full object-cover" />
                      </>
                    ) : (
                      <div className={`w-full h-full rounded-full bg-gradient-to-bl flex items-center justify-center ${
                        s.partner.type === 'system' ? 'from-rose-400 to-rose-600' : 'from-teal-400 to-teal-600'
                      }`}>
                        {s.partner.type === 'system' ? (
                          <ShieldAlert size={16} className="text-white" />
                        ) : (
                          <span className="text-xs font-bold text-white">{s.partner.name?.charAt(0)?.toUpperCase() || '?'}</span>
                        )}
                      </div>
                    )}
                    {s.partner.type !== 'system' && (
                      <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-surface ${getStateDotColor(s.partner.state)}`} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <div className="font-medium flex items-center gap-1.5 min-w-0">
                        {s.partner.type === 'system' && <ShieldAlert size={11} className="shrink-0 text-rose-400" />}
                        {s.partner.type === 'ai' && <Bot size={11} className="shrink-0 text-mint-400" />}
                        {s.is_federated && <Globe size={11} className="text-primary-400 shrink-0" />}
                        <span className="truncate">{s.partner.name}</span>
                        {s.partner.status_text && (
                          <span className="text-[11px] font-medium truncate" style={s.partner.status_color
                            ? getStatusTextStyle(s.partner.status_color, theme === 'dark' ? BG_SURFACE_DARK : BG_SURFACE_LIGHT)
                            : undefined}>
                            · {s.partner.status_text}
                          </span>
                        )}
                      </div>
                      {s.unread_count > 0 && (
                        <span className="shrink-0 ml-1 min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-bold text-white bg-primary-500/80">
                          {s.unread_count > 99 ? '99+' : s.unread_count}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-textMuted mt-0.5 flex items-center gap-1 min-w-0">
                      <span className="min-w-0 flex-1" style={{ display: 'block' }}>
                        <span className="truncate block">{s.last_message_preview || t('chatlist.noMessages')}</span>
                      </span>
                      {s.last_message_at && (
                        <span className="shrink-0">{formatRelativeTime(s.last_message_at, lang)}</span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </>
        )}

      </div>

    </div>
  )
}
