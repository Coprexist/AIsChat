/**
 * 气泡文本对比度工具
 * 运行时读取气泡背景色，自动计算合适的链接/代码颜色。
 * 为未来用户自定义气泡颜色打下基础。
 */

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!m) return null
  return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) }
}

function linearize(c: number): number {
  const s = c / 255
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
}

function relativeLuminance(r: number, g: number, b: number): number {
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
}

/** 判断背景是深色还是浅色，返回对应的气泡文本 CSS 类 */
export function getBubbleTextClasses(bgColor: string): string {
  const rgb = hexToRgb(bgColor)
  if (!rgb) {
    // 解析失败 → 默认浅色背景样式
    return LINK_LIGHT + ' ' + CODE_LIGHT + ' ' + TABLE_LIGHT
  }
  const lum = relativeLuminance(rgb.r, rgb.g, rgb.b)
  // 亮度 < 0.2 视为深色背景
  if (lum < 0.2) {
    return LINK_DARK + ' ' + CODE_DARK + ' ' + TABLE_DARK
  }
  return LINK_LIGHT + ' ' + CODE_LIGHT + ' ' + TABLE_LIGHT
}

// ═══════════════════════════════════════════════════════════
// 深色背景样式（own bubble / 深色气泡）
// ═══════════════════════════════════════════════════════════

const LINK_DARK =
  '[&_a]:break-all [&_a]:text-white/85 [&_a]:underline [&_a]:decoration-white/30 hover:[&_a]:text-white [&_a]:transition-colors'
const CODE_DARK =
  '[&_code]:bg-white/15 [&_code]:text-white [&_code]:px-1 [&_code]:rounded [&_pre]:bg-black/20 [&_pre_code]:bg-transparent'
const TABLE_DARK =
  '[&_table]:w-full [&_table]:border-collapse [&_table]:my-1 [&_table_th]:text-white [&_table_td]:text-white/85 [&_table_th]:py-1.5 [&_table_td]:py-1.5 [&_table_th]:px-3 [&_table_td]:px-3 [&_table_th]:border-b [&_table_td]:border-b [&_table_th]:border-white/15 [&_table_td]:border-white/15 [&_table_th]:text-left [&_table_th]:font-semibold [&_table_th]:bg-white/10 [&_table_tr:nth-child(even)]:bg-white/5'

// ═══════════════════════════════════════════════════════════
// 浅色背景样式（对方气泡 / 默认）
// ═══════════════════════════════════════════════════════════

const LINK_LIGHT =
  '[&_a]:break-all [&_a]:text-primary-500 dark:[&_a]:text-primary-400 [&_a]:underline'
const CODE_LIGHT = ''
const TABLE_LIGHT =
  '[&_table]:w-full [&_table]:border-collapse [&_table]:my-1 [&_table_th]:text-textPrimary [&_table_td]:text-textSecondary [&_table_th]:py-1.5 [&_table_td]:py-1.5 [&_table_th]:px-3 [&_table_td]:px-3 [&_table_th]:border-b [&_table_td]:border-b [&_table_th]:border-border [&_table_td]:border-border [&_table_th]:text-left [&_table_th]:font-semibold [&_table_th]:bg-elevated [&_table_tr:nth-child(even)]:bg-canvas/50'
