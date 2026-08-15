import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

/**
 * 统一 Modal 弹窗组件
 *
 * 消灭 23 个手写 Modal（fixed inset-0 重复）。特性：
 * - 居中卡片 + 半透明遮罩 + 点击遮罩关闭
 * - ESC 键关闭
 * - 标题栏（可选关闭按钮）+ 内容 + 底部操作区（可选）
 * - 滚动锁定（打开时禁止背景滚动）
 */
interface ModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: string
  closeOnOverlay?: boolean
}

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'max-w-lg',
  closeOnOverlay = true,
}: ModalProps) {
  // ESC 关闭 + 滚动锁定
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={closeOnOverlay ? onClose : undefined}
      />
      {/* 卡片 */}
      <div className={`relative w-full ${width} bg-surface border border-border rounded-2xl shadow-2xl max-h-[85vh] flex flex-col`}>
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <h3 className="font-semibold text-textPrimary">{title}</h3>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-textMuted hover:text-textPrimary hover:bg-canvas transition-colors"
              aria-label="关闭"
            >
              <X size={18} />
            </button>
          </div>
        )}
        <div className="px-5 py-4 overflow-y-auto flex-1">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-border shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
