/**
 * 群视界设计页 — 世界文件管理 + 界面预览 + 群视界机器人对话
 *
 * 布局参考 TRAE/Cursor：左（文件树/预览）右（对话窗口）
 * 普通用户可直接用；专业用户可编辑代码（专业模式）。
 */
import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, ChevronDown, Folder, FolderOpen, FileText, FileCode, FileJson, FileImage, FileAudio, FileVideo, File, Trash2, Upload, Plus, Pencil, Eye, Brain, MessageCircle, Save, Send, ArrowDown, Search, Globe, Terminal, Package, Clock, Wrench, Eraser } from 'lucide-react'
import { api } from '../api/client'
import MarkdownContent from '../components/shared/MarkdownContent'
import CodeRenderer from '../components/shared/CodeRenderer'
import { getCodeLang, isMarkdownFile } from '../utils/mime'
import { tryOpenWorldWindow } from '../utils/worldView'
import { useResizableSidebar } from '../hooks/useResizableSidebar'
import { useWorldChat } from '../hooks/useWorldChat'

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

// 工具气泡图标：按摘要内容关键词映射（后端文本不带 emoji，图标由前端渲染）
function toolIcon(content: string) {
  const s = content || ''
  if (s.includes('接口文档')) return <FileText size={12} />
  if (s.includes('记住') || s.includes('记忆') || s.includes('检索')) return <Brain size={12} />
  if (s.includes('搜索')) return <Search size={12} />
  if (s.includes('获取') || s.includes('http')) return <Globe size={12} />
  if (s.includes('世界代码')) return <Terminal size={12} />
  if (s.includes('压缩')) return <Package size={12} />
  if (s.includes('清空')) return <Eraser size={12} />
  if (s.includes('排队')) return <Clock size={12} />
  return <Wrench size={12} />
}

// 文件内容区：md/html/代码渲染、图片显示、纯文本编辑（桌面右栏 / 移动端编辑器共用）
function FileContentPane({ wid, currentFile, content, setContent, viewMode, canRender, isMdFile, fileCodeLang, isImgFile }: {
  wid: number
  currentFile: string
  content: string
  setContent: (v: string) => void
  viewMode: 'edit' | 'render'
  canRender: boolean
  isMdFile: boolean
  fileCodeLang: string
  isImgFile: boolean
}) {
  if (viewMode === 'render' && canRender) {
    if (isImgFile) {
      return (
        <div className="flex-1 overflow-hidden bg-canvas flex items-center justify-center">
          <img
            src={`/world/${wid}/files/${currentFile.split('/').map(encodeURIComponent).join('/')}`}
            alt={currentFile}
            className="w-full h-full object-contain"
          />
        </div>
      )
    }
    return (
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
  }
  return (
    <textarea
      value={content}
      onChange={(e) => setContent(e.target.value)}
      spellCheck={false}
      className="flex-1 bg-canvas text-sm text-textPrimary p-3 font-mono outline-none resize-none"
      placeholder="在这里编辑代码…"
    />
  )
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

  // 世界 AI 配置表单（单独表单，不属于 agent）
  const [showCreatorForm, setShowCreatorForm] = useState(false)
  const [creatorForm, setCreatorForm] = useState({ name: '', system_prompt: '', model: '', temperature: 0.8, thinking: false, max_tool_rounds: 50 })
  const [creatorSaving, setCreatorSaving] = useState(false)
  // 2.7：LLM 用量/缓存命中率
  const [usageStats, setUsageStats] = useState<{ total_calls: number; prompt_tokens: number; completion_tokens: number; cached_tokens: number; cache_hit_rate_pct: number } | null>(null)

  // 当前文件内联渲染：md 渲染 + 查看原文；html/代码高亮渲染；图片直接显示（不用弹窗）
  const [viewMode, setViewMode] = useState<'edit' | 'render'>('edit')

  // ── 移动端（<lg）：tab 切换（文件/对话，对话默认打开）+ 目录逐层导航 ──
  const [mobileTab, setMobileTab] = useState<'files' | 'chat'>('chat')
  const [mobileView, setMobileView] = useState<'dirs' | 'file'>('dirs')
  const [mobileDir, setMobileDir] = useState('')  // 当前浏览目录（'' = 根）
  // 上传：顶部菜单（上传到此位置 / 选择其它位置）+ 目录选择弹层
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false)
  const [uploadDirPickerOpen, setUploadDirPickerOpen] = useState(false)
  const [uploadNavDir, setUploadNavDir] = useState('')
  const mobileUploadDirRef = useRef<string | null>(null)  // 非 null = 移动端上传，目标目录由此指定
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
  const uploadFile = async (f: File, targetPath: string) => {
    try {
      const fd = new FormData()
      fd.append('file', f)
      fd.append('path', targetPath.replace(/^\/+/, ''))
      await api.post(`/worlds/${wid}/files/upload`, fd)
      await load()
      selectFile(targetPath.replace(/^\/+/, ''))
      setMsg('✅ 已上传')
    } catch (err: any) {
      setMsg(`上传失败: ${err?.message || err}`)
    }
  }
  const handleUploadPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''  // 允许重复选同一文件
    if (!f) return
    // 移动端：目标目录由 mobileUploadDirRef 指定（上传菜单/目录选择器设置）
    const mobileOverride = mobileUploadDirRef.current
    mobileUploadDirRef.current = null
    if (mobileOverride !== null) {
      await uploadFile(f, mobileOverride ? `${mobileOverride}/${f.name}` : f.name)
      setMobileView('file')  // 上传完自动打开文件（移动端）
      return
    }
    // 桌面端：prompt 输入目标路径（默认当前选中文件所在目录）
    const dir = currentFile?.includes('/') ? currentFile.slice(0, currentFile.lastIndexOf('/') + 1) : ''
    const target = prompt(`上传到哪个路径？（当前目录：${dir || '/'}）`, dir + f.name)
    if (!target) return
    await uploadFile(f, target)
  }
  // 移动端上传：菜单（上传到此位置 / 选择其它位置）
  const mobileUploadHere = () => {
    setUploadMenuOpen(false)
    mobileUploadDirRef.current = mobileDir
    fileInputRef.current?.click()
  }
  const mobileUploadElsewhere = () => {
    setUploadMenuOpen(false)
    setUploadNavDir('')
    setUploadDirPickerOpen(true)
  }
  const mobileUploadToNavDir = () => {
    setUploadDirPickerOpen(false)
    mobileUploadDirRef.current = uploadNavDir
    fileInputRef.current?.click()
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

  // 移动端：当前浏览目录节点 / 上传目录选择器节点（从 fileTree 定位）
  const mobileDirNode = useMemo(() => {
    if (!mobileDir) return fileTree
    const parts = mobileDir.split('/')
    let node = fileTree
    for (const p of parts) {
      const next = node.children.find((c) => c.isDir && c.name === p)
      if (!next) break
      node = next
    }
    return node
  }, [fileTree, mobileDir])

  const uploadDirNode = useMemo(() => {
    if (!uploadNavDir) return fileTree
    const parts = uploadNavDir.split('/')
    let node = fileTree
    for (const p of parts) {
      const next = node.children.find((c) => c.isDir && c.name === p)
      if (!next) break
      node = next
    }
    return node
  }, [fileTree, uploadNavDir])

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
              <ChevronRight size={12} className={`shrink-0 transition-transform ${collapsedDirs.has(n.path) ? '' : 'rotate-90'}`} />
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

  // ── 世界 AI 对话（状态/发送/排队/建议/命令 全部在 useWorldChat） ──
  const chat = useWorldChat({ wid, onRefresh: load, onMsg: setMsg })

  // world 加载完成 → 聊天面板渲染 → 确保在底部（刷新时历史先到、面板后渲染，滚动要补一次）
  useEffect(() => {
    if (world) chat.forceScrollToBottom()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world])

  // 最后一条 AI 回复的 id（建议按钮插在它下面）
  const lastAiMsgId = useMemo(() => {
    for (let i = chat.chatMsgs.length - 1; i >= 0; i--) {
      if (chat.chatMsgs[i].role === 'ai') return chat.chatMsgs[i].id
    }
    return null
  }, [chat.chatMsgs])

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

  // ── 聊天面板内容（桌面右栏 / 移动端对话 tab 共用） ──
  const renderChatInner = () => (
    <>
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
            {/* 排队消息（AI 处理中，输入框上方弹窗展示：普通消息一起发，命令逐个执行） */}
        {chat.pendingItems.length > 0 && (
          <div className="absolute bottom-full left-3 right-3 mb-1 max-h-32 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
            <div className="px-3 py-1.5 text-[10px] text-textMuted border-b border-border">
              ⏳ AI 处理中，以下 {chat.pendingItems.length} 条将按顺序执行（普通消息一起发，命令逐个执行）
            </div>
            {chat.pendingItems.map((it, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-border/40 last:border-b-0">
                <span className={`truncate flex-1 ${it.kind === 'cmd' ? 'font-mono text-primary-400' : 'text-textPrimary'}`}>{it.text}</span>
                <span className="shrink-0 text-[10px] text-textMuted">{it.kind === 'cmd' ? '命令' : '消息'}</span>
                <button
                  onClick={() => chat.setPendingItems((items) => items.filter((_, j) => j !== i))}
                  className="shrink-0 text-textMuted hover:text-rose-400 transition-colors"
                  title="移除这条"
                >✕</button>
              </div>
            ))}
          </div>
        )}
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
            {creatorSaving ? '保存中...' : (<span className="inline-flex items-center gap-1"><Save size={12} /> 保存配置</span>)}
          </button>
        </div>
      )}

      {/* 消息列表（滚到顶加载更早；在底部 = 自动跟随最新，否则右下角 ↓ 可回底） */}
      <div ref={chat.chatListRef} onScroll={chat.handleChatScroll} className="flex-1 overflow-y-auto p-3 space-y-2 relative">
        {chat.chatLoadingOlder && <div className="text-[10px] text-textMuted text-center py-1">加载更早消息…</div>}
        {chat.chatMsgs.length === 0 && (
          <div className="text-xs text-textMuted text-center mt-8">
            暂无消息<br/>试试发送：「把页面标题改成红色」
          </div>
        )}
        {chat.chatMsgs.map((m) => {
          const isLastAi = m.role === 'ai' && m.id === lastAiMsgId
          return (
            <div key={m.id} className="space-y-2">
              {m.role === 'tool' ? (
                <div className={`world-msg flex items-center justify-center gap-1.5 text-[11px] text-center py-1 px-2 rounded-lg max-w-[90%] mx-auto ${m.error ? 'text-rose-400 bg-rose-500/10 border border-rose-500/20' : 'text-mint-400 bg-mint-400/10 border border-mint-400/20'}`}>
                  <span className="shrink-0">{toolIcon(m.content)}</span>
                  <span className="min-w-0">{m.content}</span>
                </div>
              ) : (
                <div className={`world-msg text-sm max-w-[90%] p-2 rounded-lg ${m.error ? 'bg-rose-500/10 border border-rose-500/30 text-rose-400' : m.role === 'user' ? 'bg-primary-500/20 ml-auto' : 'bg-elevated/80'}`}>
                  <div className="text-[10px] text-textMuted mb-0.5">{m.error ? '⚠️ 错误' : m.role === 'user' ? (m.pending ? '我（排队中，发送后生效）' : '我') : '世界 AI'}</div>
                  {!m.error && (m.role === 'ai' || m.role === 'note') && !!m.reasoning && (
                    <details className="group/details mb-1.5">
                      <summary className="flex items-center gap-1 text-[10px] text-textMuted cursor-pointer select-none hover:text-textSecondary list-none [&::-webkit-details-marker]:hidden">
                        <ChevronRight size={11} className="transition-transform group-open/details:rotate-90" />
                        <Brain size={11} className="text-textMuted" />
                        思考过程
                      </summary>
                      <div className="text-xs text-textMuted mt-1 whitespace-pre-wrap bg-elevated/70 rounded p-2">{m.reasoning}</div>
                    </details>
                  )}
                  {m.content ? <MarkdownContent content={m.content} /> : (m.role === 'ai' ? <span className="opacity-40">…</span> : null)}
                </div>
              )}
              {/* "你可以"建议：插在最后一条 AI 回复下面（无对话时显示在列表底部），一个建议一行（文字 | 发送 | 插入） */}
              {(isLastAi || chat.chatMsgs.length === 0) && chat.suggestions.length > 0 && !chat.chatSending && !chat.chatProcessing && (
                <div className="space-y-1.5 pl-1">
                  <div className="text-[10px] text-textMuted">你可以：</div>
                  {chat.suggestions.map((q, i) => (
                    <div key={i} className="flex items-stretch rounded-lg bg-elevated border border-border overflow-hidden max-w-[85%]">
                      <button
                        onClick={() => chat.submitText(q)}
                        className="flex-1 min-w-0 px-2.5 py-1.5 text-left text-xs text-textSecondary hover:bg-primary-500/20 hover:text-primary-300 transition-colors truncate"
                        title={q}
                      >{q}</button>
                      <div className="w-px bg-border shrink-0" />
                      <button
                        onClick={(e) => { e.stopPropagation(); chat.submitText(q) }}
                        className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                        title="发送这条"
                      ><Send size={11} /></button>
                      <div className="w-px bg-border shrink-0" />
                      <button
                        onClick={(e) => { e.stopPropagation(); chat.insertSuggestion(q) }}
                        className="px-2 flex items-center text-textMuted hover:text-primary-300 hover:bg-primary-500/20 transition-colors shrink-0"
                        title="插入到输入框（追加，不覆盖）"
                      ><Plus size={12} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {/* ↓ 回到底部（不在最下方时显示；显示即未跟随） */}
        {!chat.isAtBottom && chat.chatMsgs.length > 0 && (
          <button
            onClick={() => chat.scrollToBottom(true)}
            className="absolute bottom-3 right-3 z-40 flex items-center justify-center w-8 h-8 bg-elevated border border-border rounded-full shadow-lg text-textSecondary hover:text-textPrimary hover:bg-surface transition-all"
            title="回到底部并跟随"
          >
            <ArrowDown size={14} />
          </button>
        )}
      </div>

      {/* 输入 */}
      <div className="p-3 border-t border-border relative">
        {/* 斜杠命令列表（输入 / 弹出；选中即发送） */}
        {chat.cmdActive && chat.cmdFiltered.length > 0 && (
          <div className="absolute bottom-full left-3 mb-1 w-64 max-h-40 overflow-y-auto rounded-xl bg-elevated border border-border shadow-xl z-50">
            {chat.cmdFiltered.map((c, i) => (
              <button
                key={c.cmd}
                className={`w-full text-left px-3 py-2 transition-colors ${i === chat.cmdIdx ? 'bg-primary-500/20 text-primary-400' : 'text-textPrimary hover:bg-hover'}`}
                onMouseDown={(e) => { e.preventDefault(); chat.submitText(c.cmd) }}
              >
                <span className="font-mono text-xs">{c.cmd}</span>
                <span className="block text-[10px] text-textMuted">{c.desc}</span>
              </button>
            ))}
          </div>
        )}
        <textarea
          ref={chat.chatInputRef}
          value={chat.chatInput}
          onChange={(e) => {
            const ta = e.target
            chat.setChatInput(ta.value)
            // / 检测：光标前只有 / + 字母（命令整行输入）；AI 忙时命令需等待，不弹列表
            const before = ta.value.slice(0, ta.selectionStart)
            const m = before.match(/^\/\w*$/)
            if (m) { chat.setCmdQuery(before.slice(1)); chat.setCmdActive(true); chat.setCmdIdx(0) }
            else chat.setCmdActive(false)
          }}
          onKeyDown={(e) => {
            if (chat.cmdActive && chat.cmdFiltered.length > 0) {
              if (e.key === 'ArrowDown') { e.preventDefault(); chat.setCmdIdx((i) => (i + 1) % chat.cmdFiltered.length); return }
              if (e.key === 'ArrowUp') { e.preventDefault(); chat.setCmdIdx((i) => (i - 1 + chat.cmdFiltered.length) % chat.cmdFiltered.length); return }
              if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); chat.submitText(chat.cmdFiltered[chat.cmdIdx].cmd); return }
              if (e.key === 'Escape') { e.preventDefault(); chat.setCmdActive(false); return }
            }
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chat.submitText(chat.chatInput) }
          }}
          rows={2}
          placeholder={(chat.chatSending || chat.chatProcessing) ? "AI 处理中，消息将排队…" : "和世界 AI 对话…（输入 / 查看命令）"}
          className="w-full bg-elevated text-sm p-2 rounded border border-border outline-none resize-none focus:border-primary-500/50"
        />
        <button
          onClick={() => chat.submitText(chat.chatInput)}
          disabled={!chat.chatInput.trim()}
          className="w-full mt-2 py-1.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded transition-colors disabled:opacity-40"
        >
          {(chat.chatSending || chat.chatProcessing) ? '排队发送' : (chat.chatSending ? '思考中...' : '发送')}
        </button>
        {chat.chatProcessing && (
          <div className="text-[10px] text-textMuted mt-2 text-center">
            ⏳ 上一轮还在执行（刷新不影响），完成后自动显示
          </div>
        )}
        <div className="text-[10px] text-textMuted mt-2 text-center">
          世界级会话（非 DM）：账单走世界主人，让它改界面、加功能
        </div>
      </div>
    </>
  )

  if (loading) return <div className="flex items-center justify-center h-screen text-textMuted">加载中...</div>
  if (!world) return <div className="p-8 text-textMuted">世界不存在</div>

  return (
    <div className="h-screen bg-canvas text-textPrimary">
      {/* ═══ 移动端（<lg）：tab 切换 ── 文件（目录导航/编辑器）+ 对话（默认打开） ═══ */}
      <div className="lg:hidden flex flex-col h-full relative pb-14 lg:pb-0">
        {/* 顶栏：返回 + 世界信息 + 上传（文件 tab 时显示） */}
        <div className="flex items-center gap-2 px-3 py-2 bg-surface border-b border-border">
          <button onClick={() => navigate('/worlds')} className="inline-flex items-center gap-1 text-sm text-textMuted hover:text-textPrimary transition-colors shrink-0">
            <ChevronLeft size={14} />
            世界
          </button>
          <span className="font-semibold truncate">{world.name}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${world.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-elevated text-textMuted'}`}>
            {world.status === 'active' ? '活跃' : '休眠'}
          </span>
          <div className="flex-1" />
          {mobileTab === 'files' && (
            <div className="relative shrink-0">
              <button onClick={() => setUploadMenuOpen((v) => !v)} className="inline-flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors px-2 py-1" title="上传文件">
                <Upload size={14} />
                上传
              </button>
              {uploadMenuOpen && (
                <div className="absolute right-0 top-full mt-1 w-56 bg-surface border border-border rounded-lg shadow-lg p-1 z-50">
                  <button onClick={mobileUploadHere} className="w-full inline-flex items-center gap-1.5 text-left text-xs px-3 py-2 rounded hover:bg-elevated text-textPrimary">
                    <Upload size={13} /> 上传到此位置（{mobileDir || '/'}）
                  </button>
                  <button onClick={mobileUploadElsewhere} className="w-full inline-flex items-center gap-1.5 text-left text-xs px-3 py-2 rounded hover:bg-elevated text-textPrimary">
                    <FolderOpen size={13} /> 选择其它位置…
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* tab：文件 / 对话（对话默认打开） */}
        <div className="flex items-stretch bg-surface border-b border-border">
          <button
            onClick={() => setMobileTab('files')}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 text-sm transition-colors ${mobileTab === 'files' ? 'text-primary-400 border-b-2 border-primary-500 font-medium' : 'text-textMuted'}`}
          >
            <Folder size={14} /> 文件
          </button>
          <button
            onClick={() => setMobileTab('chat')}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 text-sm transition-colors ${mobileTab === 'chat' ? 'text-primary-400 border-b-2 border-primary-500 font-medium' : 'text-textMuted'}`}
          >
            <MessageCircle size={14} /> 对话
          </button>
        </div>

        {/* 内容区：对话 tab（默认）/ 文件 tab（目录导航 → 编辑器） */}
        {mobileTab === 'chat' ? (
          <div className="flex-1 flex flex-col min-h-0 bg-surface">
            {renderChatInner()}
          </div>
        ) : mobileView === 'file' ? (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-3 py-1.5 text-xs text-textSecondary bg-surface/60 border-b border-border flex items-center gap-2">
              <button onClick={() => setMobileView('dirs')} className="inline-flex items-center gap-0.5 text-primary-400 hover:text-primary-300 transition-colors shrink-0">
                <ChevronLeft size={13} />
                返回
              </button>
              <span className="truncate flex-1">{currentFile || '未选择文件'}</span>
              {canRender && (
                <button
                  onClick={() => setViewMode((v) => (v === 'render' ? 'edit' : 'render'))}
                  className="text-primary-400 hover:text-primary-300 transition-colors shrink-0"
                  title={viewMode === 'render' ? '切到原文/编辑' : '切到渲染视图'}
                >
                  {viewMode === 'render' ? (isMdFile ? '查看原文' : '编辑') : '渲染'}
                </button>
              )}
              {viewMode !== 'render' && (
                <button onClick={saveFile} disabled={saving} className="text-primary-400 hover:text-primary-300 transition-colors shrink-0">
                  {saving ? '保存中...' : (<span className="inline-flex items-center gap-1"><Save size={12} /> 保存</span>)}
                </button>
              )}
            </div>
            <FileContentPane wid={wid} currentFile={currentFile} content={content} setContent={setContent} viewMode={viewMode} canRender={canRender} isMdFile={isMdFile} fileCodeLang={fileCodeLang} isImgFile={isImgFile} />
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            {/* 面包屑（路径可逐级返回） */}
            <div className="flex items-center gap-0.5 px-3 py-2 bg-surface/60 border-b border-border overflow-x-auto text-xs">
              <button onClick={() => setMobileDir('')} className="text-primary-400 hover:underline shrink-0">/</button>
              {mobileDir.split('/').filter(Boolean).map((seg, i, arr) => {
                const path = mobileDir.split('/').slice(0, i + 1).join('/')
                const isLast = i === arr.length - 1
                return isLast ? (
                  <span key={path} className="flex items-center gap-0.5 min-w-0">
                    <ChevronRight size={11} className="text-textMuted shrink-0" />
                    <span className="text-textSecondary truncate">{seg}</span>
                  </span>
                ) : (
                  <span key={path} className="flex items-center gap-0.5 shrink-0">
                    <ChevronRight size={11} className="text-textMuted" />
                    <button onClick={() => setMobileDir(path)} className="text-primary-400 hover:underline">{seg}</button>
                  </span>
                )
              })}
            </div>
            {/* 目录内容：文件夹在前，点文件夹进入；点文件打开编辑器 */}
            <div className="flex-1 overflow-y-auto p-2">
              {mobileDirNode.children.length === 0 && (
                <div className="text-xs text-textMuted text-center mt-10 px-4">
                  空目录<br />点右上角「上传」放文件，或去「对话」让机器人生成
                </div>
              )}
              {mobileDirNode.children.map((n) => n.isDir ? (
                <button
                  key={n.path}
                  onClick={() => setMobileDir(n.path)}
                  className="w-full flex items-center gap-2 px-2 py-2.5 rounded-lg hover:bg-elevated text-textSecondary text-sm transition-colors"
                >
                  <Folder size={16} className="text-primary-400 shrink-0" />
                  <span className="truncate flex-1 text-left">{n.name}</span>
                  <ChevronRight size={14} className="text-textMuted shrink-0" />
                </button>
              ) : (
                <div key={n.path} className="flex items-center">
                  <button
                    onClick={() => { selectFile(n.path); setMobileView('file') }}
                    className={`flex items-center gap-2 flex-1 min-w-0 text-left px-2 py-2.5 rounded-lg text-sm transition-colors ${currentFile === n.path ? 'bg-primary-500/20 text-primary-300' : 'hover:bg-elevated text-textSecondary'}`}
                  >
                    <span className="shrink-0">{fileTypeIcon(n.name)}</span>
                    <span className="truncate flex-1">{n.name}</span>
                  </button>
                  <button
                    onClick={() => deleteFile(n.path)}
                    className="shrink-0 w-8 h-8 flex items-center justify-center text-textMuted hover:text-rose-400 transition-colors"
                    title="删除此文件"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 目录选择弹层（上传 → 选择其它位置） */}
        {uploadDirPickerOpen && (
          <div className="absolute inset-0 z-50 bg-black/50 flex items-end">
            <div className="w-full bg-surface rounded-t-2xl border-t border-border flex flex-col max-h-[75%]">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
                <span className="text-sm font-semibold flex-1">选择上传位置</span>
                <button onClick={() => setUploadDirPickerOpen(false)} className="text-xs text-textMuted hover:text-textPrimary px-2 py-1">取消</button>
              </div>
              <div className="flex items-center gap-0.5 px-4 py-2 overflow-x-auto text-xs border-b border-border/60">
                <button onClick={() => setUploadNavDir('')} className="text-primary-400 hover:underline shrink-0">/</button>
                {uploadNavDir.split('/').filter(Boolean).map((seg, i, arr) => {
                  const path = uploadNavDir.split('/').slice(0, i + 1).join('/')
                  const isLast = i === arr.length - 1
                  return isLast ? (
                    <span key={path} className="flex items-center gap-0.5 min-w-0">
                      <ChevronRight size={11} className="text-textMuted shrink-0" />
                      <span className="text-textSecondary truncate">{seg}</span>
                    </span>
                  ) : (
                    <span key={path} className="flex items-center gap-0.5 shrink-0">
                      <ChevronRight size={11} className="text-textMuted" />
                      <button onClick={() => setUploadNavDir(path)} className="text-primary-400 hover:underline">{seg}</button>
                    </span>
                  )
                })}
              </div>
              <div className="flex-1 overflow-y-auto p-2">
                {uploadDirNode.children.filter((n) => n.isDir).length === 0 && (
                  <div className="text-xs text-textMuted text-center mt-8">当前目录没有子文件夹</div>
                )}
                {uploadDirNode.children.filter((n) => n.isDir).map((n) => (
                  <button
                    key={n.path}
                    onClick={() => setUploadNavDir(n.path)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-elevated text-textSecondary text-sm transition-colors"
                  >
                    <Folder size={16} className="text-primary-400 shrink-0" />
                    <span className="truncate flex-1 text-left">{n.name}</span>
                    <ChevronRight size={14} className="text-textMuted shrink-0" />
                  </button>
                ))}
              </div>
              <div className="p-3 border-t border-border">
                <button onClick={mobileUploadToNavDir} className="w-full py-2.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-lg transition-colors">
                  上传到此位置（{uploadNavDir || '/'}）
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ═══ 桌面端（≥lg）：标题栏 + 三栏（分隔线贯穿，拖拽手柄覆盖标题栏与内容区） ═══ */}
      <div className="hidden lg:flex flex-col h-full">
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
        {/* 标题栏：文件（横跨文件树+编辑区） | 对话（右列上方）；内容行手柄贯穿 */}
        <div className="flex items-stretch bg-surface border-b border-border">
          <div style={{ width: fileWidth }} className="shrink-0" />
          <div className="flex-1 flex items-center justify-center gap-1.5 h-9 font-medium text-textSecondary">
            <Folder size={14} className="text-textMuted" />
            文件
          </div>
          <div style={{ width: chatWidth }} className="shrink-0 flex items-center justify-center gap-1.5 h-9 font-medium text-textSecondary border-l border-border">
            <MessageCircle size={14} className="text-textMuted" />
            对话
          </div>
        </div>
        {/* 内容行：拖拽手柄贯穿（拖动 = 整列宽度同步） */}
        <div className="flex flex-1 min-h-0">
        {/* 左列：文件树 */}
        <div ref={fileTreeRef} className="flex flex-col shrink-0 bg-surface border-r border-border" style={{ width: fileWidth }}>
          <div className="flex-1 overflow-y-auto p-2">
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-xs font-medium text-textSecondary">文件</span>
              <span className="flex items-center gap-2">
                <button onClick={() => fileInputRef.current?.click()} className="inline-flex items-center gap-0.5 text-xs text-primary-400 hover:text-primary-300 transition-colors" title="上传文件（先选位置）">
                  <Upload size={12} />
                  上传
                </button>
                <button onClick={createFile} className="inline-flex items-center gap-0.5 text-xs text-primary-400 hover:text-primary-300 transition-colors" title="新建文件">
                  <Plus size={12} />
                  新建
                </button>
              </span>
            </div>
            <input ref={fileInputRef} type="file" className="hidden" onChange={handleUploadPick} />
            {files.length === 0 && <div className="text-xs text-textMuted p-2">空世界，点 + 新建或让机器人生成</div>}
            {renderTree(fileTree.children, 0)}
          </div>
        </div>
        <div onMouseDown={fileResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors" />
        {/* 中列：编辑 / 预览 */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 min-h-0">
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
                          {viewMode === 'render' ? (isMdFile ? (
                            <span className="inline-flex items-center gap-0.5"><FileText size={12} /> 查看原文</span>
                          ) : (
                            <span className="inline-flex items-center gap-0.5"><Pencil size={12} /> 编辑</span>
                          )) : (
                            <span className="inline-flex items-center gap-0.5"><Eye size={12} /> 渲染</span>
                          )}
                        </button>
                      )}
                      {viewMode !== 'render' && (
                        <button onClick={saveFile} disabled={saving} className="text-primary-400 hover:text-primary-300 transition-colors">
                          {saving ? '保存中...' : (<span className="inline-flex items-center gap-1"><Save size={12} /> 保存</span>)}
                        </button>
                      )}
                    </span>
                  )}
                </div>
                <FileContentPane wid={wid} currentFile={currentFile} content={content} setContent={setContent} viewMode={viewMode} canRender={canRender} isMdFile={isMdFile} fileCodeLang={fileCodeLang} isImgFile={isImgFile} />
              </div>
            ) : (
              <div className="h-full flex flex-col">
                <div className="px-3 py-1.5 text-xs text-textSecondary bg-surface/60 border-b border-border flex items-center gap-2">
                  <span className="truncate flex-1">世界预览（/world/{wid}/preview）</span>
                  <button onClick={() => setPreviewKey((k) => k + 1)} className="text-primary-400 hover:text-primary-300 transition-colors shrink-0" title="刷新预览">↻ 刷新</button>
                  <button
                    onClick={() => { if (!tryOpenWorldWindow(wid)) navigate(`/world-view/${wid}`) }}
                    className="text-primary-400 hover:text-primary-300 transition-colors shrink-0"
                    title="在沉浸界面新窗口打开（WebView 下自动应用内跳转）"
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
        <div onMouseDown={chatResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors" />
        {/* 右列：对话面板（标题已在顶部标题栏） */}
        <div ref={chatPanelRef} className="flex flex-col shrink-0 bg-surface" style={{ width: chatWidth }}>
          <div className="flex-1 min-h-0 flex flex-col">
            {renderChatInner()}
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
