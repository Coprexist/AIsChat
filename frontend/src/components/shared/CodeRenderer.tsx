import MermaidBlock from '../MermaidBlock'

/**
 * 共享代码块渲染器——消息气泡和文件预览共用。
 *
 * - mermaid 块 → <MermaidBlock>
 * - inline code → 允许断词换行
 * - block code → 横向滚动，不换行
 */
export default function CodeRenderer({ className, children, inline, node, ...props }: any) {
  // react-markdown v10 不传 inline prop，改用 data-inline 属性区分
  const isInline = inline || node?.properties?.dataInline
  const match = /language-(\w+)/.exec(className || '')
  const code = String(children).replace(/\n$/, '')

  if (!isInline && match && match[1] === 'mermaid') {
    return <MermaidBlock code={code} compact />
  }

  if (isInline) {
    return (
      <code className={`bg-black/5 dark:bg-white/10 rounded px-1 py-0.5 text-[0.85em] break-all ${className || ''}`}>
        {children}
      </code>
    )
  }

  return (
    <code className={`block overflow-x-auto whitespace-pre rounded-xl bg-black/5 dark:bg-white/5 border border-border/50 p-5 text-xs ${className || ''}`}>
      {children}
    </code>
  )
}
