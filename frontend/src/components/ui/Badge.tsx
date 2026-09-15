import type { ReactNode } from 'react'

/**
 * 统一胶囊标签
 *
 * 单一来源：状态、分类、计数等小标签一律用它，
 * 不再手写 text-3xs px-1.5 py-0.5 rounded-full 的散装类名。
 */
type Tone = 'primary' | 'mint' | 'accent' | 'rose' | 'muted'

interface BadgeProps {
  tone?: Tone
  children: ReactNode
  className?: string
}

export default function Badge({ tone = 'muted', children, className = '' }: BadgeProps) {
  return <span className={`chip chip-${tone} ${className}`}>{children}</span>
}
