import { InputHTMLAttributes, ReactNode } from 'react'

/**
 * 统一 Input 组件
 *
 * 统一输入框视觉：圆角、边框、背景、焦点态。
 * 支持前置图标（icon）与后缀元素（suffix，如清除按钮）。
 */
interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode
  suffix?: ReactNode
  label?: ReactNode
  hint?: ReactNode
  error?: string
}

export default function Input({
  icon,
  suffix,
  label,
  hint,
  error,
  className = '',
  id,
  ...rest
}: InputProps) {
  const inputId = id || (label ? `input-${Math.random().toString(36).slice(2, 8)}` : undefined)

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-textSecondary">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-textMuted flex items-center">
            {icon}
          </span>
        )}
        <input
          id={inputId}
          className={`w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary
            placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary-500/50
            transition-shadow ${icon ? 'pl-10' : ''} ${suffix ? 'pr-10' : ''}
            ${error ? 'border-rose-500' : ''} ${className}`}
          {...rest}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-textMuted flex items-center">
            {suffix}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      {!error && hint && <p className="text-xs text-textMuted">{hint}</p>}
    </div>
  )
}
