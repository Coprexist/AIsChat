/**
 * 页面标题栏底座（2026-08-07 统一所有界面顶端）
 *
 * 用法：页面根容器用 `h-full flex flex-col bg-canvas`，
 * 标题栏用 <PageHeader title="..." subtitle="...">右侧操作区</PageHeader>，
 * 内容区 flex-1 自行滚动。
 * onBack：提供后标题栏左侧显示返回按钮（子页面用，如 我的→用量）。
 *
 * 样式与 AgentsPage / SettingsPage / FriendsPage 现有标题栏完全一致（h-14 + border-b + bg-surface）。
 */
import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  onBack?: () => void
  children?: ReactNode
}

export default function PageHeader({ title, subtitle, onBack, children }: PageHeaderProps) {
  return (
    <div className="px-4 h-14 border-b border-border bg-surface flex items-center gap-2 shrink-0">
      {onBack && (
        <button
          onClick={onBack}
          className="-ml-1 px-1.5 rounded hover:bg-elevated text-textMuted hover:text-textPrimary transition-colors shrink-0 text-lg leading-none font-light"
          title="返回"
        >
          &lt;
        </button>
      )}
      <h1 className="font-semibold text-textPrimary text-sm truncate">{title}</h1>
      {subtitle && <span className="text-xs text-textMuted hidden sm:inline truncate">{subtitle}</span>}
      <div className="ml-auto flex items-center gap-2 shrink-0">{children}</div>
    </div>
  )
}
