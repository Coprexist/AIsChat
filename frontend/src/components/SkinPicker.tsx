import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import { type PluginView } from '../utils/skin'
import { Palette, Check } from 'lucide-react'

/**
 * 皮肤选择 — 设置页「皮肤」区块（统一插件系统 2026-08-17）
 * - 列出全部皮肤插件（管理员开放的才可启用）
 * - 一键启用/停用（POST /plugins/{id}/pref），启用即时应用，互斥由后端保证
 * - 皮肤变量最后应用，覆盖用户自选色；停用皮肤后自选色自然恢复
 */

// 预览用主色 key（light 套）
const PREVIEW_KEYS = ['primary_500', 'accent_500', 'mint_500', 'rose_500', 'bubble'] as const

export default function SkinPicker() {
  const t = useT()
  const [skins, setSkins] = useState<PluginView[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const res = await api.safe.get<{ plugins: PluginView[] }>('/plugins')
      if (res.ok) {
        setSkins((res.value?.plugins || []).filter((p) => p.category === 'skin'))
        setError('')
      } else {
        setError(String(res.error?.message || res.error))
      }
    } catch (e: any) {
      setError(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async (skin: PluginView) => {
    setToggling(skin.id)
    try {
      await api.post(`/plugins/${skin.id}/pref`, { enabled: !skin.user_enabled })
      await load()
      // 通知 AuthContext 统一应用链重算（启用即时应用；停用回退自选色/默认）
      window.dispatchEvent(new CustomEvent('plugins-changed'))
    } catch (e: any) {
      setError(e?.message || '操作失败')
    } finally {
      setToggling(null)
    }
  }

  const activeSkin = skins.find((s) => s.effective) || null

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-medium text-textPrimary flex items-center gap-1.5">
          <Palette size={14} className="text-primary-400" />
          {t('settings.skinTitle')}
        </p>
        {activeSkin && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-400/10 text-primary-400 border border-primary-400/20 flex items-center gap-0.5">
            <Check size={11} /> {activeSkin.name}
          </span>
        )}
      </div>
      <p className="text-xs text-textMuted mb-1">{t('settings.skinDesc')}</p>
      <p className="text-[11px] text-accent-500 mb-3">{t('settings.skinMutualExclusive')}</p>

      {loading ? (
        <p className="text-xs text-textMuted">{t('settings.loadingPlugins')}</p>
      ) : error ? (
        <p className="text-xs text-rose-400">{error}</p>
      ) : skins.length === 0 ? (
        <p className="text-xs text-textMuted">{t('settings.noSkins')}</p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {skins.map((skin) => {
            const light = skin.skin_vars?.light || {}
            const on = skin.effective
            const adminOff = !skin.global_enabled
            return (
              <div
                key={skin.id}
                className={`relative rounded-xl border p-3 transition-colors ${
                  on
                    ? 'border-mint-400/60 bg-mint-400/5 ring-1 ring-mint-400/30'
                    : 'border-border bg-surface'
                }`}
              >
                {on && (
                  <span className="absolute -top-2 left-3 px-2 py-0.5 rounded-full bg-mint-500 text-white text-[10px] font-medium flex items-center gap-0.5 shadow">
                    <Check size={10} /> {t('settings.skinInUse')}
                  </span>
                )}
                {/* 色板预览（light 主色） */}
                <div className="flex items-center gap-1.5 mb-2">
                  {PREVIEW_KEYS.map((k) => (
                    <span
                      key={k}
                      className="w-5 h-5 rounded-full ring-1 ring-white/20"
                      style={{ background: light[k] || '#888' }}
                      title={k}
                    />
                  ))}
                </div>
                <p className="text-sm font-medium text-textPrimary leading-tight">{skin.name}</p>
                <p className="text-[11px] text-textMuted mt-0.5 line-clamp-2 min-h-[2em]">{skin.description}</p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] font-mono text-textMuted">{skin.version}</span>
                  <button
                    onClick={() => toggle(skin)}
                    disabled={toggling === skin.id || adminOff}
                    className={`relative w-9 h-5 rounded-full transition-colors disabled:opacity-40 ${
                      on ? 'bg-mint-500' : 'bg-border'
                    }`}
                    title={adminOff ? t('settings.skinAdminOff') : (on ? t('settings.skinOff') : t('settings.skinOn'))}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
                  </button>
                </div>
                {adminOff && (
                  <p className="text-[10px] text-rose-400 mt-1">{t('settings.skinAdminOff')}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
