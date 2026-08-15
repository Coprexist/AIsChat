import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import Modal from './Modal'
import Button from './Button'
import { useT } from '../../i18n/I18nContext'

/**
 * 统一确认弹窗（替换原生 confirm()）
 *
 * 原生 confirm() 是浏览器默认样式，破坏整体观感。
 * 用法：把「是否确认」变成受控状态，返回 Promise<boolean>。
 *
 * 示例：
 *   const confirmed = await confirmAsync({ title: '删除？', message: '不可恢复' })
 */
export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

// 全局确认队列（简单实现：一次只弹一个）
let pendingResolver: ((v: boolean) => void) | null = null
let pendingOptions: ConfirmOptions | null = null
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((fn) => fn())
}

/** 在任意处调用：返回 Promise，用户确认后 resolve(true/false) */
export function confirmAsync(options: ConfirmOptions): Promise<boolean> {
  pendingOptions = options
  notify()
  return new Promise((resolve) => {
    pendingResolver = resolve
  })
}

function resolveAndClose(value: boolean) {
  pendingResolver?.(value)
  pendingResolver = null
  pendingOptions = null
  notify()
}

/** 全局确认弹窗组件（在 App 根部挂一次） */
export function ConfirmDialogHost() {
  const t = useT()
  const [, force] = useState(0)
  listeners.add(() => force((n) => n + 1))

  const options = pendingOptions
  if (!options) return null

  return (
    <Modal
      open
      onClose={() => resolveAndClose(false)}
      width="max-w-sm"
      title={
        <span className="flex items-center gap-2">
          <AlertTriangle size={18} className={options.danger ? 'text-rose-400' : 'text-accent-400'} />
          {options.title || t('common.confirm') || '确认'}
        </span>
      }
      footer={
        <>
          <Button variant="secondary" onClick={() => resolveAndClose(false)}>
            {options.cancelText || t('common.cancel') || '取消'}
          </Button>
          <Button variant={options.danger ? 'danger' : 'primary'} onClick={() => resolveAndClose(true)}>
            {options.confirmText || t('common.confirm') || '确认'}
          </Button>
        </>
      }
    >
      <p className="text-sm text-textSecondary">{options.message}</p>
    </Modal>
  )
}
