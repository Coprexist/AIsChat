/**
 * 空状态（全站唯一规范）
 *
 * 单一来源：图标圆角容器 + 标题 + 说明 + 可选行动按钮。
 * 行动按钮走 Button 组件，不再手写主按钮类名。
 */
import { type LucideIcon, Inbox } from 'lucide-react'
import Button from './Button'

interface Props {
  icon?: LucideIcon
  title?: string
  description?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

export default function EmptyState({ icon: Icon = Inbox, title, description, action, className = '' }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 px-4 ${className}`}>
      <div className="w-12 h-12 rounded-card bg-canvas border border-border flex items-center justify-center mb-3">
        <Icon size={22} className="text-textMuted/60" />
      </div>
      {title && <p className="text-sm font-medium text-textSecondary mb-1">{title}</p>}
      {description && <p className="text-xs text-textMuted text-center max-w-xs leading-relaxed">{description}</p>}
      {action && (
        <Button size="sm" className="mt-3" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
