import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Download, Trash2, CheckCircle, RefreshCw, Plug } from 'lucide-react'
import { useT } from '../i18n/I18nContext'

interface Plugin {
  id: string
  name: string
  description: string
  category: string
  installed: boolean
}

export default function PluginManager() {
  const t = useT()
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const fetchPlugins = async () => {
    try {
      const res = await api.get('/admin/plugins')
      setPlugins(res.data.plugins)
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || '加载插件列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPlugins() }, [])

  const handleInstall = async (pluginId: string) => {
    setInstalling(pluginId)
    setMessage(null)
    try {
      const res = await api.post(`/admin/plugins/${pluginId}/install`)
      setMessage({ type: 'success', text: res.data.message || '安装成功' })
      await fetchPlugins()
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || '安装失败' })
    } finally {
      setInstalling(null)
    }
  }

  const handleUninstall = async (pluginId: string) => {
    if (!confirm('确定要卸载此插件吗？AI 将无法使用相关功能。')) return
    setInstalling(pluginId)
    setMessage(null)
    try {
      const res = await api.post(`/admin/plugins/${pluginId}/uninstall`)
      setMessage({ type: 'success', text: res.data.message || '已卸载' })
      await fetchPlugins()
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || '卸载失败' })
    } finally {
      setInstalling(null)
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
        <h2 className="text-base font-semibold text-textPrimary mb-1">🧩 插件下载</h2>
        <p className="text-sm text-textSecondary">
          按需安装扩展功能。未安装的插件不会占用系统资源，按需选择。
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
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">
                      <CheckCircle size={11} /> 已安装
                    </span>
                  )}
                </div>
                <p className="text-sm text-textSecondary">{plugin.description}</p>
              </div>
              <button
                onClick={() => plugin.installed ? handleUninstall(plugin.id) : handleInstall(plugin.id)}
                disabled={installing === plugin.id}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shrink-0 ${
                  plugin.installed
                    ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/40 border border-red-200 dark:border-red-800'
                    : 'bg-primary-500 text-white hover:bg-primary-600'
                } disabled:opacity-50`}
              >
                {installing === plugin.id ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : plugin.installed ? (
                  <Trash2 size={14} />
                ) : (
                  <Download size={14} />
                )}
                {installing === plugin.id ? '处理中…' : plugin.installed ? '卸载' : '下载安装'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {plugins.length === 0 && (
        <div className="text-center py-12 text-textMuted">
          <Plug size={32} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">暂无可下载的插件</p>
        </div>
      )}
    </div>
  )
}
