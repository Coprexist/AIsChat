/**
 * 皮肤应用 — 皮肤插件（category=skin）把 light/dark 两套变量覆盖到 CSS
 *
 * 设计（统一插件系统 2026-08-17）：
 * - 皮肤变量 key 与 theme_colors 一致（primary_400…rose_500 + bubble），
 *   应用时转成 --tw-* CSS 变量（bubble → --tw-bubble）
 * - inline style 只能存一份值 → 按当前主题模式（light/dark）应用对应套；
 *   主题切换时上层必须重新调用 applySkin（AuthContext 依赖 theme 重新应用）
 * - 皮肤最后应用（覆盖用户自选色之上）；clearSkin 后自选色自然恢复
 */
import { hexToRgbTriplet } from './userTheme'

export interface SkinVars {
  light: Record<string, string>
  dark: Record<string, string>
}

export interface PluginView {
  id: string
  name: string
  description: string
  category: string
  version: string
  author: string
  icon: string
  builtin: boolean
  global_enabled: boolean
  user_enabled: boolean
  effective: boolean
  is_admin: boolean
  skin_vars: SkinVars
}

/** key（primary_500 / bubble）→ CSS 变量名（--tw-primary-500 / --tw-bubble） */
export function skinVarName(key: string): string {
  return key.startsWith('--') ? key : '--tw-' + key.replace(/_/g, '-')
}

let _appliedSkinId: string | null = null
let _appliedVars: string[] = []

/** 应用皮肤（mode 由调用方按当前主题传入；无皮肤或空变量 = 清除） */
export function applySkin(skinId: string | null, vars: SkinVars | undefined, isDark: boolean) {
  clearSkin()
  if (!skinId || !vars) return
  const set = (isDark ? vars.dark : vars.light) || {}
  const root = document.documentElement
  const applied: string[] = []
  for (const [key, hex] of Object.entries(set)) {
    const triplet = hexToRgbTriplet(hex)
    if (!triplet) continue
    root.style.setProperty(skinVarName(key), triplet)
    applied.push(skinVarName(key))
  }
  _appliedSkinId = skinId
  _appliedVars = applied
}

/** 清除当前皮肤（恢复默认/自选色） */
export function clearSkin() {
  if (_appliedVars.length === 0) return
  const root = document.documentElement
  for (const v of _appliedVars) root.style.removeProperty(v)
  _appliedSkinId = null
  _appliedVars = []
}

export function getAppliedSkinId(): string | null {
  return _appliedSkinId
}
