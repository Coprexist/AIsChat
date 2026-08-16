import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Play, Square, CheckCircle, RefreshCw, Plug, Circle, Palette, Wand2, Globe, Box, RefreshCcw } from 'lucide-react'
import { useT } from '../i18n/I18nContext'
import DocExportTab from './DocExportTab'
import ApiDocSectionsTab from './ApiDocSectionsTab'
import type { PluginView } from '../utils/skin'

interface Plugin {
  id: string
  name: string
  description: string
  category: string
  installed: boolean
  running: boolean
  port: number | null
}

const CATEGORY_ICON: Record<string, any> = {
  skin: Palette,
  skill: Wand2,
  world: Globe,
  other: Box,
}

const CATEGORY_LABEL: Record<string, string> = {
  skin: '皮肤',
  skill: '技能',
  world: '世界',
  other: '其他',
}

export default function PluginManager() {
  const t = useT()
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // ── 统一插件（内容插件：皮肤/技能/世界）管理员视图 ──
  const [contentPlugins, setContentPlugins] = useState<PluginView[]>([])
  const [contentLoading, setContentLoading] = useState(false)
  const [contentToggling, setContentToggling] = useState<string | null>(null)

  const fetchContentPlugins = async () => {
    setContentLoading(true)
    try {
      const data = await api.get<{ plugins: PluginView[] }>('/plugins')
      setContentPlugins(data.plugins || [])
    } catch (e: any) {
      setMessage({ type: 'error', text: `内容插件加载失败: ${e?.message || e}` })
    } finally {
      setContentLoading(false)
    }
  }

  useEffect(() => {
    fetchContentPlugins()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleContentToggle = async (plugin: PluginView) => {
    setContentToggling(plugin.id)
    try {
      const res: any = await api.post(`/plugins/${plugin.id}/toggle`)
      setMessage({ type: 'success', text: res.message || '已切换' })
      await fetchContentPlugins()
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.message || '操作失败' })
    } finally {
      setContentToggling(null)
    }
  }

  const handleRescan = async () => {
    setContentLoading(true)
    try {
      const res: any = await api.post('/plugins/rescan')
      setMessage({ type: 'success', text: res.message || '重扫完成' })
      await fetchContentPlugins()
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.message || '重扫失败' })
    } finally {
      setContentLoading(false)
    }
  }

  const fetchPlugins = async () => {
    try {
      const data: any = await api.get('/admin/plugins')
      setPlugins(data.plugins || [])
    } catch (e: any) {
      const detail = e?.message || e?.detail || '加载失败'
      setMessage({ type: 'error', text: `加载失败: ${detail}` })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPlugins() }, [])

  // 每 5 秒刷新状态
  useEffect(() => {
    const iv = setInterval(fetchPlugins, 5000)
    return () => clearInterval(iv)
  }, [])

  const handleToggle = async (plugin: Plugin) => {
    setToggling(plugin.id)
    setMessage(null)
    const action = plugin.running ? 'stop' : 'start'
    try {
      const res: any = await api.post(`/admin/plugins/${plugin.id}/${action}`)
      setMessage({ type: 'success', text: res.message || (plugin.running ? '已停止' : '已启动') })
      await fetchPlugins()
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || '操作失败' })
    } finally {
      setToggling(null)
    }
  }

  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto p-6 flex items-center justify-center">
        <RefreshCw size={20} className="animate-spin text-textMuted" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div>
        <h2 className="text-base font-semibold text-textPrimary mb-1">插件管理</h2>

        {/* ═══ 统一插件（内容插件：皮肤 / 技能 / 世界）═══ */}
        <div className="rounded-xl border border-border bg-elevated/30 p-4 mb-4">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-medium text-textPrimary flex items-center gap-1.5">
              <Plug size={15} className="text-primary-400" /> 统一插件（目录即插件）
            </h3>
            <button
              onClick={handleRescan}
              disabled={contentLoading}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-primary-500/10 text-primary-400 hover:bg-primary-500/20 border border-primary-400/20 transition-colors disabled:opacity-50"
            >
              <RefreshCcw size={12} className={contentLoading ? 'animate-spin' : ''} /> 重扫目录
            </button>
          </div>
          <p className="text-xs text-textMuted mb-3">
            插件放在 backend/plugins/ 或 data/plugins/ 目录（含 plugin.json）即自动发现，装好即可用。
            这里控制全局开放/关闭；用户可在自己的设置页一键启用/停用。
          </p>
          {contentLoading && contentPlugins.length === 0 ? (
            <p className="text-xs text-textMuted py-3">加载中…</p>
          ) : contentPlugins.length === 0 ? (
            <p className="text-xs text-textMuted py-3">暂无内容插件</p>
          ) : (
            <div className="space-y-2">
              {contentPlugins.map((plugin) => {
                const Icon = CATEGORY_ICON[plugin.category] || Box
                const on = plugin.global_enabled
                return (
                  <div key={plugin.id} className="flex items-start justify-between gap-3 p-3 rounded-lg border border-border bg-surface">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Icon size={14} className="text-textMuted shrink-0" />
                        <span className="font-medium text-sm text-textPrimary">{plugin.name}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary-400/10 text-primary-400 border border-primary-400/20">
                          {CATEGORY_LABEL[plugin.category] || plugin.category}
                        </span>
                        <span className="text-[10px] font-mono text-textMuted">v{plugin.version}</span>
                        {plugin.builtin && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">内置</span>
                        )}
                        {plugin.users_count != null && plugin.users_count > 0 && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-mint-400/10 text-mint-400 border border-mint-400/20">
                            {plugin.users_count} 人{plugin.category === 'skin' ? '在用' : '启用'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-textSecondary mt-0.5 line-clamp-2">{plugin.description}</p>
                    </div>
                    <button
                      onClick={() => handleContentToggle(plugin)}
                      disabled={contentToggling === plugin.id}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shrink-0 disabled:opacity-50 ${
                        on
                          ? 'bg-mint-500 text-white hover:bg-mint-600'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                      }`}
                    >
                      {contentToggling === plugin.id ? (
                        <RefreshCw size={14} className="animate-spin" />
                      ) : on ? (
                        <CheckCircle size={14} />
                      ) : (
                        <Circle size={14} />
                      )}
                      {contentToggling === plugin.id ? '处理中…' : on ? '已开放' : '已关闭'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* 可选能力：文档导出（pandoc）——并入插件管理 */}
        <div className="rounded-xl border border-border bg-elevated/30 p-4 mb-4">
          <DocExportTab />
        </div>

        {/* 接口文档分区管理（标题/介绍表单注入） */}
        <div className="rounded-xl border border-border bg-elevated/30 p-4 mb-4">
          <ApiDocSectionsTab />
        </div>
        <p className="text-sm text-textSecondary">
          管理扩展服务。启动后所有 AI 共享同一实例，无需每个 AI 单独运行。
        </p>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${
          message.type === 'success'
            ? 'bg-mint-50 dark:bg-mint-900/20 text-mint-700 dark:text-mint-400 border border-mint-200 dark:border-mint-800'
            : 'bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
        }`}>
          {message.text}
        </div>
      )}

      <div className="space-y-3">
        {plugins.map(plugin => (
          <div
            key={plugin.id}
            className="p-4 rounded-xl border border-border bg-surface hover:bg-elevated transition-colors"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Plug size={16} className="text-textMuted shrink-0" />
                  <h3 className="font-medium text-textPrimary">{plugin.name}</h3>
                  {plugin.installed && (
                    plugin.running ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-mint-100 dark:bg-mint-900/30 text-mint-700 dark:text-mint-400">
                        <CheckCircle size={11} /> 运行中 :{plugin.port}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                        <Circle size={11} /> 已停止
                      </span>
                    )
                  )}
                  {!plugin.installed && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400">
                      未安装
                    </span>
                  )}
                </div>
                <p className="text-sm text-textSecondary">{plugin.description}</p>
              </div>
              {plugin.installed && (
                <button
                  onClick={() => handleToggle(plugin)}
                  disabled={toggling === plugin.id}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shrink-0 ${
                    plugin.running
                      ? 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/40 border border-rose-200 dark:border-rose-800'
                      : 'bg-mint-500 text-white hover:bg-mint-600'
                  } disabled:opacity-50`}
                >
                  {toggling === plugin.id ? (
                    <RefreshCw size={14} className="animate-spin" />
                  ) : plugin.running ? (
                    <Square size={14} />
                  ) : (
                    <Play size={14} />
                  )}
                  {toggling === plugin.id ? '处理中…' : plugin.running ? '停止' : '启动'}
                </button>
              )}
              {plugin.id === 'browser' && plugin.running && (
                <button
                  onClick={async () => {
                    setMessage(null)
                    try {
                      const res: any = await api.post('/admin/plugins/browser/test')
                      const detail = res.cdp_msgs?.length ? ` [CDP: ${res.cdp_msgs.join('→')}]` : ''
                      setMessage({ type: res.ok ? 'success' : 'error', text: (res.ok ? `${res.message}` : `${res.error}`) + detail })
                    } catch (e: any) { setMessage({ type: 'error', text: `请求失败: ${e?.message || e}` }) }
                  }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 hover:bg-blue-100 border border-blue-200 dark:border-blue-800 transition-colors shrink-0"
                >
                  测通百度
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {plugins.length === 0 && (
        <div className="text-center py-12 text-textMuted">
          <Plug size={32} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">暂无可管理的插件</p>
        </div>
      )}
    </div>
  )
}
