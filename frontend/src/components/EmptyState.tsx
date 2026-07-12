import { type LucideIcon, Inbox } from 'lucide-react'

interface Props {
  icon?: LucideIcon
  title?: string
  description?: string
  action?: { label: string; onClick: () => void }
}

export default function EmptyState({ icon: Icon = Inbox, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-12 h-12 rounded-xl bg-canvas border border-border/50 flex items-center justify-center mb-3">
        <Icon size={22} className="text-textMuted/60" />
      </div>
      {title && <p className="text-sm font-medium text-textSecondary mb-1">{title}</p>}
      {description && <p className="text-xs text-textMuted text-center max-w-xs leading-relaxed">{description}</p>}
      {action && (
        <button onClick={action.onClick} className="mt-3 px-4 py-1.5 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-400 transition-colors">
          {action.label}
        </button>
      )}
    </div>
  )
}
