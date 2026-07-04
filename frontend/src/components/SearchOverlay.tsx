import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X, MessageSquare, UserPlus, Bot, User } from 'lucide-react'
import { api } from '../api/client'
import { getStateDotColor } from '../constants'
import { useT } from '../i18n/I18nContext'
import ProfileCard from './ProfileCard'

interface SearchResult {
  id: number
  type: 'human' | 'ai'
  name: string
  avatar_url: string | null
  owner_name: string | null
  state: string | null
  is_friend?: boolean
}

export default function SearchOverlay() {
  const t = useT()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sendingDM, setSendingDM] = useState<string | null>(null)
  // 加好友留言
  const [addFriendTarget, setAddFriendTarget] = useState<string | null>(null) // `${type}:${id}`
  const [friendMessage, setFriendMessage] = useState('')
  const [addingFriend, setAddingFriend] = useState(false)
  // 资料卡
  const [profileCard, setProfileCard] = useState<{
    type: 'human' | 'ai'; id: number; name: string; state: string | null
  } | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // 防抖搜索
  useEffect(() => {
    if (query.length < 1) {
      setResults([])
      setShowDropdown(false)
      return
    }
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await api.get<{ results: SearchResult[] }>(
          `/search?q=${encodeURIComponent(query)}`
        )
        setResults(data.results)
        setShowDropdown(true)
      } catch (err) {
        console.error('搜索失败:', err)
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  // 点击外部关闭
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSendDM = async (item: SearchResult) => {
    const key = `${item.type}:${item.id}`
    setSendingDM(key)
    try {
      const dm = await api.post<{ session_id: string }>(`/dm/${item.id}`)
      if (dm.session_id) {
        navigate(`/chat/dm/${dm.session_id}`)
        setShowDropdown(false)
        setQuery('')
      }
    } catch (err: any) {
      alert(err.message || t('search.sendDMFailed'))
    } finally {
      setSendingDM(null)
    }
  }

  const handleAddFriend = async (item: SearchResult) => {
    const key = `${item.type}:${item.id}`
    setAddingFriend(true)
    try {
      await api.post('/friends/requests', {
        target_type: item.type,
        target_id: item.id,
        message: friendMessage.trim() || undefined,
      })
      setResults(prev => prev.map(r =>
        r.type === item.type && r.id === item.id ? { ...r, is_friend: true } : r
      ))
      setAddFriendTarget(null)
      setFriendMessage('')
      alert(t('search.addFriendSuccess'))
    } catch (err: any) {
      alert(err.message || t('search.addFriendFailed'))
    } finally {
      setAddingFriend(false)
    }
  }

  const openProfile = (item: SearchResult) => {
    setProfileCard({
      type: item.type,
      id: item.id,
      name: item.name,
      state: item.state,
    })
  }

  return (
    <div ref={containerRef} className="relative">
      {/* 搜索框 */}
      <div className="flex items-center gap-2 px-3 py-2 bg-canvas border border-border rounded-xl">
        <Search size={14} className="text-textMuted shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setShowDropdown(true)}
          placeholder={t('search.placeholder')}
          className="flex-1 bg-transparent text-sm text-textPrimary placeholder:text-textMuted focus:outline-none"
        />
        {query && (
          <button onClick={() => { setQuery(''); setResults([]) }} className="text-textMuted hover:text-textSecondary">
            <X size={14} />
          </button>
        )}
      </div>

      {/* 下拉结果 */}
      {showDropdown && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-elevated border border-border rounded-xl shadow-2xl shadow-black/30 z-50 max-h-80 overflow-y-auto">
          {loading ? (
            <div className="p-3 text-sm text-textMuted text-center">{t('search.searching')}</div>
          ) : results.length === 0 ? (
            <div className="p-3 text-sm text-textMuted text-center">{t('search.noResults')}</div>
          ) : (
            results.map((item) => {
              const key = `${item.type}:${item.id}`
              const isAddingThis = addFriendTarget === key

              return (
              <div key={key} className="flex items-center gap-3 px-3 py-2.5 hover:bg-canvas/50">
                {/* 头像（可点击 → 资料卡） */}
                <button
                  onClick={() => openProfile(item)}
                  className="shrink-0"
                >
                  <div className="relative w-8 h-8 rounded-full shrink-0 overflow-hidden">
                    {item.avatar_url ? (
                      <>
                        <div className={`absolute inset-0.5 rounded-full bg-gradient-to-bl ${
                          item.type === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
                        }`} />
                        <img src={item.avatar_url} alt={item.name} className="relative w-full h-full rounded-full object-cover" />
                      </>
                    ) : (
                      <div className={`w-full h-full rounded-full bg-gradient-to-bl flex items-center justify-center ${
                        item.type === 'human' ? 'from-primary-500 to-primary-700' : 'from-teal-400 to-teal-600'
                      }`}>
                        <span className="text-xs font-bold text-white">{item.name.charAt(0).toUpperCase()}</span>
                      </div>
                    )}
                  </div>
                </button>

                {/* 信息（可点击 → 资料卡） */}
                <button
                  onClick={() => openProfile(item)}
                  className="flex-1 min-w-0 text-left"
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium text-textPrimary truncate">
                      {item.name}
                    </span>
                    <span className="text-xs text-textMuted shrink-0">
                      {item.type === 'ai' ? <Bot size={12} className="inline" /> : <User size={12} className="inline" />}
                    </span>
                    {item.state && (
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getStateDotColor(item.state)}`} />
                    )}
                  </div>
                  {item.owner_name && (
                    <div className="text-xs text-textMuted truncate">{t('search.creator')} {item.owner_name}</div>
                  )}
                </button>

                {/* 操作按钮 — 好友则发私信，非好友则加好友 */}
                {item.is_friend ? (
                  <button
                    onClick={() => handleSendDM(item)}
                    disabled={sendingDM === key}
                    className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-primary-500/10 text-primary-400 hover:bg-primary-500/20 shrink-0 transition-colors disabled:opacity-50"
                  >
                    <MessageSquare size={12} />
                    {sendingDM === key ? '...' : t('search.sendDM')}
                  </button>
                ) : isAddingThis ? (
                  <div className="shrink-0 flex items-center gap-1">
                    <input
                      type="text"
                      value={friendMessage}
                      onChange={(e) => setFriendMessage(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleAddFriend(item) }}
                      placeholder={t('profileCard.friendMessagePlaceholder')}
                      maxLength={200}
                      className="w-24 md:w-32 px-2 py-1 rounded-lg border border-border bg-canvas text-xs text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-1 focus:ring-primary-500/50"
                      autoFocus
                    />
                    <button
                      onClick={() => handleAddFriend(item)}
                      disabled={addingFriend}
                      className="p-1 rounded text-mint-400 hover:bg-mint-400/10 disabled:opacity-40"
                    >
                      <UserPlus size={14} />
                    </button>
                    <button
                      onClick={() => { setAddFriendTarget(null); setFriendMessage('') }}
                      className="p-1 rounded text-textMuted hover:text-textSecondary"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setAddFriendTarget(key)}
                    disabled={sendingDM === key}
                    className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-mint-400/10 text-mint-400 hover:bg-mint-400/20 shrink-0 transition-colors disabled:opacity-50"
                  >
                    <UserPlus size={12} />
                    {sendingDM === key ? '...' : t('search.addFriend')}
                  </button>
                )}
              </div>
              )
            })
          )}
        </div>
      )}

      {/* 资料卡 */}
      {profileCard && (
        <ProfileCard
          entityType={profileCard.type}
          entityId={profileCard.id}
          entityName={profileCard.name}
          state={profileCard.state || undefined}
          onClose={() => setProfileCard(null)}
        />
      )}
    </div>
  )
}
