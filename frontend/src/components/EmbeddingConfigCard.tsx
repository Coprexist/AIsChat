import { useEffect, useState } from 'react'
import { Brain, Loader2, Check, RotateCcw } from 'lucide-react'
import { api } from '../api/client'

/**
 * Embedding 提供方配置卡片（管理员图形化修改）
 * 读取：GET /admin/embedding-config（DB 覆盖 + env 兜底）
 * 保存：PUT /admin/embedding-config（DB 持久化 + 热更新，api_key 加密）
 * 恢复：DELETE /admin/embedding-config（回到环境变量配置）
 */
export default function EmbeddingConfigCard() {
  const [backend, setBackend] = useState('disabled')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [dimension, setDimension] = useState('1536')
  const [apiKeySet, setApiKeySet] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [source, setSource] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [msg, setMsg] = useState('')
  const [testResult, setTestResult] = useState('')

  const load = async () => {
    try {
      const cfg = await api.get<any>('/admin/embedding-config')
      setBackend(cfg.embedding_backend || 'disabled')
      setBaseUrl(cfg.embedding_base_url || '')
      setModel(cfg.embedding_model || '')
      setDimension(String(cfg.embedding_dimension ?? 1536))
      setApiKeySet(!!cfg.embedding_api_key_set)
      setSource(cfg.source || {})
    } catch { /* */ }
  }

  useEffect(() => { load() }, [])

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      const payload: Record<string, any> = {
        embedding_backend: backend,
        embedding_base_url: baseUrl.trim() || undefined,
        embedding_model: model.trim() || undefined,
        embedding_dimension: parseInt(dimension, 10) || undefined,
      }
      if (apiKeyInput.trim()) payload.embedding_api_key = apiKeyInput.trim()
      await api.put('/admin/embedding-config', payload)
      setSaved(true)
      setApiKeySet(!!apiKeyInput.trim())
      setApiKeyInput('')
      await load()
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setMsg(err?.detail || '保存失败')
    }
    setSaving(false)
  }

  const handleReset = async () => {
    if (!confirm('确定恢复默认？将清除 DB 覆盖，回到环境变量配置。')) return
    setSaving(true)
    try {
      await api.delete('/admin/embedding-config')
      await load()
      setMsg('已恢复默认（回到环境变量配置）')
    } catch { setMsg('恢复失败') }
    setSaving(false)
  }

  const handleTest = async () => {
    setTestResult('测试中...')
    try {
      const vec = await api.post<any>('/admin/embedding-config/test', {})
      setTestResult(`✅ 连接成功（维度 ${vec.dimension}）`)
    } catch (err: any) {
      setTestResult(`❌ ${err?.detail || '连接失败'}`)
    }
  }

  const BACKENDS: Record<string, { label: string; hint: string; modelDefault: string }> = {
    disabled: { label: '不启用（纯文本检索）', hint: '默认。不生成向量，记忆使用文本关键词检索。', modelDefault: '' },
    ollama: { label: 'Ollama（本地）', hint: '复用本机/局域网 Ollama 实例，无需额外部署。', modelDefault: 'nomic-embed-text' },
    api: { label: 'OpenAI 兼容 API', hint: '任意 /v1/embeddings 端点：OpenAI、硅基流动、智谱、阿里云等。', modelDefault: 'text-embedding-3-small' },
    local: { label: '本地模型（fastembed）', hint: '离线运行，首次自动下载模型，不依赖外部服务。', modelDefault: 'BAAI/bge-small-zh-v1.5' },
  }

  return (
    <section className="bg-surface border border-border rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
        <Brain size={16} className="text-accent-400" />
        Embedding 向量配置
      </h3>
      <p className="text-xs text-textMuted">
        部署后可在此图形化修改向量配置，保存即时生效（无需重启）。未在界面修改的项自动使用环境变量。
      </p>

      {/* 后端选择 */}
      <div>
        <label className="block text-sm font-medium mb-1 text-textSecondary">后端类型</label>
        <select
          value={backend}
          onChange={(e) => {
            setBackend(e.target.value)
            const b = BACKENDS[e.target.value]
            if (b && b.modelDefault && !model) setModel(b.modelDefault)
          }}
          className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
        >
          {Object.entries(BACKENDS).map(([key, v]) => (
            <option key={key} value={key}>{v.label}</option>
          ))}
        </select>
        <p className="text-xs text-textMuted mt-1">{BACKENDS[backend]?.hint}</p>
      </div>

      {/* 端点（ollama/api 用） */}
      {backend !== 'disabled' && backend !== 'local' && (
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">API 地址 (Base URL)</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={backend === 'ollama' ? 'http://127.0.0.1:11434' : 'https://host/v1'}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
          />
          <p className="text-xs text-textMuted mt-1">
            来源：{source.embedding_base_url === 'db' ? '界面已修改（DB）' : '环境变量'}
          </p>
        </div>
      )}

      {/* 模型 */}
      {backend !== 'disabled' && (
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">模型</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={BACKENDS[backend]?.modelDefault}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
          />
          <p className="text-xs text-textMuted mt-1">
            ollama: nomic-embed-text / api: text-embedding-3-small 或 bge-large-zh-v1.5 / local: BAAI/bge-small-zh-v1.5
          </p>
        </div>
      )}

      {/* 维度 */}
      {backend !== 'disabled' && (
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">
            向量维度（速度 vs 质量取舍）
          </label>
          <input
            type="number"
            value={dimension}
            onChange={(e) => setDimension(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
          />
          <p className="text-xs text-textMuted mt-1">
            需与模型匹配：nomic-embed-text=768 / text-embedding-3-small=1536 / bge-large-zh-v1.5=1024。无向量数据时启动自动对齐，有数据时需迁移。
          </p>
        </div>
      )}

      {/* API Key（仅 api 后端） */}
      {backend === 'api' && (
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">
            API Key {apiKeySet ? '（已设置，留空不修改）' : '（未设置）'}
          </label>
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={apiKeySet ? '••••••••（已加密存储）' : '输入 API Key'}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
          />
          <p className="text-xs text-textMuted mt-1">密钥加密存储于数据库，不会明文回显。</p>
        </div>
      )}

      {msg && <p className="text-sm text-textSecondary">{msg}</p>}
      {testResult && <p className={`text-sm ${testResult.startsWith('✅') ? 'text-mint-400' : 'text-rose-400'}`}>{testResult}</p>}

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pt-1">
        {backend !== 'disabled' && (
          <button
            onClick={handleTest}
            disabled={saving}
            className="px-4 py-2.5 rounded-xl border border-border text-sm text-textSecondary hover:bg-canvas disabled:opacity-50"
          >
            测试连接
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent-500 hover:bg-accent-600 text-white text-sm font-medium disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : saved ? <Check size={16} /> : null}
          {saved ? '已保存' : '保存并生效'}
        </button>
        <button
          onClick={handleReset}
          disabled={saving}
          className="px-4 py-2.5 rounded-xl border border-border text-sm text-textSecondary hover:bg-canvas disabled:opacity-50"
          title="恢复默认（回到环境变量）"
        >
          <RotateCcw size={16} />
        </button>
      </div>
    </section>
  )
}
