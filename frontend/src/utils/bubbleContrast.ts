/**
 * 气泡文本对比度工具
 *
 * 运行时读取气泡 background-color，通过 CSS 变量注入适配样式。
 * 所有颜色用空格分隔 RGB 格式（避免 Tailwind 解析逗号/括号出错）。
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

  // 使用空格分隔 RGB（无逗号/括号，Tailwind 解析无歧义）
  return dark ? [
    // 链接：白色半透明
    '[--b-link-r:255]',
    '[--b-link-g:255]',
    '[--b-link-b:255]',
    '[--b-link-a:0.85]',
    // 行内代码背景
    '[--b-code-r:255]',
    '[--b-code-g:255]',
    '[--b-code-b:255]',
    '[--b-code-a:0.15]',
    // 代码块背景
    '[--b-pre-r:0]',
    '[--b-pre-g:0]',
    '[--b-pre-b:0]',
    '[--b-pre-a:0.2]',
    // 分割线
    '[--b-hr-r:255]',
    '[--b-hr-g:255]',
    '[--b-hr-b:255]',
    '[--b-hr-a:0.2]',
    // 表头背景
    '[--b-thead-r:76]',
    '[--b-thead-g:29]',
    '[--b-thead-b:149]',
    '[--b-thead-a:1]',
    // 斑马纹
    '[--b-zebra-r:91]',
    '[--b-zebra-g:33]',
    '[--b-zebra-b:182]',
    '[--b-zebra-a:0.35]',
  ].join(' ') : [
    // 浅色气泡：不设覆盖（回退到 index.css 默认值）
    '[--b-link-r:initial]',
    '[--b-link-g:initial]',
    '[--b-link-b:initial]',
    '[--b-link-a:initial]',
    '[--b-thead-r:237]',
    '[--b-thead-g:233]',
    '[--b-thead-b:254]',
    '[--b-thead-a:1]',
    '[--b-zebra-r:243]',
    '[--b-zebra-g:240]',
    '[--b-zebra-b:255]',
    '[--b-zebra-a:1]',
    // 清除深色模式的覆盖
    '[--b-code-r:initial]',
    '[--b-pre-r:initial]',
    '[--b-hr-r:initial]',
  ].join(' ')
}
