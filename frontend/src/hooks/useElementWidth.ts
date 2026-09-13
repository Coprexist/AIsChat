import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 观测元素实时宽度（0 = 尚未测量），返回 [ref 回调, 宽度]。
 *
 * 布局需要「本组件的实际可用宽度」而不是 window.innerWidth 时用它：外层还有导航栏等占位元素时，
 * innerWidth 会把可用空间算大，据此反推的保底/上限会把面板挤出可视区。
 * 用 ref 回调而非 RefObject：元素随条件渲染挂载/卸载时，ResizeObserver 自动改绑。
 */
export function useElementWidth(): [(node: HTMLElement | null) => void, number] {
  const [width, setWidth] = useState(0)
  const observerRef = useRef<ResizeObserver | null>(null)

  useEffect(() => () => observerRef.current?.disconnect(), [])

  const ref = useCallback((node: HTMLElement | null) => {
    observerRef.current?.disconnect()
    observerRef.current = null
    if (!node) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(node)
    observerRef.current = observer
    setWidth(node.getBoundingClientRect().width)
  }, [])

  return [ref, width]
}
