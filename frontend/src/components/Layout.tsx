import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import MobileNav from './MobileNav'
import BalancePromptModal from './BalancePromptModal'
import { useDesktopNotification } from '../hooks/useDesktopNotification'
import { Wrench } from 'lucide-react'

export default function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [maintenance, setMaintenance] = useState(false)
  const [softMaintenance, setSoftMaintenance] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const h1 = () => setMaintenance(true)
    const h2 = () => setSoftMaintenance(true)
    window.addEventListener('maintenance-mode', h1)
    window.addEventListener('maintenance-soft', h2)
    return () => {
      window.removeEventListener('maintenance-mode', h1)
      window.removeEventListener('maintenance-soft', h2)
    }
  }, [])

  // 桌面通知：标签页标题未读计数 + 任务栏闪烁（所有页面生效）
  useDesktopNotification()

  // 聊天详情页（群聊/私信）隐藏底部导航栏，给输入框更多空间
  const hideNav = /^\/chat\/(dm\/[^/]+|\d+)/.test(location.pathname)
                   || /^\/dm\/[^/]+/.test(location.pathname)

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      {/* ── 桌面端侧栏（始终可见） ── */}
      <div className="hidden md:block shrink-0">
        <Sidebar />
      </div>

      {/* ── 移动端抽屉遮罩 ── */}
      {drawerOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/60 transition-opacity"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* ── 移动端抽屉 ── */}
      <div
        className={`md:hidden fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-250 ${
          drawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar mobile onClose={() => setDrawerOpen(false)} />
      </div>

      {/* ── 主内容区 ── */}
      <main className={`flex-1 min-w-0 overflow-y-auto bg-canvas ${hideNav ? 'pb-0' : 'pb-14 md:pb-0'}`}>
        <Outlet context={{ openDrawer: () => setDrawerOpen(true), closeDrawer: () => setDrawerOpen(false) }} />
      </main>

      {/* ── 移动端底部导航（聊天详情页隐藏） ── */}
      {!hideNav && <MobileNav closeDrawer={() => setDrawerOpen(false)} />}

      {/* ── 全局弹窗 ── */}
      <BalancePromptModal />

      {/* 软维护顶栏（API正常，仅提示） */}
      {softMaintenance && (
        <div className="fixed top-0 left-0 right-0 z-[65] bg-amber-500/90 text-white text-xs text-center py-1.5 px-4 font-medium">
          服务器维护中——部分功能可能不稳定 · 管理员正在调整
          <button onClick={() => setSoftMaintenance(false)} className="ml-2 underline opacity-80 hover:opacity-100">关闭</button>
        </div>
      )}

      {/* 硬维护弹窗（API 503） */}
      {maintenance && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-surface rounded-2xl p-6 max-w-sm w-full text-center shadow-2xl border border-border">
            <Wrench size={40} className="text-amber-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-textPrimary mb-2">服务器维护中</h2>
            <p className="text-sm text-textSecondary mb-4">管理员正在对服务器进行维护，请稍后再来。</p>
            <button onClick={() => setMaintenance(false)} className="px-4 py-2 text-sm rounded-lg bg-primary-500 text-white hover:bg-primary-400 transition-colors">
              知道了
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
