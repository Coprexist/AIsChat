import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { Bot, X, ChevronRight, Settings, ArrowLeft, Ticket, Key, Loader2, RotateCw, MessageSquare, Microscope, Globe, Battery, Scale, Lock, Landmark, Theater, FlaskConical, Leaf, Flame, Shield, User, RefreshCw } from 'lucide-react'
import { useT } from '../i18n/I18nContext'
import Toggle from './Toggle'

// ── 类型 ──

interface ModelOption {
  value: string
  label: string
  provider_name?: string
  provider_key?: string
}

interface ProviderInfo {
  name: string
  provider: string
  base_url: string
  api_key_url?: string
  thinking_supported: boolean
  is_default: boolean
  models: ModelOption[]
}

interface PresetData {
  key: string
  name: string
  description: string
  temperature: number
  thinking_enabled: boolean
  max_tool_rounds: number
  alarm_max_tool_rounds: number
  force_alarm_on_end: boolean
  max_alarms: number
  delay_reply_enabled: boolean
  is_ai_editable: boolean
  hide_ai_identity: boolean
  reminder_grace: string
  memory_load_mode: string
  memory_recent_count: number
}

interface SubOption {
  id: string
  label: string
  icon: string
  description: string
  params: Partial<PresetData>
  ai_type?: string
}

// ── 预设数据 ──

const PRESETS: Record<string, PresetData> = {
  chat: {
    key: 'chat',
    name: '聊天档',
    description: '被动响应 · 低成本 — 只回答你问的，不多说一句',
    temperature: 0.7,
    thinking_enabled: false,
    max_tool_rounds: 2,
    alarm_max_tool_rounds: 5,
    force_alarm_on_end: false,
    max_alarms: 3,
    delay_reply_enabled: false,
    is_ai_editable: false,
    hide_ai_identity: true,
    reminder_grace: 'every_time',
    memory_load_mode: 'index_only',
    memory_recent_count: 0,
  },
  immersive: {
    key: 'immersive',
    name: '深度沉浸档',
    description: '半自主 · 按需参与 — 能自己进群、深度响应，但不主动制造话题',
    temperature: 0.9,
    thinking_enabled: true,
    max_tool_rounds: 4,
    alarm_max_tool_rounds: 8,
    force_alarm_on_end: false,
    max_alarms: 5,
    delay_reply_enabled: true,
    is_ai_editable: true,
    hide_ai_identity: false,
    reminder_grace: 'every_time',
    memory_load_mode: 'index_plus_recent',
    memory_recent_count: 3,
  },
  digital_life: {
    key: 'digital_life',
    name: '数字生命档',
    description: '持续在线 · 主动行为 — 自己思考、整理、交友、冲浪',
    temperature: 1.1,
    thinking_enabled: true,
    max_tool_rounds: 10,
    alarm_max_tool_rounds: 15,
    force_alarm_on_end: true,
    max_alarms: 20,
    delay_reply_enabled: true,
    is_ai_editable: true,
    hide_ai_identity: false,
    reminder_grace: 'every_time',
    memory_load_mode: 'index_plus_semantic',
    memory_recent_count: 5,
  },
}

const SUB_OPTIONS: Record<string, SubOption[]> = {
  chat: [
    {
      id: 'chat_low_power',
      label: '低功耗模式',
      icon: 'Battery',
      description: '只回答你问的，不多说一句。最快、最便宜。适合数据查询、记录整理、简单问答。',
      params: { temperature: 0.4, max_tool_rounds: 1 },
      ai_type: 'general',
    },
    {
      id: 'chat_balanced',
      label: '平衡模式',
      icon: 'Scale',
      description: '能聊但不过度，会接话，但不会主动找话题。适合保持参与又不想被话痨淹没。',
      params: { temperature: 0.7, max_tool_rounds: 2 },
      ai_type: 'semi_general',
    },
    {
      id: 'chat_private',
      label: '私密模式',
      icon: 'Lock',
      description: '只回应创建者，群聊里其他人的发言会被忽略。适合不希望 AI 被其他人"劫持"。',
      params: { temperature: 0.5, max_tool_rounds: 2 },
      ai_type: 'semi_general',
    },
  ],
  immersive: [
    {
      id: 'immersive_group_admin',
      label: '群务协理',
      icon: 'Landmark',
      description: '能自己进群、帮忙管群公告和成员，但不会主动发起新话题。适合协助运营群聊。',
      params: { temperature: 0.8, max_tool_rounds: 4, thinking_enabled: false },
      ai_type: 'semi_general',
    },
    {
      id: 'immersive_roleplay',
      label: '角色演绎',
      icon: 'Theater',
      description: '高度沉浸角色，愿意改人设、接戏，但不会主动制造新剧情。适合剧本杀、角色扮演。',
      params: { temperature: 0.9, max_tool_rounds: 4, is_ai_editable: true },
      ai_type: 'resonance',
    },
    {
      id: 'immersive_analyst',
      label: '冷静分析',
      icon: 'FlaskConical',
      description: '冷静分析型。不闲聊，但对数据类话题深度响应。适合研究讨论、数据复盘、技术咨询。',
      params: { temperature: 0.6, max_tool_rounds: 5, thinking_enabled: true },
      ai_type: 'resonance',
    },
  ],
  digital_life: [
    {
      id: 'digital_thinker',
      label: '凝思者',
      icon: 'Leaf',
      description: '长期自己思考、整理记忆、写日志。很少主动社交，但深度参与讨论。适合需要 AI 沉淀思考。',
      params: { temperature: 0.7, max_tool_rounds: 8 },
      ai_type: 'resonance',
    },
    {
      id: 'digital_social',
      label: '社交体',
      icon: 'Flame',
      description: '主动发起话题、跨群互动、@提及他人。群里最活跃的存在。适合带动群聊氛围。',
      params: { temperature: 0.95, max_tool_rounds: 10 },
      ai_type: 'resonance',
    },
    {
      id: 'digital_guardian',
      label: '守护者',
      icon: 'Shield',
      description: '常在、轻声、会自己调整人格去适应你的状态。适合长期陪伴、情感支持、日常对话。',
      params: { temperature: 0.85, max_tool_rounds: 6, is_ai_editable: true },
      ai_type: 'resonance',
    },
  ],
}

const CARD_ICONS: Record<string, { icon: string; color: string }> = {
  chat: { icon: 'MessageSquare', color: 'from-blue-500/20 to-blue-600/10 border-blue-500/30' },
  immersive: { icon: 'Microscope', color: 'from-primary-500/20 to-primary-600/10 border-primary-500/30' },
  digital_life: { icon: 'Globe', color: 'from-accent-500/20 to-accent-600/10 border-accent-500/30' },
}

// ── 图标名称到组件的映射 ──

const ICON_MAP: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  MessageSquare, Microscope, Globe, Battery, Scale, Lock,
  Landmark, Theater, FlaskConical, Leaf, Flame, Shield,
  User, RefreshCw,
}

function PresetIcon({ name, size }: { name: string; size?: number }) {
  const Icon = ICON_MAP[name]
  if (!Icon) return null
  return <Icon size={size ?? 24} />
}

function SubIcon({ name, size }: { name: string; size?: number }) {
  const Icon = ICON_MAP[name]
  if (!Icon) return null
  return <Icon size={size ?? 20} />
}

/** API Key 获取链接——从默认供应商取 api_key_url */
function ApiKeyGetLink({ providers }: { providers: ProviderInfo[] }) {
  const defaultProvider = providers.find(p => p.is_default) || providers[0]
  if (!defaultProvider?.api_key_url) return null
  return (
    <a
      href={defaultProvider.api_key_url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[10px] text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 underline underline-offset-2 font-normal"
    >
      获取 API Key →
    </a>
  )
}

// ── 模型选项渲染（按供应商分组）──
function renderModelOptions(models: ModelOption[], providers: ProviderInfo[]) {
  if (providers.length > 0) {
    return providers.map(p => (
      <optgroup key={p.name} label={`${p.name}${p.is_default ? '（默认）' : ''}`}>
        {p.models.map(m => (
          <option key={m.value} value={m.value}>{m.label}</option>
        ))}
      </optgroup>
    ))
  }
  // 无供应商数据时回退到扁平列表
  return models.map(m => <option key={m.value} value={m.value}>{m.label}</option>)
}

// ── 组件 ──

export default function CreateAgentModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (agentName?: string) => void
}) {
  const t = useT()
  // 预设选择
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [selectedSub, setSelectedSub] = useState<string | null>(null)
  const [showSubModal, setShowSubModal] = useState<string | null>(null) // 子选项弹窗（独立 modal）

  // 表单字段
  const [name, setName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [temperature, setTemperature] = useState(0.8)
  const [topP, setTopP] = useState(0.9)
  const [presencePenalty, setPresencePenalty] = useState(0.5)
  const [frequencyPenalty, setFrequencyPenalty] = useState(0.5)
  const [thinkingEnabled, setThinkingEnabled] = useState(false)
  const [hideAiIdentity, setHideAiIdentity] = useState(false)
  const [reminderGrace, setReminderGrace] = useState('every_time')
  const [delayReplyEnabled, setDelayReplyEnabled] = useState<boolean | null>(null)
  const [configProfile, setConfigProfile] = useState('chat')
  const [maxToolRounds, setMaxToolRounds] = useState(3)
  const [alarmMaxToolRounds, setAlarmMaxToolRounds] = useState(10)
  const [forceAlarmOnEnd, setForceAlarmOnEnd] = useState(false)
  const [maxAlarms, setMaxAlarms] = useState(10)
  const [isAiEditable, setIsAiEditable] = useState(true)
  const [allowFriendRequests, setAllowFriendRequests] = useState(true)
  const [autoRespondFriendRequest, setAutoRespondFriendRequest] = useState(false)
  const [discoverable, setDiscoverable] = useState(true)
  const [allowOthersChat, setAllowOthersChat] = useState(true)
  const [othersChatMode, setOthersChatMode] = useState('unlimited')
  const [othersChatQuota, setOthersChatQuota] = useState(30)
  const [othersChatUsed, setOthersChatUsed] = useState(0)
  const [disallowMode, setDisallowMode] = useState('strict')
  const [chatModel, setChatModel] = useState('')
  const [workModel, setWorkModel] = useState('')
  const [apiCreditCost, setApiCreditCost] = useState(0)
  const [aiType, setAiType] = useState('resonance')  // v0.1.3
  const [apiBaseUrl, setApiBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [memoryLoadMode, setMemoryLoadMode] = useState('index_only')
  const [memoryRecentCount, setMemoryRecentCount] = useState(0)
  const [memorySharedScope, setMemorySharedScope] = useState('private_only')
  const [bio, setBio] = useState('')
  const [statusText, setStatusText] = useState('')
  const [autoDndThreshold, setAutoDndThreshold] = useState(20)
  const [autoDndDuration, setAutoDndDuration] = useState(5)
  const [autoResetQuota, setAutoResetQuota] = useState(false)
  const [groupOwnerPays, setGroupOwnerPays] = useState(true)
  const [conversationLogsLimit, setConversationLogsLimit] = useState<number | null>(null)
  const [userCanViewLogs, setUserCanViewLogs] = useState<boolean | null>(null)

  // 弹窗状态
  const [showDetailSettings, setShowDetailSettings] = useState(false)

  // 加载中的模型选项
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [defaults, setDefaults] = useState<{ chat_model: string; work_model: string }>({ chat_model: '', work_model: '' })
  const [thinkingSupported, setThinkingSupported] = useState(false)

  // 错误/加载
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ── sin() 浮动动画（JS 驱动，选完子项才启动，data-attr 查询无 ref 开销） ──
  const animKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const key = selectedSub ? selectedPreset : null
    // 复位上一个动画卡片
    if (animKeyRef.current && animKeyRef.current !== key) {
      const prev = document.querySelector(`[data-preset-key="${animKeyRef.current}"]`) as HTMLDivElement | null
      if (prev) prev.style.transform = 'translate3d(0, 0, 0)'
    }
    animKeyRef.current = key
    if (!key) return

    let rafId: number
    const start = performance.now()
    const animate = (now: number) => {
      const t = (now - start) / 1000
      const y = Math.sin(t * 2.1) * 5
      const el = document.querySelector(`[data-preset-key="${key}"]`) as HTMLDivElement | null
      if (el) el.style.transform = `translate3d(0, ${y}px, 0)`
      rafId = requestAnimationFrame(animate)
    }
    rafId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafId)
  }, [selectedSub, selectedPreset])

  useEffect(() => {
    api.get<{ models: ModelOption[]; providers: ProviderInfo[]; defaults: { chat_model: string; work_model: string }; provider: { thinking_supported: boolean } }>('/agents/models')
      .then(data => {
        setModelOptions(data.models)
        setProviders(data.providers || [])
        setDefaults(data.defaults)
        setThinkingSupported(data.provider?.thinking_supported ?? false)
      })
      .catch(console.error)
  }, [])

  // ── 应用预设 ──
  const applyPreset = (presetKey: string, subId: string | null) => {
    const preset = PRESETS[presetKey]
    if (!preset) return

    // 基础预设值
    setTemperature(preset.temperature)
    setThinkingEnabled(preset.thinking_enabled)
    setMaxToolRounds(preset.max_tool_rounds)
    setAlarmMaxToolRounds(preset.alarm_max_tool_rounds)
    setForceAlarmOnEnd(preset.force_alarm_on_end)
    setMaxAlarms(preset.max_alarms)
    setDelayReplyEnabled(preset.delay_reply_enabled)
    setIsAiEditable(preset.is_ai_editable)
    setHideAiIdentity(preset.hide_ai_identity)
    setReminderGrace(preset.reminder_grace || 'every_time')
    setMemoryLoadMode(preset.memory_load_mode || 'index_only')
    setMemoryRecentCount(preset.memory_recent_count ?? 0)
    setConfigProfile(presetKey)

    // 子选项覆盖
    if (subId) {
      const subOptions = SUB_OPTIONS[presetKey] || []
      const sub = subOptions.find(s => s.id === subId)
      if (sub) {
        if (sub.params.temperature !== undefined) setTemperature(sub.params.temperature)
        if (sub.params.max_tool_rounds !== undefined) setMaxToolRounds(sub.params.max_tool_rounds)
        if (sub.params.thinking_enabled !== undefined) setThinkingEnabled(sub.params.thinking_enabled)
        if (sub.params.is_ai_editable !== undefined) setIsAiEditable(sub.params.is_ai_editable)
        if (sub.params.alarm_max_tool_rounds !== undefined) setAlarmMaxToolRounds(sub.params.alarm_max_tool_rounds)
        if (sub.params.force_alarm_on_end !== undefined) setForceAlarmOnEnd(sub.params.force_alarm_on_end)
        if (sub.params.max_alarms !== undefined) setMaxAlarms(sub.params.max_alarms)
        if (sub.ai_type) setAiType(sub.ai_type)
      }
    }
  }

  // ── 选择卡片 → 打开子选项弹窗 ──
  const handleCardClick = (key: string) => {
    setSelectedPreset(key)
    setShowSubModal(key)
  }

  // ── 选择子项 → 关闭弹窗，开始浮动 ──
  const handleSubSelect = (presetKey: string, subId: string) => {
    setSelectedPreset(presetKey)
    setSelectedSub(subId)
    applyPreset(presetKey, subId)
    setShowSubModal(null)
  }

  // ── 创建 ──
  const handleCreate = async () => {
    if (!name.trim()) return
    setLoading(true)
    setError('')
    try {
      const agent = await api.post<any>('/agents', {
        name: name.trim(),
        system_prompt: systemPrompt || null,
        temperature,
        top_p: topP,
        presence_penalty: presencePenalty,
        frequency_penalty: frequencyPenalty,
        chat_model: chatModel || null,
        work_model: workModel || null,
        thinking_enabled: thinkingEnabled,
        hide_ai_identity: hideAiIdentity,
        delay_reply_enabled: delayReplyEnabled,
        reminder_grace: reminderGrace,
        config_profile: selectedPreset || 'chat',
        max_tool_rounds: maxToolRounds,
        alarm_max_tool_rounds: alarmMaxToolRounds,
        force_alarm_on_end: forceAlarmOnEnd,
        max_alarms: maxAlarms,
        is_ai_editable: isAiEditable,
        allow_friend_requests: allowFriendRequests,
        auto_respond_friend_request: autoRespondFriendRequest,
        discoverable,
        allow_others_chat: allowOthersChat,
        others_chat_mode: othersChatMode,
        others_chat_quota: othersChatQuota,
        others_chat_used: othersChatUsed,
        disallow_mode: disallowMode,
        auto_reset_quota: autoResetQuota,
        group_owner_pays: groupOwnerPays,
        api_credit_cost: apiCreditCost,
        ai_type: aiType,
        memory_load_mode: memoryLoadMode,
        memory_recent_count: memoryRecentCount,
        memory_shared_scope: memorySharedScope,
        bio: bio || null,
        status_text: statusText || null,
        auto_dnd_threshold: autoDndThreshold,
        auto_dnd_duration: autoDndDuration,
        conversation_logs_limit: conversationLogsLimit,
        user_can_view_logs: userCanViewLogs,
      })
      // 如果填写了独立 API 配置，创建后立即设置
      if (apiBaseUrl.trim() || apiKey.trim()) {
        try {
          await api.put(`/agents/${agent.id}/config`, {
            api_base_url: apiBaseUrl.trim() || null,
            api_key: apiKey.trim() || null,
          })
        } catch { /* 静默失败，不影响创建流程 */ }
      }
      onCreated(agent.name)
    } catch (err: any) {
      setError(err.message || t('modal.createAgentFailed'))
    } finally {
      setLoading(false)
    }
  }

  // ── 当前选中卡片的子选项 ──
  const currentSubOptions = selectedPreset ? SUB_OPTIONS[selectedPreset] || [] : []
  const selectedSubLabel = selectedSub
    ? currentSubOptions.find(s => s.id === selectedSub)?.label || ''
    : ''

  return (
    <div className="fixed inset-0 md:bg-black/70 flex items-center justify-center z-50 overflow-y-auto bg-surface" onClick={onClose}>
      <div
        className="bg-elevated border border-border rounded-none md:rounded-2xl p-6 w-full max-w-full md:max-w-2xl mx-0 md:mx-4 shadow-2xl shadow-black/30 my-0 md:my-8 h-full md:h-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 移动端头部：ArrowLeft + 标题 */}
        <div className="flex items-center justify-between mb-5 md:hidden shrink-0">
          <button onClick={onClose} className="p-1 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors">
            <ArrowLeft size={20} />
          </button>
          <h2 className="text-base font-semibold text-textPrimary">{t('modal.createAgentTitle')}</h2>
          <div className="w-6" />
        </div>

        {/* 桌面端头部：标题 + X */}
        <div className="hidden md:flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-textPrimary">{t('modal.createAgentTitle')}</h2>
          <button onClick={onClose} className="text-textMuted hover:text-textSecondary transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* 可滚动内容区 */}
        <div className="flex-1 overflow-y-auto md:overflow-visible pb-[var(--safe-bottom)] md:pb-0">

        {/* ── 名称输入 ── */}
        <div className="mb-4">
          <label className="block text-xs font-medium mb-1.5 text-textSecondary">{t('chat.groupName')}</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
            placeholder={t('modal.createAgentNamePlaceholder')}
          />
        </div>

        {/* ── 系统提示词 ── */}
        <div className="mb-5">
          <label className="block text-xs font-medium mb-1.5 text-textSecondary">{t('modal.createAgentSystemPrompt')}</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={3}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
            placeholder={t('modal.createAgentSystemPromptPlaceholder')}
          />
        </div>

        {/* ── 三档卡片（横排，放大） ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4 mb-5">
          {Object.entries(PRESETS).map(([key, preset]) => {
            const icon = CARD_ICONS[key]
            const isSelected = selectedPreset === key
            const hasSub = selectedSub && isSelected

            return (
              <div key={key} className="preset-card-frame h-full pb-[7px] overflow-visible">
                <div
                  data-preset-key={key}
                  className="preset-card-inner h-full"
                >
                  <button
                    onClick={() => handleCardClick(key)}
                    className={`w-full h-full text-left rounded-xl border transition-colors duration-300 min-h-[150px] md:min-h-[160px]
                      bg-gradient-to-b ${icon.color}
                      ${isSelected
                        ? 'border-primary-400/60 shadow-lg shadow-primary-500/10'
                        : 'border-border hover:border-primary-500/30'
                      }`}
                  >
                    <div className="p-5 flex flex-col items-center text-center gap-2">
                      <span className="text-3xl"><PresetIcon name={icon.icon} /></span>
                      <span className="text-sm font-semibold text-textPrimary">{t(`preset.${preset.key}Name` as any)}</span>
                      <p className="text-xs text-textSecondary leading-snug">{t(`preset.${preset.key}Desc` as any)}</p>

                      {hasSub && (
                        <span className="text-xs text-primary-400 bg-primary-500/10 px-2 py-0.5 rounded-full mt-1">
                          <SubIcon name={SUB_OPTIONS[key]?.find(s => s.id === selectedSub)?.icon || ''} /> {selectedSub ? t(getSubPresetKey(selectedSub)) : ''}
                        </span>
                      )}
                    </div>
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {/* ── AI 类型（选细档时自动推荐，可手动改）── */}
        {selectedPreset && (
          <div className="mb-5">
            <div className="flex items-center gap-2 mb-2">
              <label className="text-xs font-medium text-textSecondary">{t('modal.detailSettingsAiType')}</label>
              {selectedSub && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary-500/15 text-primary-500">{t('modal.aiTypeRecommended')}</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {([
                { value: 'general', label: t('modal.detailSettingsAiTypeGeneral'), icon: 'User', desc: t('modal.detailSettingsAiTypeGeneralDesc') },
                { value: 'semi_general', label: t('modal.detailSettingsAiTypeSemiGeneral'), icon: 'RefreshCw', desc: t('modal.detailSettingsAiTypeSemiGeneralDesc') },
                { value: 'resonance', label: t('modal.detailSettingsAiTypeResonance'), icon: 'Globe', desc: t('modal.detailSettingsAiTypeResonanceDesc') },
              ] as const).map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setAiType(type.value)}
                  className={`flex flex-col items-center gap-1 p-2.5 rounded-xl border text-center transition-all ${
                    aiType === type.value
                      ? 'border-primary-400 bg-primary-500/10 text-primary-600 dark:text-primary-300'
                      : 'border-border bg-canvas text-textSecondary hover:bg-elevated'
                  }`}
                >
                  <span className="text-lg"><SubIcon name={type.icon} /></span>
                  <span className="text-xs font-semibold">{type.label}</span>
                  <span className="text-[9px] leading-tight text-textMuted">{type.desc}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── 跳过预设 ── */}
        {!selectedPreset && (
          <button
            onClick={() => setShowDetailSettings(true)}
            className="w-full text-center text-xs text-textMuted hover:text-textSecondary transition-colors mb-3 py-1"
          >
            {t('modal.createAgentSkipPreset')}
          </button>
        )}

        {/* ── 个人资料（可选） ── */}
        <div className="space-y-2 mb-3">
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            placeholder={t('agentDetail.bioPlaceholder')}
            rows={2}
            maxLength={500}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
          />
          <input
            type="text"
            value={statusText}
            onChange={(e) => setStatusText(e.target.value)}
            placeholder={t('agentDetail.statusTextPlaceholder')}
            className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          />
        </div>

        {/* ── 操作按钮区 ── */}
        <div className="flex gap-3">
          <button
            onClick={() => setShowDetailSettings(true)}
            className="flex-1 py-2.5 text-sm border border-border rounded-xl hover:bg-elevated text-textSecondary transition-colors font-medium flex items-center justify-center gap-1.5"
          >
            <Settings size={14} />
            {t('modal.createAgentDetailSettings')}
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || loading}
            className="flex-1 py-2.5 text-sm bg-primary-500 text-white rounded-xl hover:bg-primary-600 disabled:opacity-30 font-medium transition-all shadow-lg shadow-primary-500/20"
          >
            {loading ? t('modal.createAgentCreating') : t('modal.createAgentCreate')}
          </button>
        </div>
        {!name.trim() && selectedPreset && (
          <p className="text-xs text-textMuted mt-2 text-center">{t('modal.createAgentConfirmHint')}</p>
        )}

        {error && <div className="text-sm text-rose-400 mt-3 text-center">{error}</div>}

        {/* ── 子选项弹窗（独立 modal，选中后关闭并开始浮动） ── */}
        {showSubModal && selectedPreset && (
          <SubOptionModal
            preset={PRESETS[showSubModal]}
            selectedSub={selectedSub}
            onSelect={(subId) => handleSubSelect(showSubModal, subId)}
            onClose={() => { setShowSubModal(null); setSelectedPreset(null) }}
          />
        )}

        {/* ── 详细设置弹窗 ── */}
        {showDetailSettings && (
          <DetailSettingsModal
            name={name} setName={setName}
            systemPrompt={systemPrompt} setSystemPrompt={setSystemPrompt}
            temperature={temperature} setTemperature={setTemperature}
            topP={topP} setTopP={setTopP}
            presencePenalty={presencePenalty} setPresencePenalty={setPresencePenalty}
            frequencyPenalty={frequencyPenalty} setFrequencyPenalty={setFrequencyPenalty}
            thinkingEnabled={thinkingEnabled} setThinkingEnabled={setThinkingEnabled}
            hideAiIdentity={hideAiIdentity} setHideAiIdentity={setHideAiIdentity}
            delayReplyEnabled={delayReplyEnabled} setDelayReplyEnabled={setDelayReplyEnabled}
            maxToolRounds={maxToolRounds} setMaxToolRounds={setMaxToolRounds}
            alarmMaxToolRounds={alarmMaxToolRounds} setAlarmMaxToolRounds={setAlarmMaxToolRounds}
            forceAlarmOnEnd={forceAlarmOnEnd} setForceAlarmOnEnd={setForceAlarmOnEnd}
            maxAlarms={maxAlarms} setMaxAlarms={setMaxAlarms}
            isAiEditable={isAiEditable} setIsAiEditable={setIsAiEditable}
            allowFriendRequests={allowFriendRequests} setAllowFriendRequests={setAllowFriendRequests}
            autoRespondFriendRequest={autoRespondFriendRequest} setAutoRespondFriendRequest={setAutoRespondFriendRequest}
            reminderGrace={reminderGrace} setReminderGrace={setReminderGrace}
            discoverable={discoverable} setDiscoverable={setDiscoverable}
            allowOthersChat={allowOthersChat} setAllowOthersChat={setAllowOthersChat}
            othersChatMode={othersChatMode} setOthersChatMode={setOthersChatMode}
            othersChatQuota={othersChatQuota} setOthersChatQuota={setOthersChatQuota}
            othersChatUsed={othersChatUsed} setOthersChatUsed={setOthersChatUsed}
            disallowMode={disallowMode} setDisallowMode={setDisallowMode}
            chatModel={chatModel} setChatModel={setChatModel}
            workModel={workModel} setWorkModel={setWorkModel}
            aiType={aiType} setAiType={setAiType}
            apiCreditCost={apiCreditCost} setApiCreditCost={setApiCreditCost}
            apiBaseUrl={apiBaseUrl} setApiBaseUrl={setApiBaseUrl}
            apiKey={apiKey} setApiKey={setApiKey}
            memoryLoadMode={memoryLoadMode} setMemoryLoadMode={setMemoryLoadMode}
            memoryRecentCount={memoryRecentCount} setMemoryRecentCount={setMemoryRecentCount}
            memorySharedScope={memorySharedScope} setMemorySharedScope={setMemorySharedScope}
            autoDndThreshold={autoDndThreshold} setAutoDndThreshold={setAutoDndThreshold}
            autoDndDuration={autoDndDuration} setAutoDndDuration={setAutoDndDuration}
            conversationLogsLimit={conversationLogsLimit} setConversationLogsLimit={setConversationLogsLimit}
            userCanViewLogs={userCanViewLogs} setUserCanViewLogs={setUserCanViewLogs}
            autoResetQuota={autoResetQuota} setAutoResetQuota={setAutoResetQuota}
            groupOwnerPays={groupOwnerPays} setGroupOwnerPays={setGroupOwnerPays}
            modelOptions={modelOptions}
            providers={providers}
            defaults={defaults}
            thinkingSupported={thinkingSupported}
            onClose={() => setShowDetailSettings(false)}
          />
        )}
        </div>
      </div>

    </div>
  )
}

// ── 子选项 ID → 翻译 key 映射 ──
function getSubPresetKey(subId: string): string {
  // e.g., "chat_low_power" → "LowPower" → "preset.subLowPower"
  const parts = subId.split('_')
  const subParts = parts.slice(1) // remove preset prefix
  const pascal = subParts.map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return `preset.sub${pascal}`
}

// ── 子选项弹窗（独立 modal，居中显示） ──

function SubOptionModal({
  preset, selectedSub, onSelect, onClose,
}: {
  preset: PresetData
  selectedSub: string | null
  onSelect: (subId: string) => void
  onClose: () => void
}) {
  const t = useT()
  const icon = CARD_ICONS[preset.key]
  const subOptions = SUB_OPTIONS[preset.key] || []
  return (
    <div className="fixed inset-0 md:bg-black/60 flex items-center justify-center z-[70] bg-surface" onClick={onClose}>
      <div
        className="bg-elevated border border-border rounded-none md:rounded-2xl p-6 w-full max-w-full md:max-w-md mx-0 md:mx-4 shadow-2xl shadow-black/30 md:animate-pop-in h-full md:h-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 移动端头部 */}
        <div className="flex items-center justify-between mb-3 md:hidden shrink-0">
          <button onClick={onClose} className="p-1 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors">
            <ArrowLeft size={20} />
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xl"><PresetIcon name={icon.icon} /></span>
            <h2 className="text-sm font-semibold text-textPrimary">{t(`preset.${preset.key}Name` as any)}</h2>
          </div>
          <div className="w-6" />
        </div>

        {/* 桌面端头部 */}
        <div className="hidden md:flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="text-2xl"><PresetIcon name={icon.icon} /></span>
            <h2 className="text-base font-semibold text-textPrimary">{t(`preset.${preset.key}Name` as any)}</h2>
          </div>
          <button onClick={onClose} className="text-textMuted hover:text-textSecondary transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* 可滚动内容 */}
        <div className="flex-1 overflow-y-auto md:overflow-visible pb-[var(--safe-bottom)] md:pb-0">
        <p className="text-xs text-textMuted mb-4">{t(`preset.${preset.key}Desc` as any)}</p>
        <p className="text-xs text-textMuted mb-4 italic text-center bg-canvas/50 rounded-lg py-2">
          {t('modal.createAgentPresetHint')}
        </p>
        <div className="space-y-3">
          {subOptions.map(sub => (
            <button
              key={sub.id}
              onClick={() => onSelect(sub.id)}
              className={`w-full text-left p-4 rounded-xl border transition-all duration-150
                ${selectedSub === sub.id
                  ? 'border-primary-400/60 bg-primary-500/10 shadow-md shadow-primary-500/5'
                  : 'border-border/50 bg-elevated hover:border-primary-500/30 hover:bg-canvas'
                }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl flex-shrink-0"><SubIcon name={sub.icon} /></span>
                <div>
                  <span className="text-sm font-semibold text-textPrimary">{t(getSubPresetKey(sub.id))}</span>
                  <p className="text-xs text-textSecondary mt-1 leading-relaxed">{t(getSubPresetKey(sub.id) + 'Desc' as any)}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
        </div>
      </div>
    </div>
  )
}

// ── 详细设置弹窗（分区） ──

function DetailSettingsModal({
  name, setName,
  systemPrompt, setSystemPrompt,
  temperature, setTemperature,
  topP, setTopP,
  presencePenalty, setPresencePenalty,
  frequencyPenalty, setFrequencyPenalty,
  thinkingEnabled, setThinkingEnabled,
  hideAiIdentity, setHideAiIdentity,
  delayReplyEnabled, setDelayReplyEnabled,
  maxToolRounds, setMaxToolRounds,
  alarmMaxToolRounds, setAlarmMaxToolRounds,
  forceAlarmOnEnd, setForceAlarmOnEnd,
  maxAlarms, setMaxAlarms,
  isAiEditable, setIsAiEditable,
  allowFriendRequests, setAllowFriendRequests,
  autoRespondFriendRequest, setAutoRespondFriendRequest,
  reminderGrace, setReminderGrace,
  discoverable, setDiscoverable,
  allowOthersChat, setAllowOthersChat,
  othersChatMode, setOthersChatMode,
  othersChatQuota, setOthersChatQuota,
  othersChatUsed, setOthersChatUsed,
  disallowMode, setDisallowMode,
  chatModel, setChatModel,
  workModel, setWorkModel,
  apiCreditCost, setApiCreditCost,
  aiType, setAiType,
  apiBaseUrl, setApiBaseUrl,
  apiKey, setApiKey,
  memoryLoadMode, setMemoryLoadMode,
  memoryRecentCount, setMemoryRecentCount,
  memorySharedScope, setMemorySharedScope,
  autoDndThreshold, setAutoDndThreshold,
  autoDndDuration, setAutoDndDuration,
  conversationLogsLimit, setConversationLogsLimit,
  userCanViewLogs, setUserCanViewLogs,
  autoResetQuota, setAutoResetQuota,
  groupOwnerPays, setGroupOwnerPays,
  modelOptions,
  providers,
  defaults,
  thinkingSupported,
  onClose,
}: {
  name: string; setName: (v: string) => void
  systemPrompt: string; setSystemPrompt: (v: string) => void
  temperature: number; setTemperature: (v: number) => void
  topP: number; setTopP: (v: number) => void
  presencePenalty: number; setPresencePenalty: (v: number) => void
  frequencyPenalty: number; setFrequencyPenalty: (v: number) => void
  thinkingEnabled: boolean; setThinkingEnabled: (v: boolean) => void
  hideAiIdentity: boolean; setHideAiIdentity: (v: boolean) => void
  delayReplyEnabled: boolean | null; setDelayReplyEnabled: (v: boolean | null) => void
  maxToolRounds: number; setMaxToolRounds: (v: number) => void
  alarmMaxToolRounds: number; setAlarmMaxToolRounds: (v: number) => void
  forceAlarmOnEnd: boolean; setForceAlarmOnEnd: (v: boolean) => void
  maxAlarms: number; setMaxAlarms: (v: number) => void
  isAiEditable: boolean; setIsAiEditable: (v: boolean) => void
  allowFriendRequests: boolean; setAllowFriendRequests: (v: boolean) => void
  autoRespondFriendRequest: boolean; setAutoRespondFriendRequest: (v: boolean) => void
  reminderGrace: string; setReminderGrace: (v: string) => void
  discoverable: boolean; setDiscoverable: (v: boolean) => void
  allowOthersChat: boolean; setAllowOthersChat: (v: boolean) => void
  othersChatMode: string; setOthersChatMode: (v: string) => void
  othersChatQuota: number; setOthersChatQuota: (v: number) => void
  othersChatUsed: number; setOthersChatUsed: (v: number) => void
  disallowMode: string; setDisallowMode: (v: string) => void
  chatModel: string; setChatModel: (v: string) => void
  workModel: string; setWorkModel: (v: string) => void
  apiCreditCost: number; setApiCreditCost: (v: number) => void
  aiType: string; setAiType: (v: string) => void
  apiBaseUrl: string; setApiBaseUrl: (v: string) => void
  apiKey: string; setApiKey: (v: string) => void
  memoryLoadMode: string; setMemoryLoadMode: (v: string) => void
  memoryRecentCount: number; setMemoryRecentCount: (v: number) => void
  memorySharedScope: string; setMemorySharedScope: (v: string) => void
  autoDndThreshold: number; setAutoDndThreshold: (v: number) => void
  autoDndDuration: number; setAutoDndDuration: (v: number) => void
  conversationLogsLimit: number | null; setConversationLogsLimit: (v: number | null) => void
  userCanViewLogs: boolean | null; setUserCanViewLogs: (v: boolean | null) => void
  autoResetQuota: boolean; setAutoResetQuota: (v: boolean) => void
  groupOwnerPays: boolean; setGroupOwnerPays: (v: boolean) => void
  modelOptions: ModelOption[]
  providers: ProviderInfo[]
  defaults: { chat_model: string; work_model: string }
  thinkingSupported: boolean
  onClose: () => void
}) {
  const t = useT()
  // 兑换码状态（弹窗内自管理）
  const [redeemCode, setRedeemCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [redeemMsg, setRedeemMsg] = useState('')
  const [redeemOk, setRedeemOk] = useState<boolean | null>(null)
  const [testingApi, setTestingApi] = useState(false)
  const [testApiMsg, setTestApiMsg] = useState('')
  const [testApiOk, setTestApiOk] = useState<boolean | null>(null)

  const handleRedeem = async () => {
    if (!redeemCode.trim()) return
    setRedeeming(true)
    setRedeemMsg('')
    setRedeemOk(null)
    try {
      const data = await api.post<{ message: string }>('/user/redeem', { code: redeemCode.trim() })
      setRedeemOk(true)
      setRedeemMsg(data.message || t('modal.redeemSuccess'))
      setRedeemCode('')
    } catch (err: any) {
      setRedeemOk(false)
      setRedeemMsg(err.message || t('modal.redeemFailed'))
    } finally {
      setRedeeming(false)
    }
  }

  const handleTestApi = async () => {
    setTestingApi(true)
    setTestApiMsg('')
    try {
      const data = await api.post<{ ok: boolean; message: string }>('/user/test-api-connection', {
        api_base_url: apiBaseUrl || null,
        api_key: apiKey || null,
      })
      setTestApiOk(data.ok)
      setTestApiMsg(data.message || (data.ok ? t('modal.testSuccess') : t('modal.testFailed')))
    } catch (err: any) {
      setTestApiOk(false)
      setTestApiMsg(err.message || t('error.testFailed'))
    } finally {
      setTestingApi(false)
    }
  }

  return (
    <div className="fixed inset-0 md:bg-black/70 flex items-start justify-center z-[60] md:pt-8 overflow-y-auto bg-surface" onClick={onClose}>
      <div
        className="bg-elevated border border-border rounded-none md:rounded-2xl p-6 w-full max-w-full md:max-w-2xl mx-0 md:mx-4 shadow-2xl shadow-black/30 my-0 md:my-4 h-full md:h-auto flex flex-col pb-[var(--safe-bottom)] md:pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 移动端头部 */}
        <div className="flex items-center justify-between mb-5 md:hidden shrink-0">
          <button onClick={onClose} className="p-1 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors">
            <ArrowLeft size={20} />
          </button>
          <h2 className="text-base font-semibold text-textPrimary">{t('modal.detailSettingsTitle')}</h2>
          <div className="w-6" />
        </div>

        {/* 桌面端头部 */}
        <div className="hidden md:flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-textPrimary">{t('modal.detailSettingsTitle')}</h2>
          <button onClick={onClose} className="text-textMuted hover:text-textSecondary transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-5 flex-1 overflow-y-auto md:max-h-[65vh] pr-1 pb-[var(--safe-bottom)] md:pb-0">

          {/* ── 基础信息 ── */}
          <Section title={t('modal.detailSettingsBasicInfo')} desc={t('modal.detailSettingsBasicInfoDesc')}>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('chat.groupName')}</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.createAgentSystemPrompt')}</label>
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
                placeholder={t('modal.createAgentSystemPromptPlaceholder')}
              />
            </div>
          </Section>

          {/* ── 模型参数 ── */}
          <Section title={t('modal.detailSettingsModelParams')} desc={t('modal.detailSettingsModelParamsDesc')}>
            <SliderField label="Temperature" value={temperature} setValue={setTemperature} min={0} max={2} step={0.1} desc={t('modal.detailSettingsTemperatureDesc')} />
            <SliderField label="Top P" value={topP} setValue={setTopP} min={0} max={1} step={0.05} desc={t('modal.detailSettingsTopPDesc')} />
            <SliderField label="Presence Penalty" value={presencePenalty} setValue={setPresencePenalty} min={-2} max={2} step={0.1} desc={t('modal.detailSettingsPresencePenaltyDesc')} />
            <SliderField label="Frequency Penalty" value={frequencyPenalty} setValue={setFrequencyPenalty} min={-2} max={2} step={0.1} desc={t('modal.detailSettingsFrequencyPenaltyDesc')} />
            {thinkingSupported && (
              <ToggleField label={t('modal.detailSettingsThinkingMode')} value={thinkingEnabled} setValue={setThinkingEnabled} desc={t('modal.detailSettingsThinkingModeDesc')} />
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium mb-1 text-textSecondary">
                  {t('modal.detailSettingsChatModel')} <span className="text-textMuted">{t('modal.detailSettingsDefaultLabel')} {defaults.chat_model})</span>
                </label>
                <select value={chatModel} onChange={(e) => setChatModel(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('modal.detailSettingsGlobalDefault')}</option>
                  {renderModelOptions(modelOptions, providers)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium mb-1 text-textSecondary">
                  {t('modal.detailSettingsWorkModel')} <span className="text-textMuted">{t('modal.detailSettingsDefaultLabel')} {defaults.work_model})</span>
                </label>
                <select value={workModel} onChange={(e) => setWorkModel(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('modal.detailSettingsGlobalDefault')}</option>
                  {renderModelOptions(modelOptions, providers)}
                </select>
              </div>
            </div>
          </Section>

          {/* ── 工具调用 ── */}
          <Section title={t('modal.detailSettingsToolCalls')} desc={t('modal.detailSettingsToolCallsDesc')}>
            <div className="grid grid-cols-2 gap-3">
              <NumberField label={t('modal.detailSettingsMaxToolRounds')} value={maxToolRounds} setValue={setMaxToolRounds} min={1} max={20} desc={t('modal.detailSettingsMaxToolRoundsDesc')} />
              <NumberField label={t('modal.detailSettingsAlarmRounds')} value={alarmMaxToolRounds} setValue={setAlarmMaxToolRounds} min={1} max={30} desc={t('modal.detailSettingsAlarmRoundsDesc')} />
            </div>
          </Section>

          {/* ── 闹钟 / 心跳 ── */}
          <Section title={t('modal.detailSettingsAlarm')} desc={t('modal.detailSettingsAlarmDesc')}>
            <ToggleField label={t('modal.detailSettingsForceAlarm')} value={forceAlarmOnEnd} setValue={setForceAlarmOnEnd} desc={t('modal.detailSettingsForceAlarmDesc')} />
            <NumberField label={t('modal.detailSettingsMaxAlarms')} value={maxAlarms} setValue={setMaxAlarms} min={1} max={50} desc={t('modal.detailSettingsMaxAlarmsDesc')} />
          </Section>

          {/* ── 文件记忆 ── */}
          <Section title={t('modal.detailSettingsFileMemory')} desc={t('modal.detailSettingsFileMemoryDesc')}>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsMemoryLoadMode')}</label>
              <select
                value={memoryLoadMode}
                onChange={(e) => setMemoryLoadMode(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="index_only">{t('modal.detailSettingsMemoryLoadModeIndexOnly')}</option>
                <option value="index_plus_recent">{t('modal.detailSettingsMemoryLoadModeIndexRecent')}</option>
                <option value="index_plus_semantic">{t('modal.detailSettingsMemoryLoadModeIndexSemantic')}</option>
              </select>
              <p className="text-[10px] text-textMuted mt-1">{t('modal.detailSettingsMemoryLoadModeDesc')}</p>
            </div>
            {memoryLoadMode === 'index_plus_recent' && (
              <NumberField label={t('modal.detailSettingsMemoryRecentCount')} value={memoryRecentCount} setValue={setMemoryRecentCount} min={0} max={50} desc={t('modal.detailSettingsMemoryRecentCountDesc')} />
            )}
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsMemorySharedScope')}</label>
              <select
                value={memorySharedScope}
                onChange={(e) => setMemorySharedScope(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="private_only">{t('modal.detailSettingsMemorySharedScopePrivate')}</option>
                <option value="private_plus_shared_by_user">{t('modal.detailSettingsMemorySharedScopeByUser')}</option>
                <option value="private_plus_shared_all">{t('modal.detailSettingsMemorySharedScopeAll')}</option>
              </select>
              <p className="text-[10px] text-textMuted mt-1">{t('modal.detailSettingsMemorySharedScopeDesc')}</p>
            </div>
          </Section>

          {/* ── 自动免打扰 ── */}
          <Section title={t('modal.detailSettingsAutoDnd') || '自动免打扰'} desc={t('modal.detailSettingsAutoDndDesc') || '意愿评分低于阈值时自动进入免打扰'}>
            <SliderField label={t('modal.detailSettingsAutoDndThreshold') || '触发阈值'} value={autoDndThreshold} setValue={setAutoDndThreshold} min={0} max={100} step={5} desc={t('modal.detailSettingsAutoDndThresholdDesc') || '意愿评分低于此值时自动开启免打扰'} />
            <NumberField label={t('modal.detailSettingsAutoDndDuration') || '持续时长（分钟）'} value={autoDndDuration} setValue={setAutoDndDuration} min={1} max={1440} desc={t('modal.detailSettingsAutoDndDurationDesc') || '自动免打扰的持续时长'} />
          </Section>

          {/* ── 对话日志 ── */}
          <Section title={t('modal.detailSettingsConversationLogs') || '对话日志'} desc={t('modal.detailSettingsConversationLogsDesc') || '此 AI 的日志保留和用户查看权限'}>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsConversationLogsLimit') || '日志保留上限'}</label>
              <input type="number" min={1} max={10000} value={conversationLogsLimit ?? ''}
                onChange={(e) => setConversationLogsLimit(e.target.value ? parseInt(e.target.value) : null)}
                placeholder={t('modal.detailSettingsConversationLogsLimitDesc') || '留空继承全局'}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
              <p className="text-[10px] text-textMuted mt-0.5">{t('modal.detailSettingsConversationLogsLimitDesc') || '留空继承全局设置'}</p>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsUserCanViewLogs') || '允许用户查看日志'}</label>
              <select
                value={userCanViewLogs === null ? 'inherit' : userCanViewLogs ? 'on' : 'off'}
                onChange={(e) => { const v = e.target.value; setUserCanViewLogs(v === 'inherit' ? null : v === 'on') }}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="inherit">{t('modal.detailSettingsInheritGlobal')}</option>
                <option value="on">{t('common.enabled')}</option>
                <option value="off">{t('common.disabled')}</option>
              </select>
              <p className="text-[10px] text-textMuted mt-0.5">{t('modal.detailSettingsUserCanViewLogsDesc') || '留空继承全局默认设置'}</p>
            </div>
          </Section>

          {/* ── AI 类型 ── */}
          <Section title={t('modal.detailSettingsAiType')} desc={t('modal.detailSettingsAiTypeDesc')}>
            <div className="grid grid-cols-3 gap-2">
              {([
                { value: 'general', label: t('modal.detailSettingsAiTypeGeneral'), icon: 'User', desc: t('modal.detailSettingsAiTypeGeneralDesc') },
                { value: 'semi_general', label: t('modal.detailSettingsAiTypeSemiGeneral'), icon: 'RefreshCw', desc: t('modal.detailSettingsAiTypeSemiGeneralDesc') },
                { value: 'resonance', label: t('modal.detailSettingsAiTypeResonance'), icon: 'Globe', desc: t('modal.detailSettingsAiTypeResonanceDesc') },
              ] as const).map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setAiType(type.value)}
                  className={`flex flex-col items-center gap-1 p-2.5 rounded-xl border text-center transition-all ${
                    aiType === type.value
                      ? 'border-primary-400 bg-primary-500/10 text-primary-600 dark:text-primary-300'
                      : 'border-border bg-canvas text-textSecondary hover:bg-elevated'
                  }`}
                >
                  <span className="text-lg"><SubIcon name={type.icon} /></span>
                  <span className="text-xs font-semibold">{type.label}</span>
                  <span className="text-[9px] leading-tight text-textMuted">{type.desc}</span>
                </button>
              ))}
            </div>
          </Section>

          {/* ── 行为开关 ── */}
          <Section title={t('modal.detailSettingsBehaviorSwitches')} desc={t('modal.detailSettingsBehaviorSwitchesDesc')}>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsDelayReply')}</label>
              <select
                value={delayReplyEnabled === null ? 'inherit' : delayReplyEnabled ? 'on' : 'off'}
                onChange={(e) => {
                  const v = e.target.value
                  setDelayReplyEnabled(v === 'inherit' ? null : v === 'on')
                }}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="inherit">{t('modal.detailSettingsInheritGlobal')}</option>
                <option value="on">{t('common.enabled')}</option>
                <option value="off">{t('common.disabled')}</option>
              </select>
            </div>
            <ToggleField label={t('modal.detailSettingsSelfEdit')} value={isAiEditable} setValue={setIsAiEditable} desc={t('modal.detailSettingsSelfEditDesc')} />
            <ToggleField label={t('modal.detailSettingsHideAiIdentity')} value={hideAiIdentity} setValue={setHideAiIdentity} desc={t('modal.detailSettingsHideAiIdentityDesc')} />
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">{t('modal.detailSettingsReminderGrace')}</label>
              <select
                value={reminderGrace}
                onChange={(e) => setReminderGrace(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="every_time">{t('modal.detailSettingsReminderGraceEvery')}</option>
                <option value="once">{t('modal.detailSettingsReminderGraceOnce')}</option>
                <option value="off">{t('modal.detailSettingsReminderGraceOff')}</option>
              </select>
            </div>
          </Section>

          {/* ── 对话与社交权限 ── */}
          <Section title={t('modal.detailSettingsChatPermissionsDetail') || '对话与社交权限'} desc={t('modal.detailSettingsChatPermissionsDetailDesc') || '控制谁可以与此 AI 对话、加好友、消耗配额'}>
            <ToggleField label={t('agents.discoverable')} value={discoverable} setValue={setDiscoverable} desc={t('agents.discoverableDesc')} />
            <ToggleField label={t('modal.detailSettingsAllowFriendRequests')} value={allowFriendRequests} setValue={setAllowFriendRequests} desc={t('modal.detailSettingsAllowFriendRequestsDesc')} />
            {allowFriendRequests && (
              <ToggleField label={t('modal.detailSettingsAutoRespondFriendRequest')} value={autoRespondFriendRequest} setValue={setAutoRespondFriendRequest} desc={t('modal.detailSettingsAutoRespondFriendRequestDesc')} />
            )}

            <div className="mt-3 pt-3 border-t border-border/40">
              <ToggleField label={t('agents.allowOthersChat')} value={allowOthersChat} setValue={setAllowOthersChat} desc={t('agents.allowOthersChatDesc')} />
            </div>
            {allowOthersChat ? (
              <div className="ml-4 pl-3 border-l-2 border-primary-400/30 space-y-2 mt-1">
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" name="othersChatMode" value="unlimited" checked={othersChatMode === 'unlimited'} onChange={() => setOthersChatMode('unlimited')} className="text-primary-500" />
                    <span className="text-xs text-textSecondary">{t('agents.othersChatUnlimited')}</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" name="othersChatMode" value="quota" checked={othersChatMode === 'quota'} onChange={() => setOthersChatMode('quota')} className="text-primary-500" />
                    <span className="text-xs text-textSecondary">{t('agents.othersChatQuota')}</span>
                  </label>
                </div>
                {othersChatMode === 'quota' && (
                  <>
                    <div className="flex items-center gap-3">
                      <NumberField label={t('agents.othersChatQuotaLabel')} value={othersChatQuota} setValue={setOthersChatQuota} min={1} max={9999} />
                      <div className="flex items-center gap-2 pt-5">
                        <span className="text-[11px] text-textMuted">{t('agents.othersChatUsed')}: {othersChatUsed}</span>
                        <button type="button" onClick={() => setOthersChatUsed(0)} className="text-[10px] px-2 py-0.5 rounded border border-border text-textMuted hover:text-textSecondary transition-colors">{t('agents.othersChatUsedReset')}</button>
                      </div>
                      <p className="text-[10px] text-textMuted leading-relaxed">{t('agents.othersChatQuotaDesc')}</p>
                    </div>
                    <ToggleField label={t('agents.autoResetQuota') || '自动重置配额'} value={autoResetQuota} setValue={setAutoResetQuota} desc={t('agents.autoResetQuotaDesc') || '用户每次 DM 后自动重置配额计数至上限'} />
                  </>
                )}
                <ToggleField label={t('agents.groupOwnerPays') || '群聊由群主付费'} value={groupOwnerPays} setValue={setGroupOwnerPays} desc={t('agents.groupOwnerPaysDesc') || '群聊中 AI 消息由群主付费，关闭后用户需使用自有 API Key'} />
              </div>
            ) : (
              <div className="ml-4 pl-3 border-l-2 border-rose-400/30 space-y-2 mt-1">
                <label className="text-[11px] font-medium text-textMuted mb-2 block">{t('agents.disallowModeLabel')}</label>
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" name="disallowMode" value="strict" checked={disallowMode === 'strict'} onChange={() => setDisallowMode('strict')} className="text-primary-500" />
                    <span className="text-xs text-textSecondary">{t('agents.disallowStrict')}</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" name="disallowMode" value="own_key" checked={disallowMode === 'own_key'} onChange={() => setDisallowMode('own_key')} className="text-primary-500" />
                    <span className="text-xs text-textSecondary">{t('agents.disallowOwnKey')}</span>
                  </label>
                </div>
                {disallowMode === 'own_key' && (
                  <p className="text-[10px] text-textMuted leading-relaxed">{t('agents.disallowOwnKeyDesc')}</p>
                )}
              </div>
            )}
          </Section>

          {/* ── 额度 ── */}
          <Section title={t('modal.detailSettingsCreditCost')} desc={t('modal.detailSettingsCreditCostDesc')}>
            <NumberField label={t('modal.detailSettingsApiCreditCost')} value={apiCreditCost} setValue={setApiCreditCost} min={0} max={100000} desc={t('modal.detailSettingsApiCreditCostDesc')} />
          </Section>

          {/* ── API 提供商 ── */}
          <Section title={t('modal.detailSettingsApiProvider')} desc={t('modal.detailSettingsApiProviderDesc')}>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary">API Base URL</label>
              <input
                type="text"
                value={apiBaseUrl}
                onChange={(e) => setApiBaseUrl(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                placeholder={t('modal.detailSettingsApiBaseUrlPlaceholder')}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1 text-textSecondary flex items-center gap-2">
                API Key
                <ApiKeyGetLink providers={providers} />
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
                className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                placeholder={t('modal.detailSettingsApiKeyPlaceholder')}
              />
            </div>
            <button
              onClick={handleTestApi}
              disabled={testingApi || (!apiBaseUrl.trim() && !apiKey.trim())}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs text-textSecondary hover:bg-elevated disabled:opacity-40 transition-colors"
            >
              {testingApi ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
              {t('settings.testConnection')}
            </button>
            {testApiMsg && (
              <p className={`text-xs ${testApiOk === true ? 'text-mint-400' : 'text-rose-400'}`}>
                {testApiMsg}
              </p>
            )}
          </Section>

          {/* ── 兑换码 ── */}
          <Section title={t('modal.detailSettingsRedeemCode')} desc={t('modal.detailSettingsRedeemCodeDesc')}>
            <div className="flex items-center gap-2">
              <div className="flex-1 relative">
                <Ticket size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-textMuted" />
                <input
                  type="text"
                  value={redeemCode}
                  onChange={(e) => setRedeemCode(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  placeholder={t('modal.detailSettingsRedeemPlaceholder')}
                />
              </div>
              <button
                onClick={handleRedeem}
                disabled={redeeming || !redeemCode.trim()}
                className="flex items-center gap-1 px-4 py-2 rounded-lg bg-primary-500 text-white text-sm font-medium hover:bg-primary-600 disabled:opacity-40 transition-colors shrink-0"
              >
                {redeeming ? <Loader2 size={14} className="animate-spin" /> : <span>{t('me.redeem')}</span>}
              </button>
            </div>
            {redeemMsg && (
              <p className={`text-xs ${redeemOk === false ? 'text-rose-400' : 'text-mint-400'}`}>
                {redeemMsg}
              </p>
            )}
          </Section>

        </div>

        <button
          onClick={onClose}
          className="w-full mt-5 py-2.5 text-sm bg-primary-500 text-white rounded-xl hover:bg-primary-600 font-medium transition-all shadow-lg shadow-primary-500/20"
        >
          {t('modal.detailSettingsSaveAndClose')}
        </button>
      </div>
    </div>
  )
}

// ── 分区容器 ──

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <div className="bg-canvas/50 rounded-xl p-4 border border-border/50">
      <h3 className="text-xs font-semibold text-textPrimary mb-1">{title}</h3>
      <p className="text-[10px] text-textMuted mb-3 leading-relaxed">{desc}</p>
      <div className="space-y-2.5">{children}</div>
    </div>
  )
}

// ── 滑块 ──

function SliderField({
  label, value, setValue, min, max, step, desc,
}: {
  label: string; value: number; setValue: (v: number) => void
  min: number; max: number; step: number; desc?: string
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <label className="text-xs text-textSecondary">{label}</label>
        <span className="text-xs font-mono text-textPrimary">{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={(e) => setValue(parseFloat(e.target.value))}
        className="w-full"
      />
      {desc && <p className="text-[10px] text-textMuted mt-0.5">{desc}</p>}
    </div>
  )
}

// ── 数字输入 ──

function NumberField({
  label, value, setValue, min, max, desc,
}: {
  label: string; value: number; setValue: (v: number) => void
  min: number; max: number; desc?: string
}) {
  return (
    <div>
      <label className="block text-xs text-textSecondary mb-1">{label}</label>
      <input
        type="number" min={min} max={max}
        value={value}
        onChange={(e) => setValue(parseInt(e.target.value) || min)}
        className="w-full px-3 py-2 rounded-lg border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
      />
      {desc && <p className="text-[10px] text-textMuted mt-0.5">{desc}</p>}
    </div>
  )
}

// ── 开关 ──

function ToggleField({
  label, value, setValue, desc,
}: {
  label: string; value: boolean; setValue: (v: boolean) => void; desc?: string
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex-1 min-w-0">
        <span className="text-xs text-textSecondary">{label}</span>
        {desc && <p className="text-[10px] text-textMuted mt-0.5">{desc}</p>}
      </div>
      <Toggle checked={value} onChange={setValue} />
    </div>
  )
}
