import { useState, useEffect, Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import MobileNav from './MobileNav'
import BalancePromptModal from './BalancePromptModal'
import { useDesktopNotification } from '../hooks/useDesktopNotification'
import { Wrench, X } from 'lucide-react'
import { loadFromStorage, apply } from '../utils/cssFilters'

export default function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [maintenance, setMaintenance] = useState(false)
  const [hardText, setHardText] = useState({ title: '正在更新', body: '服务器正在更新，稍等一下就好~', color: '#f59e0b', textColor: '#ffffff', image: '', style: 'popup' })
  const [softMaintenance, setSoftMaintenance] = useState(false)
  const [softText, setSoftText] = useState('服务器正在调整，功能可能偶尔不稳定')
  const [softColor, setSoftColor] = useState('#f59e0b')
  const [softTextColor, setSoftTextColor] = useState('#ffffff')
  const [softStyle, setSoftStyle] = useState('banner')
  const [softOnce, setSoftOnce] = useState(false)
  const [imgError, setImgError] = useState(false)
  const location = useLocation()

  // 魔视界：首屏渲染完成后恢复 CSS 滤镜
  useEffect(() => {
    const p = loadFromStorage()
    if (p) apply(p)
  }, [])

  useEffect(() => {
    const fetchMsg = async () => {
      try {
        const res = await fetch('/api/maintenance-msg')
        const d = await res.json()
        const txt = { title: d.hard_title||'正在更新', body: d.hard_body||'服务器正在更新', color: d.hard_color||'#f59e0b', textColor: d.hard_text_color||'#ffffff', image: d.hard_image||'', style: d.hard_style||'popup' }
        localStorage.setItem('maintenance_msg', JSON.stringify(txt))
        setHardText(txt)
        if (d.soft_text) { setSoftText(d.soft_text); localStorage.setItem('maintenance_soft', d.soft_text) }
        if (d.soft_color) { setSoftColor(d.soft_color); localStorage.setItem('maintenance_soft_color', d.soft_color) }
        if (d.soft_text_color) { setSoftTextColor(d.soft_text_color); localStorage.setItem('maintenance_soft_text_color', d.soft_text_color) }
        if (d.soft_style) { setSoftStyle(d.soft_style) }
        setSoftOnce(!!d.soft_once)
      } catch {}
    }
    const h1 = async (e?: CustomEvent) => {
      setMaintenance(true); setImgError(false)
      // 优先用事件带的数据（含全量 msg），其次读 API
      const m = e?.detail?.msg
      if (m?.hard_title) {
        setHardText({ title: m.hard_title, body: m.hard_body||'', color: m.hard_color||'#f59e0b', textColor: m.hard_text_color||'#ffffff', image: m.hard_image||'', style: m.hard_style||'popup' })
        localStorage.setItem('maintenance_msg', JSON.stringify({title: m.hard_title, body: m.hard_body, color: m.hard_color, textColor: m.hard_text_color, image: m.hard_image, style: m.hard_style}))
        if (m.soft_text) { setSoftText(m.soft_text); setSoftColor(m.soft_color||'#f59e0b'); setSoftTextColor(m.soft_text_color||'#ffffff'); setSoftStyle(m.soft_style||'banner'); setSoftOnce(!!m.soft_once) }
      } else if (e?.detail?.detail) {
        setHardText({ title: '服务器维护中', body: e.detail.detail, color: '#f59e0b', textColor: '#ffffff', image: '', style: 'popup' })
      } else await fetchMsg()
    }
    const h2 = async () => {
      setSoftMaintenance(true)
      await fetchMsg()
    }
    const hClear = () => { setMaintenance(false); setSoftMaintenance(false) }
    const hWs = (e: CustomEvent) => {
      const { mode, msg } = e.detail
      if (mode === 'hard') h1({ detail: { msg } } as any)
      else if (mode === 'soft') { if (msg) applySoftData(msg); setSoftMaintenance(true) }
      else if (mode === 'none') hClear()
    }
    const applySoftData = (d: any) => {
      if (d.soft_text) { setSoftText(d.soft_text); localStorage.setItem('maintenance_soft', d.soft_text) }
      if (d.soft_color) { setSoftColor(d.soft_color); localStorage.setItem('maintenance_soft_color', d.soft_color) }
      if (d.soft_text_color) { setSoftTextColor(d.soft_text_color); localStorage.setItem('maintenance_soft_text_color', d.soft_text_color) }
      if (d.soft_style) { setSoftStyle(d.soft_style) }
      setSoftOnce(!!d.soft_once)
    }
    window.addEventListener('maintenance-mode' as any, h1 as any)
    window.addEventListener('maintenance-soft' as any, h2 as any)
    window.addEventListener('maintenance-cleared', hClear)
    window.addEventListener('ws-maintenance-update' as any, hWs as any)
    return () => {
      window.removeEventListener('maintenance-mode' as any, h1 as any)
      window.removeEventListener('maintenance-soft' as any, h2 as any)
      window.removeEventListener('maintenance-cleared', hClear)
      window.removeEventListener('ws-maintenance-update' as any, hWs as any)
    }
  }, [])

  // 桌面通知：标签页标题未读计数 + 任务栏闪烁（所有页面生效）
  useDesktopNotification()

  // 聊天详情页（群聊/私信）隐藏底部导航栏，给输入框更多空间
  const hideNav = /^\/chat\/(dm\/[^/]+|\d+)/.test(location.pathname)
                   || /^\/dm\/[^/]+/.test(location.pathname)

  // 沉浸界面（世界视界）：隐藏侧边栏，全屏沉浸
  const hideSidebar = /^\/world-view\//.test(location.pathname)

  // 沉浸界面：悬浮图标切换侧边栏（覆盖式，不挤压世界画面）
  const [sidebarOverlay, setSidebarOverlay] = useState(false)
  const [floatingIconHidden, setFloatingIconHidden] = useState(false)
  useEffect(() => { setSidebarOverlay(false); setFloatingIconHidden(false) }, [location.pathname])

  // 世界代码 → 宿主 UI 桥（window.WorldUI，postMessage）：控制侧边栏/悬浮图标
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const d = e.data
      if (!d || d.type !== 'world_ui' || !d.action) return
      switch (d.action) {
        case 'toggle_sidebar': setSidebarOverlay((v) => !v); break
        case 'show_sidebar': setSidebarOverlay(true); break
        case 'hide_sidebar': setSidebarOverlay(false); break
        case 'hide_floating_icon': setFloatingIconHidden(true); break
        case 'show_floating_icon': setFloatingIconHidden(false); break
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      {/* ── 桌面端侧栏（沉浸界面默认收起） ── */}
      {!hideSidebar && (
        <div className="hidden md:block shrink-0">
          <Sidebar />
        </div>
      )}

      {/* ── 沉浸界面：侧边栏悬浮开关（世界代码可经 WorldUI 隐藏） ── */}
      {hideSidebar && !floatingIconHidden && (
        sidebarOverlay ? (
          <>
            {/* 点击外部关闭 */}
            <div className="fixed inset-0 z-30" onClick={() => setSidebarOverlay(false)} />
            {/* 覆盖式侧边栏：flex 容器宽度跟随侧边栏（含其内部折叠），收起标签固定在右缘 */}
            <div className="fixed inset-y-0 left-0 z-40 flex">
              <div className="h-full shadow-2xl border-r border-border">
                <Sidebar translucent onClose={() => setSidebarOverlay(false)} />
              </div>
              <button
                onClick={() => setSidebarOverlay(false)}
                className="h-full w-5 flex items-center justify-center bg-surface/70 border-r border-border text-textMuted hover:text-textPrimary transition-colors"
                title="收起侧边栏"
              >
                «
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={() => setSidebarOverlay(true)}
            className="fixed left-0 top-1/2 -translate-y-1/2 z-50 flex items-center px-1 py-6 rounded-r-xl bg-surface border border-l-0 border-border text-textMuted hover:text-textPrimary hover:bg-elevated shadow-lg transition-colors"
            title="显示侧边栏"
          >
            »
          </button>
        )
      )}

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
      {/* 聊天详情页（hideNav）内部自己管理滚动（消息列表 flex-1 overflow-y-auto），main 不滚动，
          避免任何 scrollIntoView 连带滚动 main 把标题栏滚出视口；其他页面保持 overflow-y-auto */}
      <main className={`flex-1 min-w-0 bg-canvas ${hideNav ? 'overflow-hidden pb-0' : 'overflow-y-auto pb-14 md:pb-0'}`}>
        <Suspense fallback={
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
          </div>
        }>
          <Outlet context={{ openDrawer: () => setDrawerOpen(true), closeDrawer: () => setDrawerOpen(false) }} />
        </Suspense>
      </main>

      {/* ── 移动端底部导航（聊天详情页隐藏） ── */}
      {!hideNav && <MobileNav closeDrawer={() => setDrawerOpen(false)} />}

      {/* ── 全局弹窗 ── */}
      <BalancePromptModal />

      {/* 软维护——顶栏 */}
      {softMaintenance && !(softOnce && sessionStorage.getItem('maint_soft_done')) && softStyle === 'banner' && (
        <div className="fixed top-0 left-0 right-0 z-[65] text-xs text-center py-2 px-4 font-medium flex items-center justify-center gap-2" style={{ backgroundColor: softColor, color: softTextColor }}>
          <span>{softText}</span>
          <button onClick={() => { setSoftMaintenance(false); if (softOnce) sessionStorage.setItem('maint_soft_done', '1') }}
            className="shrink-0 px-2 py-0.5 rounded text-[10px] opacity-80 hover:opacity-100 transition-opacity" style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}><X size={12} /></button>
        </div>
      )}
      {/* 软维护——弹窗 */}
      {softMaintenance && !(softOnce && sessionStorage.getItem('maint_soft_done')) && softStyle === 'popup' && (
        <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4" onClick={() => { setSoftMaintenance(false); if (softOnce) sessionStorage.setItem('maint_soft_done', '1') }}>
          <div className="bg-surface rounded-xl p-5 max-w-xs w-full text-center shadow-xl border border-border/50" onClick={e => e.stopPropagation()}>
            <div className="text-sm mb-3">{softText}</div>
            <button onClick={() => { setSoftMaintenance(false); if (softOnce) sessionStorage.setItem('maint_soft_done', '1') }}
              className="px-4 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-90" style={{ backgroundColor: softColor, color: softTextColor }}>知道了</button>
          </div>
        </div>
      )}

      {/* 硬维护——顶栏 */}
      {maintenance && hardText.style === 'banner' && (
        <div className="fixed top-0 left-0 right-0 z-[70] text-xs text-center py-2 px-4 font-medium flex items-center justify-center gap-2" style={{ backgroundColor: hardText.color, color: hardText.textColor }}>
          <span>{hardText.title} · {hardText.body}</span>
          <button onClick={() => setMaintenance(false)}
            className="shrink-0 px-2 py-0.5 rounded text-[10px] opacity-80 hover:opacity-100 transition-opacity" style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}><X size={12} /></button>
        </div>
      )}
      {/* 硬维护——弹窗 */}
      {maintenance && hardText.style !== 'banner' && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-surface rounded-xl p-6 max-w-sm w-full text-center shadow-xl border border-border/50">
            <Wrench size={36} className="mx-auto mb-3" style={{ color: hardText.color }} />
            <h2 className="text-base font-semibold mb-2" style={{ color: hardText.color }}>{hardText.title}</h2>
            <p className="text-sm text-textSecondary mb-4">{hardText.body}</p>
            {hardText.image && !imgError && (
              <img src={hardText.image} alt="" className="w-24 h-24 object-contain mx-auto mb-4 rounded-lg" onError={() => setImgError(true)} />
            )}
            <button onClick={() => setMaintenance(false)}
              className="px-5 py-2 text-sm rounded-lg font-medium transition-opacity hover:opacity-90" style={{ backgroundColor: hardText.color, color: hardText.textColor }}>知道了</button>
          </div>
        </div>
      )}
    </div>
  )
}
