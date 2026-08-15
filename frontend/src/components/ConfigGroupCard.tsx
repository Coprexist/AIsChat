import { useEffect, useState } from 'react'
import { Loader2, Check, RotateCcw, Settings2, Brain, Plug } from 'lucide-react'
import { api } from '../api/client'

/**
 * 通用配置组卡片（管理员图形化修改任意配置组）
 *
 * 从后端 schema（GET /admin/configs）自动渲染表单：
 * - 每个字段按 type 渲染控件（select/number/float/text/secret）
 * - 每个字段带 hint 说明（小白也能看懂"是什么 + 为什么改"）
 * - 保存 PUT /admin/configs/{group}（热更新，无需重启）
 * - 恢复 DELETE /admin/configs/{group}（回到环境变量配置）
 *
 * 特别支持：embedding 组的「测试连接」按钮（POST /admin/embedding-config/test）
 */
export default function ConfigGroupCard({ groupKey }: { groupKey: string }) {
  const [group, setGroup] = useState<any>(null)
  const [values, setValues] = useState<Record<string, any>>({})
  const [source, setSource] = useState<Record<string, string>>({})
  const [secretSet, setSecretSet] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [msg, setMsg] = useState('')
  const [testResult, setTestResult] = useState('')

  const load = async () => {
    try {
      // schema + 当前生效值
      const [schemaRes, cfg] = await Promise.all([
        api.get<any>('/admin/configs'),
        api.get<any>(`/admin/configs/${groupKey}`),
      ])
      const g = (schemaRes.groups || []).find((x: any) => x.key === groupKey)
      if (!g) return
      setGroup(g)

      const v: Record<string, any> = {}
      const s: Record<string, string> = {}
      const ss: Record<string, boolean> = {}
      for (const [key, field] of Object.entries(g.fields as Record<string, any>)) {
        if (field.type === 'secret') {
          ss[key] = !!cfg[`${key}_set`]
          v[key] = ''
        } else {
          v[key] = cfg[key] ?? ''
        }
        s[key] = cfg.source?.[key] || 'env'
      }
      setValues(v)
      setSource(s)
      setSecretSet(ss)
    } catch { /* */ }
  }

  useEffect(() => { load() }, [groupKey])

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      const payload: Record<string, any> = {}
      for (const key of Object.keys(group.fields)) {
        const field = group.fields[key]
        if (field.type === 'secret') {
          if (values[key]?.trim()) payload[key] = values[key].trim()  // 留空 = 不改
        } else if (field.type === 'number') {
          const n = Number(values[key])
          if (values[key] !== '' && !isNaN(n)) payload[key] = n
        } else if (field.type === 'float') {
          const n = Number(values[key])
          if (values[key] !== '' && !isNaN(n)) payload[key] = n
        } else {
          if (values[key] !== '') payload[key] = values[key]
        }
      }
      await api.put(`/admin/configs/${groupKey}`, payload)
      setSaved(true)
      await load()
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setMsg(err?.detail || '保存失败')
    }
    setSaving(false)
  }

  const handleReset = async () => {
    if (!confirm(`确定恢复「${group?.label}」的默认值？将清除界面修改，回到环境变量配置。`)) return
    setSaving(true)
    try {
      await api.delete(`/admin/configs/${groupKey}`)
      await load()
      setMsg('已恢复默认（回到环境变量配置）')
    } catch { setMsg('恢复失败') }
    setSaving(false)
  }

  const handleTest = async () => {
    setTestResult('测试中...')
    try {
      const res = await api.post<any>('/admin/embedding-config/test', {})
      setTestResult(`✅ 连接成功（维度 ${res.dimension}）`)
    } catch (err: any) {
      setTestResult(`❌ ${err?.detail || '连接失败'}`)
    }
  }

  if (!group) return null

  const Icon = groupKey === 'embedding' ? Brain : Settings2
  const isSecret = (key: string) => group.fields[key]?.type === 'secret'

  return (
    <section className="bg-surface border border-border rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
        <Icon size={16} className="text-accent-400" />
        {group.label}
      </h3>
      {group.hint && <p className="text-xs text-textMuted">{group.hint}</p>}

      {/* 字段表单（按 schema 自动渲染） */}
      {Object.entries(group.fields as Record<string, any>).map(([key, field]) => (
        <div key={key}>
          <label className="block text-sm font-medium mb-1 text-textSecondary">
            {field.label}
            {isSecret(key) && (secretSet[key] ? '（已设置，留空不修改）' : '（未设置）')}
            <span className="text-xs text-textMuted ml-2">
              来源：{source[key] === 'db' ? '界面已修改' : '环境变量'}
            </span>
          </label>

          {field.type === 'select' ? (
            <select
              value={values[key] ?? ''}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
              className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
            >
              {(field.options || []).map((opt: any) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          ) : field.type === 'number' || field.type === 'float' ? (
            <input
              type="number"
              step={field.step}
              min={field.min}
              max={field.max}
              value={values[key] ?? ''}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
              className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
            />
          ) : (
            <input
              type={isSecret(key) ? 'password' : 'text'}
              value={values[key] ?? ''}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
              placeholder={isSecret(key) && secretSet[key] ? '••••••••（已加密存储）' : field.placeholder || ''}
              className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
            />
          )}

          {/* 说明文案（小白友好：是什么 + 为什么） */}
          {field.hint && <p className="text-xs text-textMuted mt-1">{field.hint}</p>}
        </div>
      ))}

      {msg && <p className="text-sm text-textSecondary">{msg}</p>}
      {testResult && <p className={`text-sm ${testResult.startsWith('✅') ? 'text-mint-400' : 'text-rose-400'}`}>{testResult}</p>}

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pt-1">
        {groupKey === 'embedding' && (
          <button
            onClick={handleTest}
            disabled={saving}
            className="px-4 py-2.5 rounded-xl border border-border text-sm text-textSecondary hover:bg-canvas disabled:opacity-50"
          >
            <Plug size={14} className="inline mr-1" />
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
