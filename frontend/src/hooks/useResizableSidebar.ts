import { useState, useCallback, useEffect, useRef, useMemo, useSyncExternalStore } from 'react'

export const SIDEBAR_MIN = 200
export const SIDEBAR_MAX = 500
const SIDEBAR_DEFAULT = 320
const RIGHT_DEFAULT = 480

/** 宽度收敛到 [min, max] 并取整 */
export function clampWidth(value: number, min: number, max: number): number {
  return Math.round(Math.max(min, Math.min(max, value)))
}

const subscribeViewport = (onChange: () => void) => {
  window.addEventListener('resize', onChange)
  return () => window.removeEventListener('resize', onChange)
}

/**
 * 可拖拽侧边栏宽度 Hook。
 * 桌面端 mousedown 拖拽手柄 → 调整宽度 → 持久化到 localStorage。
 *
 * 宽度分两层：`preferredWidth` 是用户意图（唯一被持久化的值），渲染宽度每次按当前上限收敛。
 * 上限常是动态的（按邻栏保底反推），所以窄屏或拖宽邻栏只会临时压缩面板，压小的值不写回存储——
 * 否则面板被挤小一次就再也回不来。
 *
 * @param storageKey localStorage 存储键
 * @param sidebarRef 侧边栏容器 DOM ref，用于计算锚点边缘的偏移
 * @param options.side 'left'（默认，锚点=左边缘）| 'right'（锚点=右边缘，右侧面板用）
 * @param options.min/max 宽度范围（默认 200-500；max 可为函数，按当前布局实时求值）
 */
export function useResizableSidebar(
  storageKey: string,
  sidebarRef: React.RefObject<HTMLElement | null>,
  options?: { side?: 'left' | 'right'; min?: number; max?: number | (() => number) },
) {
  const side = options?.side ?? 'left'
  const min = options?.min ?? SIDEBAR_MIN
  // max 支持 number 或函数（动态上限：拖动/窗口变化时实时算，如按其他区域保底反推）
  const max: number | (() => number) = options?.max ?? SIDEBAR_MAX
  const resolveMax = () => (typeof max === 'function' ? max() : max)
  const [preferredWidth, setPreferredWidth] = useState(() => {
    const saved = Number(localStorage.getItem(storageKey))
    // 低于下限的存量值不当作意图：下限是布局硬约束，用户不可能在它之外表达过偏好
    // （多半是旧版本下限更小、或曾被写小），这种情况回落默认值而不是夹到下限——
    // 夹到下限会把"最小"当成"合适"。高于上限的不丢：上限随窗口/邻栏变化，收敛在渲染层做。
    if (saved >= min) return saved
    return side === 'left' ? SIDEBAR_DEFAULT : RIGHT_DEFAULT
  })
  const resizing = useRef(false)
  const anchorRef = useRef(0)
  // 视口宽度只作「重新收敛」的信号：窗口变小后收敛上限可能变小，需要重算渲染宽度
  const viewportWidth = useSyncExternalStore(subscribeViewport, () => window.innerWidth, () => 0)
  const sidebarWidth = useMemo(
    () => clampWidth(preferredWidth, min, resolveMax()),
    [preferredWidth, min, max, viewportWidth],
  )

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
      const clamped = clampWidth(w, min, resolveMax())
      setPreferredWidth(clamped)
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
