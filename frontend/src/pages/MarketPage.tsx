/**
 * 世界商城 — 本地 / GitHub 双板块（2026-08-08）
 *
 * - 本地板块：本实例发布的商品（DB source=local），标注同步状态
 *   （未同步 / 已同步🟢 / 同步过🟡），显示本地+云端下载数与更新时间
 * - GitHub 板块：GitHub 索引快照（refresh 缓存），标注来源（本地/远程），
 *   非本地资源可一键导入
 * - GitHub 绑定：用户绑定自己的 GitHub 账户，同步时以本人身份推送
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Download, Upload, X, Trash2, Globe, Tag, User, Clock,
  Package, Store, Edit3, CheckCircle2, RefreshCw, Github, Link2, Unlink, ArrowUpCircle, Database,
} from 'lucide-react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import PageHeader from '../components/PageHeader'

interface MarketItem {
  id: number
  kind: string
  title: string
  description: string
  tags: string[]
  author_id: number
  author_name: string
  source_world_id: number | null
  package_size: number
  downloads: number            // 本地下载数
  github_downloads?: number | null  // 云端下载数
  updated_at: string | null    // 本地更新时间
  github_updated_at?: string | null // 云端更新时间
  sync_state: 'unsynced' | 'synced' | 'stale'
  github_path: string | null
  slug?: string
}

interface GithubItem {
  id: number
  slug: string
  title: string
  description: string
  tags: string[]
  author_name: string
  downloads: number | null
  updated_at: string | null
  is_local: boolean
}

interface WorldBrief { id: number; name: string }

type Tab = 'local' | 'github'

const fmtSize = (n: number) => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`
const fmtDate = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'

export default function MarketPage() {
  const t = useT()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('local')

  // ── 本地板块 ──
  const [items, setItems] = useState<MarketItem[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')

  // ── GitHub 板块 ──
  const [ghItems, setGhItems] = useState<GithubItem[]>([])
  const [ghSyncedAt, setGhSyncedAt] = useState<string | null>(null)
  const [ghLoading, setGhLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  // ── GitHub 绑定 ──
  const [bindState, setBindState] = useState<{ bound: boolean; username: string | null } | null>(null)
  const [bindToken, setBindToken] = useState('')
  const [binding, setBinding] = useState(false)

  // ── 发布/编辑/导入 ──
  const [showPublish, setShowPublish] = useState(false)
  const [myWorlds, setMyWorlds] = useState<WorldBrief[]>([])
  const [pubWorld, setPubWorld] = useState<number | null>(null)
  const [pubTitle, setPubTitle] = useState('')
  const [pubDesc, setPubDesc] = useState('')
  const [pubTags, setPubTags] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [importingId, setImportingId] = useState<number | null>(null)
  const [syncingId, setSyncingId] = useState<number | null>(null)
  const [editItem, setEditItem] = useState<MarketItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editTags, setEditTags] = useState('')
  const [editing, setEditing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [myId, setMyId] = useState<number | null>(null)

  // ── 数据加载 ──
  const loadLocal = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (q.trim()) params.set('q', q.trim())
      if (tag.trim()) params.set('tag', tag.trim())
      params.set('kind', 'world')
      const r = await api.get<{ total: number; items: MarketItem[] }>(`/market/items?${params}`)
      setItems(r.items || [])
      setTotal(r.total || 0)
    } catch (e: any) {
      setMsg(`加载失败: ${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }, [q, tag])

  const loadGithub = useCallback(async () => {
    setGhLoading(true)
    try {
      const r = await api.get<{ synced_at: string | null; items: GithubItem[] }>(`/market/github/items`)
      setGhItems(r.items || [])
      setGhSyncedAt(r.synced_at || null)
    } catch (e: any) {
      setMsg(`GitHub 板块加载失败: ${e?.message || e}`)
    } finally {
      setGhLoading(false)
    }
  }, [])

  const loadBind = useCallback(async () => {
    try {
      const r = await api.get<{ bound: boolean; username: string | null }>(`/market/github/bind`)
      setBindState(r)
    } catch { /* 非致命 */ }
  }, [])

  useEffect(() => { loadLocal() }, [loadLocal])
  useEffect(() => { loadBind() }, [loadBind])
  useEffect(() => { if (tab === 'github') loadGithub() }, [tab, loadGithub])

  // 当前用户 id（操作权限判断）
  useEffect(() => {
    try {
      const me = localStorage.getItem('user_info')
      if (me) setMyId(JSON.parse(me).id ?? null)
    } catch { /* ignore */ }
  }, [])

  // ── GitHub 绑定 ──
  const doBind = async () => {
    if (!bindToken.trim()) { setMsg('请输入 GitHub token'); return }
    setBinding(true)
    try {
      const r = await api.post<{ bound: boolean; username: string }>('/market/github/bind', { token: bindToken.trim() })
      setBindState(r)
      setBindToken('')
      setToast(`✅ 已绑定 GitHub 账户 @${r.username}`)
      setTimeout(() => setToast(null), 2500)
    } catch (e: any) {
      setMsg(`绑定失败: ${e?.message || e}`)
    } finally {
      setBinding(false)
    }
  }

  const doUnbind = async () => {
    if (!confirm('解绑 GitHub 账户？（同步将回退为管理员 token）')) return
    try {
      await api.delete('/market/github/bind')
      setBindState({ bound: false, username: null })
      setToast('已解绑 GitHub 账户')
      setTimeout(() => setToast(null), 2500)
    } catch (e: any) {
      setMsg(`解绑失败: ${e?.message || e}`)
    }
  }

  // ── 刷新 GitHub 快照（管理员）──
  const doRefreshGithub = async () => {
    setRefreshing(true)
    setMsg('')
    try {
      const r = await api.post<{ added: number; updated: number; removed: number }>('/market/github/refresh')
      setToast(`✅ GitHub 刷新完成: +${r.added} 新增, ${r.updated} 更新, -${r.removed} 移除`)
      setTimeout(() => setToast(null), 3000)
      loadGithub()
      loadLocal() // 本地同步状态可能变化
    } catch (e: any) {
      setMsg(`刷新失败: ${e?.message || e}`)
    } finally {
      setRefreshing(false)
    }
  }

  // ── 发布 ──
  const openPublish = async () => {
    setShowPublish(true)
    setMsg('')
    try {
      const ws = await api.get<WorldBrief[]>(`/worlds`)
      setMyWorlds(Array.isArray(ws) ? ws : [])
      if (ws.length > 0) setPubWorld(ws[0].id)
    } catch { setMyWorlds([]) }
  }

  const doPublish = async () => {
    if (!pubWorld) { setMsg('请选择要发布的世界'); return }
    setPublishing(true)
    try {
      await api.post('/market/items', {
        world_id: pubWorld,
        title: pubTitle.trim(),
        description: pubDesc.trim(),
        tags: pubTags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      })
      setShowPublish(false)
      setPubTitle(''); setPubDesc(''); setPubTags('')
      setToast('✅ 发布成功')
      setTimeout(() => setToast(null), 2500)
      loadLocal()
    } catch (e: any) {
      setMsg(`发布失败: ${e?.message || e}`)
    } finally {
      setPublishing(false)
    }
  }

  // ── 同步到 GitHub ──
  const doSync = async (item: MarketItem) => {
    setSyncingId(item.id)
    setMsg('')
    try {
      const r = await api.post<{ success: boolean; path: string }>(`/market/items/${item.id}/sync-github`)
      setToast(`✅ 已同步到 GitHub: ${r.path}`)
      setTimeout(() => setToast(null), 3000)
      loadLocal()
      loadGithub()
    } catch (e: any) {
      setMsg(`同步失败: ${e?.message || e}`)
    } finally {
      setSyncingId(null)
    }
  }

  // ── 导入（本地商品 / GitHub 远程资源）──
  const doImport = async (item: MarketItem | GithubItem) => {
    setImportingId(item.id)
    setMsg('')
    try {
      const r = await api.post<{ world_id: number; name: string; imported: number }>(
        item && 'is_local' in item ? `/market/github/import` : `/market/items/${item.id}/import`,
        item && 'is_local' in item ? { id: item.id } : undefined,
      )
      setToast(`✅ 已导入「${r.name}」（${r.imported} 个文件），正在打开…`)
      setTimeout(() => navigate(`/worlds/${r.world_id}/design`), 900)
    } catch (e: any) {
      setMsg(`导入失败: ${e?.message || e}`)
      setImportingId(null)
    }
  }

  // ── 编辑/下架 ──
  const openEdit = (item: MarketItem) => {
    setEditItem(item)
    setEditTitle(item.title)
    setEditDesc(item.description || '')
    setEditTags((item.tags || []).join(','))
  }

  const doEdit = async () => {
    if (!editItem) return
    setEditing(true)
    try {
      const updated = await api.put<MarketItem>(`/market/items/${editItem.id}`, {
        title: editTitle.trim(),
        description: editDesc.trim(),
        tags: editTags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      })
      setEditItem(null)
      setToast(`✅ 商品「${updated.title}」已更新`)
      setTimeout(() => setToast(null), 2500)
      loadLocal()
    } catch (e: any) {
      setMsg(`保存失败: ${e?.message || e}`)
    } finally {
      setEditing(false)
    }
  }

  const doUnpublish = async (item: MarketItem) => {
    if (!confirm(`下架「${item.title}」？（不影响已导入的世界）`)) return
    try {
      await api.delete(`/market/items/${item.id}`)
      setMsg('✅ 已下架')
      loadLocal()
    } catch (e: any) {
      setMsg(`下架失败: ${e?.message || e}`)
    }
  }

  // ── 同步状态徽标 ──
  const SyncBadge = ({ item }: { item: MarketItem }) => {
    if (item.sync_state === 'synced') {
      return <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-mint-500/15 text-mint-400"><CheckCircle2 size={9} /> 已同步</span>
    }
    if (item.sync_state === 'stale') {
      return <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400"><RefreshCw size={9} /> 同步过（有改动）</span>
    }
    return null
  }

  return (
    <div className="h-full flex flex-col bg-canvas">
      {/* 标题栏（统一底座） */}
      <PageHeader title="世界商城" subtitle="本地发布 / GitHub 资源共享" onBack={() => navigate(-1)}>
        <button
          onClick={openPublish}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-primary-500 hover:bg-primary-400 text-white transition-colors shrink-0"
        >
          <Upload size={13} /> 发布世界
        </button>
      </PageHeader>

      {/* 板块切换 */}
      <div className="px-4 pt-2 shrink-0">
        <div className="flex items-center gap-1 bg-elevated rounded-lg p-0.5 w-fit">
          <button
            onClick={() => setTab('local')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md transition-colors ${tab === 'local' ? 'bg-primary-500/15 text-primary-400' : 'text-textSecondary hover:text-textPrimary'}`}
          >
            <Database size={12} /> 本地 <span className="text-[10px] opacity-70">({total})</span>
          </button>
          <button
            onClick={() => setTab('github')}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md transition-colors ${tab === 'github' ? 'bg-primary-500/15 text-primary-400' : 'text-textSecondary hover:text-textPrimary'}`}
          >
            <Github size={12} /> GitHub <span className="text-[10px] opacity-70">({ghItems.length})</span>
          </button>
        </div>
      </div>

      {/* GitHub 绑定条 */}
      <div className="px-4 pt-2 shrink-0">
        <div className="flex items-center gap-2 text-xs rounded-lg bg-surface border border-border px-3 py-2">
          <Link2 size={12} className="text-textMuted shrink-0" />
          {bindState?.bound ? (
            <>
              <span className="text-textSecondary">已绑定 GitHub：<span className="text-primary-400 font-semibold">@{bindState.username}</span>（同步以你的身份推送）</span>
              <button onClick={doUnbind} className="ml-auto inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-elevated text-textMuted hover:text-rose-400 transition-colors shrink-0">
                <Unlink size={10} /> 解绑
              </button>
            </>
          ) : (
            <>
              <span className="text-textMuted shrink-0">绑定 GitHub 后同步用你的身份</span>
              <input
                value={bindToken}
                onChange={(e) => setBindToken(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') doBind() }}
                placeholder="github_pat_… / ghp_…"
                type="password"
                className="flex-1 min-w-0 bg-elevated text-xs px-2 py-1 rounded border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
              <button
                onClick={doBind}
                disabled={binding}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-primary-500/15 text-primary-400 hover:bg-primary-500/25 transition-colors shrink-0 disabled:opacity-40"
              >
                <Link2 size={10} /> {binding ? '绑定中…' : '绑定'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* 搜索 / 刷新 */}
      <div className="px-4 pt-2 pb-2 bg-canvas shrink-0">
        <div className="flex items-center gap-2">
          {tab === 'local' ? (
            <>
              <div className="relative flex-1">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-textMuted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') loadLocal() }}
                  placeholder="搜索世界标题 / 描述…"
                  className="w-full bg-elevated text-sm pl-8 pr-3 py-1.5 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
                />
              </div>
              <input
                value={tag}
                onChange={(e) => setTag(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') loadLocal() }}
                placeholder="标签，如 2d冒险"
                className="w-36 bg-elevated text-sm px-3 py-1.5 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary shrink-0"
              />
              <button onClick={loadLocal} className="text-xs px-3 py-1.5 rounded-lg bg-elevated hover:bg-border text-textSecondary transition-colors shrink-0">
                搜索
              </button>
            </>
          ) : (
            <>
              <div className="flex-1 text-[10px] text-textMuted">
                {ghSyncedAt ? `快照时间: ${fmtDate(ghSyncedAt)}（点击刷新获取最新）` : 'GitHub 快照为空，点击刷新获取'}
              </div>
              <button
                onClick={doRefreshGithub}
                disabled={refreshing}
                className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-elevated hover:bg-border text-textSecondary transition-colors shrink-0 disabled:opacity-40"
              >
                <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} /> {refreshing ? '刷新中…' : '刷新'}
              </button>
            </>
          )}
        </div>
        {msg && <div className="text-xs text-amber-400 mt-2">{msg}</div>}
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'local' ? (
          loading ? (
            <div className="text-center text-textMuted text-sm py-16">加载中…</div>
          ) : items.length === 0 ? (
            <div className="text-center text-textMuted text-sm py-16 space-y-2">
              <Package size={32} className="mx-auto opacity-40" />
              <div>本地商城还没有世界。把做好的世界发布出来吧。</div>
              <button onClick={openPublish} className="text-xs px-3 py-1.5 rounded-lg bg-elevated hover:bg-border text-primary-400 transition-colors">
                + 发布第一个世界
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {items.map((item) => (
                <div key={item.id} className="rounded-xl bg-surface border border-border p-3 flex flex-col gap-2 hover:border-primary-500/40 transition-colors">
                  <div className="flex items-start gap-2">
                    <div className="w-9 h-9 rounded-lg bg-primary-500/15 text-primary-400 flex items-center justify-center shrink-0">
                      <Globe size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-textPrimary truncate">{item.title}</span>
                        <SyncBadge item={item} />
                      </div>
                      <div className="text-[10px] text-textMuted flex items-center gap-1 mt-0.5">
                        <User size={10} /> {item.author_name || `#${item.author_id}`}
                        <span className="mx-0.5">·</span>
                        <Clock size={10} /> 更新 {fmtDate(item.updated_at)}
                      </div>
                    </div>
                    {myId !== null && item.author_id === myId && (
                      <div className="flex items-center shrink-0">
                        <button
                          onClick={() => openEdit(item)}
                          className="p-1 text-textMuted hover:text-primary-400 transition-colors"
                          title="编辑介绍"
                        ><Edit3 size={13} /></button>
                        <button
                          onClick={() => doUnpublish(item)}
                          className="p-1 text-textMuted hover:text-rose-400 transition-colors"
                          title="下架"
                        ><Trash2 size={13} /></button>
                      </div>
                    )}
                  </div>
                  {item.description && (
                    <div className="text-xs text-textSecondary line-clamp-2 min-h-[2em]">{item.description}</div>
                  )}
                  {item.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {item.tags.map((tg) => (
                        <button
                          key={tg}
                          onClick={() => { setTag(tg); loadLocal() }}
                          className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted hover:text-primary-400 transition-colors"
                        ><Tag size={9} /> {tg}</button>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-auto pt-1 border-t border-border/50">
                    <span className="text-[10px] text-textMuted space-x-2">
                      <span>本地 {item.downloads} 次导入</span>
                      {item.github_downloads != null && <span>云端 {item.github_downloads} 次</span>}
                      {item.sync_state === 'stale' && <span className="text-amber-400/80">云端 {fmtDate(item.github_updated_at)}</span>}
                    </span>
                    {myId !== null && item.author_id === myId && (
                      <button
                        onClick={() => doSync(item)}
                        disabled={syncingId === item.id || item.sync_state === 'synced'}
                        title={item.sync_state === 'synced' ? '已是最新' : '同步到 GitHub'}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-elevated text-textMuted hover:text-primary-400 transition-colors disabled:opacity-40 shrink-0"
                      >
                        <ArrowUpCircle size={11} />
                        {syncingId === item.id ? '同步中…' : item.sync_state === 'synced' ? '已同步' : '同步'}
                      </button>
                    )}
                    {!(myId !== null && item.author_id === myId) && (
                      <button
                        onClick={() => doImport(item)}
                        disabled={importingId === item.id}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-primary-500/15 text-primary-400 hover:bg-primary-500/25 transition-colors disabled:opacity-40"
                      >
                        <Download size={11} />
                        {importingId === item.id ? '导入中…' : '一键导入'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )
        ) : (
          ghLoading ? (
            <div className="text-center text-textMuted text-sm py-16">加载中…</div>
          ) : ghItems.length === 0 ? (
            <div className="text-center text-textMuted text-sm py-16 space-y-2">
              <Github size={32} className="mx-auto opacity-40" />
              <div>GitHub 快照为空。点击右上「刷新」从仓库拉取世界列表。</div>
              <div className="text-[10px] opacity-60">仓库: Coprexist/AIsChat-Community · 管理员可在后台配置仓库与自动获取</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {ghItems.map((item) => (
                <div key={item.id} className="rounded-xl bg-surface border border-border p-3 flex flex-col gap-2 hover:border-primary-500/40 transition-colors">
                  <div className="flex items-start gap-2">
                    <div className="w-9 h-9 rounded-lg bg-[#24292F]/10 dark:bg-white/10 text-[#24292F] dark:text-white flex items-center justify-center shrink-0">
                      <Github size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-textPrimary truncate">{item.title}</span>
                        {item.is_local ? (
                          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-primary-500/15 text-primary-400 shrink-0"><Store size={9} /> 本地</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted shrink-0"><Github size={9} /> 远程</span>
                        )}
                      </div>
                      <div className="text-[10px] text-textMuted flex items-center gap-1 mt-0.5">
                        <User size={10} /> {item.author_name || 'GitHub'}
                        <span className="mx-0.5">·</span>
                        <Clock size={10} /> 更新 {fmtDate(item.updated_at)}
                      </div>
                    </div>
                  </div>
                  {item.description && (
                    <div className="text-xs text-textSecondary line-clamp-2 min-h-[2em]">{item.description}</div>
                  )}
                  {item.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {item.tags.map((tg) => (
                        <span key={tg} className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted"><Tag size={9} /> {tg}</span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-auto pt-1 border-t border-border/50">
                    <span className="text-[10px] text-textMuted">
                      {item.downloads != null ? `云端 ${item.downloads} 次下载` : ''}
                      {item.slug ? ` · ${item.slug}` : ''}
                    </span>
                    {!item.is_local && (
                      <button
                        onClick={() => doImport(item)}
                        disabled={importingId === item.id}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-primary-500/15 text-primary-400 hover:bg-primary-500/25 transition-colors disabled:opacity-40"
                      >
                        <Download size={11} />
                        {importingId === item.id ? '导入中…' : '导入到我的世界'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
        {!loading && tab === 'local' && items.length > 0 && (
          <div className="text-center text-[10px] text-textMuted mt-3">共 {total} 个世界</div>
        )}
      </div>

      {/* 居中 toast */}
      {toast && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2 px-4 py-2.5 rounded-xl bg-surface border border-border shadow-2xl text-sm text-mint-400">
          <CheckCircle2 size={16} className="shrink-0" />
          <span className="whitespace-nowrap">{toast}</span>
        </div>
      )}

      {/* 编辑弹窗 */}
      {editItem && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setEditItem(null)}>
          <div className="w-full max-w-md rounded-2xl bg-surface border border-border p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-textPrimary">编辑商品介绍</span>
              <button onClick={() => setEditItem(null)} className="p-1 text-textMuted hover:text-textPrimary"><X size={15} /></button>
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标题</div>
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">描述</div>
              <textarea
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                rows={3}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none resize-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标签（逗号分隔）</div>
              <input
                value={editTags}
                onChange={(e) => setEditTags(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <button
              onClick={doEdit}
              disabled={editing}
              className="w-full py-2 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors disabled:opacity-40"
            >
              {editing ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      )}

      {/* 发布弹窗 */}
      {showPublish && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowPublish(false)}>
          <div className="w-full max-w-md rounded-2xl bg-surface border border-border p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-textPrimary">发布世界到商城</span>
              <button onClick={() => setShowPublish(false)} className="p-1 text-textMuted hover:text-textPrimary"><X size={15} /></button>
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">选择要发布的世界（打包代码区，不含 content/ 数据）</div>
              <select
                value={pubWorld ?? ''}
                onChange={(e) => setPubWorld(Number(e.target.value))}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none text-textPrimary"
              >
                {myWorlds.length === 0 && <option value="">（没有可发布的世界）</option>}
                {myWorlds.map((w) => <option key={w.id} value={w.id}>{w.name} (#{w.id})</option>)}
              </select>
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标题（留空 = 世界名；同步到 GitHub 时作为目录名）</div>
              <input
                value={pubTitle}
                onChange={(e) => setPubTitle(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">描述</div>
              <textarea
                value={pubDesc}
                onChange={(e) => setPubDesc(e.target.value)}
                rows={2}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none resize-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标签（逗号分隔，如 2d冒险,卡牌）</div>
              <input
                value={pubTags}
                onChange={(e) => setPubTags(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <button
              onClick={doPublish}
              disabled={publishing || myWorlds.length === 0}
              className="w-full py-2 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors disabled:opacity-40"
            >
              {publishing ? '发布中…' : '发布'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
