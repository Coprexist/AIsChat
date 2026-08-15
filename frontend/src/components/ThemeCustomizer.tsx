import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import { RotateCcw, Check } from 'lucide-react'
import {
  THEME_COLOR_KEYS, THEME_COLORS_PREF_KEY, applyUserTheme,
  getEffectiveThemeColors, themeVarName, hexToRgbTriplet,
  type ThemeColorKey,
} from '../utils/userTheme'

/**
 * 主题定制 — 用户个性化主色（为个性化铺路，2026-08-13）
 * - 选色即时生效（applyUserTheme 覆盖 CSS 变量）
 * - 点「保存」持久化到 ui_prefs.theme_colors
 * - 点「恢复默认」清空（后端删除该键）
 */

// 每个 key 的候选色板（与默认主题协调的色系）
const CANDIDATES: Record<ThemeColorKey, { hex: string; label: string }[]> = {
  primary_400: [
    { hex: '#8B5CF6', label: 'violet-500' },
    { hex: '#7C3AED', label: 'violet-600' },
    { hex: '#A78BFA', label: 'violet-400' },
    { hex: '#9B7BFA', label: '亮紫' },
    { hex: '#7E69EA', label: '柔和紫' },
    { hex: '#6D28D9', label: 'violet-700' },
    { hex: '#6366F1', label: 'indigo-500' },
  ],
  primary_500: [
    { hex: '#8B5CF6', label: '当前' },
    { hex: '#7C3AED', label: 'violet-600' },
    { hex: '#A78BFA', label: '更亮' },
    { hex: '#9B7BFA', label: '明亮紫' },
    { hex: '#7E69EA', label: '柔和' },
    { hex: '#6D28D9', label: '深紫' },
    { hex: '#6366F1', label: 'indigo-500' },
  ],
  primary_600: [
    { hex: '#7C3AED', label: '当前' },
    { hex: '#6D28D9', label: 'violet-700' },
    { hex: '#8B5CF6', label: '浅一档' },
    { hex: '#5B21B6', label: 'violet-800' },
  ],
  accent_400: [
    { hex: '#F59E0B', label: 'amber-500' },
    { hex: '#FBBF24', label: 'amber-400' },
    { hex: '#F0A020', label: '暖金' },
    { hex: '#E8972C', label: '柔和金' },
    { hex: '#D97706', label: 'amber-600' },
    { hex: '#FACC15', label: '鲜黄' },
  ],
  accent_500: [
    { hex: '#D97706', label: '当前' },
    { hex: '#F59E0B', label: 'amber-500' },
    { hex: '#E8972C', label: '柔和' },
    { hex: '#B45309', label: 'amber-700' },
    { hex: '#C2710A', label: '深金' },
  ],
  mint_400: [
    { hex: '#22C55E', label: 'green-500' },
    { hex: '#10B981', label: 'emerald-500' },
    { hex: '#34D399', label: 'emerald-400' },
    { hex: '#14B8A6', label: 'teal-500' },
    { hex: '#059669', label: 'emerald-600' },
    { hex: '#2DD4BF', label: 'teal-400' },
  ],
  mint_500: [
    { hex: '#059669', label: '当前' },
    { hex: '#10B981', label: 'emerald-500' },
    { hex: '#047857', label: 'emerald-700' },
    { hex: '#0D9488', label: 'teal-600' },
  ],
  rose_400: [
    { hex: '#E84A69', label: '当前亮玫红' },
    { hex: '#E11D48', label: 'rose-600' },
    { hex: '#C9364F', label: '暗玫红' },
    { hex: '#DC2626', label: 'red-600' },
    { hex: '#E11D48', label: 'rose-600' },
    { hex: '#F26D8D', label: '亮粉' },
    { hex: '#A8283F', label: '深玫红' },
  ],
  rose_500: [
    { hex: '#E11D48', label: '当前' },
    { hex: '#BE123C', label: 'rose-700' },
    { hex: '#A8283F', label: '暗玫红' },
    { hex: '#DC2626', label: 'red-600' },
    { hex: '#C9364F', label: '玫红' },
  ],
}

const KEY_LABELS: Record<ThemeColorKey, string> = {
  primary_400: '主色 · 强调文字/图标',
  primary_500: '主色 · 按钮背景',
  primary_600: '主色 · 按钮 hover',
  accent_400: '琥珀金 · 状态/徽章',
  accent_500: '琥珀金 · 实底按钮',
  mint_400: '活跃绿 · 在线/成功',
  mint_500: '活跃绿 · 实底按钮',
  rose_400: '危险玫红 · 文字',
  rose_500: '危险玫红 · 按钮',
}

export default function ThemeCustomizer() {
  const t = useT()
  const { user, refreshUser } = useAuth()
  const [colors, setColors] = useState<Partial<Record<ThemeColorKey, string>>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)

  // 加载：默认 = 当前生效值；用户已存 = 覆盖
  useEffect(() => {
    const eff = getEffectiveThemeColors()
    const savedColors = (user?.ui_prefs?.[THEME_COLORS_PREF_KEY] as Record<string, string> | undefined) || {}
    const merged = {} as Partial<Record<ThemeColorKey, string>>
    for (const key of THEME_COLOR_KEYS) {
      merged[key] = savedColors[key] || eff[key] || ''
    }
    setColors(merged)
    setDirty(false)
    // 应用已存主题（确保进入页面即生效）
    applyUserTheme(savedColors)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  const pick = (key: ThemeColorKey, hex: string) => {
    setColors(prev => ({ ...prev, [key]: hex }))
    setDirty(true)
    // 即时预览：临时覆盖该变量
    document.documentElement.style.setProperty(themeVarName(key), hexToRgbTriplet(hex))
  }

  const previewColors = () => {
    // 用当前选择生成临时对象并整体应用（预览）
    const merged = {} as Record<string, string>
    for (const key of THEME_COLOR_KEYS) {
      const hex = colors[key]
      if (hex) merged[key] = hex
    }
    applyUserTheme(merged)
  }

  const save = async () => {
    setSaving(true)
    try {
      const themeColors = {} as Record<string, string>
      for (const key of THEME_COLOR_KEYS) {
        const hex = colors[key]
        if (hex) themeColors[key] = hex
      }
      const ui_prefs = { ...(user?.ui_prefs || {}), [THEME_COLORS_PREF_KEY]: themeColors }
      await api.put('/user/settings', { ui_prefs })
      await refreshUser()
      applyUserTheme(themeColors)
      setSaved(true)
      setDirty(false)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: any) {
      console.error('保存主题失败', err)
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    setSaving(true)
    try {
      // 清空已存主题 → 恢复默认
      const ui_prefs = { ...(user?.ui_prefs || {}) }
      delete ui_prefs[THEME_COLORS_PREF_KEY]
      await api.put('/user/settings', { ui_prefs })
      await refreshUser()
      applyUserTheme(null)
      const eff = getEffectiveThemeColors()
      setColors(eff as Partial<Record<ThemeColorKey, string>>)
      setDirty(false)
    } catch (err: any) {
      console.error('恢复默认失败', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-medium text-textPrimary">{t('settings.themeCustom')}</p>
        <div className="flex items-center gap-2">
          {dirty && <span className="text-[10px] text-accent-500">未保存</span>}
          {saved && <span className="text-[10px] text-mint-400 flex items-center gap-0.5"><Check size={11} /> 已保存</span>}
        </div>
      </div>
      <p className="text-xs text-textMuted mb-3">{t('settings.themeCustomDesc')}</p>

      <div className="space-y-4">
        {THEME_COLOR_KEYS.map((key) => (
          <div key={key}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-medium text-textSecondary">{KEY_LABELS[key]}</span>
              <span className="text-[10px] font-mono text-textMuted">{(colors[key] || '').toUpperCase()}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {CANDIDATES[key].map((c) => {
                const selected = (colors[key] || '').toLowerCase() === c.hex.toLowerCase()
                return (
                  <button
                    key={c.hex}
                    onClick={() => pick(key, c.hex)}
                    title={c.hex + ' · ' + c.label}
                    className={`w-8 h-8 rounded-lg transition-transform hover:scale-110 ${selected ? 'ring-2 ring-textPrimary ring-offset-1' : ''}`}
                    style={{ background: c.hex }}
                    aria-label={c.hex}
                  />
                )
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 mt-4">
        <button
          onClick={save}
          disabled={saving || !dirty}
          className="btn btn-md btn-primary disabled:opacity-40"
        >
          {saving ? '保存中…' : t('settings.saveTheme')}
        </button>
        <button
          onClick={reset}
          disabled={saving}
          className="btn btn-md btn-secondary"
        >
          <RotateCcw size={14} /> {t('settings.resetTheme')}
        </button>
      </div>
    </div>
  )
}
