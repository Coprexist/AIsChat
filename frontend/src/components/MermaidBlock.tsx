import { useEffect, useRef, useState, useId } from 'react'
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
 * Mermaid 以 sandbox iframe 输出 SVG，无法直接获取。
 * 从容器内的 iframe srcdoc/data URL 中提取纯 SVG 字符串。
 * 取最后一个 <svg>（mermaid 实际渲染结果），固定像素宽度从 viewBox 推导。
 */
function extractCleanSvg(container: HTMLDivElement | null): string | null {
  const iframe = container?.querySelector('iframe')
  if (!iframe) return null

  const src = iframe.getAttribute('srcdoc') || iframe.src || ''

  // case 1: base64 data URL
  const b64Match = src.match(/;base64,([^"']+)/)
  if (b64Match) {
    try {
      const decoded = atob(b64Match[1])
      // atob 对二进制不一定安全，但 mermaid 输出是 UTF-8 HTML，没问题
      const html = decodeURIComponent(Array.from(decoded, c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''))
      const svgs = html.match(/<svg[\s\S]*?<\/svg>/gi)
      if (!svgs) return null
      const svg = svgs[svgs.length - 1]
      const vb = svg.match(/viewBox="(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"/)
      return vb ? svg.replace(/width="[^"]*"/, `width="${vb[3]}"`) : svg
    } catch {
      return null
    }
  }

  // case 2: inline SVG in srcdoc
  const svgMatch = src.match(/<svg[\s\S]*?<\/svg>/i)
  return svgMatch ? svgMatch[0] : null
}

/** Mermaid 语法错误时出的 SVGs 均含此 class，以此判断渲染结果是否有效 */
function isMermaidErrorSvg(svg: string): string | null {
  // mermaid v11+ 错误 SVG 结构：<path class="error-icon" …/> + <text class="error-text" …>错误信息</text>
  if (/<path[^>]*class="[^"]*\berror-icon\b[^"]*"/.test(svg)) {
    const m = svg.match(/class="error-text"[^>]*>([^<]+)</)
    return m ? m[1].trim() : 'Mermaid 语法错误'
  }
  return null
}

// ---------------------------------------------------------------------------
// 全屏缩放/拖拽工具
// ---------------------------------------------------------------------------

function useFullscreenPanZoom(expanded: boolean) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const svgWrapRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef(1)
  const panRef = useRef({ x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null)

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

  const handleMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: panRef.current.x, panY: panRef.current.y }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current) return
    panRef.current = {
      x: dragRef.current.panX + e.clientX - dragRef.current.startX,
      y: dragRef.current.panY + e.clientY - dragRef.current.startY,
    }
    updateTransform()
  }

  const handleMouseUp = () => { dragRef.current = null }

  return {
    overlayRef,
    svgWrapRef,
    zoomIn,
    zoomOut,
    resetTransform,
    updateTransform,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
  }
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

export default function MermaidBlock({ code, compact = false }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [cleanSvg, setCleanSvg] = useState<string | null>(null)
  const uniqueId = useId().replace(/:/g, '')

  const {
    overlayRef, svgWrapRef,
    zoomIn, zoomOut, resetTransform,
    handleMouseDown, handleMouseMove, handleMouseUp,
  } = useFullscreenPanZoom(expanded)

  // ---- 渲染 mermaid ----
  useEffect(() => {
    let cancelled = false

    async function render() {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'sandbox',
          fontFamily: 'inherit',
        })

        const { svg: rendered } = await mermaid.render(`mermaid-${uniqueId}`, code)
        if (cancelled) return

        const errMsg = isMermaidErrorSvg(rendered)
        if (errMsg) {
          setError(errMsg)
          setSvg(null)
        } else {
          setSvg(rendered)
          setError(null)
        }
      } catch (err: any) {
        if (!cancelled) {
          containerRef.current?.querySelectorAll('iframe').forEach(el => el.remove())
          setError(err?.message || 'Mermaid 渲染失败')
          setSvg(null)
        }
      }
    }

    render()
    return () => { cancelled = true }
  }, [code, uniqueId])

  // ---- 展开全屏时提取纯 SVG ----
  const handleExpand = () => {
    setExpanded(true)
    if (!cleanSvg) {
      const s = extractCleanSvg(containerRef.current)
      if (s) setCleanSvg(s)
    }
  }

  const handleClose = () => {
    setExpanded(false)
    resetTransform()
  }

  // ---- 渲染分支 ----

  // 错误态
  if (error) {
    return (
      <div className="my-3 rounded-xl border border-rose-400/20 bg-rose-400/5 overflow-hidden">
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-400/10 border-b border-rose-400/10 text-[10px] text-rose-400 font-medium">
          <AlertTriangle size={12} /> Mermaid 图表渲染失败
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

  // 加载态
  if (!svg) {
    return (
      <div className="my-3 rounded-xl border border-border bg-elevated p-4 flex items-center gap-2 text-textMuted text-sm">
        <Loader2 size={14} className="animate-spin" />
        图表加载中...
      </div>
    )
  }

  // 成功态
  const svgContainerClass = expanded
    ? 'w-screen h-screen flex items-center justify-center p-8 overflow-auto'
    : 'overflow-x-auto p-4' + (compact ? ' max-h-[420px] overflow-y-auto' : '')

  return (
    <>
      <div className={
        (compact
          ? 'my-2 max-w-full'
          : 'my-4')
        + ' rounded-xl border border-border bg-white dark:bg-[#1e1e2e] overflow-hidden'
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
          className={svgContainerClass}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>

      {/* 全屏浮层 */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
          ref={overlayRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
        >
          <div className={svgContainerClass}>
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
                const s = cleanSvg || extractCleanSvg(containerRef.current)
                if (!s) return
                const a = document.createElement('a')
                a.href = 'data:image/svg+xml,' + encodeURIComponent(s)
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
              dangerouslySetInnerHTML={{ __html: cleanSvg || '' }}
            />
          </div>
        </div>
      )}
    </>
  )
}
