import { InputHTMLAttributes, ReactNode, useId } from 'react'

/**
 * 统一 Input 组件
 *
 * 视觉来自 .field 语义类（index.css），与 Select / textarea 共用同一套边框与焦点态。
 * 支持前置图标（icon）与后缀元素（suffix，如清除按钮）。
 */
interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode
  suffix?: ReactNode
  label?: ReactNode
  hint?: ReactNode
  error?: string
  /** 尺寸档位：md=40px（默认）/ sm=32px */
  fieldSize?: 'sm' | 'md'
}

export default function Input({
  icon,
  suffix,
  label,
  hint,
  error,
  fieldSize = 'md',
  className = '',
  id,
  ...rest
}: InputProps) {
  const autoId = useId()
  const inputId = id || (label ? `input-${autoId}` : undefined)

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-textSecondary">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-textMuted flex items-center pointer-events-none">
            {icon}
          </span>
        )}
        <input
          id={inputId}
          className={`field ${fieldSize === 'sm' ? 'field-sm' : ''} ${icon ? 'pl-9' : ''} ${suffix ? 'pr-9' : ''} ${error ? 'border-rose-500' : ''} ${className}`}
          {...rest}
        />
        {suffix && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-textMuted flex items-center">
            {suffix}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      {!error && hint && <p className="text-xs text-textMuted">{hint}</p>}
    </div>
  )
}
