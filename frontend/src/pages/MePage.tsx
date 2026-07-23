import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useT, useLang } from '../i18n/I18nContext'
import { api } from '../api/client'
import { AI_TYPE_LABEL } from '../constants'
import { fmtTokenNum } from '../utils/format'
import { getStatusTextStyle, STATUS_COLORS, BG_SURFACE_LIGHT, BG_SURFACE_DARK } from '../utils/statusColor.tsx'
import VerificationCodeInput from '../components/VerificationCodeInput'
import { useTheme } from '../context/ThemeContext'
import {
  User, Settings, LogOut, Shield,
  Gift, BarChart3, Bot, ChevronRight, Edit3,
  Loader2, Check, X, ArrowRight, Activity,
  FileText, HardDrive, Camera, Users, MessageSquare, Share2
} from 'lucide-react'
import AvatarCropModal from '../components/AvatarCropModal'
import ForwardFileModal from '../components/ForwardFileModal'

interface AgentBrief {
  id: number
  name: string
  state: string
  chat_model: string | null
  avatar_url: string | null
  ai_type: string
}

interface UsageOverview {
  agent_id: number
  agent_name: string
  model: string | null
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  reasoning_tokens: number
  cached_tokens: number
  total_calls: number
}

function StatCard({ icon, value, label, onClick, bg }: {
  icon: React.ReactNode; value: string | number; label: string; onClick: () => void; bg: string;
}) {
  return (
    <button onClick={onClick} className={`rounded-xl p-3.5 text-center hover:brightness-95 transition-all cursor-pointer w-full ${bg}`}>
      <div className="mx-auto mb-1 flex justify-center">{icon}</div>
      <div className="text-lg font-bold text-textPrimary tabular-nums">{value}</div>
      <div className="text-[10px] text-textMuted mt-0.5">{label}</div>
    </button>
  )
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function MePage() {
  const { user, logout, refreshUser } = useAuth()
  const t = useT()
  const lang = useLang()
  const { theme } = useTheme()
  const navigate = useNavigate()

  const [agents, setAgents] = useState<AgentBrief[]>([])
  const [usage, setUsage] = useState<UsageOverview[]>([])
  const [usageLoading, setUsageLoading] = useState(true)
  const [redeemCode, setRedeemCode] = useState('')
  const [redeemMsg, setRedeemMsg] = useState('')
  const [redeeming, setRedeeming] = useState(false)

  // 存储概览
  const [storage, setStorage] = useState<{ total_used: number; total_files: number; quota_mb: number; usage_percent: number } | null>(null)
  const [storageLoading, setStorageLoading] = useState(true)
  const [stats, setStats] = useState<{ ai_count: number; friend_count: number; group_count: number; storage_used: number } | null>(null)

  // 编辑资料弹窗
  const [showEditProfile, setShowEditProfile] = useState(false)
  const [editUsername, setEditUsername] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editBio, setEditBio] = useState('')
  const [editStatusText, setEditStatusText] = useState('')
  const [editStatusColor, setEditStatusColor] = useState('')
  const [editAvatarUrl, setEditAvatarUrl] = useState('')
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [cropFile, setCropFile] = useState<File | null>(null)

  // 文件列表 + 转发
  const [fileList, setFileList] = useState<Array<{id:number;path:string;size:number;mime_type:string;created_at:string}>>([])
  const [fileListLoading, setFileListLoading] = useState(false)
  const [forwardFile, setForwardFile] = useState<{file_id:number;name:string;size:number;mime_type:string}|null>(null)

  // v1.0.0 邮箱绑定
  const [showBindEmail, setShowBindEmail] = useState(false)
  const [bindEmail, setBindEmail] = useState('')
  const [bindCode, setBindCode] = useState('')
  const [bindCodeSent, setBindCodeSent] = useState(false)
  const [bindSendCooldown, setBindSendCooldown] = useState(0)
  const [bindError, setBindError] = useState('')
  const [bindLoading, setBindLoading] = useState(false)
  const { rebindEmail, removeEmail } = useAuth()

  interface FileItem {
    id: number; path: string; size: number; mime_type: string; created_at: string
    is_forwarded?: boolean
  }

  const loadFileList = () => {
    setFileListLoading(true)
    api.get<FileItem[]>('/fs/list?path=/&include_forwarded=true')
      .then(r => setFileList(Array.isArray(r) ? r : []))
      .catch(() => {})
      .finally(() => setFileListLoading(false))
  }

  const releaseFile = async (fileId: number) => {
    try {
      await api.delete(`/fs/release/${fileId}`)
      setFileList(prev => prev.filter(f => f.id !== fileId))
    } catch (err: any) {
      alert(err.message || t('error.unknown'))
    }
  }

  useEffect(() => {
    // 加载我的 AI 列表
    api.get<AgentBrief[]>('/agents').then(r => {
      setAgents((Array.isArray(r) ? r : []).slice(0, 3))
    }).catch(() => {})

    // 加载用量概览
    setUsageLoading(true)
    api.get<UsageOverview[]>('/conversation-log/usage/overview?days=30').then(r => {
      setUsage(Array.isArray(r) ? r : [])
    }).catch(() => {}).finally(() => setUsageLoading(false))

    // 加载存储概览
    setStorageLoading(true)
    api.get<{ total_used: number; total_files: number; quota_mb: number; usage_percent: number }>('/user/storage').then(r => {
      setStorage(r)
    }).catch(() => {}).finally(() => setStorageLoading(false))

    // 加载个人统计（单次高效 COUNT 查询）
    api.get<{ ai_count: number; friend_count: number; group_count: number; storage_used: number }>('/user/stats').then(r => {
      setStats(r)
    }).catch(() => {})
  }, [])

  // 汇总
  const totalTokens = usage.reduce((s, u) => s + (u.total_tokens || 0), 0)
  const totalCalls = usage.reduce((s, u) => s + (u.total_calls || 0), 0)
  const totalReasoning = usage.reduce((s, u) => s + (u.reasoning_tokens || 0), 0)
  const totalCached = usage.reduce((s, u) => s + (u.cached_tokens || 0), 0)
  const cacheRate = totalTokens > 0 ? Math.round(totalCached / totalTokens * 100) : 0

  // 上线天数
  const daysSince = user?.created_at
    ? Math.max(1, Math.floor((Date.now() - new Date(user.created_at).getTime()) / 86400000))
    : 1

  // ── 兑换码 ──
  const handleRedeem = async () => {
    if (!redeemCode.trim()) return
    setRedeeming(true)
    setRedeemMsg('')
    try {
      const res = await api.post<{ message: string }>('/user/redeem', { code: redeemCode.trim().toUpperCase() })
      setRedeemMsg(res.message || t('common.redeemSuccess'))
      setRedeemCode('')
      refreshUser?.()
    } catch (err: any) {
      setRedeemMsg(err.message || t('common.redeemFailed'))
    } finally { setRedeeming(false) }
  }

  // 存储区滚动引用
  const storageRef = useRef<HTMLDivElement>(null)
  const scrollToStorage = useCallback(() => {
    storageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    loadFileList()
  }, [])
  useEffect(() => {
    if (bindSendCooldown <= 0) return
    const timer = setInterval(() => setBindSendCooldown(c => c - 1), 1000)
    return () => clearInterval(timer)
  }, [bindSendCooldown])

  const handleSendBindCode = async () => {
    if (!bindEmail || bindSendCooldown > 0) return
    setBindError('')
    try {
      await api.post('/auth/send-verification-code', { email: bindEmail, purpose: 'rebind' })
      setBindCodeSent(true)
      setBindSendCooldown(60)
    } catch (err: any) {
      setBindError(err.message || t('common.error'))
    }
  }

  const handleConfirmBind = async () => {
    if (!bindEmail || !bindCode) return
    setBindLoading(true)
    setBindError('')
    try {
      await rebindEmail(bindEmail, bindCode)
      setShowBindEmail(false)
      setBindEmail('')
      setBindCode('')
      setBindCodeSent(false)
    } catch (err: any) {
      setBindError(err.message || t('common.error'))
    } finally { setBindLoading(false) }
  }

  const handleRemoveEmail = async () => {
    if (!confirm(t('auth.removeEmail') + '?')) return
    try {
      await removeEmail()
    } catch (err: any) {
      alert(err.message || t('common.error'))
    }
  }

  // ── 编辑资料 ──
  const openEditProfile = () => {
    setEditUsername(user?.username || '')
    setEditPassword('')
    setEditBio(user?.bio || '')
    setEditStatusText(user?.status_text || '')
    setEditStatusColor(user?.status_color || '')
    setEditAvatarUrl(user?.avatar_url || '')
    setShowEditProfile(true)
  }
  const handleAvatarSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    // 从缓存读取头像大小限制
    let maxAvatarMB = 10
    try {
      const cached = sessionStorage.getItem('upload_limits')
      if (cached) {
        const parsed = JSON.parse(cached)
        if (Date.now() - parsed.ts < 300000) {
          maxAvatarMB = parsed.avatar_max_size_mb || 10
        }
      }
    } catch {}
    if (file.size > maxAvatarMB * 1024 * 1024) { alert(t('error.avatarTooLarge')); return }
    // GIF 动图无法裁剪，直接上传
    if (file.type === 'image/gif') {
      uploadAvatarDirectly(file)
      return
    }
    setCropFile(file)
    e.target.value = ''
  }

  const uploadAvatarDirectly = async (file: File) => {
    setAvatarUploading(true)
    try {
      const res = await api.upload('/user/avatar', file)
      setEditAvatarUrl(res.avatar_url)
      refreshUser?.()
    } catch (err: any) { alert(err?.message || err?.detail || t('error.unknown')) }
    finally { setAvatarUploading(false) }
  }

  const handleCropConfirm = async (blob: Blob) => {
    setCropFile(null)
    setAvatarUploading(true)
    try {
      const ext = blob.type === 'image/gif' ? 'gif' : blob.type === 'image/png' ? 'png' : 'jpg'
      const res = await api.upload('/user/avatar', new File([blob], `avatar.${ext}`, { type: blob.type || 'image/jpeg' }))
      setEditAvatarUrl(res.avatar_url)
    } catch (err: any) {
      alert(err?.message || err?.detail || (typeof err === 'string' ? err : '上传失败，请检查网络或文件大小'))
    } finally { setAvatarUploading(false) }
  }
  const handleSaveProfile = async () => {
    setEditSaving(true)
    try {
      const body: any = {}
      if (editUsername && editUsername !== user?.username) body.username = editUsername
      if (editPassword) body.password = editPassword
      if (editBio !== (user?.bio || '')) body.bio = editBio
      if (editStatusText !== (user?.status_text || '')) body.status_text = editStatusText
      if (editStatusColor !== (user?.status_color || '')) body.status_color = editStatusColor || null
      if (editAvatarUrl !== (user?.avatar_url || '')) body.avatar_url = editAvatarUrl
      if (Object.keys(body).length > 0) {
        await api.put('/user/settings', body)
      }
      await refreshUser?.()
      setShowEditProfile(false)
    } catch (err: any) {
      alert(err.message || t('error.saveFailed'))
    } finally { setEditSaving(false) }
  }

  if (!user) return null

  return (
    <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-5 pb-24 md:pb-6">
      {/* ====== 页面标题 ====== */}
      <h1 className="text-lg font-bold text-textPrimary">{t('me.title')}</h1>

      {/* ====== 个人资料卡 ====== */}
      <div className="bg-surface rounded-2xl border border-border p-5">
        <div className="flex items-center gap-4">
          {/* 头像 */}
          <div className="shrink-0">
            {user.avatar_url ? (
              <div className="relative w-16 h-16 rounded-full overflow-hidden shadow shadow-primary-500/25">
                <div className="absolute inset-px rounded-full bg-gradient-to-br from-primary-500 to-primary-700/30" />
                <img src={user.avatar_url} className="relative w-full h-full rounded-full object-cover" />
              </div>
            ) : (
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow shadow-primary-500/25">
                <User size={28} className="text-white" />
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-textPrimary truncate">{user.username}</h2>
              {user.role === 'admin' && (
                <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-medium">{t('me.adminBadge')}</span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-textMuted">
              <span className="flex items-center gap-1"><Bot size={12} /> AI {agents.length}</span>
              <span>{t('me.daysOnline')} {daysSince} {t('me.daysSuffix')}</span>
              {user.status_text && (
                <span className="font-medium" style={user.status_color
                  ? getStatusTextStyle(user.status_color, theme === 'dark' ? BG_SURFACE_DARK : BG_SURFACE_LIGHT)
                  : undefined}>
                  {user.status_text}
                </span>
              )}
            </div>
            <button
              onClick={openEditProfile}
              className="mt-2 text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 flex items-center gap-1 transition-colors"
            >
              <Edit3 size={12} /> {t('me.editProfile')}
            </button>
            {/* 邮箱 */}
            <div className="mt-3 pt-3 border-t border-border/60">
              <span className="text-[10px] text-textMuted uppercase tracking-wider">{t('auth.email')}</span>
              <div className="flex items-center gap-2 mt-1">
                {user?.email ? (
                  <>
                    <span className="text-sm text-textPrimary truncate">{user.email}</span>
                    {user.email_verified ? (
                      <span className="text-[10px] text-mint-400 bg-mint-500/10 px-1.5 py-0.5 rounded-full">{t('auth.emailVerified')}</span>
                    ) : (
                      <span className="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">{t('auth.emailNotVerified')}</span>
                    )}
                  </>
                ) : (
                  <span className="text-sm text-textMuted">{t('auth.noEmailBound')}</span>
                )}
                <button
                  onClick={() => setShowBindEmail(true)}
                  className="text-[10px] text-primary-400 hover:text-primary-500 transition-colors"
                >
                  {user?.email ? t('auth.changeEmail') : t('auth.bindEmailTitle')}
                </button>
                {user?.email && (
                  <button
                    onClick={handleRemoveEmail}
                    className="text-[10px] text-rose-400 hover:text-rose-500 transition-colors"
                  >
                    {t('auth.removeEmail')}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 个人统计概览 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 pt-4 border-t border-border/60">
          <StatCard
            icon={<Bot size={18} className="text-primary-400" />}
            value={stats?.ai_count ?? '...'}
            label={t('me.aiCountCard')}
            bg="bg-primary-500/5"
            onClick={() => navigate('/agents')}
          />
          <StatCard
            icon={<Users size={18} className="text-mint-400" />}
            value={stats?.friend_count ?? '...'}
            label={t('me.friendCountCard')}
            bg="bg-mint-500/5"
            onClick={() => navigate('/friends')}
          />
          <StatCard
            icon={<MessageSquare size={18} className="text-amber-400" />}
            value={stats?.group_count ?? '...'}
            label={t('me.groupCountCard')}
            bg="bg-amber-500/5"
            onClick={() => navigate('/chat')}
          />
          <StatCard
            icon={<HardDrive size={18} className="text-accent-400" />}
            value={stats ? formatSize(stats.storage_used) : '...'}
            label={t('me.storageUsedCard')}
            bg="bg-accent-500/5"
            onClick={scrollToStorage}
          />
        </div>
      </div>

      {/* ====== 我的 AI ====== */}
      <div className="bg-surface rounded-2xl border border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
            <Bot size={16} className="text-primary-400" /> {t('me.myAiSection')}
          </h3>
          <Link to="/agents" className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 flex items-center gap-1 transition-colors">
            {t('me.viewAll')} <ArrowRight size={12} />
          </Link>
        </div>
        {agents.length === 0 ? (
          <p className="text-sm text-textMuted py-3 text-center">{t('me.noAiLink')}<Link to="/agents" className="text-primary-400">{t('me.goCreate')}</Link></p>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1">
            {agents.map(a => (
              <Link
                key={a.id}
                to={`/agents/${a.id}`}
                className="shrink-0 w-28 bg-canvas rounded-xl p-3 border border-border hover:border-primary-400/30 transition-colors text-center"
              >
                {a.avatar_url ? (
                  <div className="relative w-10 h-10 rounded-full mx-auto mb-1.5 shadow shadow-primary-500/15 overflow-hidden">
                    <div className="absolute inset-px rounded-full bg-gradient-to-br from-primary-500 to-primary-700/30" />
                    <img src={a.avatar_url} className="relative w-full h-full rounded-full object-cover" />
                  </div>
                ) : (
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center mx-auto mb-1.5 shadow shadow-primary-500/15">
                    <Bot size={18} className="text-white" />
                  </div>
                )}
                <div className="text-xs font-medium text-textPrimary truncate">{a.name}</div>
                <div className="text-[10px] text-textMuted mt-0.5">{a.state === 'active' ? t('me.stateActive') : a.state === 'dnd' ? t('me.stateDnd') : t('me.stateOffline')}</div>
                {(AI_TYPE_LABEL[a.ai_type]) && (
                  <span className={`inline-block text-[9px] px-1.5 py-0.5 rounded-full mt-1 font-medium ${AI_TYPE_LABEL[a.ai_type].cls}`}>
                    {t(AI_TYPE_LABEL[a.ai_type].key)}
                  </span>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* ====== API 用量 ====== */}
      <div className="bg-surface rounded-2xl border border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
            <BarChart3 size={16} className="text-primary-400" /> {t('me.apiUsage30d')}
          </h3>
          <Link to="/me/usage" className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 flex items-center gap-1 transition-colors">
            {t('me.viewDetails')} <ArrowRight size={12} />
          </Link>
        </div>
        {usageLoading ? (
          <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-textMuted" /></div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { key: 'me.totalTokens', value: fmtTokenNum(totalTokens, lang), icon: Activity, color: 'text-primary-400' },
              { key: 'me.calls', value: totalCalls, icon: BarChart3, color: 'text-mint-400' },
              { key: 'me.cacheHitRate', value: `${cacheRate}%`, icon: FileText, color: 'text-amber-400' },
              { key: 'me.thinkingTokens', value: fmtTokenNum(totalReasoning, lang), icon: Activity, color: 'text-accent-400' },
            ].map(item => (
              <div key={item.key} className="bg-canvas rounded-xl p-3 text-center">
                <item.icon size={16} className={`${item.color} mx-auto mb-1`} />
                <div className="text-sm font-semibold text-textPrimary">{item.value}</div>
                <div className="text-[10px] text-textMuted">{t(item.key)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ====== 存储概览 ====== */}
      <div ref={storageRef} className="bg-surface rounded-2xl border border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
            <HardDrive size={16} className="text-primary-400" /> {t('me.storageSection')}
          </h3>
          {storage && storage.total_files > 0 && (
            <button
              onClick={loadFileList}
              className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 transition-colors"
            >
              {fileList.length > 0 ? t('common.refresh') : t('me.viewFiles')}
            </button>
          )}
        </div>
        {storageLoading ? (
          <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-textMuted" /></div>
        ) : storage ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-textMuted">
              <span>{t('me.used')} {storage.total_used >= 1048576 ? `${(storage.total_used / 1048576).toFixed(1)}MB` : `${(storage.total_used / 1024).toFixed(0)}KB`}</span>
              <span className={storage.usage_percent > 90 ? 'text-rose-400 font-medium' : storage.usage_percent > 70 ? 'text-amber-400 font-medium' : ''}>
                {storage.usage_percent}%
              </span>
            </div>
            <div className="w-full h-2 bg-canvas rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  storage.usage_percent > 90 ? 'bg-rose-400' : storage.usage_percent > 70 ? 'bg-amber-400' : 'bg-primary-400'
                }`}
                style={{ width: `${Math.min(storage.usage_percent, 100)}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-textMuted">
              <span>{storage.total_files} {t('me.fileCountSuffix')}</span>
              <span>{t('me.quota')} {storage.quota_mb}MB</span>
            </div>
            {storage.usage_percent > 90 && (
              <p className="text-xs text-rose-400">{t('me.storageWarning')}</p>
            )}

            {/* 文件列表 */}
            {fileListLoading ? (
              <div className="flex justify-center py-3"><Loader2 size={14} className="animate-spin text-textMuted" /></div>
            ) : fileList.length > 0 ? (
              <div className="mt-2 pt-3 border-t border-border/60 space-y-1">
                {fileList.map((f) => {
                  const name = f.path.split('/').pop() || f.path
                  return (
                    <div key={f.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-elevated transition-colors group">
                      <FileText size={14} className={`shrink-0 ${(f as any).is_forwarded ? 'text-accent-400' : 'text-textMuted'}`} />
                      <span className="text-xs text-textPrimary truncate flex-1" title={name}>
                        {name}
                        {(f as any).is_forwarded && (
                          <span className="text-[10px] text-accent-400 ml-1.5">{t('forward.forwarded')}</span>
                        )}
                      </span>
                      <span className="text-[10px] text-textMuted shrink-0">{formatSize(f.size)}</span>
                      <button
                        onClick={() => setForwardFile({ file_id: f.id, name, size: f.size, mime_type: f.mime_type || 'application/octet-stream' })}
                        className="p-1 rounded hover:bg-primary-500/10 text-textMuted hover:text-primary-400 transition-colors opacity-0 group-hover:opacity-100"
                        title={t('forward.send')}
                      >
                        <Share2 size={12} />
                      </button>
                      {(f as any).is_forwarded && (
                        <button
                          onClick={() => releaseFile(f.id)}
                          className="p-1 rounded hover:bg-rose-500/10 text-textMuted hover:text-rose-400 transition-colors opacity-0 group-hover:opacity-100"
                          title={t('forward.release')}
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-xs text-textMuted text-center py-3">{t('me.noStorage')}</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-textMuted py-3 text-center">{t('me.noStorageData')}</p>
        )}
      </div>

      {/* ====== 兑换码 ====== */}
      <div id="redeem-section" className="bg-surface rounded-2xl border border-border p-5">
        <h3 className="text-sm font-semibold text-textPrimary mb-3 flex items-center gap-2">
          <Gift size={16} className="text-primary-400" /> {t('me.redeemSection')}
        </h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={redeemCode}
            onChange={e => setRedeemCode(e.target.value)}
            placeholder={t('me.redeemPlaceholder')}
            className="flex-1 px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 font-mono"
          />
          <button
            onClick={handleRedeem}
            disabled={redeeming || !redeemCode.trim()}
            className="px-4 py-2 rounded-xl bg-primary-500 text-white hover:bg-primary-400 disabled:opacity-40 text-sm font-medium transition-colors"
          >
            {redeeming ? <Loader2 size={14} className="animate-spin" /> : t('me.redeemButton')}
          </button>
        </div>
        {redeemMsg && (
          <p className={`text-xs mt-2 ${redeemMsg.includes('失败') || redeemMsg.includes('无效') ? 'text-rose-400' : 'text-mint-400'}`}>
            {redeemMsg}
          </p>
        )}
      </div>

      {/* ====== 管理员入口 ====== */}
      {user.role === 'admin' && (
        <div className="bg-surface rounded-2xl border border-border">
          <Link
            to="/admin"
            className="flex items-center gap-3 px-5 py-3 hover:bg-elevated transition-colors"
          >
            <Shield size={16} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm text-textPrimary">{t('me.managementSection')}</div>
              <div className="text-xs text-textMuted">{t('me.managementDesc')}</div>
            </div>
            <ChevronRight size={14} className="text-textMuted shrink-0" />
          </Link>
        </div>
      )}

      {/* ====== 设置入口 ====== */}
      <Link
        to="/settings"
        className="bg-surface rounded-2xl border border-border p-5 flex items-center gap-3 hover:bg-elevated transition-colors"
      >
        <Settings size={18} className="text-textMuted shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-textPrimary">{t('me.settings')}</div>
        </div>
        <ChevronRight size={14} className="text-textMuted shrink-0" />
      </Link>

      {/* ====== 退出登录 ====== */}
      <button
        onClick={logout}
        className="w-full py-3 rounded-xl border border-rose-500/20 text-rose-400 hover:bg-rose-500/5 text-sm font-medium transition-colors flex items-center justify-center gap-2"
      >
        <LogOut size={14} /> {t('me.logout')}
      </button>

      {/* ====== 编辑资料弹窗 ====== */}
      {showEditProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowEditProfile(false)}>
          <div
            className="bg-surface rounded-2xl border border-border w-full max-w-sm mx-4 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h3 className="text-sm font-semibold text-textPrimary">{t('me.editProfileModalTitle')}</h3>
              <button onClick={() => setShowEditProfile(false)} className="p-1 rounded-lg hover:bg-elevated text-textMuted">
                <X size={16} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* 头像 */}
              <div className="flex flex-col items-center gap-2">
                <div className="w-20 h-20 rounded-full bg-primary-500/10 flex items-center justify-center overflow-hidden border-2 border-border">
                  {editAvatarUrl ? (
                    <img src={editAvatarUrl} className="w-full h-full object-cover" />
                  ) : (
                    <User size={32} className="text-primary-400" />
                  )}
                </div>
                <label className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-500 cursor-pointer transition-colors">
                  <Camera size={12} />
                  {avatarUploading ? t('me.uploadingAvatar') : t('me.changeAvatar')}
                  <input type="file" accept="image/*" className="hidden" onChange={handleAvatarSelect} disabled={avatarUploading} />
                </label>
              </div>
              <div>
                <label className="block text-xs font-medium text-textSecondary mb-1">{t('me.usernameField')}</label>
                <input
                  type="text"
                  value={editUsername}
                  onChange={e => setEditUsername(e.target.value)}
                  placeholder={user.username}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-textSecondary mb-1">{t('me.bioField')}</label>
                <textarea
                  value={editBio}
                  onChange={e => setEditBio(e.target.value)}
                  placeholder={t('me.bioPlaceholder')}
                  rows={3}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-textSecondary mb-1">{t('me.statusTextField')}</label>
                <input
                  type="text"
                  value={editStatusText}
                  onChange={e => setEditStatusText(e.target.value)}
                  placeholder={t('me.statusTextPlaceholder')}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
                <p className="text-[10px] text-textMuted mt-1">{editStatusText.length} 字</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-textSecondary mb-1">{t('me.statusColorLabel')}</label>
                <div className="flex items-center gap-2 flex-wrap">
                  {STATUS_COLORS.map(c => (
                    <button
                      key={c.value}
                      type="button"
                      onClick={() => setEditStatusColor(c.value)}
                      className={`w-6 h-6 rounded-full border-2 transition-all ${
                        editStatusColor === c.value
                          ? 'border-primary-400 scale-110 shadow-md'
                          : c.value === ''
                            ? 'border-border bg-canvas hover:border-textMuted'
                            : 'border-transparent hover:scale-105'
                      }`}
                      style={c.value ? { backgroundColor: c.value } : undefined}
                      title={c.label}
                    >
                      {c.value === '' && <X size={10} className="text-textMuted m-auto" />}
                    </button>
                  ))}
                  <div className="relative">
                    <input
                      type="color"
                      value={editStatusColor || '#000000'}
                      onChange={e => setEditStatusColor(e.target.value)}
                      className="w-6 h-6 rounded-full cursor-pointer border-2 border-border hover:border-primary-400 transition-colors"
                      title={t('me.statusColorCustom') || '自定义'}
                    />
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-textSecondary mb-1">{t('me.passwordField')}</label>
                <input
                  type="password"
                  value={editPassword}
                  onChange={e => setEditPassword(e.target.value)}
                  placeholder={t('me.passwordMinHint')}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <button
                onClick={handleSaveProfile}
                disabled={editSaving}
                className="w-full py-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-400 disabled:opacity-40 text-sm font-medium transition-colors flex items-center justify-center gap-2"
              >
                {editSaving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                {editSaving ? t('me.savingProfile') : t('me.saveButton')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 头像裁剪弹窗 */}
      {cropFile && (
        <AvatarCropModal
          file={cropFile}
          onConfirm={handleCropConfirm}
          onCancel={() => setCropFile(null)}
        />
      )}

      {/* 文件转发弹窗 */}
      {forwardFile && (
        <ForwardFileModal
          file={forwardFile}
          onClose={() => setForwardFile(null)}
        />
      )}

      {/* v1.0.0 邮箱绑定弹窗 */}
      {showBindEmail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowBindEmail(false)}>
          <div className="bg-surface border border-border rounded-2xl p-6 w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-textPrimary mb-4">{t('auth.bindEmailTitle')}</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-textSecondary mb-1">{t('auth.email')}</label>
                <input
                  type="email"
                  value={bindEmail}
                  onChange={e => { setBindEmail(e.target.value); setBindCodeSent(false) }}
                  className="w-full px-3 py-2 rounded-xl border border-border bg-canvas text-textPrimary text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/60"
                  placeholder={t('auth.emailPlaceholder')}
                />
              </div>
              <button
                type="button"
                onClick={handleSendBindCode}
                disabled={!bindEmail || bindSendCooldown > 0}
                className="w-full py-2 text-sm font-medium rounded-xl border border-primary-500/30 text-primary-500 hover:bg-primary-500/10 disabled:opacity-40 transition-colors"
              >
                {bindSendCooldown > 0
                  ? t('auth.codeResendIn').replace('{seconds}', String(bindSendCooldown))
                  : bindCodeSent ? t('auth.codeSent') : t('auth.sendCode')
                }
              </button>
              {bindCodeSent && (
                <div>
                  <label className="block text-xs text-textSecondary mb-2 text-center">{t('auth.codePlaceholder')}</label>
                  <VerificationCodeInput
                    value={bindCode}
                    onChange={setBindCode}
                    disabled={bindLoading}
                  />
                </div>
              )}
              {bindError && (
                <div className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">{bindError}</div>
              )}
              <div className="flex gap-2 pt-2">
                <button onClick={() => setShowBindEmail(false)} className="flex-1 py-2 text-sm rounded-xl border border-border text-textSecondary hover:text-textPrimary transition-colors">{t('common.cancel')}</button>
                <button
                  onClick={handleConfirmBind}
                  disabled={!bindEmail || !bindCode || bindLoading}
                  className="flex-1 py-2 text-sm rounded-xl bg-primary-500 hover:bg-primary-400 disabled:opacity-30 text-white font-medium transition-colors"
                >
                  {bindLoading ? t('auth.verifying') : t('common.confirm')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
