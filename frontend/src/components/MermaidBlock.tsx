import { useEffect, useRef, useState, useId, memo } from 'react'
import { Loader2, AlertTriangle, Maximize2, Minimize2, ZoomIn, ZoomOut, Download } from 'lucide-react'
import CodeRenderer from './shared/CodeRenderer'

interface MermaidBlockProps {
  code: string
  /** 是否为聊天消息中的（限制最大宽高） */
  compact?: boolean
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/**
 * Mermaid sandbox 模式下 render() 返回的是 iframe 包裹 HTML，
 * 从 iframe 的 srcdoc/data URL 中提取纯 SVG 字符串。
 */
function extractCleanSvg(container: HTMLDivElement | null): string | null {
  const iframe = container?.querySelector('iframe')
  if (!iframe) return null
  const src = iframe.getAttribute('srcdoc') || iframe.src || ''
  // base64 data URL
  const b64 = src.match(/;base64,([^"']+)/)
  if (b64) {
    try {
      const html = decodeURIComponent(Array.from(atob(b64[1]), c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''))
      const svgs = html.match(/<svg[\s\S]*?<\/svg>/gi)
      return svgs ? svgs[svgs.length - 1] : html.length < 50000 ? html : null
    } catch { return null }
  }
  const m = src.match(/<svg[\s\S]*?<\/svg>/i)
  return m ? m[0] : null
}

/**
 * Mermaid sandbox 模式下返回的 SVG 自带 width="10"（甚至更小），
 * 从 viewBox 中提取实际绘图宽度并修正。
 * 同时注入 CSS 防止 CJK 字符被 foreignObject 裁剪（mermaid 已知问题）。
 */
function normalizeSvgWidth(svg: string): string {
  const vb = svg.match(/viewBox="(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)"/)
  if (!vb) return svg
  // 先修 width
  let result = svg.replace(/width="[^"]*"/, `width="${vb[3]}"`)
  // 再注入 CSS：让 foreignObject 内的文字不溢出隐藏
  // 见 mermaid-js/mermaid#4950、#7359、PR#7367
  const styleTag = `<style>foreignObject{overflow:visible!important}</style>`
  if (!result.includes(styleTag)) {
    result = result.replace('</svg>', styleTag + '</svg>')
  }
  return result
}

// 模块级初始化 mermaid（一次性），所有 MermaidBlock 实例共用
// 避免每次渲染重复 initialize 导致全局配置竞争
const mermaidPromise = (async () => {
  const mermaid = (await import('mermaid')).default
  mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'sandbox',
    fontFamily: 'inherit',
    // suppressErrorRendering 让 mermaid 在语法错误时不产生错误 SVG（v11+ 支持）
    // 而是直接 throw，由组件的 catch 统一处理
    suppressErrorRendering: true,
  })
  return mermaid
})()



// ---------------------------------------------------------------------------
// 设置读取
// ---------------------------------------------------------------------------

function getMermaidSetting(key: string, fallback: boolean): boolean {
  try {
    return localStorage.getItem(key) === null ? fallback : localStorage.getItem(key) === 'true'
  } catch {
    return fallback
  }
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

function MermaidBlock({ code, compact = false }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [fullscreenSvg, setFullscreenSvg] = useState<string | null>(null)
  // expandLevel: 0=未展开, 1=已点击但正在渲染, 2=已显示结果
  const [expandLevel, setExpandLevel] = useState(0)
  const [errorRevealed, setErrorRevealed] = useState(false)
  const uniqueId = useId().replace(/:/g, '')

  // 默认折叠设置（仅 compact 模式生效）
  const collapseDefault = compact && getMermaidSetting('mermaid_collapse', true)
  const collapseErrors = compact && getMermaidSetting('mermaid_collapse_errors', true)
  const isCollapsed = collapseDefault && expandLevel === 0
  const isErrorCollapsed = error && collapseErrors && !errorRevealed

  // ---- 渲染 mermaid（仅在用户点击展开后执行） ----
  useEffect(() => {
    if (expandLevel === 0) return
    let cancelled = false

    async function render() {
      try {
        const mermaid = await mermaidPromise
        const { svg: rendered } = await mermaid.render(`mermaid-${uniqueId}`, code)
        if (cancelled) return

        if (/translate\(NaN/.test(rendered)) {
          setError('渲染坐标异常（NaN），图表包含不支持的字符')
          setSvg(null)
        } else {
          // 注入 CSS 到 iframe srcdoc 中，防止 CJK 字符被裁剪
          // mermaid 已知问题：mermaid-js/mermaid#4950、#7359
          const stylePatch = '<style>foreignObject{overflow:visible!important}</style>'
          const patched = rendered.includes(stylePatch)
            ? rendered
            : rendered.replace(/(srcdoc="[^"]*)(<\/svg>)/, (_, before, after) => before + stylePatch + after)
          setSvg(patched)
          setError(null)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || 'Mermaid 渲染失败')
          setSvg(null)
        }
      }
    }

    render()
    return () => { cancelled = true }
  }, [code, uniqueId, expandLevel])

  // ---- 展开全屏（用 ref 存 svg，避免 StrictMode 双渲导致 useCallback 闭包过期） ----
  // 全屏缩放/拖拽 refs（与原版保持一致，不抽 hook，避免 StrictMode 下引用问题）
  const overlayRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef(1)
  const panRef = useRef({ x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null)
  const svgWrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!expanded) return
    const up = () => { dragRef.current = null }
    document.addEventListener('mouseup', up)
    return () => document.removeEventListener('mouseup', up)
  }, [expanded])

  useEffect(() => {
    const el = overlayRef.current
    if (!el || !expanded) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomRef.current = Math.max(0.25, Math.min(10, zoomRef.current - e.deltaY * 0.005))
      updateTransform()
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [expanded])

  const updateTransform = (smooth = false) => {
    const el = svgWrapRef.current
    if (!el) return
    el.style.transition = smooth ? 'transform 0.12s ease-out' : 'none'
    el.style.transform = `translate3d(${panRef.current.x}px, ${panRef.current.y}px, 0) scale(${zoomRef.current})`
  }

  const resetTransform = () => {
    zoomRef.current = 1
    panRef.current = { x: 0, y: 0 }
    updateTransform(true)
  }

  const zoomIn = () => { zoomRef.current = Math.min(10, zoomRef.current + 0.25); updateTransform(true) }
  const zoomOut = () => { zoomRef.current = Math.max(0.25, zoomRef.current - 0.25); updateTransform(true) }

  const svgRef = useRef(svg)
  svgRef.current = svg

  // 构建错误报告消息
  const buildReportMsg = (err: string) => {
    const lang = document.documentElement.lang?.startsWith('zh') ? 'zh-CN' : 'en'
    const msgZh = `Mermaid 图表渲染失败：${err}\n\n原始代码：\n\`\`\`mermaid\n${code}\n\`\`\``
    const msgEn = `Mermaid diagram failed to render: ${err}\n\nOriginal code:\n\`\`\`mermaid\n${code}\n\`\`\``
    return lang === 'zh-CN' ? msgZh : msgEn
  }
  const dispatchErrorReport = (err: string) => {
    document.dispatchEvent(new CustomEvent('mermaid-error-report', { detail: { message: buildReportMsg(err) } }))
  }

  const handleExpand = () => {
    // mermaid.render 在 sandbox 模式返回 iframe 包裹 HTML，需提取纯 SVG
    const raw = extractCleanSvg(containerRef.current)
    if (raw) {
      setFullscreenSvg(normalizeSvgWidth(raw))
    }
    setExpanded(true)
  }

  const handleClose = () => {
    setExpanded(false)
    resetTransform()
  }

  // ---- 渲染分支 ----

  // 折叠占位：检测到 ```mermaid 代码块但尚未点击展开
  if (isCollapsed) {
    return (
      <div className={compact ? 'my-2' : 'my-4'}>
        <button
          onClick={() => setExpandLevel(1)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border w-full text-xs border-border/50 bg-elevated/30 hover:bg-elevated text-textMuted hover:text-textSecondary"
        >
          <Maximize2 size={13} />
          <span>展开 Mermaid 图表</span>
        </button>
      </div>
    )
  }

  // 错误折叠：渲染完成后出错，但用户尚未点击查看
  if (isErrorCollapsed) {
    return (
      <div className={compact ? 'my-2' : 'my-4'}>
        <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg border w-full text-xs border-rose-400/20 bg-rose-400/5">
          <button
            onClick={() => setErrorRevealed(true)}
            className="flex items-center gap-1 text-rose-400/70 hover:text-rose-400 transition-colors shrink-0"
          >
            <AlertTriangle size={13} />
            <span>查看详情</span>
          </button>
          <span className="text-rose-400/20">·</span>
          <button
            onClick={() => error && dispatchErrorReport(error)}
            className="text-rose-400/70 hover:text-rose-400 transition-colors shrink-0"
          >
            报告错误给AI
          </button>
        </div>
      </div>
    )
  }

  // 加载态（用户已点击但尚未完成）：保持按钮可见，仅改文字
  if (!svg && !error) {
    if (compact) {
      return (
        <div className={compact ? 'my-2' : 'my-4'}>
          <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg border w-full text-xs border-border/50 bg-elevated/30 text-textMuted">
            <Loader2 size={12} className="animate-spin" />
            <span>图表加载中...</span>
          </div>
        </div>
      )
    }
    return (
      <div ref={containerRef} className="my-3 rounded-xl border border-border bg-elevated p-4 flex items-center gap-2 text-textMuted text-sm">
        <Loader2 size={14} className="animate-spin" />
        图表加载中...
      </div>
    )
  }

  // 错误态
  if (error) {
    return (
      <div className="my-3 rounded-xl border border-rose-400/20 bg-rose-400/5 overflow-hidden">
        <div className="flex items-center justify-between gap-1.5 px-3 py-1.5 bg-rose-400/10 border-b border-rose-400/10">
          <div className="flex items-center gap-1.5 text-[10px] text-rose-400 font-medium">
            <AlertTriangle size={12} /> Mermaid 图表渲染失败
          </div>
          <button
            onClick={() => dispatchErrorReport(error)}
            className="text-[10px] px-2 py-0.5 rounded-md bg-rose-400/15 hover:bg-rose-400/25 text-rose-400 transition-colors"
            title="将错误信息发送给AI，帮助其修正"
          >
            报告错误给AI
          </button>
        </div>
        {error && <div className="px-3 py-1 text-[11px] text-rose-400/80 font-mono">{error}</div>}
        <div className="px-3 py-2 text-xs">
          <div className="text-textMuted mb-1">以下为原始代码：</div>
          <CodeRenderer className="" inline={false}>
            {code}
          </CodeRenderer>
        </div>
      </div>
    )
  }



  // 成功态
  const displaySvg = expanded ? (fullscreenSvg || svg) : svg
  const isFullscreenClass = expanded
    ? 'w-screen h-screen flex items-center justify-center p-8 overflow-auto'
    : 'overflow-x-auto p-4' + (compact ? ' max-h-[420px] overflow-y-auto' : '')

  return (
    <>
      <div className={
        (compact ? 'my-2 max-w-full' : 'my-4')
        + ' rounded-xl border border-border bg-white dark:bg-[#1e1e2e] [clip-path:inset(0_round_1rem)]' // clip-path 裁圆角但不去掉滚动能力
      }>
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-elevated/50 border-b border-border">
          <span className="text-[10px] text-textMuted font-medium tracking-wide uppercase">
            Mermaid
          </span>
          {compact && (
            <button
              onClick={handleExpand}
              className="p-0.5 rounded hover:bg-surface text-textMuted hover:text-textPrimary transition-colors"
              title="全屏查看"
            >
              <Maximize2 size={13} />
            </button>
          )}
        </div>

        {/* SVG 内容 */}
        <div
          ref={containerRef}
          className={isFullscreenClass}
          dangerouslySetInnerHTML={{ __html: displaySvg }}
        />
      </div>

      {/* 全屏浮层：使用宽度修正后的 SVG + 缩放/拖拽 */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
          ref={overlayRef}
          onMouseDown={(e) => {
            dragRef.current = { startX: e.clientX, startY: e.clientY, panX: panRef.current.x, panY: panRef.current.y }
          }}
          onMouseMove={(e) => {
            if (!dragRef.current) return
            panRef.current = { x: dragRef.current.panX + e.clientX - dragRef.current.startX, y: dragRef.current.panY + e.clientY - dragRef.current.startY }
            updateTransform()
          }}
          onMouseUp={() => { dragRef.current = null }}
          onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
        >
          <div className={isFullscreenClass}>
            {/* 工具栏 */}
            <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
              <button onClick={zoomIn} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="放大">
                <ZoomIn size={18} />
              </button>
              <button onClick={zoomOut} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="缩小">
                <ZoomOut size={18} />
              </button>
              <button onClick={resetTransform} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors text-xs font-medium" title="重置">
                还原
              </button>
              <button onClick={() => {
                const a = document.createElement('a')
                const raw = fullscreenSvg || (() => {
                  const e = extractCleanSvg(containerRef.current)
                  return e ? normalizeSvgWidth(e) : svg
                })()
                a.href = 'data:image/svg+xml,' + encodeURIComponent(raw)
                a.download = 'diagram.svg'
                a.click()
              }} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="下载 SVG">
                <Download size={18} />
              </button>
              <button onClick={handleClose} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="关闭">
                <Minimize2 size={18} />
              </button>
            </div>
            <div
              ref={svgWrapRef}
              className="cursor-grab active:cursor-grabbing"
              style={{ transition: 'transform 0.12s ease-out' }}
              dangerouslySetInnerHTML={{ __html: displaySvg }}
            />
          </div>
        </div>
      )}
    </>
  )
}

export default memo(MermaidBlock, (prev, next) => prev.code === next.code && prev.compact === next.compact)
