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
  const [hardText, setHardText] = useState({ title: '正在更新', body: '服务器正在更新，稍等一下就好~', color: '#f59e0b', image: '', style: 'popup' })
  const [softMaintenance, setSoftMaintenance] = useState(false)
  const [softText, setSoftText] = useState('服务器正在调整，功能可能偶尔不稳定')
  const [softColor, setSoftColor] = useState('#f59e0b')
  const location = useLocation()

  useEffect(() => {
    const h1 = async (e?: CustomEvent) => {
      setMaintenance(true)
      const cached = (() => { try { return JSON.parse(localStorage.getItem('maintenance_msg') || '') } catch { return null } })()
      // 优先用事件带的，其次读 API，最后读缓存
      if (e?.detail?.detail) setHardText({ title: '服务器维护中', body: e.detail.detail, color: '#f59e0b', image: '' })
      else try {
        const res = await fetch('/api/maintenance-msg')
        const d = await res.json()
        const txt = { title: d.hard_title || '正在更新', body: d.hard_body || '服务器正在更新', color: d.hard_color || '#f59e0b', image: d.hard_image || '', style: d.hard_style || 'popup' }
        localStorage.setItem('maintenance_msg', JSON.stringify(txt))
        setHardText(txt)
      } catch { if (cached?.title) setHardText(cached) }
    }
    const h2 = async () => {
      setSoftMaintenance(true)
      try {
        const res = await fetch('/api/maintenance-msg')
        const d = await res.json()
        if (d.soft_text) { setSoftText(d.soft_text); localStorage.setItem('maintenance_soft', d.soft_text) }
        if (d.soft_color) { setSoftColor(d.soft_color); localStorage.setItem('maintenance_soft_color', d.soft_color) }
      } catch {
        setSoftText(localStorage.getItem('maintenance_soft') || '服务器正在调整，功能可能偶尔不稳定')
        setSoftColor(localStorage.getItem('maintenance_soft_color') || '#f59e0b')
      }
    }
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
        <div className="fixed top-0 left-0 right-0 z-[65] text-white text-xs text-center py-1.5 px-4 font-medium" style={{ backgroundColor: softColor }}>
          {softText}
          <button onClick={() => setSoftMaintenance(false)} className="ml-2 underline opacity-80 hover:opacity-100">关闭</button>
        </div>
      )}

      {/* 硬维护（API 503）——弹窗 / 顶栏 */}
      {maintenance && hardText.style === 'banner' && (
        <div className="fixed top-0 left-0 right-0 z-[70] text-white text-xs text-center py-1.5 px-4 font-medium" style={{ backgroundColor: hardText.color }}>
          {hardText.title} · {hardText.body}
          <button onClick={() => setMaintenance(false)} className="ml-2 underline opacity-80 hover:opacity-100">关闭</button>
        </div>
      )}
      {maintenance && hardText.style !== 'banner' && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-surface rounded-2xl p-6 max-w-sm w-full text-center shadow-2xl border border-border">
            <Wrench size={40} className="mx-auto mb-3" style={{ color: hardText.color }} />
            <h2 className="text-lg font-semibold text-textPrimary mb-2">{hardText.title}</h2>
            <p className="text-sm text-textSecondary mb-3">{hardText.body}</p>
            {hardText.image && (
              <img src={hardText.image} alt="" className="w-24 h-24 object-contain mx-auto mb-3 rounded-lg" />
            )}
            <button onClick={() => setMaintenance(false)} className="px-4 py-2 text-sm rounded-lg text-white hover:opacity-90 transition-colors" style={{ backgroundColor: hardText.color }}>
              知道了
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
