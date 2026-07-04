import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, X } from 'lucide-react'

interface MsgData {
  hard_title: string; hard_body: string; hard_color: string; hard_text_color: string
  hard_image: string; hard_style: string
  soft_text: string; soft_color: string; soft_style: string
}

interface PresetItem extends MsgData { name: string }

const DEFAULT_MSG: MsgData = {
  hard_title: '正在更新', hard_body: '服务器正在更新，稍等一下就好~',
  hard_color: '#f59e0b', hard_text_color: '#ffffff', hard_image: '', hard_style: 'popup',
  soft_text: '服务器正在调整，功能可能偶尔不稳定', soft_color: '#f59e0b', soft_style: 'banner',
}

export default function MaintenanceMsgEditor() {
  const [msg, setMsg] = useState<MsgData>(DEFAULT_MSG)
  const [presets, setPresets] = useState<PresetItem[]>([])
  const [images, setImages] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saved, setSaved] = useState(false)
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
    try { await api.put('/admin/maintenance/msg', msg); setSaved(true); setTimeout(() => setSaved(false), 2000) } catch {}
  }

  const applyPreset = (name: string) => {
    const p = presets.find(x => x.name === name)
    if (p) { setMsg({ hard_title: p.hard_title, hard_body: p.hard_body, hard_color: p.hard_color, hard_text_color: p.hard_text_color, hard_image: p.hard_image, hard_style: p.hard_style, soft_text: p.soft_text, soft_color: p.soft_color, soft_style: p.soft_style }); setSelPreset(name) }
  }

  const handleUpload = async (file: File) => {
    const r: any = await api.upload('/fs/upload-attachment', file)
    const url = `/api/fs/public/${r.file_id}`
    setMsg(prev => ({ ...prev, hard_image: url }))
    try { await api.post(`/admin/maintenance/images?url=${encodeURIComponent(url)}`); setImages(prev => [url, ...prev.filter(x => x !== url)]) } catch {}
  }

  const handlePresetAction = async (action: string, name?: string) => {
    if (action === 'save') {
      const n = prompt('预设名称：', selPreset || '')
      if (!n) return
      try {
        // 同名先删再存=更新
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

  const F = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div><label className="block text-[10px] text-textMuted mb-1">{label}</label>{children}</div>
  )

  return (
    <div className="bg-surface rounded-xl border border-border p-5 space-y-4">
      <p className="text-xs font-semibold text-textSecondary uppercase tracking-wider">维护文案</p>

      {/* ── 预设 ── */}
      <div className="flex items-center gap-2">
        <select value={selPreset} onChange={e => { const v = e.target.value; if (v === '__save__') handlePresetAction('save'); else if (v) applyPreset(v); else setSelPreset('') }}
          className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50">
          <option value="">无预设</option>
          {presets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        <button onClick={() => handlePresetAction('save')} className="shrink-0 px-2 py-1 text-[10px] rounded-lg border border-dashed border-border text-textMuted hover:text-primary-400 transition-colors"><Plus size={12} className="inline" /> 存预设</button>
      </div>
      {/* 预设行内操作 */}
      {selPreset && (
        <div className="flex gap-2 -mt-2">
          <button onClick={() => handlePresetAction('rename', selPreset)} className="text-[10px] text-textMuted hover:text-primary-400">✏️ 改名</button>
          <button onClick={() => handlePresetAction('del', selPreset)} className="text-[10px] text-rose-400 hover:text-rose-300">🗑 删除</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* ── 硬维护 ── */}
        <F label="暂停服务——弹窗标题">
          <div className="flex gap-1.5"><input type="color" value={msg.hard_color} onChange={e => setMsg({...msg, hard_color: e.target.value})} className="w-8 h-8 rounded cursor-pointer border border-border" />
          <input value={msg.hard_title} onChange={e => setMsg({...msg, hard_title: e.target.value})} className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50" /></div>
        </F>
        <F label="暂停服务——文字颜色">
          <input type="color" value={msg.hard_text_color} onChange={e => setMsg({...msg, hard_text_color: e.target.value})} className="w-8 h-8 rounded cursor-pointer border border-border" />
        </F>
        <F label="暂停服务——弹窗正文">
          <input value={msg.hard_body} onChange={e => setMsg({...msg, hard_body: e.target.value})} className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50" />
        </F>
        <F label="提示样式">
          <select value={msg.hard_style} onChange={e => setMsg({...msg, hard_style: e.target.value})} className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50">
            <option value="popup">弹窗</option><option value="banner">顶栏</option>
          </select>
        </F>

        {/* ── 图片 ── */}
        <F label="弹窗图片（上传 / URL / 图库）">
          <div className="flex gap-1.5">
            <input value={msg.hard_image} onChange={e => setMsg({...msg, hard_image: e.target.value})} placeholder="图片URL或选下" className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50" />
            <label className="relative shrink-0 px-2 py-1 text-[10px] rounded-lg border border-border bg-canvas text-textSecondary hover:text-primary-400 cursor-pointer transition-colors overflow-hidden">
              上传<input type="file" accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f) }} />
            </label>
          </div>
          <div className="flex gap-1.5 mt-1">
            <select onChange={e => { const v = e.target.value; if (v === '__add__') handleImageAction('add_url'); else if (v === '__del__') handleImageAction('del'); else if (v) setMsg({...msg, hard_image: v}); e.target.value = '' }}
              className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textMuted focus:outline-none focus:ring-1 focus:ring-primary-500/50" defaultValue="">
              <option value="">从图片库选择…</option>
              {images.map((url, i) => <option key={i} value={url}>{url.slice(url.lastIndexOf('/') + 1)}</option>)}
              {presets.filter(p => p.hard_image && !images.includes(p.hard_image)).map(p => <option key={p.name} value={p.hard_image}>{p.name} 图</option>)}
              <option disabled>────────</option>
              <option value="__add__">🔗 添加外链</option>
              <option value="__del__">🗑 删除图片</option>
            </select>
          </div>
          {msg.hard_image && <img src={msg.hard_image} className="h-16 object-contain rounded-lg border border-border mt-1 bg-black/10" />}
        </F>

        {/* ── 软维护 ── */}
        <F label="维护提示——顶部文字">
          <div className="flex gap-1.5"><input type="color" value={msg.soft_color} onChange={e => setMsg({...msg, soft_color: e.target.value})} className="w-8 h-8 rounded cursor-pointer border border-border" />
          <input value={msg.soft_text} onChange={e => setMsg({...msg, soft_text: e.target.value})} className="flex-1 px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50" /></div>
        </F>
        <F label="维护提示样式">
          <select value={msg.soft_style} onChange={e => setMsg({...msg, soft_style: e.target.value})} className="w-full px-3 py-1.5 rounded-lg border border-border bg-canvas text-xs text-textPrimary focus:outline-none focus:ring-1 focus:ring-primary-500/50">
            <option value="banner">顶栏</option><option value="popup">弹窗</option>
          </select>
        </F>
      </div>

      <div className="flex items-center gap-3 pt-1">
        <button onClick={save} className="px-4 py-1.5 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-400 transition-colors">保存文案</button>
        {saved && <span className="text-xs text-mint-400">已保存</span>}
      </div>
    </div>
  )
}
