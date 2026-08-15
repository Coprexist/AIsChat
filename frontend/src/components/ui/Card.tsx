import { ReactNode } from 'react'

/**
 * 统一 Card 区块组件
 *
 * 消灭各处重复的 bg-surface border rounded-xl p-5 容器。
 */
interface CardProps {
  title?: ReactNode
  icon?: ReactNode
  hint?: ReactNode
  children: ReactNode
  className?: string
}

export default function Card({ title, icon, hint, children, className = '' }: CardProps) {
  return (
    <section className={`bg-surface border border-border rounded-xl p-5 space-y-4 ${className}`}>
      {title && (
        <h3 className="text-sm font-semibold text-textPrimary flex items-center gap-2">
          {icon}
          {title}
        </h3>
      )}
      {hint && <p className="text-xs text-textMuted">{hint}</p>}
      {children}
    </section>
  )
}
