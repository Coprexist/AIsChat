import { useState, useEffect, useCallback, useRef } from 'react'
import { Image, Upload, X, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import { useT } from '../i18n/I18nContext'
import AvatarCropModal from './AvatarCropModal'

interface FileItem {
  id: number
  path: string
  size: number
  mime_type: string
  created_at: string | null
}

interface GroupAvatarPickerModalProps {
  groupId: number
  onCancel: () => void
  onUploadComplete: (avatarUrl: string) => void
}

export default function GroupAvatarPickerModal({
  groupId,
  onCancel,
  onUploadComplete,
}: GroupAvatarPickerModalProps) {
  const t = useT()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 文件列表状态
  const [files, setFiles] = useState<FileItem[]>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [fileError, setFileError] = useState('')

  // 裁剪状态
  const [cropFile, setCropFile] = useState<File | null>(null)

  // 上传状态
  const [uploading, setUploading] = useState(false)

  // 第一步：选择模式
  const [step, setStep] = useState<'pick' | 'select-file'>('pick')

  // 加载个人空间文件
  const loadFiles = useCallback(async () => {
    setLoadingFiles(true)
    setFileError('')
    try {
      const data = await api.get<FileItem[]>('/fs/list?path=.')
      const list = Array.isArray(data) ? data : []
      // 只显示图片
      setFiles(list.filter((f) => f.mime_type?.startsWith('image/')))
    } catch (e: any) {
      setFileError(e?.detail || '加载文件列表失败')
    } finally {
      setLoadingFiles(false)
    }
  }, [])

  // 每次切到 select-file 时加载
  useEffect(() => {
    if (step === 'select-file') {
      loadFiles()
    }
  }, [step, loadFiles])

  // 从文件选择器选择新图片
  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCropFile(file)
    e.target.value = ''
  }

  // 从个人空间选择图片
  const handleSelectFromSpace = async (fileItem: FileItem) => {
    try {
      // 通过 download endpoint 获取 Blob
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/fs/download/${fileItem.id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '下载失败' }))
        throw new Error(err.detail || '下载失败')
      }
      const blob = await res.blob()
      // 提取扩展名
      const ext = fileItem.path.includes('.') ? fileItem.path.split('.').pop() || 'jpg' : 'jpg'
      const file = new File([blob], fileItem.path.split('/').pop() || `image.${ext}`, {
        type: fileItem.mime_type || 'image/jpeg',
      })
      setCropFile(file)
    } catch (e: any) {
      setFileError(e?.message || '下载文件失败')
    }
  }

  // 裁剪确认后上传
  const handleCropConfirm = async (blob: Blob) => {
    setCropFile(null)
    setUploading(true)
    try {
      const ext =
        blob.type === 'image/gif'
          ? 'gif'
          : blob.type === 'image/png'
            ? 'png'
            : 'jpg'
      const file = new File([blob], `avatar.${ext}`, {
        type: blob.type || 'image/jpeg',
      })
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post<{ avatar_url: string; avatar_mode: string }>(
        `/groups/${groupId}/avatar`,
        formData,
      )
      onUploadComplete(res.avatar_url)
    } catch (e: any) {
      setFileError(e?.detail || '头像上传失败')
      setUploading(false)
    }
  }

  const handleCropCancel = () => {
    setCropFile(null)
  }

  return (
    <>
      {/* 遮罩 */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        onClick={onCancel}
      >
        <div
          className="relative bg-surface border border-border rounded-xl shadow-2xl w-80 max-w-[90vw] p-5"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 标题栏 */}
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-textPrimary">
              {t('groupSettings.avatarPickerTitle')}
            </h3>
            <button
              onClick={onCancel}
              className="p-1 rounded-lg hover:bg-elevated text-textMuted transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* 错误提示 */}
          {fileError && (
            <div className="mb-3 text-xs text-rose-400 bg-rose-400/10 rounded-lg px-3 py-2">
              {fileError}
            </div>
          )}

          {/* 第一步：选择来源 */}
          {step === 'pick' && (
            <div className="grid grid-cols-2 gap-3">
              {/* 选项1：从个人空间选择 */}
              <button
                onClick={() => setStep('select-file')}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl border border-border bg-elevated hover:bg-canvas transition-colors"
              >
                <div className="w-12 h-12 rounded-xl bg-primary-500/10 dark:bg-primary-900/30 flex items-center justify-center">
                  <Image size={22} className="text-primary-400" />
                </div>
                <span className="text-sm font-medium text-textPrimary">
                  {t('groupSettings.avatarPickerFromSpace')}
                </span>
                <span className="text-[10px] text-textMuted text-center leading-tight">
                  {t('groupSettings.avatarPickerFromSpaceDesc')}
                </span>
              </button>

              {/* 选项2：上传新图片 */}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl border border-border bg-elevated hover:bg-canvas transition-colors"
              >
                <div className="w-12 h-12 rounded-xl bg-mint-400/10 dark:bg-mint-900/30 flex items-center justify-center">
                  <Upload size={22} className="text-mint-400" />
                </div>
                <span className="text-sm font-medium text-textPrimary">
                  {t('groupSettings.avatarPickerUploadNew')}
                </span>
                <span className="text-[10px] text-textMuted text-center leading-tight">
                  {t('groupSettings.avatarPickerUploadNewDesc')}
                </span>
              </button>
            </div>
          )}

          {/* 第二步：从个人空间文件列表选择 */}
          {step === 'select-file' && (
            <div>
              {/* 返回按钮 */}
              <button
                onClick={() => setStep('pick')}
                className="mb-3 text-xs text-primary-400 hover:text-primary-300 transition-colors"
              >
                ← {t('common.back')}
              </button>

              {loadingFiles ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={20} className="animate-spin text-textMuted" />
                </div>
              ) : files.length === 0 ? (
                <div className="text-center py-6 text-textMuted">
                  <Image size={28} className="mx-auto mb-2 opacity-40" />
                  <p className="text-xs">{t('groupSettings.avatarPickerNoImages')}</p>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto">
                  {files.map((f) => (
                    <button
                      key={f.id}
                      onClick={() => handleSelectFromSpace(f)}
                      className="relative aspect-square rounded-lg overflow-hidden border border-border bg-elevated hover:border-primary-400 transition-colors group"
                      title={f.path.split('/').pop() || f.path}
                    >
                      <img
                        src={`/api/fs/download/${f.id}`}
                        alt={f.path}
                        className="w-full h-full object-cover"
                        loading="lazy"
                        onError={(e) => {
                          // 加载失败时显示占位
                          const target = e.currentTarget
                          target.style.display = 'none'
                          if (target.parentElement) {
                            target.parentElement.classList.add(
                              'flex',
                              'items-center',
                              'justify-center',
                            )
                            const icon = document.createElement('div')
                            icon.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-textMuted"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
                            target.parentElement.appendChild(icon)
                          }
                        }}
                      />
                      <div className="absolute inset-0 bg-primary-400/0 group-hover:bg-primary-400/10 transition-colors" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 隐藏的文件选择器 */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileInputChange}
          />

          {/* 上传指示 */}
          {uploading && (
            <div className="mt-3 flex items-center justify-center gap-2 text-xs text-primary-400">
              <Loader2 size={14} className="animate-spin" />
              {t('common.uploading')}
            </div>
          )}
        </div>
      </div>

      {/* 裁剪弹窗 */}
      {cropFile && (
        <AvatarCropModal
          file={cropFile}
          onConfirm={handleCropConfirm}
          onCancel={handleCropCancel}
        />
      )}
    </>
  )
}
