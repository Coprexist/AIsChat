import { useEffect, useRef, useState, useId } from 'react'
import { Loader2, AlertTriangle, Maximize2, Minimize2, ZoomIn, ZoomOut, Download } from 'lucide-react'
import CodeRenderer from './shared/CodeRenderer'

interface MermaidBlockProps {
  code: string
  /** 是否为聊天消息中的（限制最大宽高） */
  compact?: boolean
}

/**
 * Mermaid 图表渲染块。
 * - 使用 mermaid.run() 渲染 SVG
 * - 支持点击全屏查看（compact 模式）
 * - 渲染失败时显示源码
 */
export default function MermaidBlock({ code, compact = false }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [cleanSvg, setCleanSvg] = useState<string | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef(1)
  const panRef = useRef({ x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null)
  const svgWrapRef = useRef<HTMLDivElement>(null)
  const uniqueId = useId().replace(/:/g, '')

  // 全屏拖拽时监听 document mouseup（防止移出容器后拖拽不松手）
  useEffect(() => {
    if (!expanded) return
    const up = () => { dragRef.current = null }
    document.addEventListener('mouseup', up)
    return () => document.removeEventListener('mouseup', up)
  }, [expanded])

  // 全屏滚轮缩放 — 用原生 listener 以避免 passive 拦截 preventDefault
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

  /** 直接更新 DOM 变换，不触发 React 重渲染。smooth=true 启用过渡动画（缩放/还原），拖拽时关闭 */
  /** 从 sandbox iframe 中提取纯 SVG（取最后一个 <svg>），返回带固定像素宽度的 SVG */
function extractCleanSvg(container: HTMLDivElement | null): string | null {
  const iframe = container?.querySelector('iframe')
  if (!iframe) return null
  const src = iframe.getAttribute('srcdoc') || iframe.src || ''
  // case 1: data URL with base64
  const b64Match = src.match(/;base64,([^"']+)/)
  if (b64Match) {
    try {
      const bin = atob(b64Match[1])
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      const html = new TextDecoder('utf-8').decode(bytes)
      const svgs = html.match(/<svg[\s\S]*?<\/svg>/gi)
      if (!svgs) return html.length < 50000 ? html : null  // 没找到 SVG 但内容不大就原样返回
      const svg = svgs[svgs.length - 1]  // 最后一个 <svg> 是实际渲染结果
      const vb = svg.match(/viewBox="(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"/)
      return vb ? svg.replace(/width="[^"]*"/, `width="${vb[3]}"`) : svg
    } catch { return null }
  }
  // case 2: inline SVG in srcdoc
  const svgMatch = src.match(/<svg[\s\S]*?<\/svg>/i)
  return svgMatch ? svgMatch[0] : null
}

  const updateTransform = (smooth = false) => {
    if (svgWrapRef.current) {
      svgWrapRef.current.style.transition = smooth ? 'transform 0.12s ease-out' : 'none'
      svgWrapRef.current.style.transform = `translate3d(${panRef.current.x}px, ${panRef.current.y}px, 0) scale(${zoomRef.current})`
    }
  }

  useEffect(() => {
    let cancelled = false

    async function render() {
      try {
        const mermaid = (await import('mermaid')).default

        // 初始化（mermaid.initialize 幂等，每次调用不影响性能）
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'sandbox',
          fontFamily: 'inherit',
        })

        const { svg: rendered } = await mermaid.render(`mermaid-${uniqueId}`, code)
        if (!cancelled) {
          // mermaid.render 遇到语法错误时不抛异常，而是返回一个带 .error-icon 的错误 SVG
          // 这里检测并转为我们自己的错误 UI
          if (/class="[^"]*error-icon[^"]*"/.test(rendered)) {
            const errMsg = rendered.match(/class="error-text"[^>]*>([^<]+)</)?.[1] || 'Mermaid 语法错误'
            setError(errMsg)
            setSvg(null)
          } else {
            setSvg(rendered)
            setError(null)
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          // 清理 mermaid 作为副作用创建的 DOM（退出的 iframe）
          containerRef.current?.querySelectorAll('iframe').forEach(el => el.remove())
          setError(err?.message || 'Mermaid 渲染失败')
          setSvg(null)
        }
      }
    }

    render()
    return () => { cancelled = true }
  }, [code, uniqueId])

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

  // 成功
  const containerClass = compact
    ? 'my-2 rounded-xl border border-border bg-white dark:bg-[#1e1e2e] overflow-hidden max-w-full'
    : 'my-4 rounded-xl border border-border bg-white dark:bg-[#1e1e2e] overflow-hidden'

  const wrapperClass = expanded
    ? 'fixed inset-0 z-50 bg-black/80 backdrop-blur-sm'
    : ''

  const svgContainerClass = expanded
    ? 'w-screen h-screen flex items-center justify-center p-8 overflow-auto'
    : 'overflow-x-auto p-4'
    + (compact ? ' max-h-[420px] overflow-y-auto' : '')

  return (
    <>
      <div className={containerClass}>
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-elevated/50 border-b border-border">
          <span className="text-[10px] text-textMuted font-medium tracking-wide uppercase">
            Mermaid
          </span>
          {compact && (
            <button
              onClick={() => {
                setExpanded(true)
                if (!cleanSvg) {
                  const svg = extractCleanSvg(containerRef.current)
                  if (svg) setCleanSvg(svg)
                }
              }}
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
          className={wrapperClass}
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
          onClick={(e) => { if (e.target === e.currentTarget) { setExpanded(false); zoomRef.current = 1; panRef.current = { x: 0, y: 0 }; updateTransform(true) } }}
        >
          <div className={svgContainerClass}>
            {/* 工具栏 */}
            <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
              <button onClick={() => { zoomRef.current = Math.min(10, zoomRef.current + 0.25); updateTransform(true) }} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="放大">
                <ZoomIn size={18} />
              </button>
              <button onClick={() => { zoomRef.current = Math.max(0.25, zoomRef.current - 0.25); updateTransform(true) }} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="缩小">
                <ZoomOut size={18} />
              </button>
              <button onClick={() => { zoomRef.current = 1; panRef.current = { x: 0, y: 0 }; updateTransform(true) }} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors text-xs font-medium" title="重置">
                还原
              </button>
              <button onClick={() => {
                const svg = extractCleanSvg(containerRef.current)
                if (!svg) return
                const a = document.createElement('a')
                a.href = 'data:image/svg+xml,' + encodeURIComponent(svg)
                a.download = 'diagram.svg'
                a.click()
              }} className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors" title="下载 SVG">
                <Download size={18} />
              </button>
              <button
                onClick={() => { setExpanded(false); zoomRef.current = 1; panRef.current = { x: 0, y: 0 }; updateTransform(true) }}
                className="p-2 rounded-xl bg-black/30 hover:bg-black/50 text-white/80 hover:text-white transition-colors"
                title="关闭"
              >
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
