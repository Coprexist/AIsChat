/**
 * 群视界机器人（世界 AI）配置弹窗 — 单独表单，不属于 agent
 * （从 WorldDesignPage 拆分；世界 AI 是世界的配置：让它改界面、加功能）
 * 2026-08-10：改为 Modal 弹窗（原内联展开），对齐 GroupManagerModal 风格
 */
import { useEffect, useState } from 'react'
import { Save, X, Settings, Brain, SlidersHorizontal } from 'lucide-react'
import { api } from '../../api/client'

export interface WorldCreator {
  id: string
  name: string
  system_prompt: string
  model: string | null
  temperature: number
  top_p: number
  thinking: boolean
  max_tool_rounds: number
  tools: string[]
}

export interface WorldUsageStats {
  total_calls: number
  prompt_tokens: number
  completion_tokens: number
  cached_tokens: number
  cache_hit_rate_pct: number
}

interface WorldCreatorConfigProps {
  wid: number
  creator: WorldCreator
  usageStats: WorldUsageStats | null
  onSaved: (updated: WorldCreator) => void
  onClose: () => void
  onMsg: (msg: string) => void
}

export default function WorldCreatorConfig({ wid, creator, usageStats, onSaved, onClose, onMsg }: WorldCreatorConfigProps) {
  const [form, setForm] = useState({
    name: creator.name ?? '',
    system_prompt: creator.system_prompt ?? '',
    model: creator.model ?? '',
    temperature: creator.temperature ?? 0.8,
    thinking: creator.thinking ?? false,
    max_tool_rounds: creator.max_tool_rounds ?? 50,
  })
  const [saving, setSaving] = useState(false)

  // creator 外部更新（load 重拉）后同步表单
  useEffect(() => {
    setForm({
      name: creator.name ?? '',
      system_prompt: creator.system_prompt ?? '',
      model: creator.model ?? '',
      temperature: creator.temperature ?? 0.8,
      thinking: creator.thinking ?? false,
      max_tool_rounds: creator.max_tool_rounds ?? 50,
    })
  }, [creator])

  const save = async () => {
    setSaving(true)
    try {
      const patch: Record<string, unknown> = {
        name: form.name,
        system_prompt: form.system_prompt,
        temperature: form.temperature,
        thinking: form.thinking,
        max_tool_rounds: form.max_tool_rounds,
      }
      if (form.model.trim()) patch.model = form.model.trim()
      const updated = await api.put<WorldCreator>(`/worlds/${wid}/creator`, patch)
      onSaved(updated)
      onClose()
      onMsg('✅ 世界 AI 配置已保存')
    } catch (e: any) {
      onMsg(`保存失败: ${e?.message || e}`)
    } finally {
      setSaving(false)
    }
  }

  const fieldLabel = 'text-[10px] text-textMuted mb-1'
  const fieldInput = 'w-full bg-elevated text-sm p-2 rounded-lg border border-border outline-none focus:border-primary-500/50 transition-colors'

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface border border-border rounded-2xl max-h-[85vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()}>
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 pb-2 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Settings size={16} className="text-primary-400 shrink-0" />
            <span className="text-sm font-semibold text-textPrimary truncate">群视界机器人配置</span>
            <span className="text-[10px] text-textMuted shrink-0">世界的 AI：让它改界面、加功能</span>
          </div>
          <button onClick={onClose} className="p-1 text-textMuted hover:text-textPrimary transition-colors shrink-0" title="关闭">
            <X size={16} />
          </button>
        </div>

        {/* 表单体 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {/* 用量（置顶：一眼看到成本/缓存） */}
          {usageStats && (
            <div className="bg-elevated/40 rounded-xl p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-textSecondary uppercase tracking-wide font-medium">LLM 缓存命中率</div>
                  <div className="text-[10px] text-textMuted mt-0.5">{usageStats.total_calls} 次调用 · prompt {usageStats.prompt_tokens} / 缓存 {usageStats.cached_tokens} tok</div>
                </div>
                <div className="text-lg font-bold text-mint-400">{usageStats.cache_hit_rate_pct}%</div>
              </div>
            </div>
          )}

          {/* 身份 */}
          <div className="bg-elevated/40 rounded-xl p-3 space-y-2.5">
            <div className="flex items-center gap-1.5 text-[10px] font-medium text-textSecondary uppercase tracking-wide">
              <Settings size={11} className="text-primary-400" /> 身份
            </div>
            <div>
              <div className={fieldLabel}>名字</div>
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                className={fieldInput}
                placeholder="如：星野镇的镇守者"
              />
            </div>
          </div>

          {/* 人设 */}
          <div className="bg-elevated/40 rounded-xl p-3 space-y-2.5">
            <div className="flex items-center gap-1.5 text-[10px] font-medium text-textSecondary uppercase tracking-wide">
              <Brain size={11} className="text-primary-400" /> 人设与行为
            </div>
            <div>
              <div className={fieldLabel}>系统提示词（世界观、性格、能力边界）</div>
              <textarea
                value={form.system_prompt}
                onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
                rows={7}
                className={`${fieldInput} resize-none font-mono text-xs leading-relaxed`}
                placeholder="定义这个世界 AI 的身份、目标和行为准则…"
              />
            </div>
          </div>

          {/* 模型 */}
          <div className="bg-elevated/40 rounded-xl p-3 space-y-2.5">
            <div className="flex items-center gap-1.5 text-[10px] font-medium text-textSecondary uppercase tracking-wide">
              <SlidersHorizontal size={11} className="text-primary-400" /> 模型与参数
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className={fieldLabel}>模型（留空 = 全局默认）</div>
                <input
                  value={form.model}
                  onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
                  placeholder="如 deepseek-v4-flash"
                  className={fieldInput}
                />
              </div>
              <div className="w-24">
                <div className={fieldLabel}>温度</div>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={form.temperature}
                  onChange={(e) => setForm((f) => ({ ...f, temperature: Number(e.target.value) }))}
                  className={`${fieldInput} text-right`}
                />
              </div>
            </div>
            <div className="flex items-center justify-between bg-elevated/60 rounded-lg p-2.5">
              <div>
                <div className="text-xs text-textSecondary">深度思考（推理模式）</div>
                <div className="text-[10px] text-amber-400/90 mt-0.5">⚠️ 推理 token 单独计费，费用显著增加</div>
              </div>
              <input
                type="checkbox"
                checked={form.thinking}
                onChange={(e) => setForm((f) => ({ ...f, thinking: e.target.checked }))}
                className="w-4 h-4 accent-primary-500"
              />
            </div>
            <div className="flex items-center justify-between bg-elevated/60 rounded-lg p-2.5">
              <div>
                <div className="text-xs text-textSecondary">工具循环上限</div>
                <div className="text-[10px] text-textMuted mt-0.5">单次对话最多连续调几轮工具（1-200，默认 50）</div>
              </div>
              <input
                type="number"
                min={1}
                max={200}
                value={form.max_tool_rounds}
                onChange={(e) => setForm((f) => ({ ...f, max_tool_rounds: Number(e.target.value) || 50 }))}
                className="w-20 bg-elevated text-sm p-1.5 rounded-lg border border-border outline-none text-right focus:border-primary-500/50"
              />
            </div>
          </div>

          {/* 用量 */}
          {usageStats && (
            <div className="bg-elevated/40 rounded-xl p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-textSecondary uppercase tracking-wide font-medium">LLM 缓存命中率</div>
                  <div className="text-[10px] text-textMuted mt-0.5">{usageStats.total_calls} 次调用 · prompt {usageStats.prompt_tokens} / 缓存 {usageStats.cached_tokens} tok</div>
                </div>
                <div className="text-lg font-bold text-mint-400">{usageStats.cache_hit_rate_pct}%</div>
              </div>
            </div>
          )}
        </div>

        {/* 底部操作 */}
        <div className="p-4 pt-3 shrink-0 border-t border-border">
          <button
            onClick={save}
            disabled={saving}
            className="w-full py-2 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors disabled:opacity-40"
          >
            {saving ? '保存中...' : (<span className="inline-flex items-center justify-center gap-1.5"><Save size={14} /> 保存配置</span>)}
          </button>
        </div>
      </div>
    </div>
  )
}
