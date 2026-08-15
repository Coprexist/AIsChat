import { ReactNode, SelectHTMLAttributes } from 'react'

/**
 * 统一 Select 下拉组件
 *
 * 统一下拉框视觉（与 Input 一致的圆角/边框/焦点态）。
 * 支持 label 与 hint 说明（小白友好）。
 */
interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode
  hint?: ReactNode
  options: { value: string; label: ReactNode }[]
  placeholder?: string
}

export default function Select({
  label,
  hint,
  options,
  placeholder,
  className = '',
  id,
  ...rest
}: SelectProps) {
  const selectId = id || (label ? `select-${Math.random().toString(36).slice(2, 8)}` : undefined)

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-textSecondary">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary
          focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-shadow ${className}`}
        {...rest}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={String(opt.value)} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint && <p className="text-xs text-textMuted">{hint}</p>}
    </div>
  )
}
