import MermaidBlock from '../MermaidBlock'
import hljs from 'highlight.js'

/**
 * 共享代码块渲染器——消息气泡和文件预览共用。
 *
 * - mermaid 块 → <MermaidBlock>
 * - inline code → 允许断词换行
 * - block code → 语法高亮 + 横向滚动
 */
export default function CodeRenderer({ className, children, inline, ...props }: any) {
  const match = /language-(\w+)/.exec(className || '')
  const code = String(children).replace(/\n$/, '')

  if (!inline && match && match[1] === 'mermaid') {
    return <MermaidBlock code={code} compact />
  }

  if (inline) {
    return (
      <code className={`bg-black/5 dark:bg-white/10 rounded px-1 py-0.5 text-[0.85em] break-all ${className || ''}`}>
        {children}
      </code>
    )
  }

  // 语法高亮
  let highlighted = code
  try {
    if (match) {
      const lang = match[1]
      const langOk = hljs.getLanguage(lang)
      if (langOk) highlighted = hljs.highlight(code, { language: lang }).value
    }
    if (!match || highlighted === code) {
      // 没有指定语言或高亮失败 → 自动检测
      const auto = hljs.highlightAuto(code)
      if (auto && auto.value) highlighted = auto.value
    }
  } catch (_) { /* 高亮失败不阻塞 */ }

  return (
    <code
      className={`block overflow-x-auto whitespace-pre rounded-xl bg-black/5 dark:bg-white/5 border border-border/50 p-5 text-xs ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  )
}
