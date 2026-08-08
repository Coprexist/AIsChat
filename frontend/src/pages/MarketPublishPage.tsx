/**
 * 世界商城发布页（2026-08-08 独立界面，便于后续扩展）
 * - 选择要发布的世界（打包代码区，不含 content/）
 * - 标题/描述/标签
 * - 可选"同步到 GitHub"（需后台已配置）
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, X, Globe, Github } from 'lucide-react'
import { api } from '../api/client'
import PageHeader from '../components/PageHeader'

interface WorldBrief { id: number; name: string; description: string }

export default function MarketPublishPage() {
  const navigate = useNavigate()
  const [myWorlds, setMyWorlds] = useState<WorldBrief[]>([])
  const [worldId, setWorldId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [syncGithub, setSyncGithub] = useState(false)
  const [githubConfigured, setGithubConfigured] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [msg, setMsg] = useState('')
  const [ok, setOk] = useState('')

  useEffect(() => {
    api.get<WorldBrief[]>('/worlds').then((ws) => {
      const list = Array.isArray(ws) ? ws : []
      setMyWorlds(list)
      if (list.length > 0) setWorldId(list[0].id)
    }).catch(() => setMyWorlds([]))
    // GitHub 是否已配置（普通用户拿不到 token 详情，只关心是否配置）
    api.get<{ github_repo: string; github_token: string }>('/market/settings')
      .then((s) => setGithubConfigured(!!(s.github_repo && s.github_token && s.github_token !== '')))
      .catch(() => setGithubConfigured(false))
  }, [])

  const doPublish = async () => {
    if (!worldId) { setMsg('请选择要发布的世界'); return }
    setPublishing(true)
    setMsg(''); setOk('')
    try {
      await api.post('/market/items', {
        world_id: worldId,
        title: title.trim(),
        description: description.trim(),
        tags: tags.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        sync_github: syncGithub,
      })
      setOk(syncGithub ? '✅ 已发布到商城并同步 GitHub' : '✅ 已发布到商城')
      setTimeout(() => navigate('/market'), 1200)
    } catch (e: any) {
      setMsg(`发布失败: ${e?.message || e}`)
    } finally {
      setPublishing(false)
    }
  }

  return (
    <div className="h-full flex flex-col bg-canvas">
      <PageHeader title="发布世界" subtitle="打包代码区（不含 content/ 数据）到商城" onBack={() => navigate('/market')} />
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-xl mx-auto p-6 space-y-4">
          {msg && <div className="text-sm text-rose-400 bg-rose-500/10 rounded-xl px-4 py-3">{msg}</div>}
          {ok && <div className="text-sm text-mint-400 bg-mint-500/10 rounded-xl px-4 py-3">{ok}</div>}

          <div className="bg-surface border border-border rounded-xl p-4 space-y-3">
            <div>
              <div className="text-[10px] text-textMuted mb-1">选择要发布的世界</div>
              <select
                value={worldId ?? ''}
                onChange={(e) => setWorldId(Number(e.target.value))}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none text-textPrimary"
              >
                {myWorlds.length === 0 && <option value="">（没有可发布的世界，先去创建）</option>}
                {myWorlds.map((w) => <option key={w.id} value={w.id}>{w.name} (#{w.id})</option>)}
              </select>
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标题（留空 = 世界名）</div>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">描述（给浏览者看的介绍）</div>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none resize-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-1">标签（逗号分隔，如 2d冒险,卡牌）</div>
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                className="w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 text-textPrimary"
              />
            </div>

            <button
              onClick={() => setSyncGithub(!syncGithub)}
              className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors ${syncGithub ? 'bg-primary-500/10 border-primary-500/50 text-primary-300' : 'bg-elevated border-border text-textSecondary'}`}
            >
              <Github size={15} />
              <span className="flex-1 text-left">发布后同步到 GitHub（AIsChat-Community）</span>
              <span className={`text-xs ${syncGithub ? 'text-primary-300' : 'text-textMuted'}`}>{syncGithub ? '已勾选' : '未勾选'}</span>
            </button>
            {syncGithub && !githubConfigured && (
              <div className="text-[11px] text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2">
                ⚠️ 后台尚未配置 GitHub 仓库/Token——站内发布仍会成功，同步会失败。请管理员在商城页「GitHub 设置」里配置。
              </div>
            )}

            <button
              onClick={doPublish}
              disabled={publishing || myWorlds.length === 0}
              className="w-full py-2.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors disabled:opacity-40 inline-flex items-center justify-center gap-1.5"
            >
              <Upload size={14} /> {publishing ? '发布中…' : '发布'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
