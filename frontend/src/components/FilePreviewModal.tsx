import { useState, useEffect, useCallback, useRef } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkBreaks from 'remark-breaks'
import rehypeKatex from 'rehype-katex'
import { Download, X, ArrowLeft, FileIcon, Loader2, AlertTriangle, ZoomIn, ZoomOut, RotateCcw, Share2 } from 'lucide-react'
import { useT } from '../i18n/I18nContext'
import { formatFileSize } from '../utils/format'
import { isTextPreviewable, getCodeLang, isMarkdownFile, resolveMimeType, EXT_LANG_MAP } from '../utils/mime'
import CodeRenderer from './shared/CodeRenderer'
import ForwardFileModal from './ForwardFileModal'

// FileCodeRenderer ——已迁移到 components/shared/CodeRenderer.tsx

interface FilePreviewModalProps {
  fileId: number
  fileName: string
  fileSize: number
  mimeType: string
  onClose: () => void
}

export default function FilePreviewModal({ fileId, fileName, fileSize, mimeType, onClose }: FilePreviewModalProps) {
  const t = useT()
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // 图片缩放
  const [scale, setScale] = useState(1)
  const imgContainerRef = useRef<HTMLDivElement>(null)
  const [forwardFile, setForwardFile] = useState<{file_id:number;name:string;size:number;mime_type:string}|null>(null)

  const token = localStorage.getItem('access_token')
  const dlUrl = `/api/fs/download/${fileId}?token=${token || ''}`

  // 优先后端 mimeType，缺失时从文件名扩展名推断
  const resolvedMime = resolveMimeType(fileName, mimeType)

  const isImage = resolvedMime.startsWith('image/')
  const isPDF = resolvedMime === 'application/pdf'
  const isDocx = resolvedMime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    || fileName.endsWith('.docx')
  const isText = isTextPreviewable(resolvedMime)
  const isHtml = resolvedMime === 'text/html' || fileName.endsWith('.html') || fileName.endsWith('.htm')
  const previewable = isImage || isPDF || isDocx || isText || isHtml
  const isMd = isMarkdownFile(fileName, resolvedMime)
  const codeLang = isHtml ? '' : getCodeLang(fileName, resolvedMime)  // HTML 用 iframe 渲染

  useEffect(() => {
    if (!previewable) {
      // 不可预览 → 直接触发下载
      const a = document.createElement('a')
      a.href = dlUrl
      a.download = fileName
      a.click()
      onClose()
      return
    }

    // 图片 / PDF：不需要 fetch 文本内容
    if (isImage || isPDF) {
      setLoading(false)
      return
    }

    const ac = new AbortController()
    fetch(dlUrl, { signal: ac.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)

        // DOCX → mammoth 转换
        if (isDocx) {
          const { default: mammoth } = await import('mammoth')
          const buf = await res.arrayBuffer()
          const result = await mammoth.convertToHtml({ arrayBuffer: buf })
          setContent(result.value)
          setLoading(false)
          return
        }

        // 文本类
        let text = await res.text()
        if (text.length > 2 * 1024 * 1024) {
          text = text.slice(0, 2 * 1024 * 1024) + '\n\n' + t('filePreview.fileTooLarge')
        }
        // 代码文件：包装为 markdown 代码块交给 Markdown 渲染
        if (codeLang) {
          text = '```' + codeLang + '\n' + text + '\n```'
        }
        setContent(text)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError(err.message || t('common.loadFailed'))
          setLoading(false)
        }
      })

    return () => ac.abort()
  }, [fileId, previewable, dlUrl, fileName, onClose, t, isImage, isPDF, isDocx, codeLang])

  // 图片缩放控制
  const zoomIn = useCallback(() => setScale((s) => Math.min(s + 0.5, 5)), [])
  const zoomOut = useCallback(() => setScale((s) => Math.max(s - 0.5, 0.5)), [])
  const zoomReset = useCallback(() => setScale(1), [])
  // 滚轮缩放（仅图片预览）
  useEffect(() => {
    if (!isImage) return
    const el = imgContainerRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        setScale((s) => Math.max(0.5, Math.min(5, s - e.deltaY * 0.005)))
      }
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [isImage])

  const handleDownload = useCallback(() => {
    const a = document.createElement('a')
    a.href = dlUrl
    a.download = fileName
    a.click()
  }, [dlUrl, fileName])

  if (!previewable) return null

  const fileForForward = { file_id: fileId, name: fileName, size: fileSize, mime_type: mimeType }

  const headerBar = (
    <div className="flex items-center gap-3 px-4 h-12 border-b border-border bg-surface shrink-0">
      <button
        onClick={onClose}
        className="p-1 -ml-1 rounded-lg hover:bg-elevated text-textSecondary transition-colors"
        title={t('common.close')}
      >
        <ArrowLeft size={18} className="md:hidden" />
        <X size={18} className="hidden md:block" />
      </button>

      <FileIcon size={18} className="text-textMuted shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-textPrimary truncate">{fileName}</p>
        <p className="text-[10px] text-textMuted">{formatFileSize(fileSize)}</p>
      </div>

      {/* 图片缩放按钮 */}
      {isImage && (
        <div className="flex items-center gap-0.5">
          <button onClick={zoomOut} disabled={scale <= 0.5}
            className="p-1 rounded hover:bg-elevated text-textSecondary disabled:opacity-30 transition-colors" title={t('common.zoomOut')}>
            <ZoomOut size={16} />
          </button>
          <span className="text-[11px] text-textMuted w-9 text-center tabular-nums">{Math.round(scale * 100)}%</span>
          <button onClick={zoomIn} disabled={scale >= 5}
            className="p-1 rounded hover:bg-elevated text-textSecondary disabled:opacity-30 transition-colors" title={t('common.zoomIn')}>
            <ZoomIn size={16} />
          </button>
          <button onClick={zoomReset}
            className="p-1 rounded hover:bg-elevated text-textSecondary transition-colors" title={t('common.resetZoom')}>
            <RotateCcw size={14} />
          </button>
        </div>
      )}

      <button
        onClick={() => setForwardFile({ file_id: fileId, name: fileName, size: fileSize, mime_type: mimeType })}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-textSecondary hover:bg-elevated text-xs font-medium transition-colors"
        title={t('forward.send')}
      >
        <Share2 size={14} />
        <span className="hidden sm:inline">{t('forward.send')}</span>
      </button>

      <button
        onClick={handleDownload}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary-500 text-white text-xs font-medium hover:bg-primary-400 transition-colors"
        title={t('common.download')}
      >
        <Download size={14} />
        <span className="hidden sm:inline">{t('common.download')}</span>
      </button>
    </div>
  )

  return (
    <>
      <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-0 md:p-6" onClick={onClose}>
        <div
          className="bg-surface border border-border md:rounded-2xl shadow-2xl shadow-black/30 flex flex-col
                        w-full h-full md:w-[800px] md:max-h-[88vh] md:h-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {headerBar}

          {/* 内容区 */}
          <div className="flex-1 overflow-auto bg-canvas min-h-0 flex items-start justify-center">
            {loading ? (
              <div className="flex items-center justify-center py-20 w-full">
                <Loader2 size={24} className="animate-spin text-textMuted" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-textMuted w-full">
                <AlertTriangle size={24} className="text-rose-400" />
                <p className="text-sm">{error}</p>
                <button onClick={handleDownload} className="px-4 py-2 rounded-xl bg-primary-500 text-white text-sm">
                  {t('common.downloadInstead')}
                </button>
              </div>
            ) : isImage ? (
              <div ref={imgContainerRef} className="w-full h-full flex items-center justify-center overflow-auto">
                <img
                  src={dlUrl}
                  alt={fileName}
                  className="object-contain transition-transform duration-100 select-none"
                  style={{ transform: `scale(${scale})`, maxWidth: scale <= 1 ? '100%' : 'none', maxHeight: scale <= 1 ? '100%' : 'none' }}
                  draggable={false}
                />
              </div>
            ) : isPDF ? (
              <iframe src={dlUrl} className="w-full h-full border-0" title={fileName} />
            ) : (
              <div className="w-full p-4 md:p-5">
                {isDocx ? (
                  <div
                    className="prose prose-sm dark:prose-invert max-w-none text-textPrimary"
                    dangerouslySetInnerHTML={{ __html: content || '' }}
                  />
                ) : isHtml && content ? (
                  <iframe
                    srcDoc={content}
                    className="w-full h-full border-0 bg-white rounded-lg"
                    title={fileName}
                    sandbox="allow-scripts"
                  />
                ) : isMd || codeLang ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none text-textPrimary
                    [&_.katex-display]:overflow-x-auto [&_.katex-display]:-mx-1 [&_.katex-display]:px-1
                    [&_.katex]:text-inherit [&_.katex]:max-w-full [&_.katex]:overflow-x-auto [&_.katex]:inline-block
                    [&_pre]:overflow-x-auto [&_pre]:-mx-1 [&_pre]:px-1
                    [&_table]:overflow-x-auto [&_table]:block
                    [&_img]:max-w-full [&_img]:rounded-lg
                    [&_a]:break-all [&_a]:text-primary-500 dark:[&_a]:text-primary-400 [&_a]:underline">
                    <Markdown
                      remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
                      rehypePlugins={[rehypeKatex]}
                      components={{ code: CodeRenderer }}
                    >
                      {content || ''}
                    </Markdown>
                  </div>
                ) : (
                  <pre className="text-xs text-textPrimary whitespace-pre-wrap break-all font-mono leading-relaxed select-text">
                    {content}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {forwardFile && (
        <ForwardFileModal
          file={forwardFile}
          onClose={() => setForwardFile(null)}
        />
      )}
    </>
  )
}
