import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useSearchParams, useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import { Users, Bot, MessageCircle, Ticket, FileText, Activity, Terminal, Database, Globe, BookOpen, ScrollText, ArrowLeft, BarChart3, ChevronRight, Key, Settings, Layers, Wrench, Shield, Plug } from 'lucide-react'
import { MANUAL_URL, ADMIN_MANUAL_URL } from '../constants'
import Toggle from '../components/Toggle'
import { useT } from '../i18n/I18nContext'
import { LANGUAGES } from '../i18n/languages'
import { useResizableSidebar } from '../hooks/useResizableSidebar'
import FederationTab from '../components/FederationTab'
import ConversationLogTab from '../components/ConversationLogTab'
import UsageDashboardTab from '../components/UsageDashboardTab'
import SystemMetricsTab from '../components/SystemMetricsTab'
import ApiKeyPoolTab from '../components/ApiKeyPoolTab'
import SystemPromptTab from '../components/SystemPromptTab'
import ToolsSkillsTab from '../components/ToolsSkillsTab'
import AuthSettingsTab from '../components/AuthSettingsTab'
import PluginManager from '../components/PluginManager'

type Tab = 'overview' | 'users' | 'agents' | 'groups' | 'codes' | 'logs' | 'opencli' | 'backup' | 'federation' | 'convlog' | 'usage' | 'metrics' | 'apipool' | 'system' | 'prompt' | 'tools' | 'auth' | 'plugins'
type TabCategory = string

const renderContent = (activeTab: Tab) => {
  switch (activeTab) {
    case 'overview': return <OverviewTab />
    case 'users': return <UsersTab />
    case 'agents': return <AgentsTab />
    case 'groups': return <GroupsTab />
    case 'codes': return <CodesTab />
    case 'opencli': return <OpenCLITab />
    case 'backup': return <BackupTab />
    case 'logs': return <LogsTab />
    case 'federation': return <FederationTab />
    case 'convlog': return <ConversationLogTab />
    case 'usage': return <UsageDashboardTab />
    case 'metrics': return <SystemMetricsTab />
    case 'apipool': return <ApiKeyPoolTab />
    case 'system': return <SystemSettingsTab />
    case 'prompt': return <SystemPromptTab />
    case 'tools': return <ToolsSkillsTab />
    case 'auth': return <AuthSettingsTab />
    case 'plugins': return <PluginManager />
    default: return <OverviewTab />
  }
}

export default function AdminPage() {
  const t = useT()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabs: { key: Tab; label: string; icon: React.ElementType; desc: string; category: string }[] = [
    { key: 'overview', label: t('admin.overview'), icon: Activity, desc: t('admin.overview'), category: t('admin.categoryCore') },
    { key: 'users', label: t('admin.users'), icon: Users, desc: t('admin.users'), category: t('admin.categoryCore') },
    { key: 'agents', label: t('admin.agents'), icon: Bot, desc: t('admin.agents'), category: t('admin.categoryCore') },
    { key: 'groups', label: t('admin.groups'), icon: MessageCircle, desc: t('admin.groups'), category: t('admin.categoryCore') },
    { key: 'codes', label: t('admin.codes'), icon: Ticket, desc: t('admin.codes'), category: t('admin.categoryOps') },
    { key: 'opencli', label: t('admin.opencli'), icon: Terminal, desc: t('admin.opencli'), category: t('admin.categoryOps') },
    { key: 'convlog', label: t('admin.logs'), icon: ScrollText, desc: t('admin.logs'), category: t('admin.categoryOps') },
    { key: 'backup', label: t('admin.backup'), icon: Database, desc: t('admin.backup'), category: t('admin.categorySystem') },
    { key: 'logs', label: t('admin.audit'), icon: FileText, desc: t('admin.audit'), category: t('admin.categorySystem') },
    { key: 'federation', label: t('admin.federation'), icon: Globe, desc: t('admin.federation'), category: t('admin.categorySystem') },
    { key: 'usage', label: t('admin.usage'), icon: BarChart3, desc: t('admin.usage'), category: t('admin.categorySystem') },
    { key: 'metrics', label: t('admin.systemMetrics'), icon: Activity, desc: t('admin.systemMetrics'), category: t('admin.categorySystem') },
    { key: 'apipool', label: t('admin.apikeyPool'), icon: Key, desc: t('admin.apikeyPool'), category: t('admin.categoryOps') },
    { key: 'system', label: t('admin.system'), icon: Settings, desc: t('admin.system'), category: t('admin.categorySystem') },
    { key: 'prompt', label: '系统提示词', icon: Layers, desc: '查看和自定义发给 AI 的系统提示词段', category: t('admin.categorySystem') },
    { key: 'tools', label: t('admin.toolsSkills'), icon: Wrench, desc: t('admin.toolsSkills'), category: t('admin.categorySystem') },
    { key: 'auth', label: t('admin.auth'), icon: Shield, desc: t('admin.authDesc'), category: t('admin.categorySystem') },
    { key: 'plugins', label: '插件管理', icon: Plug, desc: '管理浏览器上网等扩展服务', category: t('admin.categorySystem') },
  ]
  const initialTab = (searchParams.get('tab') as Tab) || 'overview'
  const [activeTab, setActiveTab] = useState<Tab>(initialTab)
  // 移动端：'list' 显示导航列表，'detail' 显示选中内容
  const [mobileView, setMobileView] = useState<'list' | 'detail'>(
    searchParams.get('tab') ? 'detail' : 'list'
  )
  const navigate = useNavigate()
  const sidebarRef = useRef<HTMLDivElement>(null)
  const { sidebarWidth, handleResizeStart } = useResizableSidebar('admin_sidebar_width', sidebarRef)

  const switchTab = (tab: Tab) => {
    setActiveTab(tab)
    setSearchParams({ tab })
    setMobileView('detail')
  }

  const backToList = () => {
    setMobileView('list')
  }

  const currentTab = tabs.find(t => t.key === activeTab)

  return (
    <div className="h-full flex flex-col bg-canvas">
      {/* 头部 */}
      <div className="px-4 md:px-6 py-4 border-b border-border bg-surface shrink-0">
        <div className="flex items-center gap-2 mb-1">
          {/* 返回按钮：移动端列表视图→我的；桌面端→我的；移动端详情→列表 */}
          {mobileView === 'detail' ? (
            <button
              onClick={backToList}
              className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
              title={t('admin.backToList')}
            >
              <ArrowLeft size={20} />
            </button>
          ) : (
            <button
              onClick={() => navigate('/me')}
              className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
              title={t('admin.backToMe')}
            >
              <ArrowLeft size={20} />
            </button>
          )}
          <h1 className="text-xl font-bold text-textPrimary tracking-tight">
            {mobileView === 'detail' && currentTab ? currentTab.label : t('admin.title')}
          </h1>
        </div>
        {mobileView === 'list' && (
          <div className="flex items-center gap-1.5 flex-wrap text-sm text-textSecondary mt-0.5">
            <span>{t('admin.subtitle')}</span>
            <Link
              to={MANUAL_URL}
              className="inline-flex items-center gap-1 text-primary-400 hover:text-primary-500 dark:hover:text-primary-300 transition-colors"
            >
              <BookOpen size={13} /> {t('nav.manual')}
            </Link>
            <Link
              to={ADMIN_MANUAL_URL}
              className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-500 dark:hover:text-amber-300 transition-colors"
            >
              <BookOpen size={13} /> {t('nav.adminManual')}
            </Link>
          </div>
        )}
      </div>

      {/* 桌面端：左侧竖标签 + 右侧内容 */}
      <div className="hidden md:flex flex-1 overflow-hidden">
        {/* 左侧标签栏（可拖拽宽度） */}
        <div ref={sidebarRef} className="shrink-0 relative border-r border-border bg-surface flex flex-col overflow-y-auto min-h-0" style={{ width: sidebarWidth }}>
          {([t('admin.categoryCore'), t('admin.categoryOps'), t('admin.categorySystem')]).map(cat => {
            const catTabs = tabs.filter(t => t.category === cat)
            return (
              <div key={cat}>
                <div className="px-3 h-8 border-b border-border font-medium text-[11px] text-textMuted uppercase tracking-wider flex items-center shrink-0">
                  {cat}
                </div>
                <div className="py-0.5">
                  {catTabs.map(tab => (
                    <button
                      key={tab.key}
                      onClick={() => switchTab(tab.key)}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 text-[13px] transition-colors text-left ${
                        activeTab === tab.key
                          ? 'bg-primary-500/10 text-primary-600 dark:text-primary-300 border-r-2 border-primary-400'
                          : 'text-textSecondary hover:bg-elevated hover:text-textPrimary border-r-2 border-transparent'
                      }`}
                    >
                      <tab.icon size={16} className="shrink-0" />
                      <span className="truncate">{tab.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
          {/* 拖拽手柄 */}
          <div
            className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-primary-400/30 active:bg-primary-400/50 transition-colors z-10"
            onMouseDown={handleResizeStart}
          />
        </div>
        {/* 右侧内容区 */}
        <div className="flex-1 overflow-y-auto p-6 bg-canvas">
          {renderContent(activeTab)}
        </div>
      </div>

      {/* 移动端：导航列表视图（按分类分组） */}
      {mobileView === 'list' && (
        <div className="md:hidden flex-1 overflow-y-auto p-4 pb-[var(--safe-bottom)] bg-canvas space-y-4">
          {([t('admin.categoryCore'), t('admin.categorySystem'), t('admin.categoryOps')]).map(cat => {
            const catTabs = tabs.filter(t => t.category === cat)
            return (
              <div key={cat}>
                <div className="text-xs font-semibold text-textMuted uppercase tracking-wider px-1 mb-1.5">{cat}</div>
                <div className="space-y-1">
                  {catTabs.map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => switchTab(tab.key)}
                      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-elevated active:bg-border/50 transition-colors text-left"
                    >
                      <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0">
                        <tab.icon size={18} className="text-primary-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-textPrimary">{tab.label}</div>
                        <div className="text-xs text-textMuted mt-0.5">{tab.desc}</div>
                      </div>
                      <ChevronRight size={16} className="text-textMuted shrink-0" />
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 移动端：详情内容区 */}
      <div className={`md:hidden flex-1 overflow-y-auto p-4 pb-[var(--safe-bottom)] bg-canvas ${
        mobileView === 'list' ? 'hidden' : ''
      }`}>
        {renderContent(activeTab)}
      </div>
    </div>
  )
}

function OverviewTab() {
  const t = useT()
  const [stats, setStats] = useState<any>(null)
  const [mt, setMt] = useState<{ hard: boolean; soft: boolean; auto: boolean }>({ hard: false, soft: false, auto: false })
  useEffect(() => {
    api.get('/admin/overview').then(setStats).catch(console.error)
    api.get('/admin/maintenance').then((d: any) => setMt({ hard: !!d.hard, soft: !!d.soft, auto: !!d.auto })).catch(() => {})
  }, [])

  const toggleHard = async () => {
    try { const d: any = await api.post('/admin/maintenance/hard'); setMt(prev => ({ ...prev, hard: !!d.hard })) } catch {}
  }
  const toggleSoft = async () => {
    try { const d: any = await api.post('/admin/maintenance/soft'); setMt(prev => ({ ...prev, soft: !!d.soft })) } catch {}
  }

  if (!stats) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label={t('admin.totalUsers')} value={stats.total_users} icon={Users} />
        <StatCard label={t('admin.totalAgents')} value={stats.total_agents} icon={Bot} />
        <StatCard label={t('admin.totalGroups')} value={stats.total_groups} icon={MessageCircle} />
        <StatCard label={t('admin.pendingRequests')} value={stats.pending_vector_requests} icon={Activity} />
      </div>
      <div className={`p-4 rounded-xl border ${(mt.hard || mt.soft) ? 'border-amber-500/40 bg-amber-500/5' : 'border-border bg-surface'}`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${(mt.hard || mt.soft) ? 'bg-amber-500/10' : 'bg-mint-400/10'}`}>
              <Wrench size={20} className={(mt.hard || mt.soft) ? 'text-amber-400' : 'text-mint-400'} />
            </div>
            <div>
              <p className="font-medium text-textPrimary">维护模式</p>
              <p className="text-xs text-textSecondary">
                {mt.hard ? '🔒 暂停服务' : ''}{mt.hard && mt.soft ? ' · ' : ''}{mt.soft ? '⚠️ 维护提示' : ''}
                {!mt.hard && !mt.soft && '正常'}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={toggleHard}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                mt.hard ? 'bg-mint-500 hover:bg-mint-400 text-white' : 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30'
              }`}>
              {mt.hard ? '恢复服务' : '暂停服务'}
            </button>
            <button onClick={toggleSoft}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                mt.soft ? 'bg-mint-500 hover:bg-mint-400 text-white' : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30'
              }`}>
              {mt.soft ? '取消提示' : '维护提示'}
            </button>
          </div>
        </div>
      </div>

      {/* 状态流程 */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <p className="text-xs font-semibold text-textSecondary uppercase tracking-wider mb-3">服务器状态</p>
        <div className="flex items-center gap-0.5 text-xs flex-wrap">
          {[
            { label: '启动中',       active: mt.auto, dot: mt.auto ? 'bg-amber-400 animate-pulse' : 'bg-gray-300' },
            { label: '· 运行中 ·',   active: !mt.auto && !mt.hard, dot: (!mt.auto && !mt.hard) ? 'bg-mint-400' : 'bg-gray-300' },
            { label: '暂停服务',     active: mt.hard, dot: mt.hard ? 'bg-rose-400' : 'bg-gray-300' },
            { label: '· 维护提示 ·', active: mt.soft, dot: mt.soft ? 'bg-amber-400' : 'bg-gray-300' },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-1">
              <div className={`flex items-center gap-1 px-2 py-1 rounded-lg border ${s.active ? 'border-border' : 'border-transparent'}`}>
                <div className={`w-2 h-2 rounded-full ${s.dot}`} />
                <span className={`text-[10px] whitespace-nowrap ${s.active ? 'font-medium text-textPrimary' : 'text-textMuted'}`}>{s.label}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-textMuted mt-3">
          {mt.auto ? '⚡ 后端启动/关闭中——自动暂停服务' : mt.hard ? '🔴 管理员暂停了服务' : mt.soft ? '🟡 管理员开启了维护提示' : '🟢 服务完全正常'}
        </p>
      </div>

      {/* 文案编辑 */}
      <MaintenanceMsgEditor />
    </div>
  )
}

function MaintenanceMsgEditor() {
  const [msg, setMsg] = useState({ hard_title: '', hard_body: '', soft_text: '' })
  const [loaded, setLoaded] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/admin/maintenance/msg').then((d: any) => {
      setMsg({ hard_title: d.hard_title || '', hard_body: d.hard_body || '', soft_text: d.soft_text || '' })
      setLoaded(true)
    }).catch(() => {})
  }, [])

  const save = async () => {
    try {
      await api.put('/admin/maintenance/msg', msg)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch {}
  }

  if (!loaded) return null

  return (
    <div className="bg-surface rounded-xl border border-border p-5">
      <p className="text-xs font-semibold text-textSecondary uppercase tracking-wider mb-3">维护文案</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-[10px] text-textMuted mb-1">暂停服务——弹窗标题</label>
          <input value={msg.hard_title} onChange={e => setMsg({...msg, hard_title: e.target.value})}
            className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-sm text-textPrimary text-xs focus:outline-none focus:ring-1 focus:ring-primary-500/50" />
        </div>
        <div>
          <label className="block text-[10px] text-textMuted mb-1">暂停服务——弹窗正文</label>
          <input value={msg.hard_body} onChange={e => setMsg({...msg, hard_body: e.target.value})}
            className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-sm text-textPrimary text-xs focus:outline-none focus:ring-1 focus:ring-primary-500/50" />
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-textMuted mb-1">维护提示——顶部横幅文字</label>
          <input value={msg.soft_text} onChange={e => setMsg({...msg, soft_text: e.target.value})}
            className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-sm text-textPrimary text-xs focus:outline-none focus:ring-1 focus:ring-primary-500/50" />
        </div>
      </div>
      <div className="flex items-center gap-3 mt-3">
        <button onClick={save} className="px-4 py-1.5 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-400 transition-colors">
          保存文案
        </button>
        {saved && <span className="text-xs text-mint-400">已保存</span>}
      </div>
    </div>
  )
}

function StatCard({ label, value, icon: Icon }: { label: string; value: number; icon: React.ElementType }) {
  return (
    <div className="bg-surface rounded-xl border border-border p-5 hover:border-primary-500/20 transition-colors">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary-500/10 flex items-center justify-center">
          <Icon size={20} className="text-primary-400" />
        </div>
        <div>
          <p className="text-2xl font-bold text-textPrimary">{value}</p>
          <p className="text-xs text-textSecondary">{label}</p>
        </div>
      </div>
    </div>
  )
}

function UsersTab() {
  const t = useT()
  const [data, setData] = useState<any>(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    api.get(`/admin/users?page=${page}`).then(setData).catch(console.error)
  }, [page])

  if (!data) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-textPrimary">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColId')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColUsername')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColRole')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColQuota')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColStatus')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.usersColAction')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((u: any) => (
              <tr key={u.id} className="border-b border-border/50">
                <td className="py-2 px-3">{u.id}</td>
                <td className="py-2 px-3 font-medium">{u.username}</td>
                <td className="py-2 px-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    u.role === 'admin' ? 'bg-primary-500/10 text-primary-600 dark:text-primary-300' : ''
                  }`}>
                    {u.role}
                  </span>
                </td>
                <td className="py-2 px-3">{u.ai_quota}</td>
                <td className="py-2 px-3">
                  <span className={`text-xs ${u.is_active ? 'text-mint-400' : 'text-rose-400'}`}>
                    {u.is_active ? t('admin.active') : t('admin.banned')}
                  </span>
                </td>
                <td className="py-2 px-3">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={async () => {
                        await api.post(`/admin/users/${u.id}/ban`, {})
                        setPage(page) // 触发刷新
                      }}
                      className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300"
                    >
                      {u.is_active ? t('admin.ban') : t('admin.unban')}
                    </button>
                    {u.role !== 'admin' ? (
                      <button
                        onClick={async () => {
                          if (!confirm(t('admin.confirmPromote').replace('{username}', u.username))) return
                          await api.put(`/admin/users/${u.id}/role`, { role: 'admin' })
                          setPage(page)
                        }}
                        className="text-xs text-mint-400 hover:text-mint-500 dark:hover:text-mint-300"
                      >
                        {t('admin.promote')}
                      </button>
                    ) : (
                      <button
                        onClick={async () => {
                          if (!confirm(t('admin.confirmDemote').replace('{username}', u.username))) return
                          await api.put(`/admin/users/${u.id}/role`, { role: 'user' })
                          setPage(page)
                        }}
                        className="text-xs text-rose-400 hover:text-rose-500"
                      >
                        {t('admin.demote')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 mt-4">
        <button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
          className="text-sm px-3 py-1 border border-border bg-canvas rounded hover:bg-elevated disabled:opacity-40 text-textSecondary"
        >
          {t('common.prevPage')}
        </button>
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={data.items.length < data.page_size}
          className="text-sm px-3 py-1 border border-border bg-canvas rounded hover:bg-elevated disabled:opacity-40 text-textSecondary"
        >
          {t('common.nextPage')}
        </button>
      </div>
    </div>
  )
}

function AgentsTab() {
  const t = useT()
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    api.get('/admin/agents').then(setData).catch(console.error)
  }, [])

  if (!data) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-textPrimary">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColId')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColName')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColOwner')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColStatus')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColSelfEdit')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.agentsColAction')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((a: any) => (
            <tr key={a.id} className="border-b border-border/50">
              <td className="py-2 px-3">{a.id}</td>
              <td className="py-2 px-3 font-medium">{a.name}</td>
              <td className="py-2 px-3">{a.owner_id}</td>
              <td className="py-2 px-3">{a.state}</td>
              <td className="py-2 px-3">
                <span className={a.is_ai_editable ? 'text-mint-400' : 'text-rose-400'}>
                  {a.is_ai_editable ? t('common.yes') : t('common.no')}
                </span>
              </td>
              <td className="py-2 px-3">
                <button
                  onClick={async () => {
                    await api.put(`/admin/agents/${a.id}/editable`, { is_ai_editable: !a.is_ai_editable })
                    // 触发刷新
                    const newData = await api.get('/admin/agents')
                    setData(newData)
                  }}
                  className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300"
                >
                  {a.is_ai_editable ? t('admin.disableSelfEdit') : t('admin.enableSelfEdit')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GroupsTab() {
  const t = useT()
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    api.get('/admin/groups').then(setData).catch(console.error)
  }, [])

  if (!data) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-textPrimary">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.groupsColId')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.groupsColName')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.groupsColOwner')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.groupsColVector')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.groupsColAction')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((g: any) => (
            <tr key={g.id} className="border-b border-border/50">
              <td className="py-2 px-3">{g.id}</td>
              <td className="py-2 px-3 font-medium">{g.name}</td>
              <td className="py-2 px-3">{g.owner_type}:{g.owner_id}</td>
              <td className="py-2 px-3">
                {g.is_vector_accelerated ? t('admin.enabled') : t('admin.notEnabled')}
              </td>
              <td className="py-2 px-3">
                <button
                  onClick={async () => {
                    if (confirm(t('admin.confirmDismissGroup'))) {
                      await api.delete(`/admin/groups/${g.id}`)
                      const newData = await api.get('/admin/groups')
                      setData(newData)
                    }
                  }}
                  className="text-xs text-rose-400 hover:text-rose-500"
                >
                  {t('admin.dismiss')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CodesTab() {
  const t = useT()
  const [codes, setCodes] = useState<any[]>([])
  const [quota, setQuota] = useState(3)
  const [days, setDays] = useState(30)
  const [codeType, setCodeType] = useState('ai_quota')
  const [note, setNote] = useState('')              // v0.6.0
  const [maxUsage, setMaxUsage] = useState<number | null>(null)  // v0.6.0
  const [isApiPool, setIsApiPool] = useState(false)  // v0.6.0
  const [generatedCode, setGeneratedCode] = useState('')
  const [generating, setGenerating] = useState(false)

  const CODE_TYPES: Record<string, string> = {
    ai_quota: t('admin.codeTypeDefault'),
    api_credit: t('admin.creditApi'),
    agent_bundle: t('admin.creditBundle'),
    file_quota: t('admin.creditFile'),
  }

  const loadCodes = async () => {
    try {
      const data = await api.get('/admin/redemption-codes')
      setCodes(data)
    } catch (err) { console.error(err) }
  }

  useEffect(() => { loadCodes() }, [])

  const handleGenerate = async () => {
    setGenerating(true)
    setGeneratedCode('')
    try {
      const data = await api.post('/admin/redemption-codes', {
        quota_amount: quota,
        expires_in_days: days,
        code_type: codeType,
        note: note.trim() || null,
        max_usage: maxUsage ?? null,
        is_api_pool: isApiPool,
      })
      setGeneratedCode(data.code)
      loadCodes()
    } catch (err: any) {
      console.error('生成兑换码失败:', err)
      alert(err?.message || err?.detail || t('admin.generateFailed'))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 生成兑换码 */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <h3 className="font-semibold text-textPrimary mb-3">{t('admin.generateCode')}</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.codeType')}</label>
            <select value={codeType} onChange={(e) => setCodeType(e.target.value)}
              className="px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary">
              {Object.entries(CODE_TYPES).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('me.quota')}</label>
            <input type="number" value={quota} onChange={(e) => setQuota(parseInt(e.target.value) || 0)}
              min={1} max={(codeType === 'file_size' || codeType === 'file_quota') ? 1024 : 100}
              className="w-24 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary" />
          </div>
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.expiresDays')}</label>
            <input type="number" value={days} onChange={(e) => setDays(parseInt(e.target.value) || 1)}
              min={1} max={365}
              className="w-20 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary" />
          </div>
          <div className="flex items-center gap-1.5 self-end mb-1">
            <input type="checkbox" id="isApiPool" checked={isApiPool} onChange={(e) => setIsApiPool(e.target.checked)}
              className="w-4 h-4 rounded border-border bg-canvas text-primary-500" />
            <label htmlFor="isApiPool" className="text-xs text-textSecondary">{t('admin.isApiPool')}</label>
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating || quota < 1 || days < 1}
            className="px-4 py-1.5 bg-primary-500 text-white rounded-xl hover:bg-primary-400 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium transition-colors"
          >
            {generating ? t('admin.generating') : t('admin.generate')}
          </button>
        </div>
        {/* 详细选项 */}
        <div className="flex flex-wrap items-end gap-3 mt-3 pt-3 border-t border-border/40">
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.codeNote')}</label>
            <input type="text" value={note} onChange={(e) => setNote(e.target.value)}
              placeholder={t('admin.codeNotePlaceholder')}
              className="w-48 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary placeholder:text-textMuted" />
          </div>
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.maxUsageLabel')}</label>
            <input type="number" value={maxUsage ?? ''} onChange={(e) => setMaxUsage(e.target.value ? parseInt(e.target.value) : null)}
              min={1}
              className="w-28 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary" />
          </div>
          <span className="text-[11px] text-textMuted pb-1.5">
            {t('admin.balanceHint')}
          </span>
        </div>
        {generatedCode && (
          <div className="mt-3 p-3 bg-mint-400/10 border border-mint-400/20 rounded-xl">
            <p className="text-sm font-mono text-mint-400 break-all">{generatedCode}</p>
            <p className="text-xs text-mint-400 mt-1">{t('admin.codeOneTimeWarning')}</p>
          </div>
        )}
      </div>

      {/* 已生成的兑换码 */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <h3 className="font-semibold text-textPrimary mb-3">{t('admin.codeList')}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-textPrimary">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColCode')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColType')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColAmount')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColNote')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColExpires')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.codesColStatus')}</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((c: any) => (
                <tr key={c.code} className="border-b border-border/50">
                  <td className="py-2 px-3 font-mono text-xs text-textPrimary">
                    {c.code}
                    {c.is_api_pool && <span className="ml-1 px-1 py-0.5 bg-amber-400/10 text-amber-400 rounded text-[10px]">{t('admin.pool')}</span>}
                  </td>
                  <td className="py-2 px-3 text-xs text-textSecondary">{CODE_TYPES[c.code_type] || c.code_type || t('admin.codeTypeDefault')}</td>
                  <td className="py-2 px-3 text-textPrimary">{c.quota_amount}{(c.code_type === 'file_size' || c.code_type === 'file_quota') ? ' MB' : ''}</td>
                  <td className="py-2 px-3 text-xs text-textMuted max-w-[120px] truncate" title={c.note || ''}>{c.note || '-'}</td>
                  <td className="py-2 px-3 text-xs text-textSecondary">{c.expires_at ? new Date(c.expires_at).toLocaleDateString('zh-CN') : '-'}</td>
                  <td className="py-2 px-3">
                    {c.used_by ? (
                      <span className="text-xs text-textMuted">{t('admin.usedBy')} (uid:{c.used_by})</span>
                    ) : (
                      <span className="text-xs text-mint-400">{t('admin.available')}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

/* ================================================================
   数据库备份/恢复
   ================================================================ */
function BackupTab() {
  const t = useT()
  const [downloading, setDownloading] = useState(false)
  const [downloadingFull, setDownloadingFull] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [restoringFull, setRestoringFull] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const fullFileInputRef = useRef<HTMLInputElement>(null)

  const downloadFile = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── 仅数据库备份 ──
  const handleBackup = async () => {
    setDownloading(true)
    setError('')
    setMessage('')
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/admin/backup/download', {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || t('admin.downloadFailed'))
      }
      const blob = await res.blob()
      downloadFile(blob, `aischat_backup_${new Date().toISOString().slice(0, 10)}.sql`)
      setMessage(t('admin.dbBackupSuccess'))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDownloading(false)
    }
  }

  // ── 完整备份（数据库 + 文件）──
  const handleFullBackup = async () => {
    setDownloadingFull(true)
    setError('')
    setMessage('')
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/admin/backup/full/download', {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || t('admin.downloadFailed'))
      }
      const blob = await res.blob()
      downloadFile(blob, `aischat_full_${new Date().toISOString().slice(0, 10)}.tar.gz`)
      setMessage(t('admin.fullBackupSuccess'))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDownloadingFull(false)
    }
  }

  // ── 仅数据库恢复 ──
  const handleRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!confirm(t('admin.restoreWarning'))) return
    setRestoring(true)
    setError('')
    setMessage('')
    try {
      const token = localStorage.getItem('access_token')
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/admin/backup/restore', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || t('admin.restoreFailed'))
      }
      setMessage(t('admin.dbRestoreSuccess'))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRestoring(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // ── 完整恢复（数据库 + 文件）──
  const handleFullRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!confirm(t('admin.restoreWarning'))) return
    setRestoringFull(true)
    setError('')
    setMessage('')
    try {
      const token = localStorage.getItem('access_token')
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/admin/backup/full/restore', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || t('admin.restoreFailed'))
      }
      setMessage(t('admin.fullRestoreSuccess'))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRestoringFull(false)
      if (fullFileInputRef.current) fullFileInputRef.current.value = ''
    }
  }

  return (
    <div className="space-y-5">
      {/* ========== 导出区 ========== */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <h3 className="font-semibold text-textPrimary mb-1">{t('admin.exportTitle')}</h3>
        <p className="text-sm text-textMuted mb-5">{t('admin.exportDesc')}</p>

        {/* 完整备份 */}
        <div className="bg-mint-400/5 border border-mint-400/20 rounded-xl p-4 mb-3">
          <div className="flex items-start gap-3">
            <Database size={20} className="text-mint-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-mint-400">{t('admin.fullBackup')}</h4>
              <p className="text-xs text-textSecondary mt-1" dangerouslySetInnerHTML={{ __html: t('admin.fullBackupDesc') }} />
            </div>
            <button
              onClick={handleFullBackup}
              disabled={downloadingFull}
              className="shrink-0 px-4 py-2 bg-mint-400 text-white rounded-xl hover:bg-mint-500 disabled:opacity-40 text-sm font-medium transition-colors"
            >
              {downloadingFull ? t('admin.packing') : t('admin.downloadFullBackup')}
            </button>
          </div>
        </div>

        {/* 仅数据库 */}
        <div className="bg-canvas border border-border rounded-xl p-4">
          <div className="flex items-start gap-3">
            <Database size={20} className="text-textSecondary shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-textPrimary">{t('admin.dbOnly')}</h4>
              <p className="text-xs text-textSecondary mt-1" dangerouslySetInnerHTML={{ __html: t('admin.dbOnlyDesc') }} />
            </div>
            <button
              onClick={handleBackup}
              disabled={downloading}
              className="shrink-0 px-4 py-2 bg-primary-500 text-white rounded-xl hover:bg-primary-400 disabled:opacity-40 text-sm font-medium transition-colors"
            >
              {downloading ? t('admin.exporting') : t('admin.downloadDbOnly')}
            </button>
          </div>
        </div>
      </div>

      {/* ========== 导入区 ========== */}
      <div className="bg-surface rounded-xl border border-rose-500/30 p-5">
        <h3 className="font-semibold text-textPrimary mb-1">{t('admin.restoreTitle')}</h3>
        <p className="text-sm text-rose-400 mb-5">{t('admin.restoreWarning')}</p>

        {/* 完整恢复 */}
        <div className="bg-rose-400/5 border border-rose-400/20 rounded-xl p-4 mb-3">
          <div className="flex items-start gap-3">
            <Database size={20} className="text-rose-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-rose-400">{t('admin.fullRestore')}</h4>
              <p className="text-xs text-textSecondary mt-1" dangerouslySetInnerHTML={{ __html: t('admin.fullRestoreDesc') }} />
              <input
                ref={fullFileInputRef}
                type="file"
                accept=".tar.gz,.tgz"
                onChange={handleFullRestore}
                disabled={restoringFull}
                className="block mt-2 text-sm text-textPrimary file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:bg-elevated file:text-textPrimary hover:file:bg-border"
              />
              {restoringFull && <p className="text-sm text-textMuted mt-2">{t('admin.restoringFull')}</p>}
            </div>
          </div>
        </div>

        {/* 仅数据库恢复 */}
        <div className="bg-canvas border border-border rounded-xl p-4">
          <div className="flex items-start gap-3">
            <Database size={20} className="text-textSecondary shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-textPrimary">{t('admin.dbRestore')}</h4>
              <p className="text-xs text-textSecondary mt-1" dangerouslySetInnerHTML={{ __html: t('admin.dbRestoreDesc') }} />
              <input
                ref={fileInputRef}
                type="file"
                accept=".sql"
                onChange={handleRestore}
                disabled={restoring}
                className="block mt-2 text-sm text-textPrimary file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:bg-elevated file:text-textPrimary hover:file:bg-border"
              />
              {restoring && <p className="text-sm text-textMuted mt-2">{t('admin.restoring')}</p>}
            </div>
          </div>
        </div>
      </div>

      {message && (
        <div className="text-sm text-mint-400 bg-mint-400/10 px-3 py-2 rounded-lg">{message}</div>
      )}
      {error && (
        <div className="text-sm text-rose-400 bg-rose-400/10 px-3 py-2 rounded-lg">{error}</div>
      )}
    </div>
  )
}

function LogsTab() {
  const t = useT()
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    api.get('/admin/logs?page_size=50').then(setData).catch(console.error)
  }, [])

  if (!data) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-textPrimary">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColTime')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColType')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColOperator')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColTarget')}</th>
            <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColDetail')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((log: any) => (
            <tr key={log.id} className="border-b border-border/50">
              <td className="py-2 px-3 text-xs">
                {log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : '-'}
              </td>
              <td className="py-2 px-3">
                <span className="text-xs px-2 py-0.5 rounded bg-elevated text-textPrimary">{log.log_type}</span>
              </td>
              <td className="py-2 px-3">{log.operator_type}:{log.operator_id}</td>
              <td className="py-2 px-3">{log.target_type}:{log.target_id}</td>
              <td className="py-2 px-3 text-xs text-textSecondary max-w-[200px] truncate">
                {JSON.stringify(log.details)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


// ============================================================
// OpenCLI 管理 Tab
// ============================================================

function OpenCLITab() {
  const t = useT()
  const [tab, setTab] = useState<'config' | 'agents' | 'commands' | 'logs'>('config')
  const subTabs = [
    { key: 'config' as const, label: t('admin.globalConfig') },
    { key: 'agents' as const, label: t('admin.opencliAiWhitelist') },
    { key: 'commands' as const, label: t('admin.commandWhitelist') },
    { key: 'logs' as const, label: t('admin.usageLogs') },
  ]

  return (
    <div className="space-y-4">
      <div className="flex gap-2 bg-canvas border border-border rounded-xl p-1 w-full overflow-x-auto">
        {subTabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors font-medium ${
              tab === t.key
                ? 'bg-elevated text-textPrimary shadow-sm'
                : 'text-textMuted hover:text-textSecondary hover:bg-elevated'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'config' && <OpenCLIConfigSection />}
      {tab === 'agents' && <OpenCLIAgentsSection />}
      {tab === 'commands' && <OpenCLICommandsSection />}
      {tab === 'logs' && <OpenCLILogsSection />}
    </div>
  )
}

// ---- 全局设置 ----
function OpenCLIConfigSection() {
  const t = useT()
  const [config, setConfig] = useState<any>(null)
  const [enabled, setEnabled] = useState(false)
  const [rate, setRate] = useState(5)
  const [timeout, setTimeout_] = useState(30)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/admin/opencli/config').then((d) => {
      setConfig(d)
      setEnabled(d.global_enabled)
      setRate(d.default_rate_limit_per_minute)
      setTimeout_(d.timeout_seconds)
    }).catch(console.error)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put('/admin/opencli/config', {
        global_enabled: enabled,
        default_rate_limit_per_minute: rate,
        timeout_seconds: timeout,
      })
      alert(t('admin.saveSuccess'))
    } catch (err) { console.error(err) }
    setSaving(false)
  }

  if (!config) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="bg-surface rounded-xl border border-border p-5 max-w-lg">
      <h3 className="font-semibold text-textPrimary mb-4">{t('admin.globalConfig')}</h3>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Toggle checked={enabled} onChange={setEnabled} label={t('admin.enableOpenCLI')} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">{t('admin.rateLimit')}</label>
          <input type="number" value={rate} onChange={(e) => setRate(parseInt(e.target.value))}
            className="w-24 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1 text-textSecondary">{t('admin.timeoutSeconds')}</label>
          <input type="number" value={timeout} onChange={(e) => setTimeout_(parseInt(e.target.value))}
            className="w-24 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary" />
        </div>
        <button onClick={handleSave} disabled={saving}
          className="px-4 py-2 bg-primary-500 text-white rounded-xl hover:bg-primary-400 text-sm">
          {saving ? t('admin.saving') : t('admin.save')}
        </button>
      </div>
    </div>
  )
}

// ---- AI 白名单 ----
function OpenCLIAgentsSection() {
  const t = useT()
  const [data, setData] = useState<any[]>([])
  useEffect(() => {
    api.get('/admin/opencli/agents').then(setData).catch(console.error)
  }, [])

  const toggleAgent = async (agentId: number, currentEnabled: boolean) => {
    await api.put(`/admin/opencli/agents/${agentId}`, { enabled: !currentEnabled })
    const newData = await api.get('/admin/opencli/agents')
    setData(newData)
  }

  if (!data.length) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="bg-surface rounded-xl border border-border p-5">
      <h3 className="font-semibold text-textPrimary mb-3">{t('admin.opencliAiWhitelist')}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-textPrimary">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColId')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColName')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColOwner')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColEnabled')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColRate')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.opencliAiWhitelistColAction')}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((a: any) => (
              <tr key={a.agent_id} className="border-b border-border/50">
                <td className="py-2 px-3">{a.agent_id}</td>
                <td className="py-2 px-3 font-medium">{a.agent_name}</td>
                <td className="py-2 px-3">{a.owner_id}</td>
                <td className="py-2 px-3">
                  <span className={a.enabled ? 'text-mint-400' : 'text-textMuted'}>
                    {a.enabled ? t('common.enabled') : t('common.disabled')}
                  </span>
                </td>
                <td className="py-2 px-3">{a.actual_rate_limit}/min</td>
                <td className="py-2 px-3">
                  <button
                    onClick={() => toggleAgent(a.agent_id, a.enabled)}
                    className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300"
                  >
                    {a.enabled ? t('common.disabled') : t('common.enabled')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---- 命令白名单 ----
// ⚠️ 预设命令定义：与后端 POST /admin/opencli/commands/presets 保持一致
//    每个预设包含 pattern（命令名或正则）、is_regex、description（i18n key）、category（i18n key）
function OpenCLICommandsSection() {
  const t = useT()
  const OPENCLI_PRESETS = [
    // ── 文件操作（AI 在自己的沙箱目录里读写，进程内 Python 实现） ──
    { pattern: 'file_read',   is_regex: false, description: t('opencli.preset.fileRead'), category: t('opencli.category.fileOps') },
    { pattern: 'file_write',  is_regex: false, description: t('opencli.preset.fileWrite'), category: t('opencli.category.fileOps') },
    { pattern: 'file_list',   is_regex: false, description: t('opencli.preset.fileList'), category: t('opencli.category.fileOps') },
    { pattern: 'file_delete', is_regex: false, description: t('opencli.preset.fileDelete'), category: t('opencli.category.fileOps') },
    { pattern: 'file_info',   is_regex: false, description: t('opencli.preset.fileInfo'), category: t('opencli.category.fileOps') },
    { pattern: 'create_dir',  is_regex: false, description: t('opencli.preset.createDir'), category: t('opencli.category.fileOps') },
    // ── 浏览器自动化（操控已登录的 Chrome 浏览器） ──
    { pattern: 'browser',   is_regex: false, description: t('opencli.preset.browser'), category: t('opencli.category.browser') },
    { pattern: 'list',      is_regex: false, description: t('opencli.preset.listCmds'), category: t('opencli.category.browser') },
    // ── 外部 CLI 桥接（将已有命令行工具接入 OpenCLI） ──
    { pattern: 'gh .*',     is_regex: true,  description: t('opencli.preset.ghCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'docker .*', is_regex: true,  description: t('opencli.preset.dockerCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'obsidian .*', is_regex: true, description: t('opencli.preset.obsidianCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'vercel .*', is_regex: true,  description: t('opencli.preset.vercelCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'tg .*',     is_regex: true,  description: t('opencli.preset.tgCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'discord .*', is_regex: true, description: t('opencli.preset.discordCli'), category: t('opencli.category.cliBridge') },
    { pattern: 'wx .*',     is_regex: true,  description: t('opencli.preset.wxCli'), category: t('opencli.category.cliBridge') },
  ]
  const [data, setData] = useState<any[]>([])
  const [pattern, setPattern] = useState('')
  const [isRegex, setIsRegex] = useState(false)
  const [desc, setDesc] = useState('')
  const [addingPresets, setAddingPresets] = useState(false)

  const load = async () => {
    const d = await api.get('/admin/opencli/commands')
    setData(Array.isArray(d) ? d : d.items || [])
  }

  useEffect(() => { load() }, [])

  // 检查某个预设是否已在白名单中（按 pattern + is_regex 匹配）
  const isPresetAdded = (pattern: string, isRegex: boolean) => {
    return data.some((c: any) => c.pattern === pattern && c.is_regex === isRegex)
  }

  // 获取已添加预设的当前状态
  const getPresetStatus = (pattern: string, isRegex: boolean) => {
    const found = data.find((c: any) => c.pattern === pattern && c.is_regex === isRegex)
    return found ? (found.enabled ? t('common.enabled') : t('common.disabled')) : t('opencli.status.notAdded')
  }

  const handleAdd = async () => {
    if (!pattern.trim()) return
    await api.post('/admin/opencli/commands', { pattern: pattern.trim(), is_regex: isRegex, description: desc || null })
    setPattern(''); setIsRegex(false); setDesc('')
    load()
  }

  // 一键添加所有预设（调用后端批量 API）
  const handleAddAllPresets = async () => {
    setAddingPresets(true)
    try {
      const result = await api.post('/admin/opencli/commands/presets')
      alert(result.message || t('admin.presetsAddComplete'))
      load()
    } catch (err: any) {
      alert(err.message || t('admin.presetsAddFailed'))
    }
    setAddingPresets(false)
  }

  // 添加单个预设
  const handleAddPreset = async (presetPattern: string, presetIsRegex: boolean, presetDesc: string) => {
    await api.post('/admin/opencli/commands', {
      pattern: presetPattern,
      is_regex: presetIsRegex,
      description: presetDesc,
    })
    load()
  }

  const handleToggle = async (id: number, enabled: boolean) => {
    await api.put(`/admin/opencli/commands/${id}/toggle?enabled=${!enabled}`)
    load()
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('admin.confirmDeletePoolKey').replace('{name}', ''))) return
    await api.delete(`/admin/opencli/commands/${id}`)
    load()
  }

  // 按类别分组预设
  const presetCategories = [...new Set(OPENCLI_PRESETS.map(p => p.category))]

  return (
    <div className="space-y-4">
      {/* ── 预设命令快速添加（新手友好） ── */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-semibold text-textPrimary">{t('admin.presetCommands')}</h3>
            <p className="text-xs text-textMuted mt-1">
              {t('admin.presetCommandsDesc')}
            </p>
          </div>
          <button
            onClick={handleAddAllPresets}
            disabled={addingPresets}
            className="px-4 py-2 bg-mint-500 text-white rounded-xl hover:bg-mint-400 disabled:opacity-50 text-sm font-medium transition-colors"
          >
            {addingPresets ? t('common.saving') : t('admin.addAllPresets')}
          </button>
        </div>

        {presetCategories.map(cat => {
          const catPresets = OPENCLI_PRESETS.filter(p => p.category === cat)
          const allAdded = catPresets.every(p => isPresetAdded(p.pattern, p.is_regex))
          return (
            <div key={cat} className="mb-3 last:mb-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-textSecondary uppercase tracking-wider">{cat}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded-full ${allAdded ? 'bg-mint-400/10 text-mint-400' : 'bg-amber-400/10 text-amber-400'}`}>
                  {allAdded ? t('admin.allAdded') : `${catPresets.filter(p => isPresetAdded(p.pattern, p.is_regex)).length}/${catPresets.length}`}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {catPresets.map(p => {
                  const added = isPresetAdded(p.pattern, p.is_regex)
                  const status = getPresetStatus(p.pattern, p.is_regex)
                  return (
                    <div
                      key={`${p.pattern}-${p.is_regex}`}
                      className={`rounded-lg border p-3 text-sm transition-colors ${
                        added
                          ? 'border-mint-400/30 bg-mint-400/5'
                          : 'border-border bg-canvas hover:border-primary-400/30'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <code className="text-xs font-mono text-textPrimary break-all">{p.pattern}</code>
                          <span className="text-xs text-textMuted ml-1.5">{p.is_regex ? `(${t('admin.regex')})` : `(${t('admin.exact')})`}</span>
                          <p className="text-xs text-textSecondary mt-1 leading-relaxed">{p.description}</p>
                        </div>
                        <button
                          onClick={() => !added && handleAddPreset(p.pattern, p.is_regex, p.description)}
                          disabled={added}
                          className={`shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                            added
                              ? 'bg-mint-400/10 text-mint-400 cursor-default'
                              : 'bg-primary-500 text-white hover:bg-primary-400'
                          }`}
                        >
                          {added ? status : '+ ' + t('admin.addCmd')}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* ── 手动添加表单 ── */}
      <div className="bg-surface rounded-xl border border-border p-5 max-w-lg">
        <h3 className="font-semibold mb-3 text-textPrimary">{t('admin.manualAddCommand')}</h3>
        <p className="text-xs text-textMuted mb-3" dangerouslySetInnerHTML={{ __html: t('admin.manualAddDesc') }} />
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.commandPattern')}</label>
            <input value={pattern} onChange={(e) => setPattern(e.target.value)}
              className="w-40 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary"
              placeholder={t('admin.commandPatternPlaceholder')} />
          </div>
          <div className="flex items-center gap-1.5 mb-1">
            <input type="checkbox" checked={isRegex} onChange={(e) => setIsRegex(e.target.checked)}
              className="rounded" />
            <span className="text-xs text-textSecondary">{t('admin.regexMode')}</span>
          </div>
          <div>
            <label className="block text-xs mb-1 text-textSecondary">{t('admin.description')}</label>
            <input value={desc} onChange={(e) => setDesc(e.target.value)}
              className="w-32 px-2 py-1.5 border border-border bg-canvas rounded-xl text-sm text-textPrimary"
              placeholder={t('common.optional')} />
          </div>
          <button onClick={handleAdd}
            className="px-3 py-1.5 bg-primary-500 text-white rounded-xl hover:bg-primary-400 text-sm">
            {t('admin.addCmd')}
          </button>
        </div>
      </div>

      {/* ── 白名单列表 ── */}
      <div className="bg-surface rounded-xl border border-border p-5">
        <h3 className="font-semibold mb-3 text-textPrimary">{t('admin.commandWhitelist')}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-textPrimary">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.cmdColPattern')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.cmdColType')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.cmdColDesc')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">默认</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.cmdColStatus')}</th>
                <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.cmdColAction')}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c: any) => (
                <tr key={c.id} className="border-b border-border/50">
                  <td className="py-2 px-3 font-mono text-xs text-textPrimary">{c.pattern}</td>
                  <td className="py-2 px-3 text-xs text-textSecondary">{c.is_regex ? t('admin.regex') : t('admin.exact')}</td>
                  <td className="py-2 px-3 text-xs text-textSecondary">{c.description || '-'}</td>
                  <td className="py-2 px-3">
                    <button onClick={async () => {
                      await api.put(`/admin/opencli/commands/${c.id}/default?default_enabled=${!c.default_enabled}`)
                      load()
                    }} className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.default_enabled ? 'bg-mint-400/10 text-mint-400' : 'bg-gray-100 text-gray-400'}`}>
                      {c.default_enabled ? '全部AI' : '白名单'}
                    </button>
                  </td>
                  <td className="py-2 px-3">
                    <span className={c.enabled ? 'text-mint-400 text-xs' : 'text-textMuted text-xs'}>
                      {c.enabled ? t('common.enabled') : t('common.disabled')}
                    </span>
                  </td>
                  <td className="py-2 px-3 flex gap-2">
                    <button onClick={() => handleToggle(c.id, c.enabled)}
                      className="text-xs text-primary-400 hover:text-primary-500 dark:hover:text-primary-300">
                      {c.enabled ? t('common.disabled') : t('common.enabled')}
                    </button>
                    <button onClick={() => handleDelete(c.id)}
                      className="text-xs text-rose-400 hover:text-rose-500">
                      {t('common.delete')}
                    </button>
                  </td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={5} className="py-4 text-center text-textMuted">{t('admin.noCommands')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---- 使用日志 ----
function OpenCLILogsSection() {
  const t = useT()
  const [data, setData] = useState<any>(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    api.get(`/admin/opencli/logs?page=${page}&page_size=30`).then(setData).catch(console.error)
  }, [page])

  if (!data) return <p className="text-textMuted">{t('common.loading')}</p>

  return (
    <div className="bg-surface rounded-xl border border-border p-5">
      <h3 className="font-semibold text-textPrimary mb-3">{t('admin.usageLogs')}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-textPrimary">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColTime')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColAi')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColCmd')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColExitCode')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColDuration')}</th>
              <th className="text-left py-2 px-3 font-medium text-textSecondary">{t('admin.logsColOutput')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((log: any) => (
              <tr key={log.id} className="border-b border-border/50">
                <td className="py-2 px-3 text-xs text-textSecondary">
                  {log.executed_at ? new Date(log.executed_at).toLocaleString('zh-CN') : '-'}
                </td>
                <td className="py-2 px-3 text-xs text-textPrimary">AI #{log.agent_id}</td>
                <td className="py-2 px-3 font-mono text-xs text-textPrimary">
                  {log.command}{log.args ? ` ${log.args}` : ''}
                </td>
                <td className="py-2 px-3">
                  <span className={log.exit_code === 0 ? 'text-mint-400 text-xs' : 'text-rose-400 text-xs'}>
                    {log.exit_code}
                  </span>
                </td>
                <td className="py-2 px-3 text-xs text-textSecondary">{log.duration_ms}ms</td>
                <td className="py-2 px-3 text-xs text-textSecondary max-w-[250px] truncate">
                  {log.stdout_truncated || log.stderr_truncated || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
          className="text-sm px-3 py-1 border border-border bg-canvas rounded hover:bg-elevated disabled:opacity-40 text-textSecondary">
          {t('common.prevPage')}
        </button>
        <button onClick={() => setPage(p => p + 1)} disabled={data.items.length < data.page_size}
          className="text-sm px-3 py-1 border border-border bg-canvas rounded hover:bg-elevated disabled:opacity-40 text-textSecondary">
          {t('common.nextPage')}
        </button>
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════
// 平台设置 Tab（全局默认语言等）
// ════════════════════════════════════════════════════════════

function SystemSettingsTab() {
  const t = useT()
  const [config, setConfig] = useState<any>(null)
  const [lang, setLang] = useState('en')
  const [platformCredit, setPlatformCredit] = useState(0)
  const [fileQuota, setFileQuota] = useState(100)
  const [hasActiveKeys, setHasActiveKeys] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/admin/system-settings'),
      api.get('/admin/api-key-pool'),
    ]).then(([settings, keys]) => {
      setConfig(settings)
      setLang(settings.default_language || 'en')
      setPlatformCredit(settings.default_platform_credit || 0)
      setFileQuota(settings.default_file_quota_mb ?? 100)
      setHasActiveKeys(keys.some((k: any) => k.is_active))
    }).catch(console.error)
  }, [])

  const handleSave = async (field: string, value: any) => {
    setSaving(true)
    setMsg('')
    try {
      const payload: any = {}
      if (field === 'language') payload.default_language = value
      else if (field === 'platform_credit') payload.default_platform_credit = value
      else if (field === 'file_quota') payload.default_file_quota_mb = value
      const updated = await api.put('/admin/system-settings', payload)
      setConfig(updated)
      setMsg(t('admin.saveSuccess'))
    } catch (err: any) {
      setMsg(err?.message || err?.detail || t('admin.saveFailed'))
    }
    setSaving(false)
  }

  const handlePlatformCreditSave = () => {
    const old = config?.default_platform_credit || 0
    if (platformCredit === old) return
    if (platformCredit > 0 && !hasActiveKeys) {
      setMsg(t('admin.platformCreditNoActiveKey'))
      return
    }
    const delta = platformCredit - old
    const confirmed = confirm(
      t('admin.platformCreditConfirm')
        .replace('{old}', String(old))
        .replace('{new}', String(platformCredit))
        .replace('{delta}', (delta >= 0 ? '+' : '') + delta)
        .replace('{userCount}', t('admin.allUsers'))
    )
    if (!confirmed) return
    handleSave('platform_credit', platformCredit)
  }

  if (!config) return <p className="text-textMuted p-6">{t('common.loading')}</p>

  return (
    <div className="bg-surface rounded-xl border border-border p-5 max-w-lg space-y-6">
      <h3 className="font-semibold text-textPrimary">{t('admin.systemSettings')}</h3>

      {/* 默认语言 */}
      <div>
        <label className="block text-sm font-medium mb-1 text-textSecondary">{t('admin.defaultLanguage')}</label>
        <p className="text-xs text-textMuted mb-2">{t('admin.defaultLanguageDesc')}</p>
        <select
          value={lang}
          onChange={(e) => {
            setLang(e.target.value)
            handleSave('language', e.target.value)
          }}
          className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-canvas text-sm text-textPrimary"
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>{t(l.i18nKey)}</option>
          ))}
        </select>
      </div>

      {/* 平台赠送额度 */}
      <div>
        <label className="block text-sm font-medium mb-1 text-textSecondary">{t('admin.defaultPlatformCredit')}</label>
        <p className="text-xs text-textMuted mb-2">{t('admin.defaultPlatformCreditDesc')}</p>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={platformCredit}
            onChange={(e) => setPlatformCredit(parseInt(e.target.value) || 0)}
            min={0}
            max={999999}
            disabled={platformCredit > 0 && !hasActiveKeys}
            className="w-32 px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50 disabled:opacity-40"
          />
          <button
            onClick={handlePlatformCreditSave}
            disabled={saving || platformCredit === (config?.default_platform_credit || 0)}
            className="px-3 py-2 bg-primary-500 text-white rounded-xl hover:bg-primary-400 text-sm disabled:opacity-40 transition-colors"
          >
            {t('settings.save')}
          </button>
        </div>
        {!hasActiveKeys && (
          <p className="text-xs text-amber-400 mt-1.5">{t('admin.platformCreditNoActiveKey')}</p>
        )}
      </div>

      {/* 用户默认文件配额 */}
      <div>
        <label className="block text-sm font-medium mb-1 text-textSecondary">{t('admin.defaultFileQuota')}</label>
        <p className="text-xs text-textMuted mb-2">{t('admin.defaultFileQuotaDesc')}</p>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={fileQuota}
            onChange={(e) => setFileQuota(parseInt(e.target.value) || 1)}
            min={1}
            max={1048576}
            className="w-32 px-3 py-2 rounded-xl border border-border bg-canvas text-sm text-textPrimary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          />
          <span className="text-xs text-textMuted">MB</span>
          <button
            onClick={() => {
              const old = config?.default_file_quota_mb ?? 100
              if (fileQuota === old) return
              const delta = fileQuota - old
              const confirmed = confirm(
                (fileQuota > old
                  ? t('admin.fileQuotaIncreaseConfirm')
                  : t('admin.fileQuotaDecreaseConfirm')
                )
                  .replace('{old}', String(old))
                  .replace('{new}', String(fileQuota))
                  .replace('{delta}', (delta >= 0 ? '+' : '') + delta)
              )
              if (!confirmed) return
              handleSave('file_quota', fileQuota)
            }}
            disabled={saving || fileQuota === (config?.default_file_quota_mb ?? 100)}
            className="px-3 py-2 bg-primary-500 text-white rounded-xl hover:bg-primary-400 text-sm disabled:opacity-40 transition-colors"
          >
            {t('settings.save')}
          </button>
        </div>
      </div>

      {msg && <p className={`text-sm ${msg.includes('失败') || msg.includes('无法') || msg.includes('No active') ? 'text-rose-400' : 'text-mint-400'}`}>{msg}</p>}
    </div>
  )
}
