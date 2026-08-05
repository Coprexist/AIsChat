/**
 * 群视界设计页 — 世界文件管理 + 界面预览 + 群视界机器人对话
 *
 * 布局参考 TRAE/Cursor：左（文件树/预览）右（对话窗口）
 * 普通用户可直接用；专业用户可编辑代码（专业模式）。
 */
import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Folder, FolderOpen, FileText, FileCode, FileJson, FileImage, FileAudio, FileVideo, File, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import MarkdownContent from '../components/shared/MarkdownContent'
import CodeRenderer from '../components/shared/CodeRenderer'
import { getCodeLang, isMarkdownFile } from '../utils/mime'
import { useResizableSidebar } from '../hooks/useResizableSidebar'

// 文件类型图标（与主界面风格一致）
function fileTypeIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp'].includes(ext)) return <FileImage size={13} className="text-mint-400 shrink-0" />
  if (['mp3', 'wav', 'ogg'].includes(ext)) return <FileAudio size={13} className="text-primary-400 shrink-0" />
  if (['mp4', 'webm'].includes(ext)) return <FileVideo size={13} className="text-rose-400 shrink-0" />
  if (['json'].includes(ext)) return <FileJson size={13} className="text-amber-400 shrink-0" />
  if (['md', 'txt'].includes(ext)) return <FileText size={13} className="text-textSecondary shrink-0" />
  if (['html', 'htm', 'css', 'js', 'ts', 'jsx', 'tsx', 'py', 'xml', 'yaml', 'yml', 'sh'].includes(ext)) return <FileCode size={13} className="text-primary-400 shrink-0" />
  return <File size={13} className="text-textMuted shrink-0" />
}

// ── 打字机效果：文本逐字显示（参考大同互动逐 token 渲染，简化版） ──

interface World {
  id: number
  name: string
  description: string
  status: string
  time_flow_rate: number
  world_time: string | null
  bindings: { entity_type: string; entity_id: number }[]
  agents: { agent_id: number; role: string }[]
  // 群视界机器人 = 世界配置（非 agent、无账号），身份 = world-{id}
  creator: {
    id: string
    name: string
    system_prompt: string
    model: string | null
    temperature: number
    top_p: number
    thinking: boolean
    max_tool_rounds: number
    tools: string[]
  } | null
}

interface WorldFile {
  path: string
  size: number
}

// 世界 AI 对话消息（世界级会话，非 DM；reasoning = 思考过程；tool = 工具执行结果；note = 中间叙述）
interface ChatMsg {
  id: number
  role: 'user' | 'ai' | 'tool' | 'note'
  content: string
  reasoning?: string
  error?: boolean
  created_at?: string
}

export default function WorldDesignPage() {
  const { worldId } = useParams()
  const navigate = useNavigate()
  const wid = Number(worldId)

  // 可拖拽面板（复用侧边栏 hook：左=文件树，右=对话）
  const fileTreeRef = useRef<HTMLDivElement>(null)
  const chatPanelRef = useRef<HTMLDivElement>(null)
  const { sidebarWidth: fileWidth, handleResizeStart: fileResizeStart } = useResizableSidebar('world_files_width', fileTreeRef, { min: 160, max: 400 })
  const { sidebarWidth: chatWidth, handleResizeStart: chatResizeStart } = useResizableSidebar('world_chat_width', chatPanelRef, { side: 'right', min: 320, max: 800 })

  const [world, setWorld] = useState<World | null>(null)
  const [files, setFiles] = useState<WorldFile[]>([])
  const [currentFile, setCurrentFile] = useState<string>('')
  const [content, setContent] = useState('')
  const [mode, setMode] = useState<'files' | 'preview'>('files')
  const [previewKey, setPreviewKey] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  // 世界 AI 对话状态（世界级会话）
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const [chatProcessing, setChatProcessing] = useState(false)  // 刷新后恢复：后台轮次仍在执行
  const chatProcessingRef = useRef(false)
  const [chatHasMore, setChatHasMore] = useState(false)
  const [chatLoadingOlder, setChatLoadingOlder] = useState(false)
  const chatListRef = useRef<HTMLDivElement>(null)
  const msgSeqRef = useRef(0)  // 本地临时消息 id（负数，避免与 DB id 碰撞）

  // 世界 AI 配置表单（单独表单，不属于 agent）
  const [showCreatorForm, setShowCreatorForm] = useState(false)
  const [creatorForm, setCreatorForm] = useState({ name: '', system_prompt: '', model: '', temperature: 0.8, thinking: false, max_tool_rounds: 50 })
  const [creatorSaving, setCreatorSaving] = useState(false)
  // 2.7：LLM 用量/缓存命中率
  const [usageStats, setUsageStats] = useState<{ total_calls: number; prompt_tokens: number; completion_tokens: number; cached_tokens: number; cache_hit_rate_pct: number } | null>(null)

  // 当前文件内联渲染：md 渲染 + 查看原文；html/代码高亮渲染；图片直接显示（不用弹窗）
  const [viewMode, setViewMode] = useState<'edit' | 'render'>('edit')
  const fileExt = currentFile?.split('.').pop()?.toLowerCase() ?? ''
  const isMdFile = isMarkdownFile(currentFile ?? '', '')
  const fileCodeLang = currentFile ? getCodeLang(currentFile, '') : ''
  const isImgFile = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp'].includes(fileExt)
  const canRender = !!(isMdFile || fileCodeLang || isImgFile)

  // ── 加载世界 + 文件树 ──
  const load = useCallback(async () => {
    try {
      const w = await api.get<World>(`/worlds/${wid}`)
      setWorld(w)
      setCreatorForm({
        name: w.creator?.name ?? '',
        system_prompt: w.creator?.system_prompt ?? '',
        model: w.creator?.model ?? '',
        temperature: w.creator?.temperature ?? 0.8,
        thinking: w.creator?.thinking ?? false,
        max_tool_rounds: w.creator?.max_tool_rounds ?? 50,
      })
      const f = await api.get<{ files: WorldFile[] }>(`/worlds/${wid}/files`)
      setFiles(f.files || [])
      // 2.7：缓存命中统计（失败静默，不影响主流程）
      try {
        const u = await api.get<{ total_calls: number; prompt_tokens: number; completion_tokens: number; cached_tokens: number; cache_hit_rate_pct: number }>(`/worlds/${wid}/usage`)
        setUsageStats(u)
      } catch { /* ignore */ }
      // 默认选中第一个文件
      if (f.files?.length && !currentFile) {
        selectFile(f.files[0].path)
      }
    } catch (e: any) {
      setMsg(`加载失败: ${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }, [wid])

  useEffect(() => { load() }, [load])

  // ── 文件操作 ──
  const selectFile = async (path: string) => {
    setCurrentFile(path)
    // 能内联渲染的文件默认渲染视图（md/html/代码/图片），其余默认编辑
    const ext = path.split('.').pop()?.toLowerCase() ?? ''
    const imgLike = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp'].includes(ext)
    setViewMode((isMarkdownFile(path, '') || getCodeLang(path, '') || imgLike) ? 'render' : 'edit')
    try {
      const r = await api.get<{ content: string | null; binary: boolean }>(
        `/worlds/${wid}/files/content?path=${encodeURIComponent(path)}`,
      )
      setContent(r.binary ? '(二进制文件，不可编辑)' : (r.content || ''))
    } catch { setContent('') }
  }

  // ── 记录懒通知（改动/报错都走同一条通道，agent 下次对话时收到） ──
  const pushNotice = async (file: string, location: string, summary: string) => {
    if (!world?.creator) return   // 群视界机器人是世界的默认 AI，收件人不用指定
    try {
      await api.post(`/worlds/${wid}/notices`, { file, location, summary })
    } catch { /* 通知失败不影响主流程 */ }
  }

  const saveFile = async () => {
    if (!currentFile) return
    setSaving(true)
    try {
      await api.put(`/worlds/${wid}/files`, { path: currentFile, content })
      await pushNotice(currentFile, 'manual-edit', `用户手动编辑了 ${currentFile}`)
      setPreviewKey((k) => k + 1) // 刷新预览
      setMsg('✅ 已保存')
    } catch (e: any) {
      const errMsg = `保存失败: ${e?.message || e}`
      // 报错也进懒通知，agent 下次对话能看到
      await pushNotice(currentFile || 'unknown', 'save-error', errMsg)
      setMsg(errMsg)
    } finally {
      setSaving(false)
    }
  }

  const createFile = async () => {
    const name = prompt('新文件名（如 about.html）：')
    if (!name) return
    try {
      await api.put(`/worlds/${wid}/files`, { path: name, content: '' })
      await load()
      selectFile(name)
    } catch (e: any) {
      setMsg(`创建失败: ${e?.message || e}`)
    }
  }

  // ── 上传（先选择目标位置，再选文件） ──
  const fileInputRef = useRef<HTMLInputElement>(null)
  const handleUploadPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''  // 允许重复选同一文件
    if (!f) return
    // 先选择位置：默认当前选中文件所在目录
    const dir = currentFile?.includes('/') ? currentFile.slice(0, currentFile.lastIndexOf('/') + 1) : ''
    const target = prompt(`上传到哪个路径？（当前目录：${dir || '/'}）`, dir + f.name)
    if (!target) return
    try {
      const fd = new FormData()
      fd.append('file', f)
      fd.append('path', target.replace(/^\/+/, ''))
      await api.post(`/worlds/${wid}/files/upload`, fd)
      await load()
      selectFile(target.replace(/^\/+/, ''))
      setMsg('✅ 已上传')
    } catch (err: any) {
      setMsg(`上传失败: ${err?.message || err}`)
    }
  }

  // ── 删除（AI 侧已有 file_delete 工具，这里补前端入口） ──
  const deleteFile = async (path: string) => {
    if (!confirm(`删除 ${path}？`)) return
    try {
      await api.delete(`/worlds/${wid}/files?path=${encodeURIComponent(path)}`)
      if (currentFile === path) setCurrentFile('')
      await load()
      setMsg(`✅ 已删除 ${path}`)
    } catch (e: any) {
      setMsg(`删除失败: ${e?.message || e}`)
    }
  }

  // ── 文件树（按目录层级构建，文件夹可折叠） ──
  interface TreeNode {
    name: string
    path: string
    children: TreeNode[]
    isDir: boolean
  }
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set())

  const fileTree = useMemo(() => {
    const root: TreeNode = { name: '', path: '', children: [], isDir: true }
    for (const f of files) {
      const parts = f.path.split('/')
      let node = root
      let acc = ''
      for (let i = 0; i < parts.length; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i]
        const isLast = i === parts.length - 1
        let child = node.children.find((c) => c.name === parts[i] && c.isDir === !isLast)
        if (!child) {
          child = { name: parts[i], path: acc, children: [], isDir: !isLast }
          node.children.push(child)
        }
        node = child
      }
    }
    const sortNodes = (nodes: TreeNode[]) => {
      nodes.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1))
      nodes.forEach((n) => sortNodes(n.children))
    }
    sortNodes(root.children)
    return root
  }, [files])

  const toggleDir = (path: string) => {
    setCollapsedDirs((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const renderTree = (nodes: TreeNode[], depth: number): JSX.Element[] =>
    nodes.map((n) => (
      <div key={n.path}>
        {n.isDir ? (
          <>
            <button
              onClick={() => toggleDir(n.path)}
              style={{ paddingLeft: 6 + depth * 14 }}
              className="flex items-center gap-1 w-full text-left text-xs py-1 pr-2 rounded transition-colors hover:bg-elevated text-textSecondary"
              title={n.path}
            >
              <span className="text-[10px] w-3 shrink-0">{collapsedDirs.has(n.path) ? '▶' : '▼'}</span>
              {collapsedDirs.has(n.path) ? <Folder size={13} className="text-textMuted shrink-0" /> : <FolderOpen size={13} className="text-primary-400 shrink-0" />}
              <span className="truncate">{n.name}</span>
            </button>
            {!collapsedDirs.has(n.path) && renderTree(n.children, depth + 1)}
          </>
        ) : (
          <div key={n.path} className="group flex items-center">
            <button
              onClick={() => selectFile(n.path)}
              style={{ paddingLeft: 24 + depth * 14 }}
              className={`flex items-center gap-1 flex-1 min-w-0 text-left text-xs py-1 pr-1 rounded truncate transition-colors ${currentFile === n.path ? 'bg-primary-500/20 text-primary-300' : 'hover:bg-elevated text-textSecondary'}`}
              title={n.path}
            >
              <span className="shrink-0">{fileTypeIcon(n.name)}</span>
              <span className="truncate">{n.name}</span>
            </button>
            <button
              onClick={(ev) => { ev.stopPropagation(); deleteFile(n.path) }}
              className="hidden group-hover:flex shrink-0 items-center justify-center w-6 h-6 text-textMuted hover:text-rose-400 transition-colors"
              title="删除此文件"
            >
              <Trash2 size={13} />
            </button>
          </div>
        )}
      </div>
    ))

  // ── 世界 AI 对话（世界级会话，非 DM；账单人 = 世界主人） ──
  const loadChat = useCallback(async (opts?: { before_id?: number; append?: boolean }) => {
    try {
      const q = opts?.before_id ? `?before_id=${opts.before_id}&limit=30` : '?limit=30'
      // 翻页时记录原滚动位置（prepend 后补回）
      const listEl = chatListRef.current
      const prevScrollHeight = listEl?.scrollHeight ?? 0
      const r = await api.get<{ messages: ChatMsg[]; has_more: boolean }>(`/worlds/${wid}/chat${q}`)
      if (opts?.append && opts.before_id) {
        setChatMsgs((msgs) => [...(r.messages || []), ...msgs])
        requestAnimationFrame(() => {
          const el = chatListRef.current
          if (el) el.scrollTop = el.scrollHeight - prevScrollHeight
        })
      } else {
        setChatMsgs(r.messages || [])
        // 默认滚到消息末尾
        requestAnimationFrame(() => {
          const el = chatListRef.current
          if (el) el.scrollTop = el.scrollHeight
        })
      }
      setChatHasMore(!!r.has_more)
    } catch { /* 历史拉不到不阻塞 */ }
  }, [wid])

  useEffect(() => { loadChat() }, [loadChat])

  // 刷新后恢复「思考中」状态：world_turn 在服务器端继续执行，前端状态丢失后轮询恢复
  useEffect(() => {
    if (!wid) return
    let timer: number | undefined
    const check = async () => {
      try {
        const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
        const r = await fetch(`${base}/worlds/${wid}/chat/status`, {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
        })
        const s = await r.json()
        if (s && s.processing) {
          chatProcessingRef.current = true
          setChatProcessing(true)
          timer = window.setTimeout(check, 4000)
        } else {
          if (chatProcessingRef.current) {
            chatProcessingRef.current = false
            setChatProcessing(false)
            loadChat()  // 处理完成：拉最新历史（含 AI 回复）
          }
        }
      } catch { /* 失败静默重试 */ timer = window.setTimeout(check, 8000) }
    }
    chatProcessingRef.current = false
    check()
    return () => { if (timer) clearTimeout(timer) }
  }, [wid])

  // 滚到顶 → 加载更早消息（主聊天同款无限滚动）
  const loadOlder = useCallback(async () => {
    if (chatLoadingOlder || !chatHasMore || chatMsgs.length === 0) return
    const oldest = chatMsgs[0].id
    // 历史消息来自 DB，id 为正数；本地临时负数消息跳过
    if (!oldest || oldest < 0) return
    setChatLoadingOlder(true)
    try {
      await loadChat({ before_id: oldest, append: true })
    } finally {
      setChatLoadingOlder(false)
    }
  }, [chatLoadingOlder, chatHasMore, chatMsgs, loadChat])

  const handleChatScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollTop < 30) loadOlder()
  }, [loadOlder])

  const sendChat = async () => {
    const text = chatInput.trim()
    if (!text || chatSending) return
    setChatSending(true)
    setChatInput('')
    const userMsgId = -(++msgSeqRef.current)
    setChatMsgs((msgs) => [...msgs, { id: userMsgId, role: 'user', content: text }])

    // 服务器端轮次（不依赖本页面）：入队 → 订阅直播（断开自动重连）
    let full = ''
    let reasoning = ''
    let streamTargetId: number | null = null  // 当前流式气泡（[TOOL] 后封存、开新气泡）
    const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
    const authHeaders = {
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      'Content-Type': 'application/json',
    }
    try {
      // 1. 入队（返回 turn_id；若前面有消息在跑会排队）
      const r = await api.post<{ turn_id: string; queued: boolean; position: number }>(`/worlds/${wid}/chat`, { message: text })
      if (r.queued) {
        setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'tool', content: `⏳ 已排队（前面还有 ${r.position} 条在跑）` }])
      }

      // 2. 订阅直播（SSE）；断开自动重连加入直播，最多 5 次
      let gotDone = false
      for (let attempt = 0; attempt < 5 && !gotDone; attempt++) {
        const streamResp = await fetch(`${base}/worlds/${wid}/chat/stream?turn_id=${r.turn_id}`, { headers: authHeaders })
        if (!streamResp.ok || !streamResp.body) throw new Error(`直播连接失败(${streamResp.status})`)
        const reader = streamResp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        // 首次内容/思考到达时开气泡（不在发消息时预建，避免空气泡）
        const ensureBubble = () => {
          if (streamTargetId !== null) return
          const id = -(++msgSeqRef.current)
          streamTargetId = id
          setChatMsgs((msgs) => [...msgs, { id, role: 'ai', content: '', reasoning: '' }])
        }
        // rAF 节流渲染（只更新当前流式气泡）
        let renderPending = false
        const scheduleRender = () => {
          if (renderPending) return
          renderPending = true
          requestAnimationFrame(() => {
            renderPending = false
            if (streamTargetId === null) return
            setChatMsgs((msgs) => msgs.map((m) => m.id === streamTargetId ? { ...m, content: full, reasoning } : m))
          })
        }
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()!
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6)
            if (payload === '[DONE]') { gotDone = true; break }
            if (payload.startsWith('[ERROR]')) throw new Error(payload.slice(7))
            if (payload.startsWith('[TOOL]')) {
              try {
                const t = JSON.parse(payload.slice(6))
                // 封存当前叙述气泡（内容已渲染），后续内容开新气泡；full/reasoning 重置避免拼接
                streamTargetId = null
                full = ''
                reasoning = ''
                setChatMsgs((msgs) => [...msgs, {
                  id: -(++msgSeqRef.current),
                  role: 'tool',
                  content: t.summary || `${t.name} ${t.success ? '执行成功' : '执行失败'}`,
                  error: !t.success,
                }])
              } catch { /* 解析失败忽略 */ }
              continue
            }
            if (payload.startsWith('[REASONING]')) {
              reasoning += payload.slice(11).replace(/\{NL\}/g, '\n')
            } else {
              full += payload.replace(/\{NL\}/g, '\n')
            }
            ensureBubble()
            scheduleRender()
          }
          if (gotDone) break
        }
        if (gotDone) break
        // 连接断开且未完成：稍等重连（重新订阅直播）
        await new Promise((res) => setTimeout(res, 1500 * (attempt + 1)))
      }
      // 用权威历史收尾（含断开期间漏掉的工具气泡/最终回复）；世界信息可能被工具改过，一并刷新
      await loadChat()
      load()
    } catch (e: any) {
      // 出错：独立错误气泡
      const errText = e?.message || '未知错误'
      setChatMsgs((msgs) => streamTargetId === null ? msgs : msgs.map((m) => m.id === streamTargetId ? { ...m, content: '', reasoning: '' } : m))
      setChatMsgs((msgs) => [...msgs, { id: -(++msgSeqRef.current), role: 'ai', content: errText, error: true }])
      setMsg(`发送失败: ${errText}`)
    } finally {
      setChatSending(false)
    }
  }

  // ── 世界 AI 配置表单（单独表单，不属于 agent） ──
  const saveCreator = async () => {
    if (!world?.creator) return
    setCreatorSaving(true)
    try {
      const patch: Record<string, unknown> = {
        name: creatorForm.name,
        system_prompt: creatorForm.system_prompt,
        temperature: creatorForm.temperature,
        thinking: creatorForm.thinking,
        max_tool_rounds: creatorForm.max_tool_rounds,
      }
      if (creatorForm.model.trim()) patch.model = creatorForm.model.trim()
      const updated = await api.put<World['creator']>(`/worlds/${wid}/creator`, patch)
      setWorld((w) => (w ? { ...w, creator: updated } : w))
      setShowCreatorForm(false)
      setMsg('✅ 世界 AI 配置已保存')
    } catch (e: any) {
      setMsg(`保存失败: ${e?.message || e}`)
    } finally {
      setCreatorSaving(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-screen text-textMuted">加载中...</div>
  if (!world) return <div className="p-8 text-textMuted">世界不存在</div>

  return (
    <div className="flex h-screen bg-canvas text-textPrimary">
      {/* ═══ 左栏：文件 / 预览 ═══ */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-border">
        {/* 顶部工具栏 */}
        <div className="flex items-center gap-3 px-4 py-2 bg-surface border-b border-border">
          <button onClick={() => navigate('/worlds')} className="inline-flex items-center gap-1 text-sm text-textMuted hover:text-textPrimary transition-colors">
            <ChevronLeft size={14} />
            世界列表
          </button>
          <span className="font-semibold">{world.name}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${world.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-elevated text-textMuted'}`}>
            {world.status === 'active' ? '活跃' : '休眠'}
          </span>
          <span className="text-xs text-textMuted">流速 x{world.time_flow_rate}</span>
          <div className="flex-1" />
          <button onClick={() => setMode('files')} className={`text-xs px-3 py-1 rounded transition-colors ${mode === 'files' ? 'bg-primary-500 text-white' : 'bg-elevated hover:bg-border'}`}>文件</button>
          <button onClick={() => setMode('preview')} className={`text-xs px-3 py-1 rounded transition-colors ${mode === 'preview' ? 'bg-primary-500 text-white' : 'bg-elevated hover:bg-border'}`}>预览</button>
          {msg && <span className="text-xs text-amber-400">{msg}</span>}
        </div>

        <div className="flex flex-1 min-h-0">
          {/* 文件树（可拖拽调宽） */}
          <div ref={fileTreeRef} style={{ width: fileWidth }} className="shrink-0 bg-surface border-r border-border overflow-y-auto p-2">
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-xs font-medium text-textSecondary">文件</span>
              <span className="flex items-center gap-2">
                <button onClick={() => fileInputRef.current?.click()} className="text-xs text-primary-400 hover:text-primary-300 transition-colors" title="上传文件（先选位置）">⬆️ 上传</button>
                <button onClick={createFile} className="text-xs text-primary-400 hover:text-primary-300 transition-colors" title="新建文件">+ 新建</button>
              </span>
            </div>
            <input ref={fileInputRef} type="file" className="hidden" onChange={handleUploadPick} />
            {files.length === 0 && <div className="text-xs text-textMuted p-2">空世界，点 + 新建或让机器人生成</div>}
            {renderTree(fileTree.children, 0)}
          </div>
          <div onMouseDown={fileResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors" />

          {/* 编辑 / 预览 */}
          <div className="flex-1 min-w-0">
            {mode === 'files' ? (
              <div className="h-full flex flex-col">
                <div className="px-3 py-1.5 text-xs text-textSecondary bg-surface/60 border-b border-border flex justify-between">
                  <span className="truncate">{currentFile || '未选择文件'}</span>
                  {currentFile && (
                    <span className="flex items-center gap-3 shrink-0 ml-3">
                      {canRender && (
                        <button
                          onClick={() => setViewMode((v) => (v === 'render' ? 'edit' : 'render'))}
                          className="text-primary-400 hover:text-primary-300 transition-colors"
                          title={viewMode === 'render' ? '切到原文/编辑' : '切到渲染视图'}
                        >
                          {viewMode === 'render' ? (isMdFile ? '📄 查看原文' : '✏️ 编辑') : '✨ 渲染'}
                        </button>
                      )}
                      {viewMode !== 'render' && (
                        <button onClick={saveFile} disabled={saving} className="text-primary-400 hover:text-primary-300 transition-colors">
                          {saving ? '保存中...' : '💾 保存'}
                        </button>
                      )}
                    </span>
                  )}
                </div>
                {viewMode === 'render' && canRender ? (
                  isImgFile ? (
                    <div className="flex-1 overflow-hidden bg-canvas flex items-center justify-center">
                      <img
                        src={`/world/${wid}/files/${currentFile.split('/').map(encodeURIComponent).join('/')}`}
                        alt={currentFile}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  ) : (
                    <div className="flex-1 overflow-auto bg-canvas [&_code]:!overflow-x-visible [&_code]:!rounded-none [&_code]:!border-0 [&_code]:!p-0 [&_code]:!bg-transparent">
                      <div className="w-full max-w-none text-sm leading-relaxed break-words text-textPrimary p-3 md:p-4">
                        {isMdFile ? (
                          <MarkdownContent content={content} isMine={false} />
                        ) : (
                          <CodeRenderer className={'language-' + fileCodeLang}>{content}</CodeRenderer>
                        )}
                      </div>
                    </div>
                  )
                ) : (
                  <textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    spellCheck={false}
                    className="flex-1 bg-canvas text-sm text-textPrimary p-3 font-mono outline-none resize-none"
                    placeholder="在这里编辑代码…"
                  />
                )}
              </div>
            ) : (
              <div className="h-full flex flex-col">
                <div className="px-3 py-1.5 text-xs text-textSecondary bg-surface/60 border-b border-border flex items-center gap-2">
                  <span className="truncate flex-1">世界预览（/world/{wid}/preview）</span>
                  <button onClick={() => setPreviewKey((k) => k + 1)} className="text-primary-400 hover:text-primary-300 transition-colors shrink-0" title="刷新预览">↻ 刷新</button>
                  <button
                    onClick={() => window.open(`/world-view/${wid}`, '_blank', 'noopener')}
                    className="text-primary-400 hover:text-primary-300 transition-colors shrink-0"
                    title="在沉浸界面新窗口打开"
                  >
                    ↗ 沉浸窗口
                  </button>
                </div>
                <iframe
                  key={previewKey}
                  src={`/world/${wid}/preview`}
                  className="w-full flex-1 bg-white dark:bg-gray-900"
                  title="世界预览"
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ 右栏：世界 AI（配置表单 + 对话窗口，可拖拽调宽） ═══ */}
      <div onMouseDown={chatResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors" />
      <div ref={chatPanelRef} style={{ width: chatWidth }} className="shrink-0 flex flex-col bg-surface min-w-0">
        <div className="px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{world.creator?.name || '群视界机器人'}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted">{world.creator?.id}</span>
            <div className="flex-1" />
            <button
              onClick={() => setShowCreatorForm((v) => !v)}
              className="text-xs px-2 py-1 rounded bg-elevated hover:bg-border text-textSecondary transition-colors"
              title="世界 AI 配置（单独表单，不属于 agent）"
            >
              ⚙️ 配置
            </button>
          </div>
          <div className="text-xs text-textMuted mt-0.5">世界 AI 是世界的配置：让它改界面、加功能</div>
        </div>

        {showCreatorForm && (
          <div className="px-3 py-3 border-b border-border bg-elevated/50 space-y-2">
            <div className="text-xs font-semibold text-textSecondary">群视界机器人配置（世界的，非 agent）</div>
            <div>
              <div className="text-[10px] text-textMuted mb-0.5">名字</div>
              <input
                value={creatorForm.name}
                onChange={(e) => setCreatorForm((f) => ({ ...f, name: e.target.value }))}
                className="w-full bg-elevated text-sm p-1.5 rounded border border-border outline-none focus:border-primary-500/50"
              />
            </div>
            <div>
              <div className="text-[10px] text-textMuted mb-0.5">系统提示词</div>
              <textarea
                value={creatorForm.system_prompt}
                onChange={(e) => setCreatorForm((f) => ({ ...f, system_prompt: e.target.value }))}
                rows={6}
                className="w-full bg-elevated text-xs p-1.5 rounded border border-border outline-none resize-none font-mono focus:border-primary-500/50"
              />
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <div className="text-[10px] text-textMuted mb-0.5">模型（留空 = 全局默认）</div>
                <input
                  value={creatorForm.model}
                  onChange={(e) => setCreatorForm((f) => ({ ...f, model: e.target.value }))}
                  placeholder="如 deepseek-v4-flash"
                  className="w-full bg-elevated text-sm p-1.5 rounded border border-border outline-none focus:border-primary-500/50"
                />
              </div>
              <div className="w-20">
                <div className="text-[10px] text-textMuted mb-0.5">温度</div>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={creatorForm.temperature}
                  onChange={(e) => setCreatorForm((f) => ({ ...f, temperature: Number(e.target.value) }))}
                  className="w-full bg-elevated text-sm p-1.5 rounded border border-border outline-none focus:border-primary-500/50"
                />
              </div>
            </div>
            <div className="flex items-center justify-between bg-elevated/60 rounded p-2">
              <div>
                <div className="text-[10px] text-textSecondary">深度思考（推理模式）</div>
                <div className="text-[10px] text-amber-400/90">⚠️ 开启后推理 token 单独计费，费用显著增加</div>
              </div>
              <input
                type="checkbox"
                checked={creatorForm.thinking}
                onChange={(e) => setCreatorForm((f) => ({ ...f, thinking: e.target.checked }))}
                className="w-4 h-4 accent-primary-500"
              />
            </div>
            <div className="flex items-center justify-between bg-elevated/60 rounded p-2">
              <div>
                <div className="text-[10px] text-textSecondary">工具循环上限</div>
                <div className="text-[10px] text-textMuted">单次对话最多连续调几轮工具（1-200，默认 50）</div>
              </div>
              <input
                type="number"
                min={1}
                max={200}
                value={creatorForm.max_tool_rounds}
                onChange={(e) => setCreatorForm((f) => ({ ...f, max_tool_rounds: Number(e.target.value) || 50 }))}
                className="w-20 bg-elevated text-sm p-1.5 rounded border border-border outline-none text-right"
              />
            </div>
            {usageStats && (
              <div className="flex items-center justify-between bg-elevated/60 rounded p-2">
                <div>
                  <div className="text-[10px] text-textSecondary">LLM 缓存命中率</div>
                  <div className="text-[10px] text-textMuted">{usageStats.total_calls} 次调用 · prompt {usageStats.prompt_tokens} / 缓存 {usageStats.cached_tokens} tok</div>
                </div>
                <div className="text-sm font-bold text-mint-400">{usageStats.cache_hit_rate_pct}%</div>
              </div>
            )}
            <button
              onClick={saveCreator}
              disabled={creatorSaving}
              className="w-full py-1.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded transition-colors disabled:opacity-40"
            >
              {creatorSaving ? '保存中...' : '💾 保存配置'}
            </button>
          </div>
        )}

        {/* 消息列表（滚到顶加载更早） */}
        <div ref={chatListRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-3 space-y-2">
          {chatLoadingOlder && <div className="text-[10px] text-textMuted text-center py-1">加载更早消息…</div>}
          {chatMsgs.length === 0 && (
            <div className="text-xs text-textMuted text-center mt-8">
              暂无消息<br/>试试发送：「把页面标题改成红色」
            </div>
          )}
          {chatMsgs.map((m) => (
            m.role === 'tool' ? (
              <div key={m.id} className={`text-[11px] text-center py-1 px-2 rounded-lg max-w-[90%] mx-auto ${m.error ? 'text-rose-400 bg-rose-500/10 border border-rose-500/20' : 'text-mint-400 bg-mint-400/10 border border-mint-400/20'}`}>
                🔧 {m.content}
              </div>
            ) : (
            <div key={m.id} className={`text-sm max-w-[90%] p-2 rounded-lg ${m.error ? 'bg-rose-500/10 border border-rose-500/30 text-rose-400' : m.role === 'user' ? 'bg-primary-500/20 ml-auto' : 'bg-elevated/80'}`}>
              <div className="text-[10px] text-textMuted mb-0.5">{m.error ? '⚠️ 错误' : m.role === 'user' ? '我' : '世界 AI'}</div>
              {!m.error && (m.role === 'ai' || m.role === 'note') && !!m.reasoning && (
                <details className="mb-1.5">
                  <summary className="text-[10px] text-textMuted cursor-pointer select-none hover:text-textSecondary">🤔 思考过程</summary>
                  <div className="text-xs text-textMuted mt-1 whitespace-pre-wrap bg-elevated/70 rounded p-2">{m.reasoning}</div>
                </details>
              )}
              {m.content ? <MarkdownContent content={m.content} /> : (m.role === 'ai' ? <span className="opacity-40">…</span> : null)}
            </div>
            )
          ))}
        </div>

        {/* 输入 */}
        <div className="p-3 border-t border-border">
          <textarea
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat() } }}
            rows={2}
            placeholder="和世界 AI 对话…（无需 @）"
            disabled={chatSending || chatProcessing}
            className="w-full bg-elevated text-sm p-2 rounded border border-border outline-none resize-none disabled:opacity-50 focus:border-primary-500/50"
          />
          <button
            onClick={sendChat}
            disabled={chatSending || chatProcessing || !chatInput.trim()}
            className="w-full mt-2 py-1.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded transition-colors disabled:opacity-40"
          >
            {chatSending || chatProcessing ? '思考中...' : '发送'}
          </button>
          {chatProcessing && (
            <div className="text-[10px] text-textMuted mt-2 text-center">
              ⏳ 上一轮还在执行（刷新不影响），完成后自动显示
            </div>
          )}
          <div className="text-[10px] text-textMuted mt-2 text-center">
            世界级会话（非 DM）：账单走世界主人，让它改世界、加功能
          </div>
        </div>
      </div>
    </div>
  )
}
