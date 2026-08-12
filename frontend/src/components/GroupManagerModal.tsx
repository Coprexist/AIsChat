/**
 * 群类型与群助手管理（世界设计页 "…" 菜单）
 *
 * Tab A 群类型：世界作者定义预设类型（规则/绑定上限/助手模板），
 *              群绑定到类型时按模板自动创建群助手（每群可多个）
 * Tab B 群助手：列出世界所有群助手，群主可填自定义 API / 一键应用全局 API / 清除
 *              （need_api=false 的类型助手不显示填 API 按钮——纯后端操控）
 */
import { useCallback, useEffect, useState } from 'react'
import { X, Plus, Trash2, Link2, Key, Globe, RefreshCw, Users, BookOpen, CheckCircle2 } from 'lucide-react'
import { api } from '../api/client'
import BindGroupModal from './world/BindGroupModal'

interface GroupType {
  slug: string
  name: string
  description: string
  rules: string
  bind_limit: number
  assistant_spec: { count?: number; need_api?: boolean; default_name?: string }
  bound_count: number
}

interface Assistant {
  id: number
  group_id: number
  group_type_slug: string | null
  name: string
  configured: boolean
  has_global: boolean
}

interface Props {
  worldId: number
  isOwner: boolean
  onClose: () => void
}

export default function GroupManagerModal({ worldId, isOwner, onClose }: Props) {
  const [tab, setTab] = useState<'types' | 'assistants'>('types')
  const [types, setTypes] = useState<GroupType[]>([])
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(false)

  // ── 新建类型表单 ──
  const [newType, setNewType] = useState({ name: '', description: '', rules: '', bind_limit: 3, count: 1, need_api: true, default_name: '群助手' })

  const [apiInput, setApiInput] = useState<{ agentId: number; key: string; base: string } | null>(null)
  const [applying, setApplying] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [t, a] = await Promise.all([
        api.get<{ types: GroupType[] }>(`/worlds/${worldId}/group-types`),
        api.get<{ assistants: Assistant[] }>(`/worlds/${worldId}/assistants`),
      ])
      setTypes(t.types || [])
      setAssistants(a.assistants || [])
    } catch (e: any) {
      setMsg(`加载失败: ${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }, [worldId])

  // 世界已绑定的群（绑定群时选择）
  useEffect(() => { load() }, [load])

  const createType = async () => {
    setApplying(true); setMsg('')
    try {
      const current = types.map(({ bound_count: _b, ...t }) => t)
      await api.post(`/worlds/${worldId}/group-types`, {
        types: [...current, {
          name: newType.name, description: newType.description, rules: newType.rules,
          bind_limit: Number(newType.bind_limit) || 3,
          assistant_spec: { count: Number(newType.count) || 1, need_api: newType.need_api, default_name: newType.default_name },
        }],
      })
      setNewType({ name: '', description: '', rules: '', bind_limit: 3, count: 1, need_api: true, default_name: '群助手' })
      load()
    } catch (e: any) { setMsg(`创建失败: ${e?.message || e}`) } finally { setApplying(false) }
  }

  const deleteType = async (t: GroupType) => {
    if (!confirm(`删除群类型「${t.name}」？（已绑定群将解除类型，群助手保留）`)) return
    try { await api.delete(`/worlds/${worldId}/group-types/${t.slug}`); load() }
    catch (e: any) { setMsg(`删除失败: ${e?.message || e}`) }
  }

  // 绑定群弹窗（选类型 → 勾选群批量绑定）
  const [bindOpen, setBindOpen] = useState<{ typeSlug: string } | null>(null)

  const saveApi = async (agentId: number) => {
    if (!apiInput) return
    setApplying(true); setMsg('')
    try {
      await api.put(`/worlds/${worldId}/assistants/${agentId}/api`, { api_key: apiInput.key, api_base_url: apiInput.base || undefined })
      setApiInput(null); load()
    } catch (e: any) { setMsg(`保存失败: ${e?.message || e}`) } finally { setApplying(false) }
  }

  const applyGlobal = async (agentId: number) => {
    setApplying(true); setMsg('')
    try { await api.post(`/worlds/${worldId}/assistants/${agentId}/apply-global`); load() }
    catch (e: any) { setMsg(`应用失败: ${e?.message || e}`) } finally { setApplying(false) }
  }

  const clearApi = async (agentId: number) => {
    if (!confirm('清除该群助手的 API？（回落系统默认）')) return
    try { await api.delete(`/worlds/${worldId}/assistants/${agentId}/api`); load() }
    catch (e: any) { setMsg(`清除失败: ${e?.message || e}`) }
  }

  const needApi = (a: Assistant) => {
    const t = types.find(x => x.slug === a.group_type_slug)
    return t ? (t.assistant_spec?.need_api !== false) : true
  }

  const typeName = (slug: string | null) => types.find(t => t.slug === slug)?.name || (slug ? `类型#${slug}` : '未绑定')

  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="w-full max-w-2xl bg-surface border border-border rounded-2xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 pb-2 shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-primary-400" />
            <span className="text-sm font-semibold text-textPrimary">群类型与群助手</span>
            <span className="text-[10px] text-textMuted">世界按类型分发，规则挂在类型上</span>
          </div>
          <button onClick={onClose} className="p-1 text-textMuted hover:text-textPrimary"><X size={16} /></button>
        </div>
        {/* Tab */}
        <div className="px-4 shrink-0">
          <div className="flex items-center gap-1 bg-elevated rounded-lg p-0.5 w-fit">
            <button onClick={() => setTab('types')} className={`inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md ${tab === 'types' ? 'bg-primary-500/15 text-primary-400' : 'text-textSecondary'}`}>
              <Users size={12} /> 群类型 ({types.length})
            </button>
            <button onClick={() => setTab('assistants')} className={`inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md ${tab === 'assistants' ? 'bg-primary-500/15 text-primary-400' : 'text-textSecondary'}`}>
              <Key size={12} /> 群助手 ({assistants.length})
            </button>
          </div>
        </div>

        {msg && <div className="px-4 pt-2 text-xs text-amber-400">{msg}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {tab === 'types' ? (
            <>
              {/* 类型列表 */}
              {types.map(t => (
                <div key={t.slug} className="rounded-xl bg-elevated/50 border border-border p-3 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-textPrimary">{t.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${t.bound_count >= t.bind_limit ? 'bg-amber-500/15 text-amber-400' : 'bg-elevated text-textMuted'}`}>
                      绑定 {t.bound_count}/{t.bind_limit}
                    </span>
                    <span className="text-[10px] text-textMuted">助手 {t.assistant_spec?.count ?? 1} 个{t.assistant_spec?.need_api === false ? '（无需API）' : ''}</span>
                    <div className="flex-1" />
                    {isOwner && (
                      <button onClick={() => deleteType(t)} className="p-1 text-textMuted hover:text-rose-400" title="删除类型"><Trash2 size={13} /></button>
                    )}
                  </div>
                  {t.rules && <div className="text-xs text-textSecondary whitespace-pre-wrap line-clamp-3">{t.rules}</div>}
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={() => setBindOpen({ typeSlug: t.slug })}
                      className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-primary-500/15 text-primary-400 hover:bg-primary-500/25"
                    >
                      <Link2 size={10} /> 绑定群
                    </button>
                  </div>
                </div>
              ))}
              {types.length === 0 && <div className="text-center text-textMuted text-xs py-6">还没有群类型。创建第一个，让群按类型接入你的世界。</div>}

              {bindOpen && (
        <BindGroupModal
          worldId={worldId}
          initialTypeSlug={bindOpen.typeSlug}
          onClose={() => setBindOpen(null)}
          onBound={() => { load() }}
        />
      )}

      {/* 新建类型（世界作者） */}
              {isOwner && (
                <div className="rounded-xl border border-border p-3 space-y-2">
                  <div className="text-xs font-semibold text-textPrimary flex items-center gap-1"><Plus size={12} /> 新建群类型</div>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={newType.name} onChange={e => setNewType({ ...newType, name: e.target.value })} placeholder="类型名（如 冒险团/商会）" className="bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary" />
                    <input value={newType.bind_limit} onChange={e => setNewType({ ...newType, bind_limit: Number(e.target.value) })} type="number" min={1} placeholder="绑定上限" className="bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary" />
                  </div>
                  <textarea value={newType.rules} onChange={e => setNewType({ ...newType, rules: e.target.value })} rows={2} placeholder="世界规则（群主可见；群助手行为继承）" className="w-full bg-elevated text-xs px-2 py-1.5 rounded border border-border resize-none text-textPrimary" />
                  <div className="grid grid-cols-3 gap-2">
                    <input value={newType.count} onChange={e => setNewType({ ...newType, count: Number(e.target.value) })} type="number" min={1} placeholder="助手数量" className="bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary" />
                    <input value={newType.default_name} onChange={e => setNewType({ ...newType, default_name: e.target.value })} placeholder="助手默认名" className="bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary" />
                    <label className="flex items-center gap-1.5 text-[10px] text-textSecondary">
                      <input type="checkbox" checked={newType.need_api} onChange={e => setNewType({ ...newType, need_api: e.target.checked })} className="accent-primary-500" />
                      助手需要 API
                    </label>
                  </div>
                  <button onClick={createType} disabled={!newType.name || applying} className="w-full text-xs py-1.5 rounded bg-primary-500 text-white disabled:opacity-40">
                    {applying ? '创建中…' : '创建类型'}
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              {assistants.length === 0 && (
                <div className="text-center text-textMuted text-xs py-6">还没有群助手。在世界里创建群类型并绑定群后，助手会自动生成。</div>
              )}
              {assistants.map(a => (
                <div key={a.id} className="rounded-xl bg-elevated/50 border border-border p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-textPrimary">{a.name}</span>
                    <span className="text-[10px] text-textMuted">群#{a.group_id} · {typeName(a.group_type_slug)}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${a.configured ? 'bg-mint-500/15 text-mint-400' : 'bg-amber-500/15 text-amber-400'}`}>
                      {a.configured ? '已配置 API' : '未配置 API'}
                    </span>
                    <div className="flex-1" />
                    <button onClick={() => setApiInput({ agentId: a.id, key: '', base: '' })} className="text-[10px] px-2 py-1 rounded bg-primary-500/15 text-primary-400 hover:bg-primary-500/25">
                      <Key size={10} className="inline mr-0.5" /> 填 API
                    </button>
                    {a.has_global && (
                      <button onClick={() => applyGlobal(a.id)} className="text-[10px] px-2 py-1 rounded bg-elevated text-textSecondary hover:text-primary-400">
                        <Globe size={10} className="inline mr-0.5" /> 一键全局
                      </button>
                    )}
                    {a.configured && (
                      <button onClick={() => clearApi(a.id)} className="text-[10px] px-2 py-1 rounded bg-elevated text-textMuted hover:text-rose-400">清除</button>
                    )}
                  </div>
                  {apiInput?.agentId === a.id && (
                    <div className="flex items-center gap-1.5">
                      <input
                        value={apiInput.key}
                        onChange={e => setApiInput({ ...apiInput, key: e.target.value })}
                        type="password" placeholder="API Key（加密存储，世界只能调用不能查看）"
                        className="flex-1 bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary"
                      />
                      <input
                        value={apiInput.base}
                        onChange={e => setApiInput({ ...apiInput, base: e.target.value })}
                        placeholder="Base URL（可选）"
                        className="w-40 bg-elevated text-xs px-2 py-1.5 rounded border border-border text-textPrimary"
                      />
                      <button onClick={() => saveApi(a.id)} disabled={!apiInput.key || applying} className="text-[10px] px-2 py-1.5 rounded bg-primary-500 text-white disabled:opacity-40">
                        {applying ? '保存中…' : '保存'}
                      </button>
                    </div>
                  )}
                  {needApi(a) === false && <div className="text-[10px] text-textMuted">该类型助手无需 API（纯后端代码操控）</div>}
                </div>
              ))}
            </>
          )}
        </div>

        <div className="p-3 pt-0 shrink-0 flex items-center justify-between text-[10px] text-textMuted">
          <span>群助手归属群，不占个人额度；API 加密存储，世界打包不含 key</span>
          <button onClick={() => { load() }} className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-300">
            <RefreshCw size={10} /> 刷新
          </button>
        </div>
      </div>
    </div>
  )
}
