/**
 * 沉浸界面 — 世界网页全屏渲染
 * 注入 window.WORLD_ID / GROUP_ID / USER_ID 变量后 iframe 加载世界首页
 */
import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight } from 'lucide-react'

export default function WorldViewPage() {
  const { worldId } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const groupId = params.get('group_id')
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [title, setTitle] = useState('沉浸界面')
  const [notFound, setNotFound] = useState(false)

  const wid = Number(worldId)

  // 独立窗口（Tauri）时：关闭窗口；应用内：返回
  const handleBack = () => {
    if ('__TAURI_INTERNALS__' in window) {
      ;(async () => {
        try {
          const { getCurrentWindow } = await import('@tauri-apps/api/window')
          await getCurrentWindow().close()
        } catch { navigate(-1) }
      })()
      return
    }
    navigate(-1)
  }

  useEffect(() => {
    // 注入世界编号变量（世界代码直接读 window.WORLD_ID 等变量）
    const injectVars = () => {
      try {
        const win = iframeRef.current?.contentWindow as any
        if (win) {
          win.WORLD_ID = wid
          win.GROUP_ID = groupId ? Number(groupId) : null
          // USER_ID 由主框架 localStorage 提供
          const me = localStorage.getItem('user_info')
          if (me) {
            try { win.USER_ID = JSON.parse(me).id } catch { /* ignore */ }
          }
        }
      } catch { /* 跨域时忽略 */ }
    }
    const t = setInterval(injectVars, 300)
    setTimeout(() => clearInterval(t), 5000)
    return () => clearInterval(t)
  }, [wid, groupId])

  return (
    <div className="h-screen flex flex-col bg-black">
      {/* 顶栏（沉浸界面最小化干扰） */}
      <div className="flex items-center gap-3 px-4 py-1.5 bg-gray-900/95 text-gray-300 text-sm border-b border-gray-800">
        <button onClick={handleBack} className="inline-flex items-center gap-1 text-gray-400 hover:text-white">
          <ArrowLeft size={14} />
          返回
        </button>
        <span className="font-medium truncate">{title}</span>
        <div className="flex-1" />
        <span className="text-[10px] text-gray-600">WORLD_ID={wid}{groupId ? ` · GROUP_ID=${groupId}` : ''}</span>
      </div>

      {/* 世界渲染区 */}
      <div className="flex-1 relative">
        {notFound ? (
          <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
            这个世界还没有内容，去设计页让群视界机器人生成一个吧
            <button onClick={() => navigate(`/worlds/${wid}/design`)} className="ml-3 inline-flex items-center gap-1 text-primary-400 hover:underline">
              打开设计页 <ArrowRight size={13} />
            </button>
          </div>
        ) : (
          <iframe
            ref={iframeRef}
            src={`/world/${wid}/preview${groupId ? `?group_id=${groupId}` : ''}`}
            className="w-full h-full bg-white"
            title="世界"
            onLoad={(e) => {
              const doc = (e.target as HTMLIFrameElement).contentDocument
              if (doc) setTitle(doc.title || '沉浸界面')
            }}
            onError={() => setNotFound(true)}
          />
        )}
      </div>
    </div>
  )
}
