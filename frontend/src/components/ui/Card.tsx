import { ReactNode } from 'react'

/**
 * 统一 Card 区块组件
 *
 * 样式来自 .card / .card-pad-lg 语义类（index.css），与手写卡片同一规范源。
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
    <section className={`card card-pad-lg space-y-4 ${className}`}>
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
