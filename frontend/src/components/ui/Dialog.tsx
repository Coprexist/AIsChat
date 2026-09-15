import { ReactNode, useEffect } from 'react'

/**
 * 无壳弹窗底座（只有遮罩 + 行为，不带卡片样式）
 *
 * 单一来源：全站所有「固定遮罩 + 自定义卡片」的弹窗都用它，
 * 统一拿到：ESC 关闭 · 打开时锁背景滚动 · 点遮罩关闭 · 层级令牌。
 * 需要标准卡片（标题栏 + 内容 + 底部操作区）时用 Modal（= Dialog + 卡片）。
 */
type Layer = 'overlay' | 'drawer' | 'modal' | 'toast' | 'max'

const LAYER_CLASS: Record<Layer, string> = {
  overlay: 'z-overlay',
  drawer: 'z-drawer',
  modal: 'z-modal',
  toast: 'z-toast',
  max: 'z-max',
}

interface DialogProps {
  /** 关闭动作（ESC 用）。不传则 ESC 不生效 */
  onClose?: () => void
  /** 点击遮罩是否关闭，默认 true */
  closeOnOverlay?: boolean
  layer?: Layer
  /** 遮罩外观，默认 bg-black/60 */
  backdrop?: string
  /** 定位与布局类（flex items-center justify-center p-4 …） */
  className?: string
  children: ReactNode
}

export default function Dialog({
  onClose,
  closeOnOverlay = true,
  layer = 'modal',
  backdrop = 'bg-black/60',
  className = 'flex items-center justify-center p-4',
  children,
}: DialogProps) {
  // ESC 关闭 + 背景滚动锁定
  useEffect(() => {
    if (!onClose) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div
      className={`fixed inset-0 ${LAYER_CLASS[layer]} ${backdrop} ${className}`}
      role="dialog"
      aria-modal="true"
      onClick={closeOnOverlay && onClose ? (e) => { if (e.target === e.currentTarget) onClose() } : undefined}
    >
      {children}
    </div>
  )
}
