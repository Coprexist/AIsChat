/**
 * rehype-color-text — 将气泡内 <span class="text-xxx"> 转换为内联 color 样式
 *
 * 用法：在 rehypeRaw 之后、rehypeSanitize 之前插入
 *
 * ```tsx
 * import { rehypeColorText } from '../utils/rehypeColorText'
 *
 * <Markdown rehypePlugins={[rehypeRaw, rehypeColorText(map), rehypeSanitize, ...]} />
 * ```
 */
import type { Root } from 'hast'

export type ColorMap = Record<string, string>

/**
 * 创建 rehype 插件，将 span.text-{name} 替换为内联 style
 * @param colorMap 如 { 'text-red': '255 100 100', 'text-gold': '255 215 0' }
 */
export function rehypeColorText(colorMap: ColorMap) {
  return () => (tree: Root) => {
    walk(tree.children, colorMap)
  }
}

function walk(nodes: any[], colorMap: ColorMap) {
  for (const node of nodes) {
    if (node.type === 'element' && node.tagName === 'span' && node.properties?.className) {
      const cls = Array.isArray(node.properties.className)
        ? node.properties.className.join(' ')
        : String(node.properties.className || '')
      for (const [cname, rgb] of Object.entries(colorMap)) {
        if (cls.includes(cname)) {
          node.properties.style = `color: rgb(${rgb})`
          break
        }
      }
    }
    if (node.children) walk(node.children, colorMap)
  }
}
