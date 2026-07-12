import { useState, useEffect } from 'react'

/**
 * 全局时间 tick — 单一 setInterval 驱动所有相对时间更新
 *
 * 替代每 MessageBubble 独立 setInterval（50+ 消息 = 50+ 定时器），
 * 改为 1 个全局定时器，所有订阅者共享。
 *
 * 用法：
 *   const tick = useTimeTick()  // 0, 1, 2, ... 每 15s +1
 *   // tick 变化触发重渲染，formatMessageTime 自动更新
 */

let globalTick = 0
const subscribers = new Set<() => void>()
let intervalStarted = false

function startGlobalTimer() {
  if (intervalStarted) return
  intervalStarted = true
  setInterval(() => {
    globalTick++
    subscribers.forEach(fn => fn())
  }, 15_000)
}

export function useTimeTick(): number {
  const [tick, setTick] = useState(globalTick)

  useEffect(() => {
    startGlobalTimer()
    const fn = () => setTick(globalTick)
    subscribers.add(fn)
    return () => { subscribers.delete(fn) }
  }, [])

  return tick
}
