import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { MessageCircle, Bot, User, Shield, LogOut, Menu, X, ChevronLeft, BookOpen, Users, Settings } from 'lucide-react'
import { MANUAL_URL } from '../constants'
import SearchOverlay from './SearchOverlay'
import { useT } from '../i18n/I18nContext'

const navKeys = [
  { to: '/chat', i18nKey: 'nav.chat', icon: MessageCircle },
  { to: '/friends', i18nKey: 'nav.friends', icon: Users },
  { to: '/agents', i18nKey: 'nav.ai', icon: Bot },
  { to: '/me', i18nKey: 'nav.me', icon: User },
]

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2.5 mx-2 rounded-xl text-sm font-medium transition-all duration-200 ${
    isActive
      ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300'
      : 'text-textSecondary hover:text-textPrimary hover:bg-elevated'
  }`

export default function Sidebar({ mobile, onClose }: { mobile?: boolean; onClose?: () => void }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const t = useT()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <aside
      className={`${
        collapsed ? 'w-16 h-full' : mobile ? 'w-full h-full' : 'w-60 h-full'
      } bg-surface border-r border-border flex flex-col transition-all duration-200 shrink-0`}
    >
      {/* 头部 */}
      <div className="h-14 px-4 border-b border-border flex items-center justify-between shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center shadow shadow-primary-500/30">
              <MessageCircle size={12} className="text-white" strokeWidth={2.5} />
            </div>
            <span className="text-base font-bold text-textPrimary tracking-tight">AIsChat</span>
          </div>
        )}
        {mobile ? (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-elevated text-textMuted hover:text-textSecondary transition-colors ml-auto"
          >
            <X size={20} />
          </button>
        ) : (
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg hover:bg-elevated text-textMuted hover:text-textSecondary transition-colors"
            title={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
          >
            {collapsed ? <Menu size={16} /> : <ChevronLeft size={16} />}
          </button>
        )}
      </div>

      {/* 搜索框 */}
      {!collapsed && (
        <div className="px-3 py-2 border-b border-border">
          <SearchOverlay />
        </div>
      )}

      {/* 用户信息 */}
      {!collapsed && user && (
        <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-textPrimary truncate">{user.username}</p>
            <p className="text-xs text-textMuted">
              {user.role === 'admin' ? (
                <span className="text-accent-400">{t('sidebar.adminPanel')}</span>
              ) : (
                <span>{t('sidebar.quota') + ' ' + (user.ai_quota ?? 0) + ' · ' + t('sidebar.balance') + ' ' + ((user as any).total_effective ?? (user as any).api_credit ?? 0)}</span>
              )}
            </p>
          </div>
        </div>
      )}

      {/* 主导航 */}
      {!collapsed && (
        <nav className="flex-1 py-3 space-y-0.5">
          {navKeys.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => { if (mobile) onClose?.() }}
              className={navLinkClass}
              title={collapsed ? t(item.i18nKey) : undefined}
            >
              <item.icon size={18} />
              <span>{t(item.i18nKey)}</span>
            </NavLink>
          ))}

          <NavLink to="/settings" onClick={() => { if (mobile) onClose?.() }} className={navLinkClass}>
            <Settings size={18} />
            <span>{t('nav.settings')}</span>
          </NavLink>

          {user?.role === 'admin' && (
            <NavLink to="/admin" onClick={() => { if (mobile) onClose?.() }} className={navLinkClass}>
              <Shield size={18} />
              <span>{t('nav.admin')}</span>
            </NavLink>
          )}

          <NavLink
            to={MANUAL_URL}
            onClick={() => { if (mobile) onClose?.() }}
            className={navLinkClass}
            title={collapsed ? t('nav.manual') : undefined}
          >
            <BookOpen size={18} />
            <span>{t('nav.manual')}</span>
          </NavLink>
        </nav>
      )}

      {/* 折叠时的最小导航 */}
      {collapsed && (
        <nav className="flex-1 py-3 space-y-0.5 flex flex-col items-center">
          {[
            { to: '/chat', i18nKey: 'nav.chat', icon: MessageCircle },
            { to: '/friends', i18nKey: 'nav.friends', icon: Users },
            { to: '/agents', i18nKey: 'nav.ai', icon: Bot },
            { to: '/me', i18nKey: 'nav.me', icon: User },
          ].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => { if (mobile) onClose?.() }}
              className={({ isActive }) =>
                `flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
                  isActive
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300'
                    : 'text-textSecondary hover:text-textPrimary hover:bg-elevated'
                }`
              }
              title={t(item.i18nKey)}
            >
              <item.icon size={18} />
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink
              to="/admin"
              onClick={() => { if (mobile) onClose?.() }}
              className={({ isActive }) =>
                `flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
                  isActive
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300'
                    : 'text-textSecondary hover:text-textPrimary hover:bg-elevated'
                }`
              }
              title={t('sidebar.adminPanel')}
            >
              <Shield size={18} />
            </NavLink>
          )}
          <NavLink
            to={MANUAL_URL}
            onClick={() => { if (mobile) onClose?.() }}
            className={({ isActive }) =>
              `flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'bg-primary-500/15 text-primary-600 dark:text-primary-300'
                  : 'text-textSecondary hover:text-textPrimary hover:bg-elevated'
              }`
            }
            title={t('sidebar.usageManual')}
          >
            <BookOpen size={18} />
          </NavLink>
        </nav>
      )}

      {/* 退出 */}
      <div className="p-2 border-t border-border shrink-0">
        <button
          onClick={handleLogout}
          className={`flex items-center rounded-xl text-textSecondary hover:text-rose-400 hover:bg-rose-500/10 transition-all duration-200 text-sm ${
            collapsed ? 'justify-center w-10 h-10' : 'gap-3 w-full px-3 py-2.5'
          }`}
          title={collapsed ? t('sidebar.logout') : undefined}
        >
          <LogOut size={18} />
          {!collapsed && <span>{t('sidebar.logout')}</span>}
        </button>
      </div>
    </aside>
  )
}
