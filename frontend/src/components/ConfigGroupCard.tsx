import { useEffect, useState } from 'react'
import { Loader2, Check, X, RotateCcw, Settings2, Brain, Plug } from 'lucide-react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import { Button, Card, Select } from './ui'

/**
 * 通用配置组卡片（管理员图形化修改任意配置组）
 *
 * 从后端 schema（GET /admin/configs）自动渲染表单：
 * - 每个字段按 type 渲染控件（select/number/float/text/secret）
 * - label/hint 用 i18n key（后端下发 label_key/hint_key，前端 t() 翻译，三语友好）
 * - 保存 PUT /admin/configs/{group}（热更新，无需重启）
 * - 恢复 DELETE /admin/configs/{group}（回到环境变量配置）
 *
 * 特别支持：embedding 组的「测试连接」按钮（POST /admin/embedding-config/test）
 */
export default function ConfigGroupCard({ groupKey }: { groupKey: string }) {
  const t = useT()
  const [group, setGroup] = useState<any>(null)
  const [values, setValues] = useState<Record<string, any>>({})
  const [source, setSource] = useState<Record<string, string>>({})
  const [secretSet, setSecretSet] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [msg, setMsg] = useState('')
  const [msgOk, setMsgOk] = useState(false)
  // 测试连接结果：null=未测，'testing'=测试中，'ok'/'fail'=结果（文案纯文本，图标由前端渲染）
  const [testState, setTestState] = useState<null | 'testing' | 'ok' | 'fail'>(null)
  const [testMsg, setTestMsg] = useState('')

  // i18n 取文案：key 不存在时 fallback 回原值
  const tr = (key?: string, vars?: Record<string, string | number>) =>
    key ? t(`adminConfig:${key}`, vars) : ''

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
      setMsg(err?.detail || tr('saveFailed'))
      setMsgOk(false)
    }
    setSaving(false)
  }

  const handleReset = async () => {
    if (!confirm(tr('resetConfirm', { label: tr(group?.label_key) }))) return
    setSaving(true)
    try {
      await api.delete(`/admin/configs/${groupKey}`)
      await load()
      setMsg(tr('resetDone'))
      setMsgOk(true)
    } catch {
      setMsg(tr('resetFailed'))
      setMsgOk(false)
    }
    setSaving(false)
  }

  const handleTest = async () => {
    setTestState('testing')
    setTestMsg('')
    try {
      const res = await api.post<any>('/admin/embedding-config/test', {})
      setTestState('ok')
      setTestMsg(tr('testOk', { dim: res.dimension }))
    } catch (err: any) {
      setTestState('fail')
      setTestMsg(tr('testFail', { msg: err?.detail || 'error' }))
    }
  }

  if (!group) return null

  const Icon = groupKey === 'embedding' ? Brain : Settings2
  const isSecret = (key: string) => group.fields[key]?.type === 'secret'
  const secretPlaceholder = tr('secretPlaceholder')

  return (
    <Card
      title={tr(group.label_key)}
      icon={<Icon size={16} className="text-accent-400" />}
      hint={group.hint_key ? tr(group.hint_key) : undefined}
    >
      {/* 字段表单（按 schema 自动渲染） */}
      {Object.entries(group.fields as Record<string, any>).map(([key, field]) => (
        <div key={key}>
          <label className="block text-sm font-medium mb-1 text-textSecondary">
            {tr(field.label_key)}
            {isSecret(key) && (
              <span className="text-xs text-textMuted ml-1">
                {secretSet[key] ? tr('secretSet') : tr('secretNotSet')}
              </span>
            )}
            <span className="text-xs text-textMuted ml-2">
              {source[key] === 'db' ? tr('sourceDb') : tr('sourceEnv')}
            </span>
          </label>

          {field.type === 'select' ? (
            <Select
              value={values[key] ?? ''}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
              options={(field.options || []).map((opt: any) => ({
                value: opt.value,
                label: tr(opt.label_key),
              }))}
            />
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
              placeholder={isSecret(key) && secretSet[key] ? secretPlaceholder : ''}
              className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
            />
          )}

          {/* 说明文案（i18n：是什么 + 为什么改） */}
          {field.hint_key && <p className="text-xs text-textMuted mt-1">{tr(field.hint_key)}</p>}
        </div>
      ))}

      {msg && (
        <p className={`text-sm flex items-center gap-1.5 ${msgOk ? 'text-mint-400' : 'text-rose-400'}`}>
          {msgOk ? <Check size={14} /> : <X size={14} />}
          {msg}
        </p>
      )}
      {testState && (
        <p className={`text-sm flex items-center gap-1.5 ${testState === 'ok' ? 'text-mint-400' : testState === 'fail' ? 'text-rose-400' : 'text-textSecondary'}`}>
          {testState === 'ok' && <Check size={14} />}
          {testState === 'fail' && <X size={14} />}
          {testState === 'testing' && <Loader2 size={14} className="animate-spin" />}
          {testState === 'testing' ? tr('testing') : testMsg}
        </p>
      )}

      {/* 操作按钮（统一 Button 组件） */}
      <div className="flex items-center gap-2 pt-1">
        {groupKey === 'embedding' && (
          <Button variant="outline" onClick={handleTest} disabled={saving} icon={<Plug size={14} />}>
            {tr('test')}
          </Button>
        )}
        <Button
          variant="accent"
          onClick={handleSave}
          disabled={saving}
          loading={saving}
          className="flex-1"
        >
          {saved ? tr('saved') : tr('save')}
        </Button>
        <Button variant="outline" onClick={handleReset} disabled={saving} title={tr('reset')}>
          <RotateCcw size={16} />
        </Button>
      </div>
    </Card>
  )
}
