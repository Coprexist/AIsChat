/**
 * 沉浸界面 — 世界网页全屏渲染
 * 注入 window.WORLD_ID / GROUP_ID / USER_ID 变量后 iframe 加载世界首页
 */
import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export default function WorldViewPage() {
  const { worldId } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const groupId = params.get('group_id')
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [title, setTitle] = useState('沉浸界面')
  const [notFound, setNotFound] = useState(false)

  const wid = Number(worldId)

  // 返回：Tauri 关窗口；其他一律切回「标准界面」（群聊优先，其次世界列表），不依赖关窗
  const handleBack = () => {
    if ('__TAURI_INTERNALS__' in window) {
      ;(async () => {
        try {
          const { getCurrentWindow } = await import('@tauri-apps/api/window')
          await getCurrentWindow().close()
        } catch { navigate('/worlds') }
      })()
      return
    }
    if (window.history.length > 1) {
      navigate(-1)
    } else if (groupId) {
      // 标准界面 = 该世界绑定的群聊
      navigate(`/chat/gm/${groupId}`)
    } else {
      navigate('/worlds')
    }
  }

  useEffect(() => {
    // 注入世界编号变量（世界代码直接读 window.WORLD_ID 等变量）
    const injectVars = () => {
      try {
        const win = iframeRef.current?.contentWindow as any
        if (win) {
          win.WORLD_ID = wid
          win.GROUP_ID = groupId ? Number(groupId) : null
          // USER_ID/USER_NAME/USER_AVATAR 由主框架 localStorage 提供（身份块/世界代码用）
          const me = localStorage.getItem('user_info')
          if (me) {
            try {
              const u = JSON.parse(me)
              win.USER_ID = u.id
              win.USER_NAME = u.username || ''
              win.USER_AVATAR = u.avatar_url || ''
            } catch { /* ignore */ }
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
          <ChevronLeft size={14} />
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
              打开设计页 <ChevronRight size={13} />
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
