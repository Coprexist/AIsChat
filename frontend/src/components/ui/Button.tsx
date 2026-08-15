import { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

/**
 * 统一 Button 组件
 *
 * 消灭 74 处重复的内联按钮类名。变体：
 * - primary：主操作（紫色渐变，默认）
 * - accent：强调操作（琥珀金）
 * - outline：次级操作（描边）
 * - ghost：幽灵按钮（hover 底色）
 * - danger：危险操作（红色）
 * - success：成功/在线（mint 绿）
 *
 * 尺寸：sm（紧凑）/ md（默认）/ lg（大）
 */
type Variant = 'primary' | 'accent' | 'outline' | 'ghost' | 'danger' | 'success'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
  children?: ReactNode
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-primary-500 hover:bg-primary-400 text-white shadow-sm',
  accent: 'bg-accent-500 hover:bg-accent-400 text-white shadow-sm',
  // outline = 浅底 + 深描边 + 轻阴影（浅色主题下靠描边+阴影建立边界，不只靠底色）
  outline: 'bg-elevated border border-border text-textSecondary hover:bg-border/70 hover:text-textPrimary shadow-sm',
  ghost: 'text-textSecondary hover:bg-canvas',
  danger: 'bg-rose-500 hover:bg-rose-400 text-white',
  success: 'bg-mint-400 hover:bg-mint-300 text-gray-900',
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-2.5 py-1.5 text-xs rounded-lg gap-1.5',
  md: 'px-4 py-2.5 text-sm rounded-xl gap-2',
  lg: 'px-5 py-3 text-base rounded-xl gap-2',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading ? <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" /> : icon}
      {children}
    </button>
  )
}
