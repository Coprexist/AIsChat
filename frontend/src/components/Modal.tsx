/**
 * 通用弹窗组件
 * 动画、遮罩、关闭逻辑统一，各业务弹窗只需传入内容
 */
import { useRef, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
}

export default function Modal({ open, onClose, title, children }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null)

  if (!open) return null

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 fade-in"
      onClick={(e) => { if (e.target === overlayRef.current) onClose() }}
    >
      <div className="bg-surface rounded-xl p-5 max-w-sm w-full mx-4 shadow-xl border border-border/50">
        {title && <h3 className="text-sm font-semibold mb-3 text-textPrimary">{title}</h3>}
        {children}
      </div>
    </div>
  )
}
