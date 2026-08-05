/**
 * 群视界世界列表页 — 创建世界 / 绑定群聊 / 进入设计页
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

interface World {
  id: number
  name: string
  description: string
  status: string
  time_flow_rate: number
  bindings: { entity_type: string; entity_id: number }[]
}

export default function WorldsPage() {
  const navigate = useNavigate()
  const [worlds, setWorlds] = useState<World[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => {
    try {
      const list = await api.get<World[]>('/worlds')
      setWorlds(list || [])
    } catch (e: any) {
      setMsg(`加载失败: ${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const create = async () => {
    if (!name.trim()) return
    try {
      const w = await api.post<World>('/worlds', { name, description, time_flow_rate: 1.0 })
      setShowCreate(false)
      setName('')
      setDescription('')
      navigate(`/worlds/${w.id}/design`)
    } catch (e: any) {
      setMsg(`创建失败: ${e?.message || e}`)
    }
  }

  const [bindWorld, setBindWorld] = useState<World | null>(null)
  const [groupList, setGroupList] = useState<{ id: number; name: string }[]>([])

  const openBindModal = async (world: World) => {
    setBindWorld(world)
    try {
      const groups = await api.get<{ id: number; name: string }[]>('/groups')
      setGroupList(groups || [])
    } catch { setGroupList([]) }
  }

  const doBind = async (groupId: number) => {
    if (!bindWorld) return
    try {
      await api.post(`/worlds/${bindWorld.id}/bind`, { entity_type: 'group', entity_id: groupId })
      setBindWorld(null)
      load()
    } catch (e: any) {
      setMsg(`绑定失败: ${e?.message || e}`)
    }
  }

  const toggleStatus = async (world: World) => {
    try {
      await api.post(`/worlds/${world.id}/${world.status === 'active' ? 'sleep' : 'wake'}`)
      load()
    } catch { /* ignore */ }
  }

  if (loading) return <div className="flex items-center justify-center h-screen text-gray-400">加载中...</div>

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">🌐 群视界</h1>
          <p className="text-sm text-gray-500 mt-1">给群聊一个可编程的世界——游戏、聊天室、小说互动，什么都行</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="px-4 py-2 bg-primary-500 text-white rounded-lg text-sm">
          + 创建世界
        </button>
      </div>

      {msg && <div className="text-sm text-yellow-500 mb-4">{msg}</div>}

      {showCreate && (
        <div className="bg-gray-800 rounded-lg p-4 mb-6 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="世界名称（如：木头大陆）"
            className="w-full bg-gray-900 px-3 py-2 rounded text-sm outline-none"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="世界观简介（可选）"
            rows={2}
            className="w-full bg-gray-900 px-3 py-2 rounded text-sm outline-none resize-none"
          />
          <button onClick={create} className="px-4 py-2 bg-primary-500 text-white rounded-lg text-sm">创建并进入设计页</button>
        </div>
      )}

      {worlds.length === 0 && !showCreate && (
        <div className="text-center text-gray-600 py-20 text-sm">
          还没有世界<br />
          <span className="text-gray-700">创建一个，然后绑定群聊，群成员就能"在沉浸界面打开"了</span>
        </div>
      )}

      <div className="space-y-3">
        {worlds.map((w) => (
          <div key={w.id} className="bg-gray-800 rounded-lg p-4 flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium truncate">{w.name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${w.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-600 text-gray-400'}`}>
                  {w.status === 'active' ? '活跃' : '休眠'}
                </span>
              </div>
              {w.description && <div className="text-xs text-gray-500 truncate mt-0.5">{w.description}</div>}
              <div className="text-[10px] text-gray-600 mt-1">
                入口: {w.bindings?.length ? w.bindings.map((b) => `${b.entity_type}#${b.entity_id}`).join(', ') : '未绑定'}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button onClick={() => openBindModal(w)} className="text-xs px-3 py-1.5 bg-gray-700 rounded hover:bg-gray-600">绑定群</button>
              <button onClick={() => toggleStatus(w)} className="text-xs px-3 py-1.5 bg-gray-700 rounded hover:bg-gray-600">
                {w.status === 'active' ? '休眠' : '唤醒'}
              </button>
              <button
                onClick={() => navigate(`/worlds/${w.id}/design`)}
                className="text-xs px-3 py-1.5 bg-primary-500 text-white rounded hover:bg-primary-400"
              >
                设计页 →
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* 绑定群弹窗：群列表选择 */}
      {bindWorld && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setBindWorld(null)}>
          <div className="bg-gray-800 rounded-xl p-5 w-96 max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="font-medium mb-3">给「{bindWorld.name}」绑定群聊</div>
            {groupList.length === 0 ? (
              <div className="text-sm text-gray-500 py-6 text-center">
                你还没有群聊<br />
                <span className="text-xs">先去聊天里创建一个群再回来绑定</span>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-1.5">
                {groupList.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => doBind(g.id)}
                    className="w-full text-left px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm flex items-center gap-2"
                  >
                    <span>💬</span>
                    <span className="truncate">{g.name}</span>
                    <span className="text-[10px] text-gray-500 ml-auto">#{g.id}</span>
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setBindWorld(null)} className="mt-3 text-xs text-gray-500 hover:text-gray-300">取消</button>
          </div>
        </div>
      )}
    </div>
  )
}
