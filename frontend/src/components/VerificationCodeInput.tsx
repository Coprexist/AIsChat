import { useRef, useCallback, ClipboardEvent } from 'react'

interface Props {
  value: string
  onChange: (code: string) => void
  disabled?: boolean
  error?: string
}

const DIGITS = 6

export default function VerificationCodeInput({ value, onChange, disabled, error }: Props) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  const handleChange = useCallback(
    (index: number, char: string) => {
      // 只允许数字
      const digit = char.replace(/\D/g, '').slice(-1)
      const chars = (value || '').split('')
      chars[index] = digit
      const newValue = chars.join('').slice(0, DIGITS)
      onChange(newValue)

      // 自动跳到下一个格子
      if (digit && index < DIGITS - 1) {
        inputRefs.current[index + 1]?.focus()
      }
    },
    [value, onChange],
  )

  const handleKeyDown = useCallback(
    (index: number, e: React.KeyboardEvent) => {
      if (e.key === 'Backspace') {
        e.preventDefault()
        const chars = (value || '').split('')
        if (chars[index]) {
          // 当前格有内容 → 清空当前格
          chars[index] = ''
          onChange(chars.join(''))
        } else if (index > 0) {
          // 当前格为空 → 跳到前一格并清空
          chars[index - 1] = ''
          onChange(chars.join(''))
          inputRefs.current[index - 1]?.focus()
        }
        return
      }

      // 左箭头 → 跳到前一格
      if (e.key === 'ArrowLeft' && index > 0) {
        e.preventDefault()
        inputRefs.current[index - 1]?.focus()
        return
      }

      // 右箭头 → 跳到后一格
      if (e.key === 'ArrowRight' && index < DIGITS - 1) {
        e.preventDefault()
        inputRefs.current[index + 1]?.focus()
        return
      }
    },
    [value, onChange],
  )

  const handlePaste = useCallback(
    (e: ClipboardEvent) => {
      e.preventDefault()
      const pasted = e.clipboardData.getData('text/plain').replace(/\D/g, '').slice(0, DIGITS)
      if (!pasted) return
      onChange(pasted)
      // 粘贴后聚焦到最后一个非空格或最后一个格
      const focusIndex = Math.min(pasted.length, DIGITS - 1)
      inputRefs.current[focusIndex]?.focus()
    },
    [onChange],
  )

  const chars = (value || '').split('')

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex gap-2.5 justify-center" onPaste={handlePaste}>
        {Array.from({ length: DIGITS }, (_, i) => {
          const char = chars[i] || ''
          const isFilled = char !== ''
          return (
            <input
              key={i}
              ref={el => { inputRefs.current[i] = el }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              autoComplete="one-time-code"
              disabled={disabled}
              value={char}
              onChange={e => handleChange(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              className={`w-11 h-14 rounded-card border-2 text-center text-xl font-bold transition-all
                focus:outline-none focus:ring-2 focus:ring-primary-500/50
                disabled:opacity-30 disabled:cursor-not-allowed
                ${isFilled
                  ? 'border-primary-500/30 bg-primary-500/5 text-textPrimary'
                  : 'border-border bg-canvas text-textPrimary'
                }
                ${error ? 'border-rose-400 focus:ring-rose-400/50' : 'focus:border-primary-500'}
              `}
            />
          )
        })}
      </div>
      {error && (
        <p className="text-xs text-rose-400">{error}</p>
      )}
    </div>
  )
}
