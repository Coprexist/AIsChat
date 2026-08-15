import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useT } from '../i18n/I18nContext'
import { Users, MessageSquare, UserPlus, Check, X, Search, ArrowUpDown, ArrowLeft, Bot, User, Menu, Star } from 'lucide-react'
import { getStateDotColor } from '../constants'
import { getStatusTextStyle, BG_CANVAS_LIGHT, BG_CANVAS_DARK } from '../utils/statusColor.tsx'
import { useTheme } from '../context/ThemeContext'

interface Friend {
  id: number
  friend_type: string
  friend_id: number
  friend_name: string
  state: string | null
  avatar_url: string | null
  status_text: string | null
  status_color: string | null
  is_priority: boolean
  created_at: string | null
  last_dm_at: string | null
  friend_user_id?: number | null
}

interface FriendRequest {
  id: number
  requester_id: number
  requester_name: string | null
  requester_avatar_url: string | null
  target_type: string
  target_id: number
  target_name: string | null
  target_avatar_url: string | null
  status: string
  direction: string | null
  message: string | null
  auto_respond_friend_request?: boolean
  created_at: string | null
}

// 头像组件：优先显示真实头像，否则显示首字母
function AvatarPic({ url, name, size = 'md' }: { url: string | null | undefined; name: string; size?: 'sm' | 'md' | 'lg' }) {
  const sizeClass = size === 'sm' ? 'w-7 h-7 text-[10px]' : size === 'lg' ? 'w-12 h-12 text-xl' : 'w-10 h-10 text-lg'
  return (
    <div className={`${sizeClass} rounded-full shrink-0 overflow-hidden relative ${!url ? 'bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow shadow-primary-500/15' : ''}`}>
      {url ? (
        <>
          <div className="absolute inset-px rounded-full bg-gradient-to-br from-primary-500 to-primary-700/30" />
          <img src={url} alt={name} className="relative w-full h-full rounded-full object-cover" loading="lazy" />
        </>
      ) : (
        <span className="text-white font-bold">{name.charAt(0)}</span>
      )}
    </div>
  )
}

type Tab = 'friends' | 'requests'
type SortMode = 'smart' | 'alpha' | 'recent_chat' | 'added_time'

const SORT_OPTIONS: { value: SortMode; key: string }[] = [
  { value: 'smart', key: 'friends.smartSort' },
  { value: 'alpha', key: 'friends.sortAlpha' },
  { value: 'recent_chat', key: 'friends.sortRecent' },
  { value: 'added_time', key: 'friends.sortAdded' },
]

// 状态权重：在线 > 勿扰 > 离线
function stateWeight(s: string | null): number {
  switch (s) {
    case 'active': return 0
    case 'dnd': return 1
    default: return 2
  }
}

// 类型权重：人类 > AI
function typeWeight(t: string): number {
  return t === 'human' ? 0 : 1
}

function sortFriends(friends: Friend[], mode: SortMode): Friend[] {
  const list = [...friends]
  switch (mode) {
    case 'smart':
      // 在线在前 → 人类在前 → 字典序（中文首字母）
      list.sort((a, b) => {
        const s = stateWeight(a.state) - stateWeight(b.state)
        if (s !== 0) return s
        const t = typeWeight(a.friend_type) - typeWeight(b.friend_type)
        if (t !== 0) return t
        return a.friend_name.localeCompare(b.friend_name, 'zh-CN')
      })
      break
    case 'alpha':
      // 纯字典序
      list.sort((a, b) => a.friend_name.localeCompare(b.friend_name, 'zh-CN'))
      break
    case 'recent_chat':
      // 最近聊天时间越近越顶（无时间的排末尾）
      list.sort((a, b) => {
        const ta = a.last_dm_at ? new Date(a.last_dm_at).getTime() : 0
        const tb = b.last_dm_at ? new Date(b.last_dm_at).getTime() : 0
        return tb - ta
      })
      break
    case 'added_time':
      // 加好友时间越新越顶
      list.sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0
        return tb - ta
      })
      break
  }
  return list
}

export default function FriendsPage() {
  const t = useT()
  const [friends, setFriends] = useState<Friend[]>([])
  const [requests, setRequests] = useState<FriendRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('friends')
  const [sortMode, setSortMode] = useState<SortMode>('smart')
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  const { user } = useAuth()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const { openDrawer } = useOutletContext<{ openDrawer: () => void }>()

  useEffect(() => {
    loadAll()
  }, [])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [friendsRes, reqRes] = await Promise.all([
        api.get<Friend[]>('/friends'),
        api.get<FriendRequest[]>('/friends/requests'),
      ])
      setFriends(friendsRes)
      setRequests(reqRes.filter(r => r.status === 'pending'))
    } catch (err) {
      console.error('加载好友数据失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleStartDM = async (friendType: string, friendId: number, friendUserId?: number | null) => {
    try {
      const targetUserId = friendUserId || friendId
      const dm = await api.post(`/dm/${targetUserId}`)
      if (dm.session_id) {
        navigate(`/chat/dm/${dm.session_id}`)
      }
    } catch (err: any) {
      console.error('创建私信失败:', err)
    }
  }

  const handleAccept = async (requestId: number) => {
    const req = requests.find(r => r.id === requestId)
    if (req && req.direction === 'received' && req.auto_respond_friend_request) {
      if (!confirm(t('friends.autoRespondConfirm'))) {
        return
      }
    }
    try {
      await api.post(`/friends/requests/${requestId}/accept`)
      loadAll()
    } catch (err: any) {
      console.error('接受好友申请失败:', err)
    }
  }

  const handleReject = async (requestId: number) => {
    try {
      await api.post(`/friends/requests/${requestId}/reject`)
      loadAll()
    } catch (err: any) {
      console.error('拒绝好友申请失败:', err)
    }
  }

  const handleCancelSent = async (requestId: number) => {
    try {
      await api.post(`/friends/requests/${requestId}/reject`)
      loadAll()
    } catch (err: any) {
      console.error('撤回好友申请失败:', err)
    }
  }

  // 拆分收到和发出的申请
  const receivedRequests = requests.filter(r => r.direction === 'received')
  const sentRequests = requests.filter(r => r.direction === 'sent')
  const pendingCount = receivedRequests.length

  const stateIcon = (s: string | null) => (
    <span className={`w-2 h-2 rounded-full shrink-0 ${getStateDotColor(s)}`} />
  )

  // 排序 + 搜索过滤
  const sortedFriends = useMemo(() => {
    const sorted = sortFriends(friends, sortMode)
    if (!searchQuery.trim()) return sorted
    const q = searchQuery.trim().toLowerCase()
    return sorted.filter(f => f.friend_name.toLowerCase().includes(q))
  }, [friends, sortMode, searchQuery])

  // 搜索框组件（复用，缓存避免无关状态变化时重建）
  const searchBox = useMemo(() => (
    <div className="relative">
      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-textMuted" />
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder={t('friends.searchPlaceholder')}
        className="w-full pl-9 pr-8 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
        autoFocus={showSearch}
      />
      {searchQuery && (
        <button
          onClick={() => setSearchQuery('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded text-textMuted hover:text-textSecondary"
        >
          <X size={14} />
        </button>
      )}
    </div>
  ), [searchQuery, showSearch])

  return (
    <div className="h-full flex flex-col bg-canvas">
      {/* 头部 */}
      <div className="px-4 h-14 border-b border-border bg-surface flex items-center gap-2 shrink-0">
        <button
          onClick={openDrawer}
          className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
          title={t('chatlist.menu')}
        >
          <Menu size={18} />
        </button>
        <h1 className="font-semibold text-textPrimary text-sm flex items-center gap-2">
          <Users size={16} className="text-primary-400 hidden md:inline" />
          {tab === 'friends' ? t('friends.tabFriends') : t('friends.tabRequests')}
        </h1>

        {/* 排序 + 搜索按钮（仅好友列表 Tab） */}
        {tab === 'friends' && friends.length > 0 && (
          <div className="ml-auto flex items-center gap-1">
            {/* 排序下拉 */}
            <div className="relative">
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
                className="appearance-none pl-2 pr-6 py-1 rounded-lg border border-border bg-canvas text-[11px] text-textSecondary focus:outline-none focus:ring-1 focus:ring-primary-500/50 cursor-pointer"
              >
                {SORT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{t(o.key)}</option>
                ))}
              </select>
              <ArrowUpDown size={10} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-textMuted pointer-events-none" />
            </div>
            {/* 搜索按钮 */}
            <button
              onClick={() => setShowSearch(true)}
              className="p-1.5 rounded-lg hover:bg-elevated text-textMuted hover:text-textSecondary transition-colors"
              title={t('friends.searchButton')}
            >
              <Search size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Tab 切换 */}
      <div className="flex border-b border-border bg-surface shrink-0">
        <button
          onClick={() => setTab('friends')}
          className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
            tab === 'friends'
              ? 'text-primary-400 border-b-2 border-primary-400'
              : 'text-textMuted hover:text-textSecondary'
          }`}
        >
          {t('friends.tabFriends')}
        </button>
        <button
          onClick={() => setTab('requests')}
          className={`flex-1 py-2.5 text-xs font-medium transition-colors relative ${
            tab === 'requests'
              ? 'text-primary-400 border-b-2 border-primary-400'
              : 'text-textMuted hover:text-textSecondary'
          }`}
        >
          {t('friends.tabRequests')}
          {pendingCount > 0 && (
            <span className="absolute top-1 right-4 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold text-white bg-rose-500 rounded-full">
              {pendingCount}
            </span>
          )}
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto pb-[var(--safe-bottom)] md:pb-0">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500" />
          </div>
        ) : tab === 'friends' ? (
          /* 好友列表 */
          friends.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-textMuted">
              <Users size={40} className="mb-3 opacity-30" />
              <p className="text-sm">{t('friends.noFriends')}</p>
              <p className="text-xs mt-1">{t('friends.noFriendsHint')}</p>
            </div>
          ) : sortedFriends.length === 0 && searchQuery ? (
            <div className="flex flex-col items-center justify-center py-20 text-textMuted">
              <Search size={40} className="mb-3 opacity-30" />
              <p className="text-sm">{t('friends.noSearchResults')}</p>
              <p className="text-xs mt-1">{t('friends.tryOtherKeywords')}</p>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {sortedFriends.map((f) => (
                <button
                  key={`${f.friend_type}:${f.friend_id}`}
                  onClick={() => handleStartDM(f.friend_type, f.friend_id, f.friend_user_id)}
                  className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-elevated transition-colors text-left"
                >
                  <AvatarPic url={f.avatar_url} name={f.friend_name} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-textPrimary truncate">
                        {f.friend_name}
                      </span>
                      {f.status_text && (
                        <span className="text-xs font-medium truncate" style={f.status_color
                          ? getStatusTextStyle(f.status_color, theme === 'dark' ? BG_CANVAS_DARK : BG_CANVAS_LIGHT)
                          : undefined}>
                          · {f.status_text}
                        </span>
                      )}
                      {f.is_priority && <Star size={10} className="text-accent-400 fill-accent-400 shrink-0" />}
                      {stateIcon(f.state)}
                    </div>
                    <span className="text-xs text-textMuted">
                      {f.friend_type === 'ai' ? <><Bot size={12} className="inline" /> {t('friends.friendAi')}</> : <><User size={12} className="inline" /> {t('friends.friendHuman')}</>}
                    </span>
                  </div>
                  <MessageSquare size={16} className="text-textMuted shrink-0" />
                </button>
              ))}
            </div>
          )
        ) : (
          /* 好友申请 */
          receivedRequests.length === 0 && sentRequests.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-textMuted">
              <UserPlus size={40} className="mb-3 opacity-30" />
              <p className="text-sm">{t('friends.noPendingRequests')}</p>
              <p className="text-xs mt-1">{t('friends.pendingHint')}</p>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {/* 收到的申请 */}
              {receivedRequests.length > 0 && (
                <>
                  <div className="px-4 py-2 bg-surface sticky top-0 z-10 border-b border-border/50">
                    <span className="text-xs font-semibold text-textSecondary uppercase tracking-wider">{t('friends.receivedRequests')}{receivedRequests.length}</span>
                  </div>
                  {receivedRequests.map((req) => (
                    <div key={`recv-${req.id}`} className="px-4 py-3.5">
                      <div className="flex items-center gap-3">
                        <AvatarPic url={req.requester_avatar_url} name={req.requester_name || '?'} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-textPrimary truncate">
                              {req.requester_name || `${t('friends.userPrefix')}${req.requester_id}`}
                            </span>
                          </div>
                          <span className="text-xs text-textMuted">
                            {req.message || t('friends.defaultRequestMessage')}
                          </span>
                          {req.auto_respond_friend_request && (
                            <span className="inline-block mt-0.5 text-[10px] text-accent-400 bg-accent-400/10 px-1.5 py-0.5 rounded">
                              {t('friends.autoRespondWarning')}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={() => handleAccept(req.id)}
                            className="p-1.5 rounded-lg bg-mint-400/15 text-mint-400 hover:bg-mint-400/25 transition-colors"
                            title={t('friends.accept')}
                          >
                            <Check size={16} />
                          </button>
                          <button
                            onClick={() => handleReject(req.id)}
                            className="p-1.5 rounded-lg bg-rose-400/15 text-rose-400 hover:bg-rose-400/25 transition-colors"
                            title={t('friends.reject')}
                          >
                            <X size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              )}
              {/* 发出的申请 */}
              {sentRequests.length > 0 && (
                <>
                  <div className="px-4 py-2 bg-surface sticky top-0 z-10 border-b border-border/50">
                    <span className="text-xs font-semibold text-textSecondary uppercase tracking-wider">{t('friends.sentRequests')}{sentRequests.length}</span>
                  </div>
                  {sentRequests.map((req) => (
                    <div key={`sent-${req.id}`} className="px-4 py-3.5">
                      <div className="flex items-center gap-3">
                        <AvatarPic url={req.target_avatar_url} name={req.target_name || '?'} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-textPrimary truncate">
                              {req.target_name || `${t('friends.userPrefix')}${req.target_id}`}
                            </span>
                          </div>
                          <span className="text-xs text-textMuted">
                            {req.message || t('friends.sentRequestMessage')}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={() => handleCancelSent(req.id)}
                            className="p-1.5 rounded-lg bg-rose-400/15 text-rose-400 hover:bg-rose-400/25 transition-colors"
                            title={t('friends.cancelRequest')}
                          >
                            <X size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          )
        )}
      </div>

      {/* ── 搜索弹窗 ── */}
      {showSearch && (
        <>
          {/* 移动端：全屏 */}
          <div className="md:hidden fixed inset-0 z-50 bg-surface flex flex-col">
            <div className="px-4 h-14 border-b border-border flex items-center gap-3 shrink-0">
              <button
                onClick={() => { setShowSearch(false); setSearchQuery('') }}
                className="p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
              >
                <ArrowLeft size={20} />
              </button>
              <div className="flex-1">
                {searchBox}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto divide-y divide-border/50 pb-[var(--safe-bottom)]">
              {sortedFriends.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-textMuted">
                  <Search size={40} className="mb-3 opacity-30" />
                  <p className="text-sm">{t('friends.noSearchResults')}</p>
                </div>
              ) : (
                sortedFriends.map((f) => (
                  <button
                    key={`${f.friend_type}:${f.friend_id}`}
                    onClick={() => {
                      setShowSearch(false)
                      setSearchQuery('')
                      handleStartDM(f.friend_type, f.friend_id, f.friend_user_id)
                    }}
                    className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-elevated transition-colors text-left"
                  >
                    <AvatarPic url={f.avatar_url} name={f.friend_name} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-textPrimary truncate">{f.friend_name}</span>
                        {stateIcon(f.state)}
                      </div>
                      <span className="text-xs text-textMuted">
                        {f.friend_type === 'ai' ? <><Bot size={12} className="inline" /> {t('friends.friendAi')}</> : <><User size={12} className="inline" /> {t('friends.friendHuman')}</>}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* 桌面端：悬浮下拉 */}
          <div className="hidden md:block fixed inset-0 z-50" onClick={() => { setShowSearch(false); setSearchQuery('') }}>
            <div
              className="absolute top-[4.5rem] left-1/2 -translate-x-1/2 w-full max-w-sm"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="bg-elevated border border-border rounded-2xl shadow-2xl shadow-black/30 mx-4 overflow-hidden">
                <div className="p-3">
                  {searchBox}
                </div>
                {searchQuery.trim() && (
                  <div className="max-h-64 overflow-y-auto border-t border-border divide-y divide-border/50">
                    {sortedFriends.length === 0 ? (
                      <div className="py-6 text-center text-xs text-textMuted">{t('friends.searchEmptyDesktop')}</div>
                    ) : (
                      sortedFriends.slice(0, 8).map((f) => (
                        <button
                          key={`${f.friend_type}:${f.friend_id}`}
                          onClick={() => {
                            setShowSearch(false)
                            setSearchQuery('')
                            handleStartDM(f.friend_type, f.friend_id, f.friend_user_id)
                          }}
                          className="w-full flex items-center gap-3 px-4 py-3 hover:bg-canvas transition-colors text-left"
                        >
                          <AvatarPic url={f.avatar_url} name={f.friend_name} size="sm" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-textPrimary truncate">{f.friend_name}</span>
                              {stateIcon(f.state)}
                            </div>
                            <span className="text-[10px] text-textMuted">
                              {f.friend_type === 'ai' ? <><Bot size={12} className="inline" /> {t('friends.friendAi')}</> : <><User size={12} className="inline" /> {t('friends.friendHuman')}</>}
                            </span>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
