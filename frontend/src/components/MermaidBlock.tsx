/* MermaidBlock v2 — parse 预检 + 错误 SVG 拦截 + 无占位加载 */
import { useEffect, useRef, useState, useId, useCallback } from 'react'
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
 * Mermaid sandbox 模式下返回的 SVG 自带 width="10"（甚至更小），
 * 从 viewBox 中提取实际绘图宽度并修正。
 */
function normalizeSvgWidth(svg: string): string {
  const vb = svg.match(/viewBox="(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)"/)
  if (!vb) return svg
  return svg.replace(/width="[^"]*"/, `width="${vb[3]}"`)
}

/**
 * Mermaid 语法错误时返回的 SVG 有 3 个特征，任中其一即判为错误：
 * 1. <svg aria-roledescription="error"（v11+ 最明确的信号）
 * 2. <path class="error-icon"（旧版或特定主题）
 * 3. 包含 .error-text text 节点
 */
function isMermaidErrorSvg(svg: string): string | null {
  /* V2 */
  // 特征 1：aria-roledescription="error" 最可靠
  if (/aria-roledescription="error"/.test(svg)) {
    const m = svg.match(/class="error-text"[^>]*>([^<]+)</)
    return m ? m[1].trim() : 'Mermaid 语法错误'
  }
  // 特征 2：路径含 error-icon class
  if (/<path[^>]*class="[^"]*\berror-icon\b[^"]*"/.test(svg)) {
    const m = svg.match(/class="error-text"[^>]*>([^<]+)</)
    return m ? m[1].trim() : 'Mermaid 语法错误'
  }
  // 特征 3：error-text 文本节点
  if (/class="error-text"[^>]*>/.test(svg)) {
    const m = svg.match(/class="error-text"[^>]*>([^<]+)</)
    return m ? m[1].trim() : 'Mermaid 语法错误'
  }
  return null
}

// ---------------------------------------------------------------------------
// 全屏缩放/拖拽 hook
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

  return {
    overlayRef, svgWrapRef, zoomIn, zoomOut, resetTransform,
    dragRef, panRef, updateTransform,
  }
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

console.log("MERMAIDBLOCK_V2_RUNNING");

export default function MermaidBlock({ code, compact = false }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  // 全屏用：mermaid.render 返回的 SVG 经过宽度修正后的版本
  const [fullscreenSvg, setFullscreenSvg] = useState<string | null>(null)
  const uniqueId = useId().replace(/:/g, '')

  const {
    overlayRef, svgWrapRef, zoomIn, zoomOut, resetTransform,
    panRef, dragRef, updateTransform,
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

        // 先用 parse 预检语法，避免 mermaid.render 不抛异常却返回错误 SVG
        try {
          await mermaid.parse(code, { suppressErrors: false })
        } catch (parseErr: any) {
          if (!cancelled) {
            setError(parseErr?.message || parseErr?.str || 'Mermaid 语法错误')
            setSvg(null)
          }
          return
        }

        const { svg: rendered } = await mermaid.render(`mermaid-${uniqueId}`, code)
        if (cancelled) return

        // render 成功但依然可能返回错误图（兜底检测）
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

  // ---- 展开全屏 ----
  const handleExpand = useCallback(() => {
    if (svg && !fullscreenSvg) {
      // 保存宽度修正后的版本，用于全屏 overlay
      setFullscreenSvg(normalizeSvgWidth(svg))
    }
    setExpanded(true)
  }, [svg, fullscreenSvg])

  const handleClose = useCallback(() => {
    setExpanded(false)
    resetTransform()
  }, [resetTransform])

  // ---- 全屏 overlay 的拖拽事件 ----
  const handleOverlayMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, panX: panRef.current.x, panY: panRef.current.y }
  }, [dragRef, panRef])

  const handleOverlayMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current) return
    panRef.current = {
      x: dragRef.current.panX + e.clientX - dragRef.current.startX,
      y: dragRef.current.panY + e.clientY - dragRef.current.startY,
    }
    updateTransform()
  }, [dragRef, panRef, updateTransform])

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

  // 加载态——compact 模式下不渲染占位，避免卡滚动；非 compact 显示 spinner
  if (!svg) {
    if (compact) {
      // 加载完成后会变成 SVG 或错误 UI，期间不留空白
      return null
    }
    return (
      <div className="my-3 rounded-xl border border-border bg-elevated p-4 flex items-center gap-2 text-textMuted text-sm">
        <Loader2 size={14} className="animate-spin" />
        图表加载中...
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
          className={isFullscreenClass}
          dangerouslySetInnerHTML={{ __html: displaySvg }}
        />
      </div>

      {/* 全屏浮层：使用宽度修正后的 SVG + 缩放/拖拽 */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
          ref={overlayRef}
          onMouseDown={handleOverlayMouseDown}
          onMouseMove={handleOverlayMouseMove}
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
                a.href = 'data:image/svg+xml,' + encodeURIComponent(normalizeSvgWidth(svg))
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
