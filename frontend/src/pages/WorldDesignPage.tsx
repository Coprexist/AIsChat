/**
 * 群视界设计页 — 世界文件管理 + 界面预览 + 群视界机器人对话
 *
 * 布局参考 TRAE/Cursor：左（文件树/预览）右（对话窗口）
 * 普通用户可直接用；专业用户可编辑代码（专业模式）。
 */
import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Folder, FolderOpen, FolderInput, Upload, Plus, Pencil, Eye, MessageCircle, Save, MoreHorizontal, FileText, Trash2, Settings, RefreshCw, ExternalLink, BookOpen, X, Download } from 'lucide-react'
import { api } from '../api/client'
import GroupManagerModal from '../components/GroupManagerModal'
import WorldChatPanel, { type WorldChatHandle } from '../components/WorldChatPanel'
import MarkdownContent from '../components/shared/MarkdownContent'
import WorldFileTree, { buildWorldTree, type WorldFile } from '../components/world/WorldFileTree'
import FileContentPane, { fileTypeIcon } from '../components/world/FileContentPane'
import WorldCreatorConfig, { type WorldCreator, type WorldUsageStats } from '../components/world/WorldCreatorConfig'
import { getCodeLang, isMarkdownFile } from '../utils/mime'
import { tryOpenWorldWindow } from '../utils/worldView'
import { useResizableSidebar } from '../hooks/useResizableSidebar'

interface World {
  id: number
  name: string
  description: string
  owner_id: number
  status: string
  time_flow_rate: number
  world_time: string | null
  bindings: { entity_type: string; entity_id: number }[]
  agents: { agent_id: number; role: string }[]
  // 群视界机器人 = 世界配置（非 agent、无账号），身份 = world-{id}
  creator: WorldCreator | null
}

export default function WorldDesignPage() {
  const { worldId } = useParams()
  const navigate = useNavigate()
  const wid = Number(worldId)

  // 可拖拽面板（复用侧边栏 hook：左=文件树，右=对话）
  const fileTreeRef = useRef<HTMLDivElement>(null)
  const chatPanelRef = useRef<HTMLDivElement>(null)
  // 三栏动态保底：文件树 100 / 编辑区 160 / 对话 200；上限按其他区域保底实时反推（防负：窗口过窄时至少 = 自身保底）
  const MIN_TREE = 100
  const MIN_EDITOR = 160
  const MIN_CHAT = 200
  const { sidebarWidth: fileWidth, handleResizeStart: fileResizeStart } = useResizableSidebar('world_files_width', fileTreeRef, {
    min: MIN_TREE, max: () => Math.max(MIN_TREE, window.innerWidth - MIN_EDITOR - MIN_CHAT - 8), // 8 = 两个拖拽手柄
  })
  // 聊天栏上限按「当前文件树实际宽度」实时反推（不是保底值）：文件树拖宽后，聊天栏同样不会被挤出右侧
  const { sidebarWidth: chatWidth, handleResizeStart: chatResizeStart } = useResizableSidebar('world_chat_width', chatPanelRef, {
    side: 'right', min: MIN_CHAT, max: () => Math.max(MIN_CHAT, window.innerWidth - fileWidth - MIN_EDITOR - 8),
  })
  // 渲染层兜底：无论拖拽/hook 状态怎么变，聊天栏实际宽度绝不超过可用空间（否则会被挤出屏幕右侧）
  const effectiveChatWidth = Math.min(
    chatWidth,
    Math.max(MIN_CHAT, window.innerWidth - fileWidth - MIN_EDITOR - 8),
  )

  const [world, setWorld] = useState<World | null>(null)
  const [files, setFiles] = useState<WorldFile[]>([])
  const [currentFile, setCurrentFile] = useState<string>('')
  const currentFileRef = useRef('')  // load 闭包读实时值（避免 useCallback 冻结导致每次 load 都跳第一个文件）
  currentFileRef.current = currentFile
  const [content, setContent] = useState('')
  const [mode, setMode] = useState<'files' | 'preview'>('files')
  const [previewKey, setPreviewKey] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  // 接口文档查看（程序员用：发给世界 AI 的 md）
  const [docsOpen, setDocsOpen] = useState(false)
  const [docsSections, setDocsSections] = useState<{ id: string; title: string; intro: string }[]>([])
  const [docsActive, setDocsActive] = useState<string>('')
  const [docsContent, setDocsContent] = useState('')
  const [docsLoading, setDocsLoading] = useState(false)
  const [docxAvailable, setDocxAvailable] = useState(false)
  const [isAdminUser, setIsAdminUser] = useState(false)
  const [downloadTarget, setDownloadTarget] = useState<{ scope: 'section' | 'all'; title: string } | null>(null)
  const openDocs = async () => {
    setDocsOpen(true)
    try {
      const r = await api.get<{ sections: { id: string; title: string; intro: string }[] }>('/kb')
      setDocsSections(r.sections || [])
      if (r.sections?.length) selectDoc(r.sections[0].id)
    } catch { /* ignore */ }
    try {
      const st = await api.get<{ docx_available: boolean; is_admin: boolean }>('/kb/status')
      setDocxAvailable(!!st.docx_available)
      setIsAdminUser(!!st.is_admin)
    } catch { setDocxAvailable(false); setIsAdminUser(false) }
  }
  const selectDoc = async (id: string) => {
    setDocsActive(id)
    setDocsLoading(true)
    try {
      const r = await api.get<{ content: string }>(`/kb/${id}`)
      setDocsContent(r.content || '')
    } catch { setDocsContent('（文档读取失败）') } finally { setDocsLoading(false) }
  }
  // 下载文档（md 文件）
  const downloadDoc = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }
  // 收集全部文档 md（合并）
  const getAllDocsMd = async () => {
    const parts = ['# AIsChat 世界 API 接口文档\n']
    for (const sec of docsSections) {
      try {
        const r = await api.get<{ content: string }>(`/kb/${sec.id}`)
        parts.push(`\n\n---\n\n# ${sec.id} ${sec.title}\n\n` + (r.content || ''))
      } catch { /* 单区失败跳过 */ }
    }
    return parts.join('\n')
  }
  // 下载 docx（pandoc，POST 原生 fetch）
  const downloadDocx = async (md: string, filename: string) => {
    try {
      const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
      const res = await fetch(`${base}/kb/convert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ md, filename }),
      })
      if (!res.ok) throw new Error((await res.text()) || '导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename.endsWith('.docx') ? filename : filename + '.docx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) { setMsg(`docx 导出失败: ${e?.message || e}`) }
  }
  // 下载弹窗确认：按格式执行
  const doDownload = async (format: 'md' | 'docx') => {
    if (!downloadTarget) return
    const { scope, title } = downloadTarget
    const filename = scope === 'section' ? `api-doc-${docsActive || 'doc'}` : 'aischat-world-api-docs'
    if (format === 'md') {
      const md = scope === 'section' ? docsContent : await getAllDocsMd()
      downloadDoc(md, filename + '.md')
    } else {
      const md = scope === 'section' ? docsContent : await getAllDocsMd()
      await downloadDocx(md, filename + '.docx')
    }
    setDownloadTarget(null)
  }

  // 世界 AI 配置表单（单独表单，不属于 agent）
  const [showCreatorForm, setShowCreatorForm] = useState(false)
  // 2.7：LLM 用量/缓存命中率
  const [usageStats, setUsageStats] = useState<WorldUsageStats | null>(null)

  // 当前文件内联渲染：md 渲染 + 查看原文；html/代码高亮渲染；图片直接显示（不用弹窗）
  const [viewMode, setViewMode] = useState<'edit' | 'render'>('edit')

  // ── 视口响应式：移动端 / 桌面端条件渲染（避免双实例导致输入卡顿） ──
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 1024)
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 1024)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // ── 移动端（<lg）：tab 切换（文件/对话，对话默认打开）+ 目录逐层导航 ──
  const [mobileTab, setMobileTab] = useState<'files' | 'chat' | 'preview'>('chat')
  const [mobileView, setMobileView] = useState<'dirs' | 'file'>('dirs')
  const [mobileDir, setMobileDir] = useState('')  // 当前浏览目录（'' = 根）
  // 上传：顶部菜单（上传到此位置 / 选择其它位置）+ 目录选择弹层
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false)
  const [uploadDirPickerOpen, setUploadDirPickerOpen] = useState(false)
  const [groupManagerOpen, setGroupManagerOpen] = useState(false)
  const [myId, setMyId] = useState<number | null>(null)

  useEffect(() => {
    try {
      const me = localStorage.getItem('user_info')
      if (me) setMyId(JSON.parse(me).id ?? null)
    } catch { /* ignore */ }
  }, [])
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
      const f = await api.get<{ files: WorldFile[] }>(`/worlds/${wid}/files`)
      setFiles(f.files || [])
      // 2.7：缓存命中统计（失败静默，不影响主流程）
      try {
        const u = await api.get<WorldUsageStats>(`/worlds/${wid}/usage`)
        setUsageStats(u)
      } catch { /* ignore */ }
      // 默认选中第一个文件（仅当前确实没选中时；用 ref 读实时值，AI 工具刷新不会强制跳转）
      if (f.files?.length && !currentFileRef.current) {
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
      setMsg('已保存')
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
      setMsg('已上传')
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
      setMsg(`已删除 ${path}`)
    } catch (e: any) {
      setMsg(`删除失败: ${e?.message || e}`)
    }
  }

  // ── 文件树（按目录层级构建，文件夹可折叠） ──
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set())

  const fileTree = useMemo(() => buildWorldTree(files), [files])

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

  // 发布到商城：跳转统一发布页（带当前世界预选，表单含标题/描述/标签/同步 GitHub）
  // ── 世界打包：下载 / 导入 zip ──
  const [worldZipOpen, setWorldZipOpen] = useState(false)
  const downloadWorldZip = async (includeContent: boolean) => {
    setWorldZipOpen(false)
    try {
      const base = (localStorage.getItem('instance_url') || '').replace(/\/+$/, '') + '/api'
      const res = await fetch(`${base}/worlds/${worldId}/export?include_content=${includeContent}`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
      })
      if (!res.ok) throw new Error((await res.text()).slice(0, 120) || '下载失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `world_${worldId}.zip`
      a.click()
      URL.revokeObjectURL(url)
      setMsg(includeContent ? '已下载世界包（含数据文件）' : '已下载世界包（不含数据文件）')
    } catch (err: any) { setMsg(`下载失败: ${err?.message || err}`) }
  }
  const importZipRef = useRef<HTMLInputElement>(null)
  const handleImportZip = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''  // 允许重复选同一文件
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) { setMsg('请选择 zip 文件'); return }
    if (!confirm('导入将覆盖除数据文件（content/）外的同名文件，确认继续？')) return
    try {
      const fd = new FormData()
      fd.append('file', f)
      const r = await api.post<{ imported: number; skipped_content?: number }>(`/worlds/${worldId}/files/import`, fd)
      setMsg(`导入成功：${r?.imported ?? 0} 个文件${r?.skipped_content ? `（跳过数据文件 ${r.skipped_content}）` : ''}`)
      load()
    } catch (err: any) { setMsg(`导入失败: ${err?.message || err}`) }
  }

  const publishToMarket = () => {
    if (!world) return
    navigate(`/market/publish?world_id=${wid}`)
  }

  // ── 聊天面板引用（内部管理所有聊天状态） ──
  const chatHandleRef = useRef<WorldChatHandle>(null)
  const [chatUnreadCount, setChatUnreadCount] = useState(0)

  // world 加载完成 → 聊天面板渲染 → 确保在底部
  useEffect(() => {
    if (world) chatHandleRef.current?.forceScrollToBottom()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world])

  // ── 聊天面板内容（桌面右栏 / 移动端对话 tab 共用） ──
  const renderChatInner = () => {
    if (!world) return null
    return (
    <>
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{world.creator?.name || '群视界机器人'}</span>
          {chatUnreadCount > 0 && (
            <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold animate-pulse">
              {chatUnreadCount > 99 ? '99+' : chatUnreadCount}
            </span>
          )}
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-elevated text-textMuted">{world.creator?.id}</span>
          <div className="flex-1" />
          <button
            onClick={() => setShowCreatorForm((v) => !v)}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-elevated hover:bg-border text-textSecondary transition-colors"
            title="世界 AI 配置（单独表单，不属于 agent）"
          >
            <Settings size={12} /> 配置
          </button>
        </div>
        <div className="text-xs text-textMuted mt-0.5">世界 AI 是世界的配置：让它改界面、加功能</div>
      </div>

      {showCreatorForm && world && world.creator && (
        <WorldCreatorConfig
          wid={wid}
          creator={world.creator}
          usageStats={usageStats}
          onSaved={(updated) => setWorld((w) => (w ? { ...w, creator: updated } : w))}
          onClose={() => setShowCreatorForm(false)}
          onMsg={setMsg}
        />
      )}

      <WorldChatPanel
        ref={chatHandleRef}
        wid={wid}
        onRefresh={load}
        onMsg={setMsg}
        onUnreadCountChange={setChatUnreadCount}
      />
    </>
    )
  }

  if (loading) return <div className="flex items-center justify-center h-screen text-textMuted">加载中...</div>
  if (!world) return <div className="p-8 text-textMuted">世界不存在</div>

  return (
    <div className="h-screen bg-canvas text-textPrimary">
      {/* ═══ 移动端（<lg）：tab 切换 ── 文件（目录导航/编辑器）+ 对话（默认打开） ═══ */}
      {isMobile && <div className="flex flex-col h-full relative pb-14">
        {/* 顶栏：返回 + 世界信息 + 上传（文件 tab 时显示） */}
        <div className="flex items-center gap-2 px-3 py-2 bg-surface border-b border-border">
          <button onClick={() => navigate('/worlds')} className="inline-flex items-center gap-1 text-sm text-textMuted hover:text-textPrimary transition-colors shrink-0">
            <ChevronLeft size={14} />
            世界
          </button>
          <span className="font-semibold truncate">{world.name}</span>
          <span className={`hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full shrink-0 ${world.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-elevated text-textMuted'}`}>
            {world.status === 'active' ? '活跃' : '休眠'}
          </span>
          <div className="flex-1" />
          <button onClick={openDocs} className="shrink-0 p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="接口文档（发给世界 AI 的 md）">
            <BookOpen size={14} />
          </button>
          <button onClick={() => setWorldZipOpen(true)} className="shrink-0 p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="下载世界包（zip）">
            <Download size={14} />
          </button>
          <button onClick={() => importZipRef.current?.click()} className="shrink-0 p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="导入世界包（zip 批量导入，不动数据文件）">
            <FolderInput size={14} />
          </button>
          <button onClick={publishToMarket} className="shrink-0 inline-flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors px-2 py-1 whitespace-nowrap" title="发布到世界商城">
            <Upload size={13} /> 发布
          </button>
          <button onClick={() => setGroupManagerOpen(true)} className="shrink-0 p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="群类型与群助手">
            <MoreHorizontal size={16} />
          </button>
          {mobileTab === 'files' && (
            <div className="relative shrink-0">
              <button onClick={() => setUploadMenuOpen((v) => !v)} className="inline-flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors px-2 py-1 whitespace-nowrap" title="上传文件">
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

        {/* tab：文件 / 对话 / 预览（对话默认打开） */}
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
          <button
            onClick={() => setMobileTab('preview')}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 text-sm transition-colors ${mobileTab === 'preview' ? 'text-primary-400 border-b-2 border-primary-500 font-medium' : 'text-textMuted'}`}
          >
            <Eye size={14} /> 预览
          </button>
        </div>

        {/* 内容区：对话 tab（默认）/ 预览 tab（iframe）/ 文件 tab（目录导航 → 编辑器） */}
        {mobileTab === 'chat' ? (
          <div className="flex-1 flex flex-col min-h-0 bg-surface">
            {renderChatInner()}
          </div>
        ) : mobileTab === 'preview' ? (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-3 py-1.5 text-xs text-textSecondary bg-surface/60 border-b border-border flex items-center gap-2">
              <span className="truncate flex-1">世界预览（/world/{wid}/preview）</span>
              <button onClick={() => setPreviewKey((k) => k + 1)} className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors shrink-0" title="刷新预览"><RefreshCw size={12} /> 刷新</button>
              <button
                onClick={() => { if (!tryOpenWorldWindow(wid)) navigate(`/world-view/${wid}`) }}
                className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors shrink-0"
                title="在沉浸界面新窗口打开（WebView 下自动应用内跳转）"
              ><ExternalLink size={12} /> 沉浸窗口</button>
            </div>
            <iframe
              key={previewKey}
              src={`/world/${wid}/preview`}
              className="w-full flex-1 bg-white dark:bg-gray-900"
              title="世界预览"
            />
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
      </div>}

      {/* ═══ 桌面端（≥lg）：标题栏 + 三栏（分隔线贯穿，拖拽手柄覆盖标题栏与内容区） ═══ */}
      {!isMobile && <div className="flex flex-col h-full">
        {/* 顶部工具栏 */}
        <div className="flex items-center gap-3 px-4 h-14 bg-surface border-b border-border shrink-0">
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
          <button onClick={openDocs} className="p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="接口文档（发给世界 AI 的 md）">
            <BookOpen size={15} />
          </button>
          <button onClick={() => setWorldZipOpen(true)} className="text-xs px-3 py-1 rounded transition-colors bg-elevated hover:bg-border text-textSecondary" title="下载世界包（zip）">
            <Download size={13} className="inline mr-1" />下载世界包
          </button>
          <input ref={importZipRef} type="file" accept=".zip" className="hidden" onChange={handleImportZip} />
          <button onClick={() => importZipRef.current?.click()} className="text-xs px-3 py-1 rounded transition-colors bg-elevated hover:bg-border text-textSecondary" title="导入世界包（zip 批量导入，不动数据文件）">
            <Upload size={13} className="inline mr-1" />导入世界包
          </button>
          <button onClick={publishToMarket} className="text-xs px-3 py-1 rounded transition-colors bg-elevated hover:bg-border text-primary-400" title="发布到世界商城（打包代码区）">发布</button>
          <button onClick={() => setGroupManagerOpen(true)} className="p-1.5 text-textMuted hover:text-textPrimary transition-colors" title="群类型与群助手">
            <MoreHorizontal size={16} />
          </button>
          {msg && <span className="text-xs text-amber-400">{msg}</span>}
        </div>
        {/* 标题栏：文件（居中于文件树+编辑区整块） | 对话（右列上方）；内容行手柄贯穿 */}
        <div className="flex items-stretch bg-surface border-b border-border">
          <div className="flex flex-1 relative h-9">
            <div style={{ width: fileWidth }} className="shrink-0" />
            <div className="flex-1" />
            <div className="absolute inset-0 flex items-center justify-center gap-1.5 font-medium text-textSecondary">
              {mode === 'preview' ? (
                <><Eye size={14} className="text-textMuted" /> 预览</>
              ) : (
                <><Folder size={14} className="text-textMuted" /> 文件</>
              )}
            </div>
          </div>
          <div style={{ width: effectiveChatWidth }} className="shrink-0 flex items-center justify-center gap-1.5 h-9 font-medium text-textSecondary border-l border-border">
            <MessageCircle size={14} className="text-textMuted" />
            对话
          </div>
        </div>
        {/* 内容行：拖拽手柄贯穿（拖动 = 整列宽度同步） */}
        <div className="flex flex-1 min-h-0">
        {/* 左列：文件树（仅文件模式；预览模式隐藏，让预览覆盖文件树+编辑区整块） */}
        {mode === 'files' && (
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
            <WorldFileTree files={files} currentFile={currentFile} collapsedDirs={collapsedDirs} onToggleDir={toggleDir} onSelect={selectFile} onDelete={deleteFile} />
          </div>
        </div>
        )}
        {mode === 'files' && (
        <div onMouseDown={fileResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors relative z-[70]" />
        )}
        {/* 中列：编辑 / 预览（预览模式撑满文件树+编辑区整块） */}
        <div className="flex-1 flex flex-col min-w-0" style={{ minWidth: MIN_EDITOR }}>
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
                  <button onClick={() => setPreviewKey((k) => k + 1)} className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors shrink-0" title="刷新预览"><RefreshCw size={12} /> 刷新</button>
                  <button
                    onClick={() => { if (!tryOpenWorldWindow(wid)) navigate(`/world-view/${wid}`) }}
                    className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-300 transition-colors shrink-0"
                    title="在沉浸界面新窗口打开（WebView 下自动应用内跳转）"
                  >
                    <ExternalLink size={12} /> 沉浸窗口
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
        <div onMouseDown={chatResizeStart} className="w-1 shrink-0 cursor-col-resize hover:bg-primary-500/40 transition-colors relative z-[70]" />
        {/* 右列：对话面板（标题已在顶部标题栏） */}
        <div ref={chatPanelRef} className="flex flex-col shrink-0 bg-surface" style={{ width: effectiveChatWidth, maxWidth: effectiveChatWidth }}>
          <div className="flex-1 min-h-0 flex flex-col">
            {renderChatInner()}
          </div>
        </div>
        </div>
      </div>}

      {/* 接口文档查看（程序员用） */}
      {docsOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setDocsOpen(false)}>
          <div className="w-full max-w-4xl bg-surface border border-border rounded-2xl max-h-[85vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen size={15} className="text-primary-400" />
                <span className="text-sm font-semibold text-textPrimary">世界 API 接口文档</span>
                <span className="text-[10px] text-textMuted">发给世界 AI 的 md（view_api_doc 同源）</span>
              </div>
              <button onClick={() => setDocsOpen(false)} className="p-1 text-textMuted hover:text-textPrimary transition-colors" title="关闭"><X size={16} /></button>
            </div>
            <div className="flex flex-1 min-h-0">
              {/* 分区列表 */}
              <div className="w-52 shrink-0 border-r border-border overflow-y-auto p-2 space-y-1">
                {docsSections.map((sec) => (
                  <button
                    key={sec.id}
                    onClick={() => selectDoc(sec.id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg transition-colors ${docsActive === sec.id ? 'bg-primary-500/15 text-primary-300' : 'hover:bg-elevated text-textSecondary'}`}
                  >
                    <div className="text-xs font-medium">{sec.id} {sec.title}</div>
                    <div className="text-[10px] text-textMuted line-clamp-2 mt-0.5">{sec.intro}</div>
                  </button>
                ))}
              </div>
              {/* 内容 */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center gap-2 px-4 py-2 border-b border-border shrink-0">
                  <span className="text-xs text-textSecondary truncate flex-1">
                    {docsSections.find((s) => s.id === docsActive)?.title || '接口文档'}
                  </span>
                  <button
                    onClick={() => setDownloadTarget({ scope: 'section', title: '下载此分区' })}
                    disabled={!docsContent || docsLoading}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-elevated text-textSecondary hover:text-textPrimary transition-colors disabled:opacity-40 shrink-0"
                  >
                    <Download size={11} /> 下载此分区
                  </button>
                  <button
                    onClick={() => setDownloadTarget({ scope: 'all', title: '下载全部' })}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-elevated text-textSecondary hover:text-textPrimary transition-colors shrink-0"
                  >
                    <Download size={11} /> 下载全部
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-4 min-w-0">
                {docsLoading ? (
                  <div className="flex items-center justify-center py-16 text-textMuted text-sm">加载中…</div>
                ) : (
                  <div className="max-w-none prose prose-sm dark:prose-invert [&_pre]:!bg-transparent [&_pre]:!p-0 [&_pre]:!m-0 [&_pre]:!rounded-none [&_pre]:!border-0">
                    <MarkdownContent content={docsContent} isMine={false} />
                  </div>
                )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 下载类型弹窗（md / docx；未装 pandoc 时只 md，管理员看安装提示） */}
      {downloadTarget && (
        <div className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4" onClick={() => setDownloadTarget(null)}>
          <div className="w-full max-w-xs bg-surface border border-border rounded-2xl p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-semibold text-textPrimary mb-1">{downloadTarget.title}</div>
            <div className="text-[10px] text-textMuted mb-3">
              {downloadTarget.scope === 'section' ? `当前分区：${docsSections.find((s) => s.id === docsActive)?.title || docsActive || '文档'}` : '全部分区合并'}
            </div>
            <div className="space-y-2">
              <button
                onClick={() => doDownload('md')}
                className="w-full inline-flex items-center justify-center gap-1.5 py-2.5 text-sm bg-elevated hover:bg-border text-textPrimary rounded-xl transition-colors"
              >
                <FileText size={13} /> 下载 .md
              </button>
              {docxAvailable && (
                <button
                  onClick={() => doDownload('docx')}
                  className="w-full inline-flex items-center justify-center gap-1.5 py-2.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-xl transition-colors"
                >
                  <FileText size={13} /> 下载 .docx（Word）
                </button>
              )}
            </div>
            {!docxAvailable && isAdminUser && (
              <div className="mt-3 text-[10px] text-amber-400/90 leading-relaxed">
                如需下载为 docx（Word），请前往管理页安装 pandoc 插件后重启后端。
              </div>
            )}
            <button onClick={() => setDownloadTarget(null)} className="w-full mt-3 py-1.5 text-xs text-textMuted hover:text-textPrimary transition-colors">取消</button>
          </div>
        </div>
      )}

      {/* 世界包下载（含/不含数据文件） */}
      {worldZipOpen && (
        <div className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4" onClick={() => setWorldZipOpen(false)}>
          <div className="w-full max-w-xs bg-surface border border-border rounded-2xl p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-semibold text-textPrimary mb-1">下载世界包</div>
            <div className="text-[10px] text-textMuted mb-3">
              导出为 zip，Windows 可直接解压。数据文件（content/）是运行产物。
            </div>
            <div className="space-y-2">
              <button
                onClick={() => downloadWorldZip(true)}
                className="w-full inline-flex items-center justify-center gap-1.5 py-2.5 text-sm bg-elevated hover:bg-border text-textPrimary rounded-xl transition-colors"
              >
                <Download size={13} /> 含数据文件（完整备份）
              </button>
              <button
                onClick={() => downloadWorldZip(false)}
                className="w-full inline-flex items-center justify-center gap-1.5 py-2.5 text-sm bg-primary-500 hover:bg-primary-400 text-white rounded-xl transition-colors"
              >
                <Download size={13} /> 不含数据文件（代码+资源）
              </button>
            </div>
            <button onClick={() => setWorldZipOpen(false)} className="w-full mt-3 py-1.5 text-xs text-textMuted hover:text-textPrimary transition-colors">取消</button>
          </div>
        </div>
      )}

      {/* 群类型与群助手管理（… 菜单） */}
      {groupManagerOpen && world && (
        <GroupManagerModal
          worldId={wid}
          isOwner={myId !== null && world.owner_id === myId}
          onClose={() => setGroupManagerOpen(false)}
        />
      )}
    </div>
  )
}