import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useT } from '../i18n/I18nContext'
import { overrideLangForSetup } from '../i18n/I18nContext'
import { type Lang, DEFAULT_LANG, LANGUAGES } from '../i18n/languages'
import { api } from '../api/client'
import {
  Globe, Check, User, Key, Bot, Mail, Shield, Sparkles,
  Upload, Loader2, Eye, EyeOff, ChevronLeft, ChevronRight,
  Palette, Server,
} from 'lucide-react'

// ─── 预设颜色 ──────────────────────────────────────────────
const PRESET_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
  '#f97316', '#eab308', '#22c55e', '#14b8a6',
  '#06b6d4', '#3b82f6', '#64748b', '#a1a1aa',
]

// ─── 步骤配置 ──────────────────────────────────────────────
interface StepDef {
  key: string
  labelKey: string
  icon: typeof Globe
}

const ALL_STEPS: StepDef[] = [
  { key: 'language',           labelKey: 'setup.stepLanguage',          icon: Globe },
  { key: 'instanceDefaults',   labelKey: 'setup.stepInstanceDefaults',  icon: Server },
  { key: 'profile',            labelKey: 'setup.stepProfile',           icon: User },
  { key: 'apiConfig',          labelKey: 'setup.stepApiConfig',         icon: Key },
  { key: 'createAI',           labelKey: 'setup.stepCreateAI',          icon: Bot },
  { key: 'smtp',               labelKey: 'setup.stepSmtp',              icon: Mail },
  { key: 'keyPool',            labelKey: 'setup.stepKeyPool',           icon: Shield },
  { key: 'complete',           labelKey: 'setup.stepComplete',          icon: Sparkles },
]

// Admin-only step keys
const ADMIN_STEPS = new Set(['instanceDefaults', 'smtp', 'keyPool'])

// ─── 主组件 ────────────────────────────────────────────────
export default function SetupPage() {
  const { user, refreshUser } = useAuth()
  const isAdmin = user?.role === 'admin'
  const t = useT()
  const navigate = useNavigate()

  // ── 过滤可见步骤 ──
  const visibleSteps = ALL_STEPS.filter(s => !ADMIN_STEPS.has(s.key) || isAdmin)

  // ── 步骤状态 ──
  const [currentIdx, setCurrentIdx] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())

  const currentStep = visibleSteps[currentIdx]
  const isLastStep = currentIdx === visibleSteps.length - 1

  // ── Step 1: 语言 ──
  const [selectedLang, setSelectedLang] = useState<Lang>(DEFAULT_LANG)

  // ── Step 2 (admin): 实例默认设置 ──
  const [instanceLang, setInstanceLang] = useState('zh')
  const [instanceCredit, setInstanceCredit] = useState(0)
  const [instanceFileQuota, setInstanceFileQuota] = useState(100)
  const [instanceConcurrency, setInstanceConcurrency] = useState(3)
  const [instanceDefaultsLoaded, setInstanceDefaultsLoaded] = useState(false)

  // ── Step 3: 个人资料 ──
  const [bio, setBio] = useState('')
  const [statusText, setStatusText] = useState('')
  const [statusColor, setStatusColor] = useState('#6366f1')
  const [avatarFile, setAvatarFile] = useState<File | null>(null)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 清理 preview URL
  useEffect(() => {
    return () => {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview)
    }
  }, [avatarPreview])

  // ── Step 4: API 配置 ──
  const [apiBaseUrl, setApiBaseUrl] = useState('https://api.deepseek.com')
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)

  // ── Step 5: 创建 AI ──
  const [aiName, setAiName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [configProfile, setConfigProfile] = useState('chat')

  // ── Step 6 (admin): SMTP ──
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState(587)
  const [smtpUsername, setSmtpUsername] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpFromEmail, setSmtpFromEmail] = useState('')
  const [smtpFromName, setSmtpFromName] = useState('AIsChat')
  const [smtpUseTls, setSmtpUseTls] = useState(true)

  // ── Step 7 (admin): Key 池 ──
  const [poolKeyName, setPoolKeyName] = useState('')
  const [poolKey, setPoolKey] = useState('')
  const [poolKeyBaseUrl, setPoolKeyBaseUrl] = useState('https://api.deepseek.com')

  // ── 加载实例默认设置 ──
  useEffect(() => {
    if (!isAdmin || instanceDefaultsLoaded) return
    api.get('/admin/system-settings').then((r: any) => {
      setInstanceLang(r.default_language || 'zh')
      setInstanceCredit(r.default_platform_credit ?? 0)
      setInstanceFileQuota(r.default_file_quota_mb ?? 100)
      setInstanceConcurrency(r.default_concurrent_ai_limit ?? 3)
      setInstanceDefaultsLoaded(true)
    }).catch(() => {})
  }, [isAdmin, instanceDefaultsLoaded])

  // ── 各步骤是否已修改 ──
  const stepModified: Record<string, boolean> = {
    language:         true, // canAutoSkip
    instanceDefaults: true, // canAutoSkip
    profile:          !!bio || !!statusText || !!avatarFile,
    apiConfig:        !!apiKey,
    createAI:         !!aiName.trim(),
    smtp:             !!smtpHost,
    keyPool:          !!poolKey,
  }

  // ── 保存当前步骤 ──
  const saveCurrentStep = async (): Promise<void> => {
    const step = currentStep.key
    setError('')

    if (step === 'language') {
      await api.patch('/auth/language', { language: selectedLang })
    }

    if (step === 'instanceDefaults' && isAdmin) {
      await api.put('/admin/system-settings', {
        default_language: instanceLang,
        default_platform_credit: instanceCredit,
        default_file_quota_mb: instanceFileQuota,
        default_concurrent_ai_limit: instanceConcurrency,
      })
    }

    if (step === 'profile') {
      // 先上传头像（如果有新文件），上传端点会自动更新 user.avatar_url
      if (avatarFile) {
        setAvatarUploading(true)
        try {
          await api.upload('/user/avatar', avatarFile)
        } finally {
          setAvatarUploading(false)
        }
      }
      // 保存 bio / status（头像已在上传时保存，不重复传）
      await api.put('/user/settings', {
        bio: bio || null,
        status_text: statusText || null,
        status_color: statusColor,
      })
    }

    if (step === 'apiConfig') {
      await api.put('/user/settings', {
        api_base_url: apiBaseUrl || 'https://api.deepseek.com',
        api_key: apiKey || null,
      })
    }

    if (step === 'createAI' && aiName.trim()) {
      await api.post('/agents', {
        name: aiName.trim(),
        system_prompt: systemPrompt || null,
        config_profile: configProfile,
      })
    }

    if (step === 'smtp' && isAdmin && smtpHost) {
      await api.put('/admin/smtp-config', {
        host: smtpHost,
        port: smtpPort,
        username: smtpUsername,
        password: smtpPassword || null,
        from_email: smtpFromEmail,
        from_name: smtpFromName,
        use_tls: smtpUseTls,
      })
    }

    if (step === 'keyPool' && isAdmin && poolKey) {
      await api.post('/admin/api-key-pool', {
        name: poolKeyName || '默认池 Key',
        api_base_url: poolKeyBaseUrl || 'https://api.deepseek.com',
        api_key: poolKey,
      })
    }
  }

  // ── 下一步 / 完成 ──
  const handleNext = async () => {
    setSaving(true)
    try {
      await saveCurrentStep()
      setCompletedSteps(prev => new Set([...prev, currentStep.key]))

      if (isLastStep) {
        await api.post('/auth/setup', { language: selectedLang })
        await refreshUser()
        navigate('/chat', { replace: true })
      } else {
        setCurrentIdx(prev => prev + 1)
      }
    } catch (err: any) {
      setError(err?.detail || err?.message || t('common.error'))
    } finally {
      setSaving(false)
    }
  }

  // ── 上一步 ──
  const handleBack = () => {
    if (currentIdx > 0) {
      setCurrentIdx(prev => prev - 1)
    }
  }

  // ── 语言选择 ──
  const handleSelectLang = (lang: Lang) => {
    setSelectedLang(lang)
    overrideLangForSetup(lang)
  }

  // ── 头像选择 ──
  const handleAvatarSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)) {
      setError(t('me.avatarTypeError') || '仅支持 JPEG/PNG/GIF/WebP')
      return
    }
    setAvatarFile(file)
    const url = URL.createObjectURL(file)
    setAvatarPreview(url)
  }

  // ── 每个步骤的按钮逻辑 ──
  const canAutoSkip = currentStep.key === 'language' || currentStep.key === 'instanceDefaults' || currentStep.key === 'complete'
  const isModified = stepModified[currentStep.key] ?? false
  const showSkipLabel = !canAutoSkip && !isModified

  // ── 步骤指示条 ──
  const renderStepBar = () => (
    <div className="flex items-center justify-center gap-0 mb-8 overflow-x-auto px-2">
      {visibleSteps.map((s, idx) => {
        const isCurrent = idx === currentIdx
        const isCompleted = completedSteps.has(s.key) || idx < currentIdx
        const Icon = s.icon
        return (
          <div key={s.key} className="flex items-center">
            {/* 步骤圆点 */}
            <div className="flex flex-col items-center gap-1 min-w-0">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 transition-all duration-300 ${
                isCompleted
                  ? 'bg-mint-400 text-white shadow-sm shadow-mint-400/30'
                  : isCurrent
                    ? 'bg-primary-500 text-white shadow-sm shadow-primary-500/30 ring-2 ring-primary-500/30'
                    : 'bg-border text-textMuted'
              }`}>
                {isCompleted ? <Check size={14} /> : <Icon size={14} />}
              </div>
              <span className={`text-[10px] whitespace-nowrap px-1 transition-colors ${
                isCurrent ? 'text-textPrimary font-medium' : 'text-textMuted'
              }`}>
                {t(s.labelKey)}
              </span>
            </div>
            {/* 连接线 */}
            {idx < visibleSteps.length - 1 && (
              <div className={`w-6 md:w-10 h-0.5 mx-1 rounded transition-colors ${
                idx < currentIdx ? 'bg-mint-400' : 'bg-border'
              }`} />
            )}
          </div>
        )
      })}
    </div>
  )

  // ── 渲染各步骤 ──
  const renderStep = () => {
    const key = currentStep.key

    // ═══ Step 1: 语言 ═══
    if (key === 'language') {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Globe size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step1Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step1Desc')}</p>
          <div className="space-y-3">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => handleSelectLang(l.code)}
                className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all duration-200 ${
                  selectedLang === l.code
                    ? 'border-primary-400 bg-primary-500/10 shadow-sm shadow-primary-500/10'
                    : 'border-border hover:border-borderHover bg-canvas'
                }`}
              >
                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                  selectedLang === l.code ? 'border-primary-400 bg-primary-400' : 'border-border'
                }`}>
                  {selectedLang === l.code && <Check size={12} className="text-white" />}
                </div>
                <div>
                  <div className="text-sm font-medium text-textPrimary">{l.nativeName}</div>
                  <div className="text-xs text-textMuted">{t(l.i18nKey)}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )
    }

    // ═══ Step 2 (admin): 实例默认设置 ═══
    if (key === 'instanceDefaults' && isAdmin) {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Server size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step2Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step2Desc')}</p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.instanceDefaultLang')}</label>
              <div className="flex gap-2">
                {LANGUAGES.map(l => (
                  <button
                    key={l.code}
                    onClick={() => setInstanceLang(l.code)}
                    className={`flex-1 py-2.5 rounded-xl border-2 text-sm font-medium transition-all ${
                      instanceLang === l.code
                        ? 'border-primary-400 bg-primary-500/10 text-textPrimary'
                        : 'border-border bg-canvas text-textSecondary hover:border-borderHover'
                    }`}
                  >
                    {l.nativeName}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.instanceDefaultCredit')}</label>
              <input
                type="number" min={0}
                value={instanceCredit}
                onChange={e => setInstanceCredit(parseInt(e.target.value) || 0)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.instanceDefaultFileQuota')}</label>
              <input
                type="number" min={1}
                value={instanceFileQuota}
                onChange={e => setInstanceFileQuota(parseInt(e.target.value) || 1)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.instanceDefaultConcurrency')}</label>
              <input
                type="number" min={1} max={20}
                value={instanceConcurrency}
                onChange={e => setInstanceConcurrency(parseInt(e.target.value) || 3)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
          </div>
        </div>
      )
    }

    // ═══ Step 3: 个人资料 ═══
    if (key === 'profile') {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <User size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step3Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step3Desc')}</p>

          {/* 头像 */}
          <div className="mb-5">
            <label className="block text-sm font-medium text-textSecondary mb-2">{t('setup.avatar')}</label>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={avatarUploading}
              className="w-20 h-20 rounded-full bg-canvas border-2 border-dashed border-border hover:border-primary-400 flex items-center justify-center overflow-hidden transition-colors"
            >
              {avatarUploading ? (
                <Loader2 size={20} className="animate-spin text-textMuted" />
              ) : avatarPreview ? (
                <img src={avatarPreview} alt="avatar" className="w-full h-full object-cover" />
              ) : (
                <div className="flex flex-col items-center gap-0.5 text-textMuted">
                  <Upload size={16} />
                  <span className="text-[10px]">{t('setup.avatarUpload')}</span>
                </div>
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file" accept="image/jpeg,image/png,image/gif,image/webp"
              className="hidden"
              onChange={handleAvatarSelect}
            />
          </div>

          {/* Bio */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.bio')}</label>
            <textarea
              value={bio}
              onChange={e => setBio(e.target.value)}
              placeholder={t('setup.bioPlaceholder')}
              rows={3}
              className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none resize-none"
            />
          </div>

          {/* 状态文字 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.statusText')}</label>
            <input
              value={statusText}
              onChange={e => setStatusText(e.target.value)}
              placeholder={t('setup.statusTextPlaceholder')}
              maxLength={100}
              className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
            />
          </div>

          {/* 状态颜色 */}
          <div>
            <label className="block text-sm font-medium text-textSecondary mb-2">{t('setup.statusColor')}</label>
            <div className="flex gap-2 flex-wrap">
              {PRESET_COLORS.map(c => (
                <button
                  key={c}
                  onClick={() => setStatusColor(c)}
                  className={`w-7 h-7 rounded-full border-2 transition-all ${
                    statusColor === c ? 'border-textPrimary scale-110 shadow-sm' : 'border-transparent'
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
              <label className="w-7 h-7 rounded-full border-2 border-dashed border-border flex items-center justify-center cursor-pointer hover:border-primary-400 transition-colors">
                <Palette size={12} className="text-textMuted" />
                <input
                  type="color"
                  value={statusColor}
                  onChange={e => setStatusColor(e.target.value)}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        </div>
      )
    }

    // ═══ Step 4: API 配置 ═══
    if (key === 'apiConfig') {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Key size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step4Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step4Desc')}</p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.apiBaseUrl')}</label>
              <input
                value={apiBaseUrl}
                onChange={e => setApiBaseUrl(e.target.value)}
                placeholder={t('setup.apiBaseUrlPlaceholder')}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.apiKey')}</label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder={t('setup.apiKeyPlaceholder')}
                  className="w-full px-3.5 py-2.5 pr-10 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
                />
                <button
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-textMuted hover:text-textSecondary"
                >
                  {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            {!apiKey && (
              <p className="text-xs text-textMuted italic">{t('setup.apiSkip')}</p>
            )}
          </div>
        </div>
      )
    }

    // ═══ Step 5: 创建 AI ═══
    if (key === 'createAI') {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Bot size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step5Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step5Desc')}</p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.aiName')}</label>
              <input
                value={aiName}
                onChange={e => setAiName(e.target.value)}
                placeholder={t('setup.aiNamePlaceholder')}
                maxLength={50}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.systemPrompt')}</label>
              <textarea
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
                placeholder={t('setup.systemPromptPlaceholder')}
                rows={4}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none resize-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.configProfile')}</label>
              <div className="flex gap-2">
                {(['chat', 'immersive', 'digital_life'] as const).map(profile => (
                  <button
                    key={profile}
                    onClick={() => setConfigProfile(profile)}
                    className={`flex-1 py-2.5 rounded-xl border-2 text-sm font-medium transition-all ${
                      configProfile === profile
                        ? 'border-primary-400 bg-primary-500/10 text-textPrimary'
                        : 'border-border bg-canvas text-textSecondary hover:border-borderHover'
                    }`}
                  >
                    {t(`setup.configProfile${profile === 'chat' ? 'Chat' : profile === 'immersive' ? 'Immersive' : 'DigitalLife'}`)}
                  </button>
                ))}
              </div>
            </div>
            {!aiName.trim() && (
              <p className="text-xs text-textMuted italic">{t('setup.skipAI')}</p>
            )}
          </div>
        </div>
      )
    }

    // ═══ Step 6 (admin): SMTP ═══
    if (key === 'smtp' && isAdmin) {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Mail size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step6Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step6Desc')}</p>
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpHost')}</label>
                <input
                  value={smtpHost}
                  onChange={e => setSmtpHost(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
                />
              </div>
              <div className="w-24">
                <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpPort')}</label>
                <input
                  type="number"
                  value={smtpPort}
                  onChange={e => setSmtpPort(parseInt(e.target.value) || 587)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpUsername')}</label>
              <input
                value={smtpUsername}
                onChange={e => setSmtpUsername(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpPassword')}</label>
              <input
                type="password"
                value={smtpPassword}
                onChange={e => setSmtpPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpFromEmail')}</label>
                <input
                  value={smtpFromEmail}
                  onChange={e => setSmtpFromEmail(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
                />
              </div>
              <div className="flex-1">
                <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.smtpFromName')}</label>
                <input
                  value={smtpFromName}
                  onChange={e => setSmtpFromName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-textSecondary cursor-pointer">
              <input
                type="checkbox"
                checked={smtpUseTls}
                onChange={e => setSmtpUseTls(e.target.checked)}
                className="w-4 h-4 rounded border-border accent-primary-500"
              />
              {t('setup.smtpUseTls')}
            </label>
            {!smtpHost && (
              <p className="text-xs text-textMuted italic">{t('setup.skipSmtp')}</p>
            )}
          </div>
        </div>
      )
    }

    // ═══ Step 7 (admin): Key 池 ═══
    if (key === 'keyPool' && isAdmin) {
      return (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Shield size={20} className="text-primary-400" />
            <h2 className="text-lg font-semibold text-textPrimary">{t('setup.step7Title')}</h2>
          </div>
          <p className="text-sm text-textMuted mb-6">{t('setup.step7Desc')}</p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.keyPoolName')}</label>
              <input
                value={poolKeyName}
                onChange={e => setPoolKeyName(e.target.value)}
                placeholder={t('setup.keyPoolName')}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.keyPoolBaseUrl')}</label>
              <input
                value={poolKeyBaseUrl}
                onChange={e => setPoolKeyBaseUrl(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-textSecondary mb-1.5">{t('setup.keyPoolKey')}</label>
              <input
                type="password"
                value={poolKey}
                onChange={e => setPoolKey(e.target.value)}
                placeholder={t('setup.keyPoolKey')}
                className="w-full px-3.5 py-2.5 rounded-xl bg-canvas border border-border text-textPrimary text-sm focus:border-primary-400 focus:outline-none"
              />
            </div>
            {!poolKey && (
              <p className="text-xs text-textMuted italic">{t('setup.skipKeyPool')}</p>
            )}
          </div>
        </div>
      )
    }

    // ═══ 完成页 ═══
    if (key === 'complete') {
      return (
        <div className="text-center py-6">
          <div className="w-16 h-16 rounded-full bg-mint-400/20 flex items-center justify-center mx-auto mb-4">
            <Sparkles size={32} className="text-mint-400" />
          </div>
          <h2 className="text-xl font-bold text-textPrimary mb-2">{t('setup.stepCompleteTitle')}</h2>
          <p className="text-sm text-textMuted max-w-xs mx-auto">{t('setup.stepCompleteDesc')}</p>
        </div>
      )
    }

    return null
  }

  // ── 渲染 ──
  return (
    <div className="h-full flex items-center justify-center bg-canvas overflow-y-auto">
      <div className="max-w-lg w-full px-4 py-8">
        {/* 标题 */}
        <h1 className="text-xl font-bold text-textPrimary text-center mb-6">{t('setup.title')}</h1>

        {/* 步骤条 */}
        {renderStepBar()}

        {/* 内容卡片 */}
        <div className="bg-surface border border-border rounded-2xl p-5 md:p-6 shadow-xl">
          {renderStep()}

          {/* 错误提示 */}
          {error && (
            <div className="mt-4 text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3.5 py-2.5">
              {error}
            </div>
          )}

          {/* 导航按钮（完成页不显示按钮，由 handleNext 直接跳转） */}
          {currentStep.key !== 'complete' && (
            <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
              <button
                onClick={handleBack}
                disabled={currentIdx === 0 || saving}
                className="flex items-center gap-1 px-4 py-2 rounded-xl border border-border text-sm text-textSecondary hover:bg-canvas disabled:opacity-30 transition-colors"
              >
                <ChevronLeft size={16} />
                {t('setup.back')}
              </button>

              <div className="flex items-center gap-2">
                {/* 跳过按钮 */}
                {showSkipLabel && (
                  <button
                    onClick={handleNext}
                    className="px-4 py-2 rounded-xl text-sm text-textMuted hover:text-textSecondary hover:bg-canvas transition-colors"
                  >
                    {t('setup.skip')}
                  </button>
                )}

                {/* 下一步按钮 */}
                <button
                  onClick={handleNext}
                  disabled={saving}
                  className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-primary-500 hover:bg-primary-400 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-all shadow-lg shadow-primary-500/20"
                >
                  {saving ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 size={14} className="animate-spin" />
                      <span>{t('common.saving') || '保存中...'}</span>
                    </span>
                  ) : (
                    <>
                      {t('setup.next')}
                      <ChevronRight size={16} />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* 完成页按钮 */}
          {currentStep.key === 'complete' && (
            <button
              onClick={handleNext}
              disabled={saving}
              className="w-full mt-6 py-3 rounded-xl bg-mint-400 hover:bg-mint-500 disabled:opacity-40 text-white font-semibold text-sm transition-all shadow-lg shadow-mint-400/20"
            >
              {saving ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  {t('common.saving') || '处理中...'}
                </span>
              ) : (
                t('setup.complete')
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
