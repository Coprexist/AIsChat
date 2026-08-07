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
    // max 可能是函数（动态上限）——初始化时先 resolve，避免 Math.min(函数, 值) = NaN
    const maxVal = typeof max === 'function' ? max() : max
    const saved = localStorage.getItem(storageKey)
    if (saved) return Math.max(min, Math.min(maxVal, Number(saved)))
    return side === 'left' ? SIDEBAR_DEFAULT : RIGHT_DEFAULT
  })
  const resizing = useRef(false)
  const anchorRef = useRef(0)
  // 最新 max 解析器（max 可能是函数，闭包引用会随渲染变化；用 ref 保证监听器里取到最新）
  const resolveMaxRef = useRef(resolveMax)
  resolveMaxRef.current = resolveMax

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

  // 窗口 resize 时按最新上限回收宽度：防止宽屏拖宽后换小屏（仍桌面断点）把面板挤出屏幕
  useEffect(() => {
    const onResize = () => {
      setSidebarWidth((w) => {
        const maxVal = resolveMaxRef.current()
        if (w > maxVal) {
          const clamped = Math.max(min, maxVal)
          localStorage.setItem(storageKey, String(clamped))
          return clamped
        }
        return w
      })
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [storageKey, min])

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
