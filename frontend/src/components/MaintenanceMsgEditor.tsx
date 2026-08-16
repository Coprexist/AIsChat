import { useState, useEffect, useRef } from 'react'
import { api, getApiBaseUrl } from '../api/client'
import { Plus, Save, Upload, Pencil, Check, Trash2, X, Image as ImageIcon, AlertTriangle } from 'lucide-react'
import { useT } from '../i18n/I18nContext'

interface MsgData {
  hard_title: string; hard_body: string; hard_color: string; hard_text_color: string
  hard_image: string; hard_style: string
  soft_text: string; soft_color: string; soft_text_color: string; soft_style: string; soft_once: boolean
}

interface PresetItem extends MsgData { name: string }

const DEFAULT_MSG: MsgData = {
  hard_title: '正在更新', hard_body: '服务器正在更新，稍等一下就好~',
  hard_color: '#f59e0b', hard_text_color: '#ffffff', hard_image: '', hard_style: 'popup',
  soft_text: '服务器正在调整，功能可能偶尔不稳定', soft_color: '#f59e0b', soft_text_color: '#ffffff', soft_style: 'banner', soft_once: false,
}

function toMsgData(d: any): MsgData {
  return {
    hard_title: d.hard_title ?? DEFAULT_MSG.hard_title,
    hard_body: d.hard_body ?? DEFAULT_MSG.hard_body,
    hard_color: d.hard_color ?? DEFAULT_MSG.hard_color,
    hard_text_color: d.hard_text_color ?? DEFAULT_MSG.hard_text_color,
    hard_image: d.hard_image ?? '',
    hard_style: d.hard_style ?? 'popup',
    soft_text: d.soft_text ?? DEFAULT_MSG.soft_text,
    soft_color: d.soft_color ?? DEFAULT_MSG.soft_color,
    soft_text_color: d.soft_text_color ?? DEFAULT_MSG.soft_text_color,
    soft_style: d.soft_style ?? 'banner',
    soft_once: !!d.soft_once,
  }
}

/** 把上传后的 file_id 拼成可访问的公开 URL（兼容桌面端实例地址） */
function publicFileUrl(fileId: number | string): string {
  return `${getApiBaseUrl()}/fs/public/${fileId}`
}

/** 从 URL 提取用于展示的文件名 */
function urlLabel(url: string): string {
  if (!url) return ''
  const m = url.match(/\/fs\/public\/(\d+)/)
  if (m) return `图片 #${m[1]}`
  try { return decodeURIComponent(url.split('/').pop() || url).slice(0, 24) } catch { return url }
}

export default function MaintenanceMsgEditor() {
  const t = useT()
  const [msg, setMsg] = useState<MsgData>(DEFAULT_MSG)
  const [presets, setPresets] = useState<PresetItem[]>([])
  const [images, setImages] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selPreset, setSelPreset] = useState('')
  const [presetInput, setPresetInput] = useState('')   // 保存预设名称输入
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [presetError, setPresetError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const [m, p, img] = await Promise.all([
        api.get('/admin/maintenance/msg'), api.get('/admin/maintenance/presets'), api.get('/admin/maintenance/images'),
      ])
      setMsg(toMsgData(m))
      setPresets((p as any).presets || [])
      setImages((img as any).images || [])
      setLoaded(true)
      setLoadError('')
    } catch (e: any) {
      setLoadError(e?.detail || e?.message || '加载维护配置失败')
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (saving) return
    setSaving(true); setSaveError('')
    try {
      await api.put('/admin/maintenance/msg', msg)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (e: any) {
      setSaveError(e?.detail || e?.message || '保存失败，请重试')
    }
    setSaving(false)
  }

  const applyPreset = async (name: string) => {
    setPresetError('')
    try {
      // 后端 apply 会合并全字段并写入 msg 文件 + 广播；前端同步本地状态
      const r: any = await api.post(`/admin/maintenance/presets/apply?name=${encodeURIComponent(name)}`)
      setMsg(toMsgData(r.msg))
      setSelPreset(name)
      setSaveError('')
    } catch (e: any) {
      setPresetError(e?.detail || e?.message || '应用预设失败')
    }
  }

  const savePreset = async (name: string) => {
    const n = (name || '').trim()
    if (!n) { setPresetError('请输入预设名称'); return }
    setPresetError('')
    try {
      // 同名直接覆盖（后端 upsert），不再先删后建
      await api.post('/admin/maintenance/presets', { name: n, ...msg })
      setSelPreset(n)
      load()
    } catch (e: any) {
      setPresetError(e?.detail || e?.message || '保存预设失败')
    }
  }

  const renamePreset = async (oldName: string, newName: string) => {
    const nn = (newName || '').trim()
    if (!nn || nn === oldName) { setRenaming(null); return }
    const p = presets.find(x => x.name === oldName)
    if (!p) return
    setPresetError('')
    try {
      await api.delete(`/admin/maintenance/presets/${encodeURIComponent(oldName)}`)
      await api.post('/admin/maintenance/presets', { ...p, name: nn })
      if (selPreset === oldName) setSelPreset(nn)
      setRenaming(null)
      load()
    } catch (e: any) {
      setPresetError(e?.detail || e?.message || '重命名失败')
    }
  }

  const deletePreset = async (name: string) => {
    setPresetError('')
    try {
      await api.delete(`/admin/maintenance/presets/${encodeURIComponent(name)}`)
      if (selPreset === name) setSelPreset('')
      load()
    } catch (e: any) {
      setPresetError(e?.detail || e?.message || '删除失败')
    }
  }

  const handleUpload = async (file: File) => {
    if (uploading) return
    setUploading(true); setSaveError('')
    try {
      const r: any = await api.upload('/fs/upload-attachment', file)
      const url = publicFileUrl(r.file_id)
      setMsg(prev => ({ ...prev, hard_image: url }))
      try { await api.post(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); setImages(prev => [url, ...prev.filter(x => x !== url)]) } catch {}
    } catch (e: any) {
      setSaveError(e?.detail || e?.message || '上传失败')
    }
    setUploading(false)
  }

  const addImageUrl = async () => {
    const url = prompt('输入外网图片URL：')
    if (!url) return
    try { await api.post(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); setImages(prev => [url, ...prev.filter(x => x !== url)]); setMsg(prev => ({ ...prev, hard_image: url })) } catch (e: any) { setSaveError(e?.detail || '添加图片失败') }
  }

  const removeImage = async (url: string) => {
    try {
      await api.delete(`/admin/maintenance/images?url=${encodeURIComponent(url)}`)
      setImages(prev => prev.filter(x => x !== url))
      if (msg.hard_image === url) setMsg(prev => ({ ...prev, hard_image: '' }))
    } catch (e: any) { setSaveError(e?.detail || '删除图片失败') }
  }

  if (!loaded) {
    return (
      <div className="bg-surface rounded-xl border border-border p-4">
        {loadError ? (
          <div className="flex items-center gap-2 text-xs text-rose-400">
            <AlertTriangle size={14} /> {loadError}
            <button onClick={load} className="ml-auto px-2 py-1 rounded border border-border text-textSecondary hover:text-textPrimary">重试</button>
          </div>
        ) : (
          <p className="text-xs text-textMuted">{t('common.loading')}</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3">

      {/* ── 预设栏 ── */}
      <div className="bg-surface rounded-xl border border-border p-3.5 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <select value={selPreset} onChange={e => { const v = e.target.value; if (v) applyPreset(v); else setSelPreset('') }}
            className="flex-1 min-w-[140px] px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50">
            <option value="">{t('admin.presets')} ···</option>
            {presets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          <div className="flex items-center gap-1.5">
            <input
              value={presetInput}
              placeholder={selPreset ? '另存为新预设…' : '新预设名称'}
              onChange={e => setPresetInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && presetInput.trim()) { savePreset(presetInput); setPresetInput('') } }}
              className="w-28 px-2 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textPrimary focus:outline-none"
            />
            <button onClick={() => { if (presetInput.trim()) savePreset(presetInput); setPresetInput('') }}
              className="shrink-0 px-2.5 py-1.5 text-[11px] rounded-lg bg-primary-500/10 border border-primary-500/30 text-primary-400 hover:bg-primary-500/20 transition-colors">
              <Save size={13} className="inline mr-0.5" />存预设
            </button>
          </div>
          {selPreset && (
            <div className="flex items-center gap-1">
              <button onClick={() => { setRenaming(selPreset); setRenameValue(selPreset) }} className="p-1.5 rounded-lg text-textMuted hover:text-textPrimary hover:bg-elevated transition-colors" title="重命名"><Pencil size={13} /></button>
              <button onClick={() => deletePreset(selPreset)} className="p-1.5 rounded-lg text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/10 transition-colors" title="删除"><Trash2 size={13} /></button>
            </div>
          )}
        </div>
        {renaming && (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') renamePreset(renaming, renameValue); if (e.key === 'Escape') setRenaming(null) }}
              className="flex-1 px-2 py-1.5 rounded-lg border border-border bg-canvas text-[11px] focus:outline-none focus:ring-1 focus:ring-primary-500/50"
            />
            <button onClick={() => renamePreset(renaming, renameValue)}
              className="px-2 py-1.5 text-[11px] rounded-lg bg-mint-500/10 border border-mint-500/30 text-mint-400 hover:bg-mint-500/20"><Check size={12} /></button>
            <button onClick={() => setRenaming(null)} className="p-1.5 text-textMuted hover:text-textPrimary"><X size={13} /></button>
          </div>
        )}
        {presetError && <p className="text-[11px] text-rose-400">{presetError}</p>}
      </div>

      {/* ── 双栏编辑 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* 硬维护 */}
        <div className="bg-surface rounded-xl border border-border p-4 space-y-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-textPrimary">
            <span className="w-2 h-2 rounded-full bg-rose-400 animate-pulse" />
            🔒 暂停服务
            <span className="text-textMuted font-normal text-[10px] ml-1">——用户看到弹窗/顶栏，API 全部返回 503</span>
          </div>
          <div className="space-y-2.5">
            <div className="flex gap-2 items-start">
              <div className="relative shrink-0">
                <input type="color" value={msg.hard_color} onChange={e => setMsg({...msg, hard_color: e.target.value})}
                  onMouseDown={e => e.stopPropagation()} className="absolute inset-0 opacity-0 w-8 h-8 cursor-pointer" />
                <div className="w-8 h-8 rounded-lg border border-border/50" style={{ backgroundColor: msg.hard_color }} />
              </div>
              <div className="flex-1 space-y-2">
                <input value={msg.hard_title} onChange={e => setMsg({...msg, hard_title: e.target.value})} placeholder="标题"
                  className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:border-primary-500/40" />
                <input value={msg.hard_body} onChange={e => setMsg({...msg, hard_body: e.target.value})} placeholder="正文"
                  className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:border-primary-500/40" />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-textMuted">文字色</span>
                <div className="relative">
                  <input type="color" value={msg.hard_text_color} onChange={e => setMsg({...msg, hard_text_color: e.target.value})}
                    onMouseDown={e => e.stopPropagation()} className="absolute inset-0 opacity-0 w-6 h-6 cursor-pointer" />
                  <div className="w-6 h-6 rounded border border-border/50" style={{ backgroundColor: msg.hard_text_color }} />
                </div>
              </div>
              <select value={msg.hard_style} onChange={e => setMsg({...msg, hard_style: e.target.value})}
                className="px-2.5 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textPrimary focus:outline-none">
                <option value="popup">弹窗</option>
                <option value="banner">顶栏</option>
              </select>
            </div>
            <div>
              <div className="flex gap-1.5">
                <input value={msg.hard_image} onChange={e => setMsg({...msg, hard_image: e.target.value})} placeholder="图片 URL"
                  className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:border-primary-500/40" />
                <button onClick={addImageUrl} className="shrink-0 px-2.5 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textSecondary hover:text-primary-400 transition-colors" title="添加外链"><ImageIcon size={13} /></button>
                <label className={`shrink-0 px-2.5 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textSecondary hover:text-primary-400 cursor-pointer transition-colors ${uploading ? 'opacity-40 pointer-events-none' : ''}`}>
                  {uploading ? '···' : <Upload size={13} />}
                  <input ref={fileRef} type="file" accept="image/*" className="hidden" disabled={uploading} onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = '' }} />
                </label>
              </div>
              {/* 图库缩略图 */}
              {images.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {images.map((url, i) => (
                    <div key={i} className={`group relative rounded-lg overflow-hidden border transition-colors ${msg.hard_image === url ? 'border-primary-500 ring-1 ring-primary-500/40' : 'border-border/50 hover:border-primary-500/40'}`}>
                      <button onClick={() => setMsg({...msg, hard_image: url})} className="block w-12 h-12" title={urlLabel(url)}>
                        <img src={url} alt="" className="w-12 h-12 object-cover bg-black/20" />
                      </button>
                      <button onClick={() => removeImage(url)}
                        className="absolute top-0.5 right-0.5 hidden group-hover:flex w-4 h-4 items-center justify-center rounded bg-black/60 text-white"
                        title="删除"><X size={10} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* 硬维护实时预览 */}
            <div className="rounded-lg border border-border/30 overflow-hidden">
              <div className="text-[10px] text-textMuted px-3 py-1 bg-canvas/50 border-b border-border/30">预览</div>
              <div className="p-2.5">
                {msg.hard_style === 'banner' ? (
                  <div className="text-[11px] rounded-lg px-3 py-2 flex items-center justify-center gap-2" style={{ backgroundColor: msg.hard_color, color: msg.hard_text_color }}>
                    <span>{msg.hard_title} · {msg.hard_body}</span>
                  </div>
                ) : (
                  <div className="rounded-xl border border-border/40 bg-canvas/60 p-3 text-center">
                    {msg.hard_image && <img src={msg.hard_image} alt="" className="w-12 h-12 object-contain mx-auto mb-1.5 rounded" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />}
                    <div className="text-xs font-semibold mb-1" style={{ color: msg.hard_color }}>{msg.hard_title}</div>
                    <div className="text-[11px] text-textSecondary mb-2">{msg.hard_body}</div>
                    <span className="inline-block px-3 py-1 text-[10px] rounded-md" style={{ backgroundColor: msg.hard_color, color: msg.hard_text_color }}>知道了</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 软维护 */}
        <div className="bg-surface rounded-xl border border-border p-4 space-y-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-textPrimary">
            <span className="w-2 h-2 rounded-full bg-accent-400" />
            📢 温馨提示
            <span className="text-textMuted font-normal text-[10px] ml-1">——用户看到顶栏/弹窗提示，API 正常运行</span>
          </div>
          <div className="space-y-2.5">
            <div className="flex gap-2 items-start">
              <div className="relative shrink-0">
                <input type="color" value={msg.soft_color} onChange={e => setMsg({...msg, soft_color: e.target.value})}
                  onMouseDown={e => e.stopPropagation()} className="absolute inset-0 opacity-0 w-8 h-8 cursor-pointer" />
                <div className="w-8 h-8 rounded-lg border border-border/50" style={{ backgroundColor: msg.soft_color }} />
              </div>
              <input value={msg.soft_text} onChange={e => setMsg({...msg, soft_text: e.target.value})} placeholder="播报文字"
                className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:border-primary-500/40" />
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-textMuted">文字色</span>
                <div className="relative">
                  <input type="color" value={msg.soft_text_color} onChange={e => setMsg({...msg, soft_text_color: e.target.value})}
                    onMouseDown={e => e.stopPropagation()} className="absolute inset-0 opacity-0 w-6 h-6 cursor-pointer" />
                  <div className="w-6 h-6 rounded border border-border/50" style={{ backgroundColor: msg.soft_text_color }} />
                </div>
              </div>
              <select value={msg.soft_style} onChange={e => setMsg({...msg, soft_style: e.target.value})}
                className="px-2.5 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textPrimary focus:outline-none">
                <option value="banner">顶栏</option>
                <option value="popup">弹窗</option>
              </select>
              <label className="flex items-center gap-1.5 text-[11px] text-textSecondary cursor-pointer select-none ml-auto">
                <input type="checkbox" checked={msg.soft_once} onChange={e => setMsg({...msg, soft_once: e.target.checked})} className="rounded" />
                仅首次
              </label>
            </div>
            {msg.soft_text && (
              <div className="rounded-lg border border-border/30 overflow-hidden">
                <div className="text-[10px] text-textMuted px-3 py-1 bg-canvas/50 border-b border-border/30">预览</div>
                <div className="p-2.5">
                  {msg.soft_style === 'banner' ? (
                    <div className="text-[11px] rounded-lg px-3 py-2 text-center" style={{ backgroundColor: msg.soft_color, color: msg.soft_text_color }}>
                      {msg.soft_text}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/40 bg-canvas/60 p-3 text-center">
                      <div className="text-xs mb-2" style={{ color: msg.soft_text_color }}>{msg.soft_text}</div>
                      <span className="inline-block px-3 py-1 text-[10px] rounded-md" style={{ backgroundColor: msg.soft_color, color: msg.soft_text_color }}>知道了</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 保存 ── */}
      <div className="flex items-center gap-3 bg-surface rounded-xl border border-border px-4 py-3">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-600 disabled:opacity-50 transition-colors">
          <Save size={14} />{saving ? '保存中···' : '保存'}
        </button>
        {saved && <span className="text-xs text-mint-400"><Check size={12} className="inline text-mint-400" /> 已保存，在线用户已同步</span>}
        {saveError && <span className="text-xs text-rose-400 flex items-center gap-1"><AlertTriangle size={12} />{saveError}</span>}
      </div>
    </div>
  )
}
