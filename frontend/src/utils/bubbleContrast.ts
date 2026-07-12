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
    return [LINK_LIGHT, CODE_LIGHT, HR_LIGHT, TABLE_LIGHT].join(' ')
  }
  const lum = relativeLuminance(rgb.r, rgb.g, rgb.b)
  if (lum < 0.2) {
    return [LINK_DARK, CODE_DARK, HR_DARK, TABLE_DARK].join(' ')
  }
  return [LINK_LIGHT, CODE_LIGHT, HR_LIGHT, TABLE_LIGHT].join(' ')
}

// ═══════════════════════════════════════════════
// 深色背景样式（own bubble / 深色气泡）
// ═══════════════════════════════════════════════

const LINK_DARK = [
  '[&_a]:break-all',
  '[&_a]:text-white/85',
  '[&_a]:underline',
  '[&_a]:decoration-white/30',
  'hover:[&_a]:text-white',
  '[&_a]:transition-colors',
].join(' ')

const CODE_DARK = [
  '[&_code]:bg-white/15',
  '[&_code]:text-white',
  '[&_code]:px-1',
  '[&_code]:rounded',
  '[&_pre]:bg-black/20',
  '[&_pre_code]:bg-transparent',
].join(' ')

const HR_DARK = [
  '[&_hr]:border-0',
  '[&_hr]:h-px',
  '[&_hr]:bg-white/20',
  '[&_hr]:my-3',
].join(' ')

const TABLE_DARK = [
  // Wrapper 覆盖
  '[&_.markdown-table-wrapper]:my-0',
  '[&_.markdown-table-wrapper]:border-0',
  '[&_.markdown-table-wrapper]:rounded-none',
  '[&_.markdown-table-wrapper]:[scrollbar-color:rgba(255,255,255,0.25)_transparent]',
  // 表格自身（完整路径以覆盖 index.css .markdown-table-wrapper 样式）
  '[&_table]:w-full',
  '[&_table]:border-collapse',
  '[&_table]:rounded-lg',
  '[&_table]:overflow-hidden',
  // 单元格（使用 .markdown-table-wrapper 路径避免被 index.css 覆盖）
  '[&_.markdown-table-wrapper_thead_th]:text-white',
  '[&_.markdown-table-wrapper_tbody_td]:text-white/85',
  '[&_.markdown-table-wrapper_thead_th]:py-1.5',
  '[&_.markdown-table-wrapper_tbody_td]:py-1.5',
  '[&_.markdown-table-wrapper_thead_th]:px-3',
  '[&_.markdown-table-wrapper_tbody_td]:px-3',
  '[&_.markdown-table-wrapper_thead_th]:border',
  '[&_.markdown-table-wrapper_tbody_td]:border',
  '[&_.markdown-table-wrapper_thead_th]:border-white/20',
  '[&_.markdown-table-wrapper_tbody_td]:border-white/20',
  '[&_.markdown-table-wrapper_thead_th]:text-left',
  '[&_.markdown-table-wrapper_thead_th]:font-semibold',
  // 背景色（通过完整路径确保优先级高于 index.css）
  '[&_.markdown-table-wrapper_table]:bg-primary-700/30',
  '[&_.markdown-table-wrapper_thead_th]:bg-primary-700/40',
  '[&_.markdown-table-wrapper_tbody_tr:nth-child(even)]:bg-primary-700/20',
  // 悬停由 index.css 统一处理
].join(' ')

// ═══════════════════════════════════════════════
// 浅色背景样式（对方气泡 / 默认）
// ═══════════════════════════════════════════════

const LINK_LIGHT = [
  '[&_a]:break-all',
  '[&_a]:text-primary-500',
  'dark:[&_a]:text-primary-400',
  '[&_a]:underline',
  'hover:[&_a]:text-primary-400',
  'dark:hover:[&_a]:text-primary-300',
  '[&_a]:transition-colors',
].join(' ')

const CODE_LIGHT = ''

const HR_LIGHT = [
  '[&_hr]:border-0',
  '[&_hr]:h-px',
  '[&_hr]:bg-border',
  '[&_hr]:my-3',
].join(' ')

const TABLE_LIGHT = [
  // Wrapper 覆盖
  '[&_.markdown-table-wrapper]:my-0',
  '[&_.markdown-table-wrapper]:border-0',
  '[&_.markdown-table-wrapper]:rounded-none',
  // 表格自身（完整路径以覆盖 index.css）
  '[&_table]:w-full',
  '[&_table]:border-collapse',
  '[&_table]:rounded-lg',
  '[&_table]:overflow-hidden',
  // 单元格
  '[&_.markdown-table-wrapper_thead_th]:text-textPrimary',
  '[&_.markdown-table-wrapper_tbody_td]:text-textSecondary',
  '[&_.markdown-table-wrapper_thead_th]:py-1.5',
  '[&_.markdown-table-wrapper_tbody_td]:py-1.5',
  '[&_.markdown-table-wrapper_thead_th]:px-3',
  '[&_.markdown-table-wrapper_tbody_td]:px-3',
  '[&_.markdown-table-wrapper_thead_th]:border',
  '[&_.markdown-table-wrapper_tbody_td]:border',
  '[&_.markdown-table-wrapper_thead_th]:border-border',
  '[&_.markdown-table-wrapper_tbody_td]:border-border',
  '[&_.markdown-table-wrapper_thead_th]:text-left',
  '[&_.markdown-table-wrapper_thead_th]:font-semibold',
  // 背景色
  '[&_.markdown-table-wrapper_table]:bg-surface',
  '[&_.markdown-table-wrapper_thead_th]:bg-canvas',
  '[&_.markdown-table-wrapper_tbody_tr:nth-child(even)]:bg-elevated',
  // 悬停由 index.css 统一处理
].join(' ')
