import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, AlertTriangle, Key } from 'lucide-react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'

interface BalancePromptData {
  agent_id: number
  agent_name: string
  session_id: string
}

export const BALANCE_PROMPT_EVENT = 'balance-prompt'

export function dispatchBalancePrompt(data: BalancePromptData) {
  window.dispatchEvent(new CustomEvent(BALANCE_PROMPT_EVENT, { detail: data }))
}

export default function BalancePromptModal() {
  const t = useT()
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState<BalancePromptData | null>(null)
  const [loading, setLoading] = useState(false)

  const handleEvent = useCallback((e: Event) => {
    setPrompt((e as CustomEvent).detail as BalancePromptData)
  }, [])

  useEffect(() => {
    window.addEventListener(BALANCE_PROMPT_EVENT, handleEvent)
    return () => window.removeEventListener(BALANCE_PROMPT_EVENT, handleEvent)
  }, [handleEvent])

  const handleConfirm = async () => {
    if (!prompt) return
    setLoading(true)
    try {
      await api.post('/dm/continue-with-own-key', { session_id: prompt.session_id })
      navigate(`/chat/dm/${prompt.session_id}`)
    } catch (err: any) {
      alert(err.message || '操作失败')
    } finally {
      setLoading(false)
      setPrompt(null)
    }
  }

  const handleCancel = () => {
    setPrompt(null)
  }

  if (!prompt) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70" onClick={handleCancel}>
      <div
        className="bg-elevated border border-border rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl shadow-black/30 animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-accent-500/10 flex items-center justify-center shrink-0">
            <AlertTriangle size={20} className="text-accent-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-textPrimary">{t('balance.title')}</h3>
            <p className="text-xs text-textSecondary mt-1">
              {t('balance.useOwnKeyPrompt').replace('{name}', prompt.agent_name)}
            </p>
          </div>
          <button onClick={handleCancel} className="p-1 hover:bg-canvas rounded-lg text-textMuted shrink-0">
            <X size={16} />
          </button>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleCancel}
            className="flex-1 py-2.5 rounded-xl border border-border text-textSecondary hover:bg-canvas text-sm font-medium transition-colors"
          >
            {t('balance.cancel')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-40 text-sm font-medium transition-colors"
          >
            <Key size={14} />
            {loading ? '...' : t('balance.useOwnKey')}
          </button>
        </div>
      </div>
    </div>
  )
}
