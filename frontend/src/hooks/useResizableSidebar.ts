import { useState, useCallback, useEffect, useRef } from 'react'

export const SIDEBAR_MIN = 200
export const SIDEBAR_MAX = 500
const SIDEBAR_DEFAULT = 320
const RIGHT_DEFAULT = 480

/**
 * 可拖拽侧边栏宽度 Hook。
 * 桌面端 mousedown 拖拽手柄 → 调整宽度 → 持久化到 localStorage。
 * @param storageKey localStorage 存储键
 * @param sidebarRef 侧边栏容器 DOM ref，用于计算锚点边缘的偏移
 * @param options.side 'left'（默认，锚点=左边缘）| 'right'（锚点=右边缘，右侧面板用）
 * @param options.min/max 宽度范围（默认 200-500）
 */
export function useResizableSidebar(
  storageKey: string,
  sidebarRef: React.RefObject<HTMLElement | null>,
  options?: { side?: 'left' | 'right'; min?: number; max?: number },
) {
  const side = options?.side ?? 'left'
  const min = options?.min ?? SIDEBAR_MIN
  // max 支持 number 或函数（动态上限：拖动/窗口变化时实时算，如按其他区域保底反推）
  const max = options?.max ?? SIDEBAR_MAX
  const resolveMax = () => (typeof max === 'function' ? max() : max)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem(storageKey)
    if (saved) return Math.max(min, Math.min(max, Number(saved)))
    return side === 'left' ? SIDEBAR_DEFAULT : RIGHT_DEFAULT
  })
  const resizing = useRef(false)
  const anchorRef = useRef(0)

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizing.current = true
    // 记录拖拽开始时的锚点边缘：左侧面板=左边缘，右侧面板=右边缘（相对视口）
    if (sidebarRef.current) {
      const r = sidebarRef.current.getBoundingClientRect()
      anchorRef.current = side === 'left' ? r.left : r.right
    } else {
      anchorRef.current = 0
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarRef, side])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!resizing.current) return
      const w = side === 'left'
        ? e.clientX - anchorRef.current
        : anchorRef.current - e.clientX
      const clamped = Math.round(Math.max(min, Math.min(resolveMax(), w)))
      setSidebarWidth(clamped)
      localStorage.setItem(storageKey, String(clamped))
    }
    const onUp = () => {
      if (resizing.current) {
        resizing.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [storageKey, sidebarRef, side, min, max])

  return { sidebarWidth, handleResizeStart }
}
