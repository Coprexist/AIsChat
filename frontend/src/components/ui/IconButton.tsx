import { ButtonHTMLAttributes, ReactNode } from 'react'

/**
 * 统一图标按钮
 *
 * 单一来源：不再手写 p-1 / p-1.5 / p-2 / w-8 / w-9 / w-10 的正方形按钮。
 * 尺寸：sm=28px / md=32px（默认）/ lg=40px
 * label 必填 —— 图标按钮必须有可访问名称（同时作为 title 悬浮提示）。
 */
type Size = 'sm' | 'md' | 'lg'

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: ReactNode
  label: string
  size?: Size
  /** 变体色：默认次要色，hover 转主色 */
  tone?: 'default' | 'primary' | 'danger' | 'plain'
}

const SIZE_CLASS: Record<Size, string> = { sm: 'icon-btn-sm', md: '', lg: 'icon-btn-lg' }
const TONE_CLASS: Record<NonNullable<IconButtonProps['tone']>, string> = {
  default: '',
  primary: 'hover:text-primary-400',
  danger: 'hover:text-rose-400',
  plain: 'hover:bg-transparent hover:text-textPrimary',
}

export default function IconButton({
  icon,
  label,
  size = 'md',
  tone = 'default',
  className = '',
  type = 'button',
  title,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={title ?? label}
      className={`icon-btn ${SIZE_CLASS[size]} ${TONE_CLASS[tone]} ${className}`}
      {...rest}
    >
      {icon}
    </button>
  )
}
