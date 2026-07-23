/**
 * 状态文字颜色工具 — 与父容器背景色计算 WCAG 对比度，
 * 对比度 < 4.5:1 时自动追加文字辉光保证可读性。
 */

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!m) return null
  return {
    r: parseInt(m[1], 16),
    g: parseInt(m[2], 16),
    b: parseInt(m[3], 16),
  }
}

function linearize(c: number): number {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
}

function relativeLuminance(r: number, g: number, b: number): number {
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
}

function contrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * 获取状态文字的 React 样式
 * @param textColor  用户选的状态文字颜色 (hex)
 * @param bgColor    父容器背景色 (hex，如 '#1f2937' 或 '#f9fafb')
 */
export function getStatusTextStyle(
  textColor: string,
  bgColor: string,
): React.CSSProperties {
  const fgRgb = hexToRgb(textColor)
  const bgRgb = hexToRgb(bgColor)
  if (!fgRgb || !bgRgb) return { color: textColor }

  const fgLum = relativeLuminance(fgRgb.r, fgRgb.g, fgRgb.b)
  const bgLum = relativeLuminance(bgRgb.r, bgRgb.g, bgRgb.b)
  const ratio = contrastRatio(bgLum, fgLum)

  if (ratio < 4.5) {
    // 背景偏暗 → 白色辉光；背景偏亮 → 黑色辉光
    const glowColor = bgLum < 0.5
      ? 'rgba(255,255,255,0.4)'
      : 'rgba(0,0,0,0.3)'
    return {
      color: textColor,
      textShadow: `0 0 4px ${glowColor}, 0 0 1px ${glowColor}`,
    }
  }

  return { color: textColor }
}

/** 浅色背景典型 hex（Tailwind gray-50） */
export const BG_LIGHT = '#f9fafb'
/** 深色背景典型 hex（Tailwind gray-900） */
export const BG_DARK = '#111827'
/** 表面卡片浅色 — 对应 bg-surface light: #ffffff */
export const BG_SURFACE_LIGHT = '#ffffff'
/** 表面卡片深色 — 对应 bg-surface dark: #151223 */
export const BG_SURFACE_DARK = '#151223'
/** 浮层卡片浅色 — 对应 bg-elevated light: #ffffff */
export const BG_ELEVATED_LIGHT = '#ffffff'
/** 浮层卡片深色 — 对应 bg-elevated dark: #1e1a30 */
export const BG_ELEVATED_DARK = '#1e1a30'
/** 画布浅色 — 对应 bg-canvas light: #f8fafc */
export const BG_CANVAS_LIGHT = '#f8fafc'
/** 画布深色 — 对应 bg-canvas dark: #0c0a14 */
export const BG_CANVAS_DARK = '#0c0a14'

/** 预设颜色选项 */
export const STATUS_COLORS = [
  { value: '', label: '默认' },
  { value: '#ef4444', label: '红' },
  { value: '#f97316', label: '橙' },
  { value: '#eab308', label: '黄' },
  { value: '#22c55e', label: '绿' },
  { value: '#06b6d4', label: '青' },
  { value: '#3b82f6', label: '蓝' },
  { value: '#8b5cf6', label: '紫' },
  { value: '#ec4899', label: '粉' },
] as const
