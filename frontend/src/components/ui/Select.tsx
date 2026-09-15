import { ReactNode, SelectHTMLAttributes, useId } from 'react'

/**
 * 统一 Select 下拉组件
 *
 * 视觉来自 .field 语义类（index.css），与 Input 完全一致。
 * 支持 label 与 hint 说明（小白友好）。
 */
interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode
  hint?: ReactNode
  options: { value: string; label: ReactNode }[]
  placeholder?: string
  fieldSize?: 'sm' | 'md'
}

export default function Select({
  label,
  hint,
  options,
  placeholder,
  fieldSize = 'md',
  className = '',
  id,
  ...rest
}: SelectProps) {
  const autoId = useId()
  const selectId = id || (label ? `select-${autoId}` : undefined)

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-textSecondary">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`field ${fieldSize === 'sm' ? 'field-sm' : ''} ${className}`}
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
