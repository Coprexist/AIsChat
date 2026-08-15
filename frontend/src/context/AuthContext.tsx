import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../api/client'
import { cacheLangForUnauth } from '../i18n/I18nContext'
import { type Lang, isValidLang, DEFAULT_LANG } from '../i18n/languages'
import { applyUserTheme, THEME_COLORS_PREF_KEY } from '../utils/userTheme'

interface User {
  id: number
  username: string
  role: string
  is_active: boolean
  ai_quota: number
  api_credit: number
  agent_bundle_credit: number
  file_quota_mb: number
  platform_gifted_credit: number
  total_effective: number
  has_api_key: boolean
  api_key_last4: string
  timezone: string
  language: string
  ui_prefs: Record<string, any>
  avatar_url: string | null
  bio: string | null
  status_text: string | null
  status_color: string | null
  setup_completed: boolean
  created_at: string | null
  assigned_pool_key_name: string | null  // v0.1.5: 绑定的池 Key 名
  email: string | null  // v0.2.0 邮箱
  email_verified: boolean  // v0.2.0 邮箱是否已验证
}

interface LoginOptions {
  method?: string
  code?: string
}

interface RegisterOptions {
  email?: string
  code?: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (loginId: string, password: string, options?: LoginOptions) => Promise<void>
  register: (username: string, password: string, options?: RegisterOptions) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  rebindEmail: (email: string, code: string) => Promise<void>
  removeEmail: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

// 纯函数：从登录/注册响应构建 User 对象（模块级，引用稳定）
function buildUserFromData(data: any): User {
  return {
    id: data.user_id,
    username: data.username,
    role: data.role,
    is_active: true,
    ai_quota: 0,
    api_credit: 0,
    has_api_key: false,
    api_key_last4: '',
    timezone: 'Asia/Shanghai',
    language: isValidLang(data.language) ? data.language : DEFAULT_LANG,
    ui_prefs: data.ui_prefs ?? {} as Record<string, any>,
    agent_bundle_credit: 0,
    file_quota_mb: 100,
    platform_gifted_credit: 0,
    total_effective: 0,
    avatar_url: null,
    bio: null,
    status_text: null,
    status_color: null,
    setup_completed: data.setup_completed ?? true,
    created_at: null,
    assigned_pool_key_name: null,
    email: data.email ?? null,
    email_verified: data.email_verified ?? false,
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // 同步一份到 localStorage（user_info）：世界块/沉浸界面等非 React 环境读取当前用户
  useEffect(() => {
    try {
      if (user) {
        localStorage.setItem('user_info', JSON.stringify(user))
      } else {
        localStorage.removeItem('user_info')
      }
    } catch { /* 存储不可用时忽略 */ }
  }, [user])

  // 用户主题色应用：登录/刷新/登出时把 ui_prefs.theme_colors 覆盖到 CSS 变量
  useEffect(() => {
    applyUserTheme(user?.ui_prefs?.[THEME_COLORS_PREF_KEY])
  }, [user])

  const refreshUser = useCallback(async () => {
    try {
      const data = await api.get('/auth/me')
      setUser(data)
    } catch {
      setUser(null)
      localStorage.removeItem('access_token')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      refreshUser()
    } else {
      setLoading(false)
    }
  }, [refreshUser])

  const login = useCallback(async (loginId: string, password: string, options?: LoginOptions) => {
    const body: any = {
      login_id: loginId,
      password: password || '',
      method: options?.method || 'direct',
    }
    if (options?.method === 'email_code' && options?.code) {
      body.verification_code = options.code
    }
    const data = await api.post('/auth/login', body)
    localStorage.setItem('access_token', data.access_token)
    cacheLangForUnauth(data.language as Lang)
    setUser(buildUserFromData(data))
  }, [])

  const register = useCallback(async (username: string, password: string, options?: RegisterOptions) => {
    const body: any = { username, password }
    if (options?.email) body.email = options.email
    if (options?.code) body.verification_code = options.code
    const data = await api.post('/auth/register', body)
    localStorage.setItem('access_token', data.access_token)
    cacheLangForUnauth(data.language as Lang)
    setUser(buildUserFromData(data))
  }, [])

  const rebindEmail = useCallback(async (email: string, code: string) => {
    const data = await api.put('/auth/email', { email, code })
    setUser(prev => prev ? { ...prev, email: data.email, email_verified: data.email_verified } : prev)
  }, [])

  const removeEmail = useCallback(async () => {
    const data = await api.delete('/auth/email')
    setUser(prev => prev ? { ...prev, email: data.email, email_verified: data.email_verified } : prev)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    setUser(null)
  }, [])

  const ctxValue = useMemo(() => ({
    user, loading, login, register, logout, refreshUser, rebindEmail, removeEmail,
  }), [user, loading, login, register, logout, refreshUser, rebindEmail, removeEmail])

  return (
    <AuthContext.Provider value={ctxValue}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
