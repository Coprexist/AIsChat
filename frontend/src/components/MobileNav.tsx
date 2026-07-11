import { useNavigate, useLocation } from 'react-router-dom'
import { useT } from '../i18n/I18nContext'
import { mainNavItems, type NavItem } from '../utils/navRegistry'

interface MobileNavProps {
  closeDrawer?: () => void
}

export default function MobileNav({ closeDrawer }: MobileNavProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const t = useT()

  const isActive = (item: NavItem) => {
    if (item.matchSubPaths) {
      return location.pathname.startsWith(item.path) || location.pathname === '/'
    }
    return location.pathname.startsWith(item.path)
  }

  const visibleItems = mainNavItems.filter(item => !item.hidden)

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface/95 backdrop-blur-lg border-t border-border"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex h-14">
        {visibleItems.map((item) => {
          const active = isActive(item)
          return (
            <button
              key={item.path}
              onClick={() => { closeDrawer?.(); navigate(item.path) }}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 transition-all duration-200 relative ${
                active ? 'text-primary-400' : 'text-textMuted'
              }`}
            >
              {/* Active top indicator */}
              {active && (
                <div className="absolute top-0 left-1/4 right-1/4 h-0.5 bg-primary-400 rounded-full" />
              )}
              {/* Icon with optional pulse ring */}
              <div className="relative">
                <item.icon size={22} strokeWidth={active ? 2.5 : 2} />
                {active && (
                  <div className="absolute -inset-1.5 rounded-full ai-pulse-active opacity-50" />
                )}
              </div>
              <span className="text-[10px] font-medium">{t(item.i18nKey)}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
