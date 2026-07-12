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
  const [hardText, setHardText] = useState({ title: '正在更新', body: '服务器正在更新，稍等一下就好~', color: '#f59e0b', textColor: '#ffffff', image: '', style: 'popup' })
  const [softMaintenance, setSoftMaintenance] = useState(false)
  const [softText, setSoftText] = useState('服务器正在调整，功能可能偶尔不稳定')
  const [softColor, setSoftColor] = useState('#f59e0b')
  const [softTextColor, setSoftTextColor] = useState('#ffffff')
  const [softStyle, setSoftStyle] = useState('banner')
  const [softOnce, setSoftOnce] = useState(false)
  const [imgError, setImgError] = useState(false)
  const location = useLocation()

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
      {softMaintenance && !(softOnce && sessionStorage.getItem('maint_soft_done')) && softStyle === 'banner' && (
        <div className="fixed top-0 left-0 right-0 z-[65] text-xs text-center py-1.5 px-4 font-medium" style={{ backgroundColor: softColor, color: softTextColor }}>
          {softText}
          <button onClick={() => { setSoftMaintenance(false); if (softOnce) sessionStorage.setItem('maint_soft_done', '1') }} className="ml-2 underline opacity-80 hover:opacity-100">关闭</button>
        </div>
      )}
      {softMaintenance && !(softOnce && sessionStorage.getItem('maint_soft_done')) && softStyle === 'popup' && (
        <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
          <div className="bg-surface rounded-2xl p-6 max-w-sm w-full text-center shadow-2xl border border-border">
            <p className="text-sm text-textSecondary">{softText}</p>
            <button onClick={() => { setSoftMaintenance(false); if (softOnce) sessionStorage.setItem('maint_soft_done', '1') }} className="mt-4 px-4 py-1.5 rounded-lg text-xs font-medium" style={{ backgroundColor: softColor, color: softTextColor }}>知道了</button>
          </div>
        </div>
      )}

      {/* 硬维护（API 503）——弹窗 / 顶栏 */}
      {maintenance && hardText.style === 'banner' && (
        <div className="fixed top-0 left-0 right-0 z-[70] text-xs text-center py-1.5 px-4 font-medium" style={{ backgroundColor: hardText.color, color: hardText.textColor }}>
          {hardText.title} · {hardText.body}
          <button onClick={() => setMaintenance(false)} className="ml-2 underline opacity-80 hover:opacity-100">关闭</button>
        </div>
      )}
      {maintenance && hardText.style !== 'banner' && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-surface rounded-2xl p-6 max-w-sm w-full text-center shadow-2xl border border-border">
            <Wrench size={40} className="mx-auto mb-3" style={{ color: hardText.color }} />
            <h2 className="text-lg font-semibold mb-2" style={{ color: hardText.color }}>{hardText.title}</h2>
            <p className="text-sm text-textSecondary mb-3">{hardText.body}</p>
            {hardText.image && !imgError && (
              <img src={hardText.image} alt="" className="w-24 h-24 object-contain mx-auto mb-3 rounded-lg" onError={() => setImgError(true)} />
            )}
            <button onClick={() => setMaintenance(false)} className="px-4 py-2 text-sm rounded-lg hover:opacity-90 transition-colors" style={{ backgroundColor: hardText.color, color: hardText.textColor }}>
              知道了
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
