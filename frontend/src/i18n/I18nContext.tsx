import { createContext, useContext, useCallback, useState, useEffect, type ReactNode } from 'react'
import { useAuth } from '../context/AuthContext'
import { getTranslation } from './translations'
import { type Lang, DEFAULT_LANG, isValidLang } from './languages'

interface I18nContextType {
  lang: Lang
  t: (path: string, vars?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nContextType>({
  lang: DEFAULT_LANG,
  t: (path: string) => path,
})

/** 缓存全局默认语言到 localStorage（登录页/未登录时使用） */
export function cacheLangForUnauth(lang: Lang) {
  localStorage.setItem('i18n_cached_lang', lang)
  window.dispatchEvent(new Event('i18n-lang-changed'))
}

/** 设置向导中临时覆盖语言（立即生效预览） */
export function overrideLangForSetup(lang: Lang | null) {
  if (lang) {
    localStorage.setItem('i18n_override_lang', lang)
  } else {
    localStorage.removeItem('i18n_override_lang')
  }
  window.dispatchEvent(new Event('i18n-lang-changed'))
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  const resolveLang = (): Lang => {
    // 1. 设置向导临时覆盖
    const override = localStorage.getItem('i18n_override_lang')
    if (isValidLang(override)) return override

    // 2. 已登录用户的语言设置
    if (isValidLang(user?.language)) return user.language

    // 3. localStorage 缓存的全局默认语言（登录页获取）
    const cached = localStorage.getItem('i18n_cached_lang')
    if (cached && isValidLang(cached)) return cached

    // 4. 硬回退：系统全局默认语言
    return DEFAULT_LANG
  }

  const [lang, setLang] = useState<Lang>(resolveLang)

  // user 变化时重新解析
  useEffect(() => {
    setLang(resolveLang())
  }, [user?.language])

  // 监听语言变化（跨组件 custom event + 跨标签页 storage event）
  useEffect(() => {
    const onLangChanged = () => setLang(resolveLang())
    window.addEventListener('i18n-lang-changed', onLangChanged)
    window.addEventListener('storage', onLangChanged)
    return () => {
      window.removeEventListener('i18n-lang-changed', onLangChanged)
      window.removeEventListener('storage', onLangChanged)
    }
  }, [user?.language])

  const t = useCallback(
    (path: string, vars?: Record<string, string | number>) => getTranslation(lang, path, vars),
    [lang]
  )

  return (
    <I18nContext.Provider value={{ lang, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useT() {
  const ctx = useContext(I18nContext)
  return ctx.t
}

export function useLang() {
  const ctx = useContext(I18nContext)
  return ctx.lang
}
