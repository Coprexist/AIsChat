/**
 * 左栏「会话」页签内容：会话列表（当前高亮）+ 新对话入口 + 每行 ⋯ 溢出菜单
 *
 * 只做展示与回调：会话状态与动作仍归 WorldChatPanel（useWorldChat 全页只有那一个实例），
 * 父组件从 onSessionsChange 收数据、通过 ref 调动作——不重复拉接口，也不复制一份状态。
 */
import { useState } from 'react'
import { Plus, MoreHorizontal, Pin } from 'lucide-react'
import { useLang, useT } from '../../i18n/I18nContext'
import { formatRelativeTime } from '../../utils/time'

export interface WorldSessionInfo {
  id: string
  title?: string
  last_active_at?: string
  pinned?: boolean
}

interface WorldSessionListProps {
  sessions: WorldSessionInfo[]
  /** 当前会话 id：整行高亮，不写"当前"两个字 */
  current: string
  onSelect: (id: string) => void
  onNew: () => void
  onRename: (s: WorldSessionInfo) => void
  /** 只能收藏当前会话（后端的 pin 是按当前会话落库的） */
  onTogglePin: () => void
  onExport: (s: WorldSessionInfo, fmt: 'md' | 'json') => void
}

const MENU_ITEM = 'w-full text-left px-3 py-1.5 text-2xs text-textSecondary hover:bg-surface hover:text-textPrimary transition-colors'

/** 每行的 ⋯ 菜单：改名/收藏/下载都收在这里，行本身只留"切过去"一个动作 */
function RowMenu({ sess, isCurrent, onRename, onTogglePin, onExport }: {
  sess: WorldSessionInfo
  isCurrent: boolean
  onRename: (s: WorldSessionInfo) => void
  onTogglePin: () => void
  onExport: (s: WorldSessionInfo, fmt: 'md' | 'json') => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        // 悬停才显形，触屏没有 hover 就常显——否则这行操作在手机上永远点不到
        className={`icon-btn-sm text-textMuted ${open ? '' : 'opacity-0 group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100'}`}
        title={t('tool:world.session.more')}
        aria-label={t('tool:world.session.more')}
      >
        <MoreHorizontal size={14} />
      </button>
      {open && (
        <>
          {/* 透明遮罩收起：与面板里其它小菜单同一套做法，不挂 document 监听 */}
          <div className="fixed inset-0 z-modal" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-0.5 w-44 py-1 rounded-card bg-elevated border border-border shadow-xl z-toast">
            <button className={MENU_ITEM} onClick={() => { setOpen(false); onRename(sess) }}>{t('tool:world.session.rename')}</button>
            {isCurrent && (
              <button className={MENU_ITEM} onClick={() => { setOpen(false); onTogglePin() }}>
                {sess.pinned ? t('tool:world.session.unpin') : t('tool:world.session.pin')}
              </button>
            )}
            <button className={MENU_ITEM} onClick={() => { setOpen(false); onExport(sess, 'md') }}>{t('tool:world.session.exportMd')}</button>
            <button className={MENU_ITEM} onClick={() => { setOpen(false); onExport(sess, 'json') }}>{t('tool:world.session.exportJson')}</button>
          </div>
        </>
      )}
    </div>
  )
}

export default function WorldSessionList({ sessions, current, onSelect, onNew, onRename, onTogglePin, onExport }: WorldSessionListProps) {
  const t = useT()
  const lang = useLang()
  const label = (s: WorldSessionInfo) => s.title || (s.id === 'default' ? t('tool:world.session.default') : s.id)
  return (
    <div className="p-2 space-y-0.5">
      <button
        onClick={onNew}
        className="w-full inline-flex items-center gap-1.5 px-2 py-1.5 rounded-control text-xs text-primary-400 hover:bg-elevated transition-colors"
        title={t('tool:world.session.new')}
      >
        <Plus size={13} />
        {t('tool:world.session.new')}
      </button>
      {sessions.map((s) => {
        const isCurrent = s.id === current
        return (
          <div
            key={s.id}
            className={`group flex items-center rounded-control transition-colors ${isCurrent ? 'bg-primary-500/15 text-primary-300' : 'text-textSecondary hover:bg-elevated'}`}
          >
            <button
              onClick={() => onSelect(s.id)}
              className="flex items-center gap-1.5 min-w-0 flex-1 px-2 py-1.5 text-xs text-left"
              title={`${label(s)}\n${s.id}`}
            >
              <span className="truncate min-w-0 flex-1">{label(s)}</span>
              {s.pinned && <Pin size={10} className="shrink-0 text-accent-400 fill-current" />}
              {s.last_active_at && (
                <span className="shrink-0 text-3xs text-textMuted">{formatRelativeTime(s.last_active_at, lang)}</span>
              )}
            </button>
            <RowMenu sess={s} isCurrent={isCurrent} onRename={onRename} onTogglePin={onTogglePin} onExport={onExport} />
          </div>
        )
      })}
      {sessions.length === 0 && <div className="px-2 py-3 text-2xs text-textMuted">{t('tool:world.session.empty')}</div>}
      {/* 末尾留白：末行的 ⋯ 菜单往下展开需要空间，否则会被滚动容器裁掉 */}
      <div className="h-24" aria-hidden />
    </div>
  )
}
