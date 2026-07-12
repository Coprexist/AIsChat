/**
 * 气泡文本对比度工具
 *
 * 运行时读取气泡 background-color，通过 CSS 变量注入适配样式。
 * 所有视觉样式集中在 index.css 中用 var(--b-*) 读取。
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

/** 返回 CSS 变量类名，设到气泡 div 上驱动 index.css 适配 */
export function getBubbleTextClasses(bgColor: string): string {
  const rgb = hexToRgb(bgColor)
  const dark = rgb && relativeLuminance(rgb.r, rgb.g, rgb.b) < 0.2

  // Tailwind 任意属性语法 [--var:val] → 在元素上设 CSS 变量
  return dark ? [
    // 链接
    '[--b-link:rgba(255,255,255,0.85)]',
    '[--b-link-hover:white]',
    '[--b-link-deco:rgba(255,255,255,0.3)]',
    // 行内代码
    '[--b-code-bg:rgba(255,255,255,0.15)]',
    '[--b-code-text:white]',
    // 代码块
    '[--b-pre-bg:rgba(0,0,0,0.2)]',
    // 分割线
    '[--b-hr:rgba(255,255,255,0.2)]',
    // 表头
    '[--b-thead-bg:#4C1D95]',
    '[--b-thead-text:white]',
    // 斑马纹
    '[--b-zebra-bg:rgba(91,33,182,0.35)]',
    // 滚动条
    '[--b-scrollbar:rgba(255,255,255,0.25)]',
  ].join(' ') : [
    // 链接（沿用 primary 色，深色模式按现有规则）
    '[--b-link:var(--tw-text-primary)]',
    '[--b-link-hover:#6366f1]',
    '[--b-link-deco:transparent]',
    // 行内代码（无覆盖，用默认）
    '[--b-code-bg:initial]',
    '[--b-code-text:initial]',
    // 代码块（无覆盖）
    '[--b-pre-bg:initial]',
    // 分割线
    '[--b-hr:var(--color-border)]',
    // 表头
    '[--b-thead-bg:#EDE9FE]',
    '[--b-thead-text:#111827]',
    // 斑马纹
    '[--b-zebra-bg:#F3F0FF]',
    // 滚动条（默认）
    '[--b-scrollbar:initial]',
  ].join(' ')
}
