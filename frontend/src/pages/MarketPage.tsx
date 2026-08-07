/**
 * 世界商城 — 世界包发布 / 浏览 / 一键导入（2026-08-07 MVP）
 *
 * - 浏览：列表 + 搜索（标题/描述）+ 标签过滤
 * - 导入：一键创建新世界（跳转设计页）
 * - 发布：从我的世界发布（弹窗选世界 + 标题/描述/标签）
 * - 管理：我发布的商品可下架
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Download, Upload, X, Trash2, Globe, Tag, User, Clock, Package, Store, Edit3, CheckCircle2 } from 'lucide-react'
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
  downloads: number
  created_at: string | null
}

interface WorldBrief { id: number; name: string }

export default function MarketPage() {
  const t = useT()
  const navigate = useNavigate()
  const [items, setItems] = useState<MarketItem[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  // 发布弹窗
  const [showPublish, setShowPublish] = useState(false)
  const [myWorlds, setMyWorlds] = useState<WorldBrief[]>([])
  const [pubWorld, setPubWorld] = useState<number | null>(null)
  const [pubTitle, setPubTitle] = useState('')
  const [pubDesc, setPubDesc] = useState('')
  const [pubTags, setPubTags] = useState('')
  const [publishing, setPublishing] = useState(false)
  // 导入中
  const [importingId, setImportingId] = useState<number | null>(null)
  // 编辑弹窗
  const [editItem, setEditItem] = useState<MarketItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editTags, setEditTags] = useState('')
  const [editing, setEditing] = useState(false)
  // 居中 toast（导入成功等）
  const [toast, setToast] = useState<string | null>(null)
  // 我的 user id（判断下架按钮）
  const [myId, setMyId] = useState<number | null>(null)

  const load = useCallback(async () => {
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

  useEffect(() => { load() }, [load])

  // 当前用户 id（下架权限判断）
  useEffect(() => {
    try {
      const me = localStorage.getItem('user_info')
      if (me) setMyId(JSON.parse(me).id ?? null)
    } catch { /* ignore */ }
  }, [])

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
      setMsg('✅ 发布成功')
      load()
    } catch (e: any) {
      setMsg(`发布失败: ${e?.message || e}`)
    } finally {
      setPublishing(false)
    }
  }

  const doImport = async (item: MarketItem) => {
    setImportingId(item.id)
    setMsg('')
    try {
      const r = await api.post<{ world_id: number; name: string; imported: number }>(`/market/items/${item.id}/import`)
      setToast(`✅ 已导入「${r.name}」（${r.imported} 个文件），正在打开…`)
      setTimeout(() => navigate(`/worlds/${r.world_id}/design`), 900)
    } catch (e: any) {
      setMsg(`导入失败: ${e?.message || e}`)
      setImportingId(null)
    }
  }

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
      load()
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
      load()
    } catch (e: any) {
      setMsg(`下架失败: ${e?.message || e}`)
    }
  }

  const fmtSize = (n: number) => n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`
  const fmtDate = (s: string | null) => s ? s.slice(0, 10) : ''

  return (
    <div className="h-full flex flex-col bg-canvas">
      {/* 标题栏（统一底座） */}
      <PageHeader title="世界商城" subtitle="浏览 / 一键导入别人发布的世界" onBack={() => navigate(-1)}>
        <button
          onClick={openPublish}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-primary-500 hover:bg-primary-400 text-white transition-colors shrink-0"
        >
          <Upload size={13} /> 发布世界
        </button>
      </PageHeader>

      {/* 搜索 + 提示 */}
      <div className="px-4 pt-3 pb-2 bg-canvas shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-textMuted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') load() }}
              placeholder="搜索世界标题 / 描述…"
              className="w-full bg-elevated text-sm pl-8 pr-3 py-1.5 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
            />
          </div>
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') load() }}
            placeholder="标签，如 2d冒险"
            className="w-36 bg-elevated text-sm px-3 py-1.5 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary shrink-0"
          />
          <button onClick={load} className="text-xs px-3 py-1.5 rounded-lg bg-elevated hover:bg-border text-textSecondary transition-colors shrink-0">
            搜索
          </button>
        </div>
        {msg && <div className="text-xs text-amber-400 mt-2">{msg}</div>}
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-center text-textMuted text-sm py-16">加载中…</div>
        ) : items.length === 0 ? (
          <div className="text-center text-textMuted text-sm py-16 space-y-2">
            <Package size={32} className="mx-auto opacity-40" />
            <div>商城还没有世界。把做好的世界发布出来，让大家一键导入吧。</div>
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
                    <div className="text-sm font-semibold text-textPrimary truncate">{item.title}</div>
                    <div className="text-[10px] text-textMuted flex items-center gap-1 mt-0.5">
                      <User size={10} /> {item.author_name || `#${item.author_id}`}
                      <span className="mx-0.5">·</span>
                      <Clock size={10} /> {fmtDate(item.created_at)}
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
                        onClick={() => { setTag(tg); load() }}
                        className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted hover:text-primary-400 transition-colors"
                      ><Tag size={9} /> {tg}</button>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between mt-auto pt-1 border-t border-border/50">
                  <span className="text-[10px] text-textMuted">
                    {fmtSize(item.package_size)} · {item.downloads} 次导入
                  </span>
                  <button
                    onClick={() => doImport(item)}
                    disabled={importingId === item.id}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-primary-500/15 text-primary-400 hover:bg-primary-500/25 transition-colors disabled:opacity-40"
                  >
                    <Download size={11} />
                    {importingId === item.id ? '导入中…' : '一键导入'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {!loading && items.length > 0 && (
          <div className="text-center text-[10px] text-textMuted mt-3">共 {total} 个世界</div>
        )}
      </div>

      {/* 居中 toast（导入/更新成功提示） */}
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
              <div className="text-[10px] text-textMuted mb-1">标题（留空 = 世界名）</div>
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
