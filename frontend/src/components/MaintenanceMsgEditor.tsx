import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Save, Upload, Pencil, Check } from 'lucide-react'
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

export default function MaintenanceMsgEditor() {
  const t = useT()
  const [msg, setMsg] = useState<MsgData>(DEFAULT_MSG)
  const [presets, setPresets] = useState<PresetItem[]>([])
  const [images, setImages] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selPreset, setSelPreset] = useState('')

  const load = async () => {
    try {
      const [m, p, img] = await Promise.all([
        api.get('/admin/maintenance/msg'), api.get('/admin/maintenance/presets'), api.get('/admin/maintenance/images'),
      ])
      const d: any = m; setMsg({ ...DEFAULT_MSG, ...Object.fromEntries(Object.entries(d).filter(([,v]) => v != null)) })
      setPresets((p as any).presets || [])
      setImages((img as any).images || [])
      setLoaded(true)
    } catch {}
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (saving) return
    setSaving(true)
    try { await api.put('/admin/maintenance/msg', msg); setSaved(true); setTimeout(() => setSaved(false), 2000) } catch {}
    setSaving(false)
  }

  const applyPreset = (name: string) => {
    const p = presets.find(x => x.name === name)
    if (p) {
      setMsg({
        hard_title: p.hard_title, hard_body: p.hard_body,
        hard_color: p.hard_color, hard_text_color: p.hard_text_color,
        hard_image: p.hard_image, hard_style: p.hard_style,
        soft_text: p.soft_text, soft_color: p.soft_color,
        soft_text_color: (p as any).soft_text_color ?? '#ffffff',
        soft_style: p.soft_style, soft_once: (p as any).soft_once ?? false,
      })
      setSelPreset(name)
    }
  }

  const handleUpload = async (file: File) => {
    if (uploading) return
    setUploading(true)
    try {
      const r: any = await api.upload('/fs/upload-attachment', file)
      const url = `/api/fs/public/${r.file_id}`
      setMsg(prev => ({ ...prev, hard_image: url }))
      try { await api.post(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); setImages(prev => [url, ...prev.filter(x => x !== url)]) } catch {}
    } catch {}
    setUploading(false)
  }

  const handlePresetAction = async (action: string, name?: string) => {
    if (action === 'save') {
      const n = prompt('预设名称：', selPreset || '')
      if (!n) return
      try {
        if (presets.some(p => p.name === n)) await api.delete(`/admin/maintenance/presets/${encodeURIComponent(n)}`)
        await api.post('/admin/maintenance/presets', { name: n, ...msg })
        setSelPreset(n); load()
      } catch (e: any) { alert(e?.message || '保存失败') }
    } else if (action === 'del' && name) {
      if (confirm(`删除「${name}」？`)) { await api.delete(`/admin/maintenance/presets/${encodeURIComponent(name)}`); if (selPreset === name) setSelPreset(''); load() }
    } else if (action === 'rename' && name) {
      const nn = prompt('新名称：', name)
      if (!nn || nn === name) return
      const p = presets.find(x => x.name === name)
      if (!p) return
      await api.delete(`/admin/maintenance/presets/${encodeURIComponent(name)}`)
      await api.post('/admin/maintenance/presets', { ...p, name: nn })
      if (selPreset === name) setSelPreset(nn); load()
    }
  }

  const handleImageAction = async (action: string) => {
    if (action === 'add_url') {
      const url = prompt('输入外网图片URL：')
      if (url) { setMsg(prev => ({ ...prev, hard_image: url })); try { await api.post(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); setImages(prev => [url, ...prev.filter(x => x !== url)]) } catch {} }
    } else if (action === 'del') {
      const url = prompt('删除图片URL：', msg.hard_image)
      if (url) { await api.delete(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); if (msg.hard_image === url) setMsg(prev => ({ ...prev, hard_image: '' })); load() }
    }
  }

  if (!loaded) return null

  return (
    <div className="space-y-3">

      {/* ── 预设栏 ── */}
      <div className="bg-surface rounded-xl border border-border p-3.5 flex items-center gap-2">
        <select value={selPreset} onChange={e => { const v = e.target.value; if (v === '__save__') handlePresetAction('save'); else if (v) applyPreset(v); else setSelPreset('') }}
          className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50">
          <option value="">{t('admin.presets')} ···</option>
          {presets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        <button onClick={() => handlePresetAction('save')} className="shrink-0 px-3 py-1.5 text-[11px] rounded-lg border border-dashed border-border text-textMuted hover:text-primary-400 transition-colors"><Plus size={13} className="inline mr-0.5" />存预设</button>
        {selPreset && (
          <>
            <button onClick={() => handlePresetAction('rename', selPreset)} className="text-[11px] text-textMuted hover:text-primary-400"><Pencil size={12} /></button>
            <button onClick={() => handlePresetAction('del', selPreset)} className="text-[11px] text-rose-400/70 hover:text-rose-400">🗑</button>
          </>
        )}
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
                <label className={`shrink-0 px-2.5 py-1.5 rounded-lg border border-border bg-canvas text-[11px] text-textSecondary hover:text-primary-400 cursor-pointer transition-colors ${uploading ? 'opacity-40 pointer-events-none' : ''}`}>
                  {uploading ? '···' : <Upload size={13} />}
                  <input type="file" accept="image/*" className="hidden" disabled={uploading} onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f) }} />
                </label>
              </div>
              <div className="flex gap-1.5 mt-1.5">
                <select onChange={e => { const v = e.target.value; if (v === '__add__') handleImageAction('add_url'); else if (v === '__del__') handleImageAction('del'); else if (v) setMsg({...msg, hard_image: v}); e.target.value = '' }}
                  className="flex-1 px-2.5 py-1 rounded-lg border border-border bg-canvas text-[11px] text-textMuted focus:outline-none" defaultValue="">
                  <option value="">图库</option>
                  {images.map((url, i) => <option key={i} value={url}>{url.slice(url.lastIndexOf('/') + 1)}</option>)}
                  {presets.filter(p => p.hard_image && !images.includes(p.hard_image)).map(p => <option key={p.name} value={p.hard_image}>{p.name}</option>)}
                  <option value="__add__">+ 外链</option>
                  <option value="__del__">- 删除</option>
                </select>
              </div>
              {msg.hard_image && (
                <img src={msg.hard_image} alt="" className="h-16 object-contain rounded-lg border border-border/50 mt-1.5 bg-black/20"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              )}
            </div>
          </div>
        </div>

        {/* 软维护 */}
        <div className="bg-surface rounded-xl border border-border p-4 space-y-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-textPrimary">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
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
                  <div className="text-[11px] rounded-lg px-3 py-2 text-center" style={{ backgroundColor: msg.soft_color, color: msg.soft_text_color }}>
                    {msg.soft_text}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 保存 ── */}
      <div className="flex items-center gap-3 bg-surface rounded-xl border border-border px-4 py-3">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-400 disabled:opacity-50 transition-colors">
          <Save size={14} />{saving ? '保存中···' : '保存'}
        </button>
        {saved && <span className="text-xs text-mint-400"><Check size={12} className="inline text-mint-400" /> 已保存</span>}
      </div>
    </div>
  )
}
