/**
 * 绑定群弹窗（世界设计页 / 世界列表页共用）
 *
 * 流程（对齐需求）：先选群类型 → 勾选群聊（只显示「我是群主」的群，可改绑）→ 批量绑定
 * 自动创建群助手（按类型模板），绑定结果逐群反馈。
 */
import { useEffect, useMemo, useState } from 'react'
import { X, Link2, Users, CheckSquare, Loader2, AlertCircle } from 'lucide-react'
import { api } from '../../api/client'

interface GroupType {
  slug: string
  name: string
  description: string
  bind_limit: number
  bound_count?: number
}

interface GroupItem {
  id: number
  name: string
  owner_type?: string
  owner_id?: number
  is_pinned?: boolean
}

interface BindGroupModalProps {
  worldId: number
  /** 预选类型（群类型卡片点「绑定群」时传入） */
  initialTypeSlug?: string
  onClose: () => void
  /** 绑定成功后回调（刷新类型绑定数/群助手） */
  onBound: () => void
}

export default function BindGroupModal({ worldId, initialTypeSlug, onClose, onBound }: BindGroupModalProps) {
  const [types, setTypes] = useState<GroupType[]>([])
  const [groups, setGroups] = useState<GroupItem[]>([])
  const [boundGroupIds, setBoundGroupIds] = useState<Set<number>>(new Set())
  const [typeSlug, setTypeSlug] = useState<string>(initialTypeSlug || '')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [msg, setMsg] = useState('')
  const [binding, setBinding] = useState(false)
  const myId = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user_info') || '{}').id ?? null } catch { return null }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [t, g, w] = await Promise.all([
          api.get<{ types: GroupType[] }>(`/worlds/${worldId}/group-types`),
          api.get<GroupItem[]>('/groups'),
          api.get<{ bindings: { entity_type: string; entity_id: number }[] }>(`/worlds/${worldId}`),
        ])
        if (cancelled) return
        setTypes(t.types || [])
        setGroups(g || [])
        setBoundGroupIds(new Set((w.bindings || []).filter((b) => b.entity_type === 'group').map((b) => b.entity_id)))
      } catch { /* 失败静默，弹窗可关 */ }
    })()
    return () => { cancelled = true }
  }, [worldId])

  // 可绑定群：仅「我是群主」（owner_type=human 且 owner_id=我）
  const ownedGroups = useMemo(
    () => groups.filter((g) => g.owner_type === 'human' && g.owner_id === myId),
    [groups, myId],
  )
  const currentType = types.find((t) => t.slug === typeSlug)

  const toggle = (gid: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(gid)) next.delete(gid)
      else next.add(gid)
      return next
    })
  }

  const doBind = async () => {
    if (!typeSlug || selected.size === 0) return
    setBinding(true)
    setMsg('')
    try {
      const r = await api.post<{ bound: number; failed: number; results: { group_id: number; success: boolean; error?: string }[] }>(
        `/worlds/${worldId}/bind-groups`, { type_slug: typeSlug, group_ids: [...selected] },
      )
      // 绑定成功的群从勾选移除 + 标记已绑
      const done = new Set((r.results || []).filter((x) => x.success).map((x) => x.group_id))
      setBoundGroupIds((prev) => { const n = new Set(prev); done.forEach((g) => n.add(g)); return n })
      setSelected((prev) => { const n = new Set(prev); done.forEach((g) => n.delete(g)); return n })
      if (r.failed === 0) {
        // 全部成功：直接关闭（结果已在类型/群列表上体现）
        onBound()
        onClose()
        return
      }
      // 部分失败：留在弹窗，只提示失败的
      const errors = (r.results || []).filter((x) => !x.success).map((x) => x.error).filter(Boolean)
      setMsg(`${r.failed} 个群绑定失败${errors.length ? '：' + errors[0] : ''}`)
      onBound()
    } catch (e: any) {
      setMsg(`绑定失败: ${e?.message || e}`)
    } finally {
      setBinding(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="w-full max-w-md bg-surface border border-border rounded-2xl max-h-[85vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()}>
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 pb-2 shrink-0">
          <div className="flex items-center gap-2">
            <Link2 size={16} className="text-primary-400" />
            <span className="text-sm font-semibold text-textPrimary">绑定群聊</span>
            <span className="text-[10px] text-textMuted">选类型 → 勾选群 → 批量绑定（自动创建群助手）</span>
          </div>
          <button onClick={onClose} className="p-1 text-textMuted hover:text-textPrimary transition-colors" title="关闭"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {/* 1. 选类型 */}
          <div>
            <div className="text-[10px] text-textSecondary uppercase tracking-wide font-medium mb-1.5 flex items-center gap-1"><Users size={11} className="text-primary-400" /> 1. 选择群类型</div>
            {types.length === 0 ? (
              <div className="text-xs text-textMuted bg-elevated/40 rounded-xl p-3">还没有群类型——先去「群类型与群助手」里创建（如 冒险团/商会/座谈会），才能给群分类。</div>
            ) : (
              <div className="space-y-1.5">
                {types.map((t) => (
                  <button
                    key={t.slug}
                    onClick={() => setTypeSlug(t.slug)}
                    className={`w-full text-left px-3 py-2 rounded-xl border transition-colors ${typeSlug === t.slug ? 'border-primary-500/50 bg-primary-500/10' : 'border-border bg-elevated/40 hover:bg-elevated'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-textPrimary">{t.name}</span>
                      <span className="text-[10px] text-textMuted">{t.bound_count ?? '?'}/{t.bind_limit} 群</span>
                    </div>
                    {t.description && <div className="text-xs text-textSecondary line-clamp-1 mt-0.5">{t.description}</div>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 2. 勾选群 */}
          {typeSlug && (
            <div>
              <div className="text-[10px] text-textSecondary uppercase tracking-wide font-medium mb-1.5 flex items-center gap-1"><CheckSquare size={11} className="text-primary-400" /> 2. 勾选群聊（仅显示你群主的群）</div>
              {ownedGroups.length === 0 ? (
                <div className="text-xs text-textMuted bg-elevated/40 rounded-xl p-3">你没有可绑定的群（需要是你创建的群）。</div>
              ) : (
                <div className="space-y-1">
                  {ownedGroups.map((g) => {
                    const isBound = boundGroupIds.has(g.id)
                    const isSelected = selected.has(g.id)
                    return (
                      <label
                        key={g.id}
                        className={`flex items-center gap-2 px-3 py-2 rounded-xl border cursor-pointer transition-colors ${isSelected ? 'border-primary-500/50 bg-primary-500/10' : isBound ? 'border-border bg-elevated/30 opacity-60' : 'border-border bg-elevated/40 hover:bg-elevated'}`}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={binding}
                          onChange={() => toggle(g.id)}
                          className="accent-primary-500 shrink-0"
                        />
                        <span className="truncate flex-1 text-sm text-textPrimary">{g.name}</span>
                        <span className="shrink-0 text-[10px] text-textMuted">#{g.id}</span>
                        {isBound && <span className="shrink-0 text-[10px] text-textMuted">已绑定{currentType && boundGroupIds.has(g.id) ? '' : ''}</span>}
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )}
          {msg && <div className="inline-flex items-center gap-1 text-xs text-rose-400"><AlertCircle size={12} className="shrink-0" /> {msg}</div>}
        </div>

        {/* 底部操作 */}
        <div className="p-4 pt-3 shrink-0 border-t border-border flex items-center gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-textMuted hover:text-textPrimary transition-colors rounded-lg">取消</button>
          <div className="flex-1" />
          <button
            onClick={doBind}
            disabled={!typeSlug || selected.size === 0 || binding}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors disabled:opacity-40"
          >
            {binding ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
            绑定 {selected.size > 0 ? `${selected.size} 个群` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}
