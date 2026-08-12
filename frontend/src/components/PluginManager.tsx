import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Play, Square, CheckCircle, RefreshCw, Plug, Circle } from 'lucide-react'
import { useT } from '../i18n/I18nContext'
import DocExportTab from './DocExportTab'
import ApiDocSectionsTab from './ApiDocSectionsTab'

interface Plugin {
  id: string
  name: string
  description: string
  category: string
  installed: boolean
  running: boolean
  port: number | null
}

export default function PluginManager() {
  const t = useT()
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

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
            ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
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
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">
                        <CheckCircle size={11} /> 运行中 :{plugin.port}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                        <Circle size={11} /> 已停止
                      </span>
                    )
                  )}
                  {!plugin.installed && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
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
                      ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 border border-red-200 dark:border-red-800'
                      : 'bg-emerald-500 text-white hover:bg-emerald-600'
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
