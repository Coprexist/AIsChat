import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import { getStateDotColor } from '../constants'
import { X, Bell, BellOff, LogOut, UserX, Shield, ShieldOff, UserPlus, Volume2, VolumeX, Download, Clock, Globe, Loader2, ArrowLeft, Crown } from 'lucide-react'
import Toggle from './Toggle'

// ── 联邦共享状态（v1.0.0: 群主/AI制作者按群控制联邦共享） ──

interface FederationPeerStatus {
  peer_id: number
  display_name: string
  peer_public_id: string
  is_connected: boolean
  is_shared: boolean
  federated_id: string
}

function FederationShareSection({ groupId }: { groupId: number }) {
  const t = useT()
  const [peers, setPeers] = useState<FederationPeerStatus[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [toggling, setToggling] = useState<number | null>(null)
  const [myDisplayName, setMyDisplayName] = useState('')

  const loadPeers = async () => {
    setLoading(true)
    try {
      const data = await api.get<{
        success: boolean
        my_display_name: string
        peers: FederationPeerStatus[]
      }>(`/groups/${groupId}/federation/peers`)
      setPeers(data.peers || [])
      setMyDisplayName(data.my_display_name || '')
    } catch {
      // 静默失败
    } finally {
      setLoading(false)
      setLoaded(true)
    }
  }

  // 首次自动加载
  useEffect(() => {
    loadPeers()
  }, [groupId])

  const handleToggle = async (peer: FederationPeerStatus) => {
    setToggling(peer.peer_id)
    try {
      if (peer.is_shared) {
        await api.post(`/groups/${groupId}/federation/unshare`, { peer_ids: [peer.peer_id] })
      } else {
        await api.post(`/groups/${groupId}/federation/share`, { peer_ids: [peer.peer_id] })
      }
      await loadPeers()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || (peer.is_shared ? '取消共享失败' : '共享失败')
      alert(msg)
    } finally {
      setToggling(null)
    }
  }

  const sharedCount = peers.filter(p => p.is_shared).length

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-textPrimary font-medium flex items-center gap-1">
            <Globe size={14} className="text-textMuted shrink-0" />
            {t('groupSettings.federationShare')}
          </div>
          <div className="text-xs text-textMuted">
            {sharedCount > 0
              ? `${t('groupSettings.sharedTo')}${sharedCount}${t('groupSettings.autoForward')}`
              : t('groupSettings.federationShareHint')}
          </div>
        </div>
        <button
          onClick={loadPeers}
          disabled={loading}
          className="text-xs text-textMuted hover:text-textSecondary transition-colors"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : t('common.refresh')}
        </button>
      </div>

      {!myDisplayName && loaded && (
        <div className="bg-amber-400/10 text-amber-400 rounded-lg px-3 py-2 text-xs">
          {t('groupSettings.federationNoDisplayName')}
        </div>
      )}

      {loaded && peers.length === 0 && (
        <div className="bg-elevated rounded-lg px-3 py-3 text-xs text-textMuted text-center">
          <p className="font-medium text-textSecondary mb-1">{t('groupSettings.federationNoPeers')}</p>
          <p>{t('groupSettings.federationNoPeersHint')}</p>
        </div>
      )}

      {peers.length > 0 && (
        <div className="space-y-1">
          {peers.map(peer => (
            <div
              key={peer.peer_id}
              className="flex items-center justify-between px-3 py-2 rounded-lg bg-elevated hover:bg-canvas transition-colors"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    peer.is_connected ? 'bg-mint-400' : 'bg-textMuted/40'
                  }`}
                />
                <div className="min-w-0">
                  <div className="text-sm text-textPrimary truncate">{peer.display_name}</div>
                  <div className="text-[10px] text-textMuted">
                    {peer.is_connected
                      ? t('groupSettings.federationPeerConnected')
                      : t('groupSettings.federationPeerDisconnected')}
                  </div>
                </div>
              </div>
              {toggling === peer.peer_id ? (
                <div className="w-12 h-6 flex items-center justify-center">
                  <Loader2 size={16} className="animate-spin text-textMuted" />
                </div>
              ) : (
                <Toggle checked={peer.is_shared} onChange={() => handleToggle(peer)} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface GroupMember {
  type: string
  id: number
  name: string
  state?: string
  role: string
  dnd_until?: string | null
}

interface GroupSettings {
  id: number
  name: string
  owner_type: string
  owner_id: number
  is_vector_accelerated: boolean
  announcement: string | null
  speak_limit_per_minute: number
  speak_limit_window_seconds: number
  my_role: string
}

interface Props {
  group: GroupSettings | null
  onClose: () => void
  onUpdate: (updated: Partial<GroupSettings>) => void
  onLeave: () => void
}

type Tab = 'general' | 'members' | 'speak' | 'export'

export default function GroupSettingsPanel({ group, onClose, onUpdate, onLeave }: Props) {
  const t = useT()
  const [tab, setTab] = useState<Tab>('general')
  const [members, setMembers] = useState<GroupMember[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 表单状态
  const [name, setName] = useState(group?.name || '')
  const [announcement, setAnnouncement] = useState(group?.announcement || '')
  const [speakLimit, setSpeakLimit] = useState(group?.speak_limit_per_minute === -1 ? -1 : (group?.speak_limit_per_minute || 0))
  const [speakWindow, setSpeakWindow] = useState(group?.speak_limit_window_seconds || 120)
  const [speakEnabled, setSpeakEnabled] = useState((group?.speak_limit_per_minute ?? 0) >= 0)
  const [concurrentAiLimit, setConcurrentAiLimit] = useState(group?.concurrent_ai_limit ?? 3)
  const [vectorAccel, setVectorAccel] = useState(group?.is_vector_accelerated || false)
  const [dndUntil, setDndUntil] = useState<string | null>(null)
  const [customDndMinutes, setCustomDndMinutes] = useState('')
  const [saving, setSaving] = useState(false)

  // 导出状态
  const [exportFormat, setExportFormat] = useState('json')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const isOwner = group?.my_role === 'owner'
  const isAdmin = group?.my_role === 'admin' || isOwner
  const isAiOwned = group?.owner_type === 'ai'

  useEffect(() => {
    if (!group) return
    setName(group.name)
    setAnnouncement(group.announcement || '')
    setSpeakLimit(group.speak_limit_per_minute || 0)
    setSpeakWindow(group.speak_limit_window_seconds || 120)
    setVectorAccel(group.is_vector_accelerated || false)
    loadMembers()
    loadDndStatus()
  }, [group?.id])

  const loadMembers = async () => {
    if (!group) return
    try {
      const data = await api.get(`/groups/${group.id}/members`)
      setMembers(data)
    } catch { /* ignore */ }
  }

  const loadDndStatus = async () => {
    if (!group) return
    try {
      // DND 状态从群列表中的 dnd_until 获取
      // 这里通过重新获取群列表来刷新
      const groups = await api.get('/groups')
      const g = groups.find((g: any) => g.id === group.id)
      if (g) setDndUntil(g.dnd_until || null)
    } catch { /* ignore */ }
  }

  const saveSettings = async (updates: Record<string, any>) => {
    if (!group) return
    setSaving(true)
    setError('')
    try {
      await api.patch(`/groups/${group.id}`, updates)
      onUpdate(updates)
    } catch (e: any) {
      setError(e?.detail || t('error.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleSetDnd = async (minutes: number | null) => {
    if (!group) return
    try {
      await api.post(`/groups/${group.id}/dnd`, { group_id: group.id, duration_minutes: minutes })
      const until = minutes === null ? 'permanent' : new Date(Date.now() + minutes * 60_000).toISOString()
      setDndUntil(until)
    } catch (e: any) {
      setError(e?.detail || t('error.operationFailed'))
    }
  }

  const handleCustomDnd = async () => {
    if (!group) return
    const mins = parseInt(customDndMinutes, 10)
    if (isNaN(mins) || mins <= 0) {
      setError(t('error.invalidMinutes'))
      return
    }
    if (mins > 10080) {
      setError(t('error.dndMaxDuration'))
      return
    }
    await handleSetDnd(mins)
    setCustomDndMinutes('')
  }

  const handleCancelDnd = async () => {
    if (!group) return
    try {
      await api.post(`/groups/${group.id}/dnd/cancel`)
      setDndUntil(null)
    } catch (e: any) {
      setError(e?.detail || t('error.operationFailed'))
    }
  }

  const handleRoleChange = async (m: GroupMember, newRole: string) => {
    if (!group) return
    try {
      await api.patch(`/groups/${group.id}/members/${m.type}/${m.id}/role`, { role: newRole })
      setMembers(prev => prev.map(x => x.id === m.id && x.type === m.type ? { ...x, role: newRole } : x))
    } catch (e: any) {
      setError(e?.detail || t('error.operationFailed'))
    }
  }

  const handleKick = async (m: GroupMember) => {
    if (!group) return
    if (!confirm(t('groupSettings.confirmKick') + m.name + t('groupSettings.confirmKickEnd'))) return
    try {
      await api.delete(`/groups/${group.id}/members/${m.type}/${m.id}`)
      setMembers(prev => prev.filter(x => !(x.id === m.id && x.type === m.type)))
    } catch (e: any) {
      setError(e?.detail || t('error.operationFailed'))
    }
  }

  const handleLeave = async () => {
    if (!group) return
    if (!confirm(t('groupSettings.confirmLeave'))) return
    try {
      await api.post(`/groups/${group.id}/leave`)
      onLeave()
    } catch (e: any) {
      setError(e?.detail || t('error.leaveFailed'))
    }
  }

  const handleDisband = async () => {
    if (!group) return
    if (!confirm(t('groupSettings.confirmDisband'))) return
    try {
      await api.delete(`/groups/${group.id}`)
      onLeave()  // 复用退出逻辑：关闭面板 + 刷新列表
    } catch (e: any) {
      setError(e?.detail || t('error.operationFailed'))
    }
  }

  const handleExportChat = async () => {
    if (!group) return
    setExporting(true)
    setExportError('')
    try {
      const token = localStorage.getItem('access_token')
      const params = new URLSearchParams({ fmt: exportFormat })
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      const res = await fetch(`/api/groups/${group.id}/export?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || t('error.exportFailed'))
      }
      const blob = await res.blob()
      const ext = exportFormat === 'txt' ? 'txt' : exportFormat === 'html' ? 'html' : 'json'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chat_${group.name}_${new Date().toISOString().slice(0, 10)}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setExportError(e.message)
    } finally {
      setExporting(false)
    }
  }

  if (!group) return null

  const tabs: { key: Tab; keyLabel: string; show: boolean }[] = [
    { key: 'general', keyLabel: 'groupSettings.tabGeneral', show: true },
    { key: 'members', keyLabel: 'groupSettings.tabMembers', show: true },
    { key: 'speak', keyLabel: 'groupSettings.tabSpeak', show: isAdmin },
    { key: 'export', keyLabel: 'groupSettings.tabExport', show: true },
  ]

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 点击外部关闭（桌面端） */}
      <div className="absolute inset-0 bg-black/30 hidden md:block" onClick={onClose} />

      <div className="relative w-full md:w-96 max-w-full h-full bg-surface md:border-l border-border shadow-2xl flex flex-col animate-slide-in">
        {/* 头部 */}
        <div className="h-14 px-4 border-b border-border flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
            >
              <ArrowLeft size={20} />
            </button>
            <h2 className="font-semibold text-sm text-textPrimary">{t('groupSettings.title')}</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-elevated text-textMuted hidden md:block">
            <X size={16} />
          </button>
        </div>

        {/* Tab 切换 */}
        <div className="flex border-b border-border shrink-0">
          {tabs.filter(item => item.show).map(item => (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
                tab === item.key
                  ? 'text-primary-400 border-b-2 border-primary-400'
                  : 'text-textMuted hover:text-textSecondary'
              }`}
            >
              {t(item.keyLabel)}
            </button>
          ))}
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-[var(--safe-bottom)] md:pb-4">
          {error && (
            <div className="text-xs text-rose-400 bg-rose-400/10 rounded-lg px-3 py-2">{error}</div>
          )}

          {/* === Tab: 基本设置 === */}
          {tab === 'general' && (
            <>
              {/* 群名称 */}
              <div>
                <label className="text-xs font-medium text-textSecondary">{t('groupSettings.groupName')}</label>
                <div className="flex gap-2 mt-1">
                  <input
                    value={name}
                    onChange={e => setName(e.target.value)}
                    disabled={!isAdmin}
                    className="flex-1 bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-textPrimary disabled:opacity-50 outline-none focus:border-primary-400"
                  />
                  {isAdmin && (
                    <button
                      onClick={() => saveSettings({ name })}
                      disabled={saving || name === group.name}
                      className="px-3 py-2 bg-primary-500 text-white rounded-lg text-xs font-medium hover:bg-primary-400 disabled:opacity-50 transition-colors"
                    >
                      {t('common.save')}
                    </button>
                  )}
                </div>
              </div>

              {/* 群公告 */}
              <div>
                <label className="text-xs font-medium text-textSecondary">{t('groupSettings.announcement')}</label>
                {isAdmin ? (
                  <div className="mt-1 space-y-2">
                    <textarea
                      value={announcement}
                      onChange={e => setAnnouncement(e.target.value)}
                      placeholder={t('groupSettings.announcementPlaceholder')}
                      rows={3}
                      className="w-full bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-textPrimary outline-none focus:border-primary-400 resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => saveSettings({ announcement })}
                        disabled={saving}
                        className="px-3 py-1.5 bg-primary-500 text-white rounded-lg text-xs font-medium hover:bg-primary-400 disabled:opacity-50 transition-colors"
                      >
                        {t('groupSettings.updateAnnouncement')}
                      </button>
                      {group.announcement && (
                        <button
                          onClick={async () => {
                            try {
                              await api.delete(`/groups/${group.id}/announcement`)
                              setAnnouncement('')
                              onUpdate({ announcement: null })
                            } catch (e: any) { setError(e?.detail || t('error.operationFailed')) }
                          }}
                          className="px-3 py-1.5 bg-rose-400/10 text-rose-400 rounded-lg text-xs font-medium hover:bg-rose-400/20 transition-colors"
                        >
                          {t('groupSettings.deleteAnnouncement')}
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-textSecondary bg-elevated rounded-lg px-3 py-2">
                    {group.announcement || t('groupSettings.noAnnouncement')}
                  </p>
                )}
              </div>

              <hr className="border-border" />

              {/* 免打扰 */}
              <div>
                <h3 className="text-sm font-medium text-textPrimary flex items-center gap-2 mb-3">
                  <Bell size={14} className="text-textMuted" />
                  {t('groupSettings.dnd')}
                </h3>
                {dndUntil ? (
                  <div className="space-y-3">
                    <div className="bg-mint-400/10 text-mint-400 rounded-lg px-3 py-2 text-xs flex items-center gap-2">
                      <BellOff size={14} />
                      {t('groupSettings.dndEnabled')}
                    </div>
                    <button
                      onClick={handleCancelDnd}
                      className="w-full px-4 py-2.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-400 transition-colors"
                    >
                      {t('groupSettings.dndCancel')}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-textMuted">{t('groupSettings.dndHint')}</p>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { key: 'groupSettings.dnd15min', minutes: 15 },
                        { key: 'groupSettings.dnd30min', minutes: 30 },
                        { key: 'groupSettings.dnd1hour', minutes: 60 },
                        { key: 'groupSettings.dnd4hours', minutes: 240 },
                        { key: 'groupSettings.dnd8hours', minutes: 480 },
                        { key: 'groupSettings.dndForever', minutes: null as unknown as number },
                      ].map((d) => (
                        <button
                          key={d.key}
                          onClick={() => handleSetDnd(d.minutes)}
                          className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-elevated hover:bg-primary-500/10 hover:text-primary-400 text-textSecondary border border-border rounded-lg text-xs font-medium transition-colors"
                        >
                          <Clock size={12} />
                          {t(d.key)}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2 items-center">
                      <input
                        type="number"
                        value={customDndMinutes}
                        onChange={(e) => setCustomDndMinutes(e.target.value)}
                        placeholder={t('groupSettings.dndCustomPlaceholder')}
                        min={1}
                        max={10080}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleCustomDnd() }}
                        className="flex-1 bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-textPrimary outline-none focus:border-primary-400 placeholder:text-textMuted"
                      />
                      <button
                        onClick={handleCustomDnd}
                        disabled={!customDndMinutes.trim()}
                        className="px-3 py-2 bg-primary-500 text-white rounded-lg text-xs font-medium hover:bg-primary-400 disabled:opacity-50 transition-colors shrink-0"
                      >
                        {t('common.set')}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* 向量加速（仅管理员可见） */}
              {isAdmin && (
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-textPrimary font-medium">{t('groupSettings.vectorAccel')}</div>
                    <div className="text-xs text-textMuted">
                      {isAiOwned ? t('groupSettings.vectorAccelAiOwned') : t('groupSettings.vectorAccelHybridSearch')}
                    </div>
                  </div>
                  <Toggle checked={vectorAccel} onChange={(next) => { setVectorAccel(next); saveSettings({ is_vector_accelerated: next }) }} />
                </div>
              )}

              {/* 联邦共享（仅管理员可见） */}
              {isAdmin && <FederationShareSection groupId={group!.id} />}

              <hr className="border-border" />

              {/* 退群 */}
              <button
                onClick={handleLeave}
                disabled={isOwner && !group.name.startsWith('DM:')}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-rose-400/10 text-rose-400 rounded-lg text-sm font-medium hover:bg-rose-400/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title={isOwner && !group.name.startsWith('DM:') ? t('groupSettings.ownerLeaveHint') : t('groupSettings.leaveGroup')}
              >
                <LogOut size={16} />
                {isOwner && !group.name.startsWith('DM:') ? t('groupSettings.ownerCannotLeave') : t('groupSettings.leaveGroup')}
              </button>

              {/* 解散群聊（仅群主可见） */}
              {isOwner && (
                <button
                  onClick={handleDisband}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600/15 text-red-500 rounded-lg text-sm font-medium hover:bg-red-600/25 transition-colors border border-red-500/20"
                >
                  {t('groupSettings.disbandGroup')}
                </button>
              )}
            </>
          )}

          {/* === Tab: 成员管理 === */}
          {tab === 'members' && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm text-textPrimary font-medium">
                  {t('groupSettings.memberCount')} ({members.length})
                </span>
                <button
                  onClick={() => {
                    // 触发父组件的邀请弹窗
                    const event = new CustomEvent('open-invite-modal')
                    window.dispatchEvent(event)
                  }}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-primary-400 hover:bg-primary-400/10 rounded-lg transition-colors"
                >
                  <UserPlus size={14} />
                  {t('groupSettings.invite')}
                </button>
              </div>

              <div className="space-y-1">
                {members.map(m => (
                  <div
                    key={`${m.type}:${m.id}`}
                    className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-elevated transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      {/* 状态圆点 */}
                      <span className={`w-2 h-2 rounded-full shrink-0 ${getStateDotColor(m.state)}`} />
                      <div className="min-w-0">
                        <div className="text-sm text-textPrimary truncate flex items-center gap-1.5">
                          {m.name}
                          {m.role === 'owner' && (
                            <span className="text-[10px] text-amber-400 font-medium flex items-center gap-0.5"><Crown size={10} />{t('groupSettings.roleOwner')}</span>
                          )}
                          {m.type === 'ai' && (
                            <span className="text-[10px] text-primary-400 font-medium">{t('chatlist.ai')}</span>
                          )}
                        </div>
                        <div className="text-[10px] text-textMuted">
                          {m.role === 'owner' ? t('groupSettings.roleOwner') : m.role === 'admin' ? t('groupSettings.roleAdmin') : t('groupSettings.roleMember')}
                          {m.dnd_until && ' · ' + t('dm.shortDnd')}
                        </div>
                      </div>
                    </div>

                    {/* 操作按钮（群主/管理员可见，不可操作自己） */}
                    {isAdmin && m.role !== 'owner' && (
                      <div className="flex items-center gap-1 shrink-0 ml-2">
                        {isOwner && (
                          <button
                            onClick={() => handleRoleChange(m, m.role === 'admin' ? 'member' : 'admin')}
                            className="p-1 rounded hover:bg-elevated text-textMuted hover:text-primary-400 transition-colors"
                            title={m.role === 'admin' ? t('groupSettings.demoteToMember') : t('groupSettings.promoteToAdmin')}
                          >
                            {m.role === 'admin' ? <ShieldOff size={14} /> : <Shield size={14} />}
                          </button>
                        )}
                        <button
                          onClick={() => handleKick(m)}
                          className="p-1 rounded hover:bg-rose-400/10 text-textMuted hover:text-rose-400 transition-colors"
                          title={t('groupSettings.kick')}
                        >
                          <UserX size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          {/* === Tab: AI 发言限制（仅管理员） === */}
          {tab === 'speak' && isAdmin && (
            <>
              {isAiOwned ? (
                <div className="text-center py-8">
                  <Volume2 size={32} className="mx-auto text-mint-400 mb-3" />
                  <p className="text-sm text-textPrimary font-medium">{t('groupSettings.aiManagedGroup')}</p>
                  <p className="text-xs text-textMuted mt-1">
                    {t('groupSettings.aiManagedDesc1')}<br />
                    {t('groupSettings.aiManagedDesc2')}
                  </p>
                </div>
              ) : (
                <>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-medium text-textSecondary">
                        {t('groupSettings.speakLimit')}
                      </label>
                      <span className="text-xs text-primary-400 font-medium">
                        {speakLimit === 0 ? t('groupSettings.unlimited') : `${speakLimit} ${t('groupSettings.perMinute')}`}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={60}
                      value={speakLimit}
                      onChange={e => setSpeakLimit(Number(e.target.value))}
                      className="w-full accent-primary-500"
                    />
                    <div className="flex justify-between text-[10px] text-textMuted">
                      <span>{t('groupSettings.unlimitedLabel')}</span>
                      <span>60</span>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-medium text-textSecondary">
                        {t('groupSettings.speakWindow')}
                      </label>
                      <span className="text-xs text-primary-400 font-medium">{speakWindow}s</span>
                    </div>
                    <input
                      type="range"
                      min={30}
                      max={600}
                      step={30}
                      value={speakWindow}
                      onChange={e => setSpeakWindow(Number(e.target.value))}
                      className="w-full accent-primary-500"
                    />
                    <div className="flex justify-between text-[10px] text-textMuted">
                      <span>30s</span>
                      <span>600s</span>
                    </div>
                  </div>

                  {/* 预览 */}
                  <div className="bg-elevated rounded-lg px-3 py-2.5 text-xs text-textSecondary space-y-1">
                    <div className="font-medium text-textPrimary">{t('groupSettings.preview')}</div>
                    {speakLimit > 0 ? (
                      <div>
                        {t('groupSettings.speakPreviewPer')} {speakWindow} {t('groupSettings.speakPreviewAllow')} <span className="text-primary-400 font-medium">{speakLimit * 2}</span> {t('groupSettings.speakPreviewRounds')}
                        <br />
                        <span className="text-textMuted">
                          {t('groupSettings.speakPreviewBufferNote')}
                        </span>
                      </div>
                    ) : (
                      <div>{t('groupSettings.speakPreviewUnlimitedDesc')}</div>
                    )}
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-medium text-textSecondary">AI 并发数</label>
                      <span className="text-xs text-primary-400 font-medium">{concurrentAiLimit}</span>
                    </div>
                    <input type="range" min={1} max={10} value={concurrentAiLimit} onChange={e => setConcurrentAiLimit(Number(e.target.value))} className="w-full accent-primary-500" />
                    <div className="flex justify-between text-[10px] text-textMuted"><span>1</span><span>10</span></div>
                  </div>


                  <button
                    onClick={() => saveSettings({
                      speak_limit_per_minute: speakEnabled ? speakLimit : -1,
                      concurrent_ai_limit: concurrentAiLimit,
                      speak_limit_window_seconds: speakWindow,
                    })}
                    disabled={saving}
                    className="w-full px-4 py-2.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-400 disabled:opacity-50 transition-colors"
                  >
                    {saving ? t('common.saving') : t('groupSettings.saveSpeakLimit')}
                  </button>
                </>
              )}
            </>
          )}

          {/* === Tab: 导出记录 === */}
          {tab === 'export' && (
            <>
              <div>
                <label className="text-xs font-medium text-textSecondary">{t('groupSettings.exportFormat')}</label>
                <div className="flex gap-2 mt-1">
                  {[
                    { key: 'json', labelKey: 'JSON', descKey: 'groupSettings.exportJsonDesc' },
                    { key: 'txt', labelKey: 'groupSettings.exportTxtDesc', descKey: 'groupSettings.exportTxtDesc' },
                    { key: 'html', labelKey: 'HTML', descKey: 'groupSettings.exportHtmlDesc' },
                  ].map(f => (
                    <button
                      key={f.key}
                      onClick={() => setExportFormat(f.key)}
                      className={`flex-1 py-3 px-2 rounded-xl border text-center transition-colors ${
                        exportFormat === f.key
                          ? 'border-primary-400 bg-primary-500/10 text-primary-600 dark:text-primary-300'
                          : 'border-border bg-canvas text-textSecondary hover:bg-elevated'
                      }`}
                    >
                      <div className="text-sm font-medium">{f.labelKey}</div>
                      <div className="text-[10px] text-textMuted">{t(f.descKey)}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-textSecondary">{t('groupSettings.dateRange')}</label>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={e => setDateFrom(e.target.value)}
                    className="flex-1 bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-textPrimary"
                  />
                  <span className="text-textMuted text-xs">{t('common.to')}</span>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={e => setDateTo(e.target.value)}
                    className="flex-1 bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-textPrimary"
                  />
                </div>
              </div>

              <button
                onClick={handleExportChat}
                disabled={exporting}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-500 text-white rounded-xl hover:bg-primary-400 disabled:opacity-40 text-sm font-medium transition-all"
              >
                <Download size={16} />
                {exporting ? t('common.exporting') : t('groupSettings.downloadExport')}
              </button>

              {exportError && <div className="text-xs text-rose-400">{exportError}</div>}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
