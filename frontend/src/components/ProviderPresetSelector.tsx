import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import { Plus, Trash2, Check, Loader2, Settings, Server, Star, Globe } from 'lucide-react'

interface ModelOption { value: string; label: string }

interface Preset {
  key: string
  label: string
  base_url: string
  chat_model: string
  work_model: string
  embedding_model: string
  thinking_supported: boolean
  models: ModelOption[]
}

interface ProviderItem {
  name: string
  provider: string
  base_url: string
  chat_model: string
  work_model: string
  embedding_model: string
  model_options: ModelOption[]
  thinking_supported: boolean
  is_default: boolean
}

export default function ProviderPresetSelector() {
  const t = useT()
  const [presets, setPresets] = useState<Preset[]>([])
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // 展开的 provider 名称（编辑态）
  const [expanded, setExpanded] = useState<string | null>(null)
  // 编辑中的表单数据
  const [editName, setEditName] = useState('')
  const [editProvider, setEditProvider] = useState('')
  const [editBaseUrl, setEditBaseUrl] = useState('')
  const [editChat, setEditChat] = useState('')
  const [editWork, setEditWork] = useState('')
  const [editEmbed, setEditEmbed] = useState('')
  const [editThinking, setEditThinking] = useState(false)
  const [editModels, setEditModels] = useState('')
  const [editIsDefault, setEditIsDefault] = useState(false)
  const [editIndex, setEditIndex] = useState<number | null>(null)

  // 新增模式
  const [adding, setAdding] = useState(false)
  const [newPreset, setNewPreset] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.get<{ presets: Preset[]; providers: ProviderItem[] }>('/admin/provider-presets')
      setPresets(data.presets)
      setProviders(data.providers || [])
    } catch { /* */ }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const startEdit = (p: ProviderItem, idx: number) => {
    setExpanded(p.name)
    setEditName(p.name)
    setEditProvider(p.provider)
    setEditBaseUrl(p.base_url)
    setEditChat(p.chat_model)
    setEditWork(p.work_model)
    setEditEmbed(p.embedding_model)
    setEditThinking(p.thinking_supported)
    setEditModels(p.model_options?.length ? JSON.stringify(p.model_options, null, 2) : '')
    setEditIsDefault(p.is_default)
    setEditIndex(idx)
    setAdding(false)
    setNewPreset('')
    setSaved(false)
  }

  const startAdd = (presetKey: string) => {
    setAdding(true)
    setNewPreset(presetKey)
    setExpanded(null)
    setSaved(false)

    if (presetKey === 'manual') {
      setEditName('')
      setEditProvider('manual')
      setEditBaseUrl('')
      setEditChat('')
      setEditWork('')
      setEditEmbed('')
      setEditThinking(false)
      setEditModels('')
      setEditIsDefault(providers.length === 0)
      setEditIndex(null)
    } else {
      const p = presets.find(pr => pr.key === presetKey)
      if (p) {
        setEditName(p.key)
        setEditProvider(p.key)
        setEditBaseUrl(p.base_url)
        setEditChat(p.chat_model)
        setEditWork(p.work_model)
        setEditEmbed(p.embedding_model)
        setEditThinking(p.thinking_supported)
        setEditModels(JSON.stringify(p.models, null, 2))
        setEditIsDefault(providers.length === 0)
        setEditIndex(null)
      }
    }
  }

  const handleSave = async () => {
    if (!editName.trim()) return
    setSaving(true)
    setSaved(false)
    try {
      let modelOptions: ModelOption[] = []
      try { modelOptions = JSON.parse(editModels) } catch { /* */ }

      await api.put('/admin/provider-presets/save', {
        name: editName.trim(),
        provider: editProvider,
        base_url: editBaseUrl || undefined,
        chat_model: editChat || undefined,
        work_model: editWork || undefined,
        embedding_model: editEmbed || undefined,
        model_options: modelOptions.length > 0 ? modelOptions : undefined,
        thinking_supported: editThinking,
        is_default: editIsDefault,
        index: editIndex,
      })
      setSaved(true)
      await load()
      setAdding(false)
      setExpanded(null)
      setTimeout(() => setSaved(false), 3000)
    } catch { /* */ }
    setSaving(false)
  }

  const handleDelete = async (name: string) => {
    if (!confirm(t('admin.confirmDeleteProvider') || `确定删除供应商 "${name}"？`)) return
    try {
      await api.delete(`/admin/provider-presets/${encodeURIComponent(name)}`)
      await load()
      if (expanded === name) setExpanded(null)
    } catch { /* */ }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-textMuted" />
      </div>
    )
  }

  return (
    <section className="bg-surface border border-border rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
        <Server size={16} className="text-accent-400" />
        {t('admin.llmProvider') || 'LLM 厂商预设'}
      </h3>

      {/* 已配置的供应商列表 */}
      {providers.length > 0 && (
        <div className="space-y-2">
          {providers.map((p, idx) => {
            const isOpen = expanded === p.name
            return (
              <div key={p.name} className={`border rounded-lg p-3 ${p.is_default ? 'border-primary-500/40 bg-primary-500/5' : 'border-border bg-canvas'}`}>
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => isOpen ? setExpanded(null) : startEdit(p, idx)}
                    className="flex items-center gap-2 text-sm font-medium text-textPrimary hover:text-primary-500 transition-colors"
                  >
                    {p.is_default && <Star size={14} className="text-amber-400 fill-amber-400" />}
                    {p.name}
                    <span className="text-xs text-textMuted">({p.provider})</span>
                    {p.thinking_supported && (
                      <span className="text-primary-400 bg-primary-500/10 px-1.5 py-0.5 rounded-full text-xs">🧠</span>
                    )}
                  </button>
                  <div className="flex items-center gap-2">
                    {p.is_default && (
                      <span className="text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
                        {t('admin.defaultProvider') || '默认'}
                      </span>
                    )}
                    <button
                      onClick={() => handleDelete(p.name)}
                      className="p-1 text-textMuted hover:text-rose-400 transition-colors"
                      title={t('common.delete') || '删除'}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                {!isOpen && (
                  <div className="text-xs text-textMuted mt-1 ml-6">
                    <Globe size={10} className="inline mr-1" />
                    {p.base_url}
                  </div>
                )}

                {/* 编辑表单 */}
                {isOpen && (
                  <ProviderEditForm
                    editName={editName} setEditName={setEditName}
                    editBaseUrl={editBaseUrl} setEditBaseUrl={setEditBaseUrl}
                    editChat={editChat} setEditChat={setEditChat}
                    editWork={editWork} setEditWork={setEditWork}
                    editEmbed={editEmbed} setEditEmbed={setEditEmbed}
                    editThinking={editThinking} setEditThinking={setEditThinking}
                    editModels={editModels} setEditModels={setEditModels}
                    editIsDefault={editIsDefault} setEditIsDefault={setEditIsDefault}
                    saving={saving} saved={saved}
                    onSave={handleSave}
                    t={t}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {providers.length === 0 && (
        <div className="text-xs text-textMuted py-4 text-center">{t('admin.noProvidersYet') || '尚未配置任何 API 供应商'}</div>
      )}

      {/* 添加新供应商 */}
      {adding ? (
        <div className="border border-primary-500/40 rounded-lg p-4 bg-primary-500/5 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-textPrimary">
              {t('admin.addProvider') || '添加供应商'}
            </h4>
            <button
              onClick={() => setAdding(false)}
              className="text-xs text-textMuted hover:text-textPrimary"
            >
              {t('common.cancel') || '取消'}
            </button>
          </div>

          {/* 预设选择 */}
          <div className="flex flex-wrap gap-2">
            {presets.map(p => (
              <button
                key={p.key}
                disabled={newPreset === p.key}
                onClick={() => startAdd(p.key)}
                className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors border ${
                  newPreset === p.key
                    ? 'bg-primary-500/15 border-primary-500/40 text-primary-500'
                    : 'bg-canvas border-border text-textSecondary hover:text-textPrimary hover:border-primary-500/30'
                }`}
              >
                {p.label}
              </button>
            ))}
            <button
              disabled={newPreset === 'manual'}
              onClick={() => startAdd('manual')}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors border ${
                newPreset === 'manual'
                  ? 'bg-amber-500/15 border-amber-500/40 text-amber-500'
                  : 'bg-canvas border-border text-textMuted hover:text-textSecondary'
              }`}
            >
              <Settings size={12} className="inline mr-1" />
              {t('admin.manualConfig') || '手动配置'}
            </button>
          </div>

          {newPreset && (
            <ProviderEditForm
              editName={editName} setEditName={setEditName}
              editBaseUrl={editBaseUrl} setEditBaseUrl={setEditBaseUrl}
              editChat={editChat} setEditChat={setEditChat}
              editWork={editWork} setEditWork={setEditWork}
              editEmbed={editEmbed} setEditEmbed={setEditEmbed}
              editThinking={editThinking} setEditThinking={setEditThinking}
              editModels={editModels} setEditModels={setEditModels}
              editIsDefault={editIsDefault} setEditIsDefault={setEditIsDefault}
              saving={saving} saved={saved}
              onSave={handleSave}
              t={t}
              isNew
            />
          )}
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-dashed border-border text-textMuted hover:text-primary-500 hover:border-primary-500/40 transition-colors"
        >
          <Plus size={14} />
          {t('admin.addProvider') || '添加供应商'}
        </button>
      )}
    </section>
  )
}

/** 供应商编辑表单（复用） */
function ProviderEditForm({
  editName, setEditName,
  editBaseUrl, setEditBaseUrl,
  editChat, setEditChat,
  editWork, setEditWork,
  editEmbed, setEditEmbed,
  editThinking, setEditThinking,
  editModels, setEditModels,
  editIsDefault, setEditIsDefault,
  saving, saved, onSave, t, isNew,
}: {
  editName: string; setEditName: (v: string) => void
  editBaseUrl: string; setEditBaseUrl: (v: string) => void
  editChat: string; setEditChat: (v: string) => void
  editWork: string; setEditWork: (v: string) => void
  editEmbed: string; setEditEmbed: (v: string) => void
  editThinking: boolean; setEditThinking: (v: boolean) => void
  editModels: string; setEditModels: (v: string) => void
  editIsDefault: boolean; setEditIsDefault: (v: boolean) => void
  saving: boolean; saved: boolean; onSave: () => void
  t: (key: string) => string
  isNew?: boolean
}) {
  return (
    <div className="space-y-3 mt-3">
      {isNew && (
        <div>
          <label className="block text-xs text-textSecondary mb-1">{t('admin.providerName') || '供应商名称'}</label>
          <input
            type="text" value={editName}
            onChange={e => setEditName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/60"
            placeholder="deepseek-主号"
          />
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-textSecondary mb-1">API Base URL</label>
          <input
            type="text" value={editBaseUrl}
            onChange={e => setEditBaseUrl(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/60"
          />
        </div>
        <div>
          <label className="block text-xs text-textSecondary mb-1">{t('admin.defaultChatModel') || '默认聊天模型'}</label>
          <input
            type="text" value={editChat}
            onChange={e => setEditChat(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/60"
          />
        </div>
        <div>
          <label className="block text-xs text-textSecondary mb-1">{t('admin.defaultWorkModel') || '默认工作模型'}</label>
          <input
            type="text" value={editWork}
            onChange={e => setEditWork(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/60"
          />
        </div>
        <div>
          <label className="block text-xs text-textSecondary mb-1">Embedding 模型</label>
          <input
            type="text" value={editEmbed}
            onChange={e => setEditEmbed(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs focus:outline-none focus:ring-2 focus:ring-primary-500/60"
          />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-xs text-textSecondary cursor-pointer">
          <input
            type="checkbox" checked={editThinking}
            onChange={e => setEditThinking(e.target.checked)}
            className="rounded"
          />
          🧠 {t('admin.thinkingSupported') || '支持深度推理'}
        </label>
        <label className="flex items-center gap-2 text-xs text-textSecondary cursor-pointer">
          <input
            type="checkbox" checked={editIsDefault}
            onChange={e => setEditIsDefault(e.target.checked)}
            className="rounded"
          />
          ⭐ {t('admin.setAsDefault') || '设为默认'}
        </label>
      </div>
      <div>
        <label className="block text-xs text-textSecondary mb-1">{t('admin.modelOptionsJson') || '模型选项列表 (JSON)'}</label>
        <textarea
          rows={3}
          value={editModels}
          onChange={e => setEditModels(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-textPrimary text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/60 resize-y"
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={onSave}
          disabled={saving || !editName.trim()}
          className="px-4 py-2 text-sm rounded-lg bg-primary-500 hover:bg-primary-400 disabled:opacity-30 text-white font-medium transition-colors flex items-center gap-1.5"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          {saving ? t('common.saving') : t('common.save')}
        </button>
        {saved && (
          <span className="text-xs text-mint-400 animate-pulse">{t('common.saved') || '已保存'}</span>
        )}
      </div>
    </div>
  )
}
