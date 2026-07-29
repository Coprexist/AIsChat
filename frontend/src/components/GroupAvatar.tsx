/** 群聊头像组件：默认图标 / 成员网格 / 自定义图片，含缩略图支持 */
import { Users } from 'lucide-react'

export interface GroupAvatarData {
  avatar_mode?: string
  avatar_url?: string | null
  member_avatars?: string[]
  include_ai_in_avatar?: boolean
}

/** 添加缩略图参数，动图保持原图 */
export function thumbUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  if (url.includes('/download-avatar/') && !url.endsWith('.gif')) {
    return url + (url.includes('?') ? '&thumb=1' : '?thumb=1')
  }
  return url
}

/** 侧边栏群聊头像（w-9 h-9） */
export function GroupAvatarGroup({ g }: { g: GroupAvatarData }) {
  const mode = g.avatar_mode || 'default'
  const avatars = g.member_avatars || []

  if (mode === 'custom' && g.avatar_url) {
    return (
      <div className="w-9 h-9 rounded-lg overflow-hidden shrink-0 bg-elevated">
        <img key={g.avatar_url} src={thumbUrl(g.avatar_url) || g.avatar_url} alt="" className="w-full h-full object-cover" loading="lazy" />
      </div>
    )
  }

  if (mode === 'default') {
    return (
      <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0">
        <Users size={14} className="text-primary-400/70" />
      </div>
    )
  }

  // members 模式：2×2 网格
  if (avatars.length === 0) {
    return (
      <div className="w-9 h-9 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0">
        <Users size={14} className="text-primary-400/70" />
      </div>
    )
  }
  return (
    <div className="w-9 h-9 rounded-lg bg-elevated grid grid-cols-2 grid-rows-2 gap-px overflow-hidden shrink-0">
      {avatars.slice(0, 4).map((url, i) => (
        <div key={i} className="bg-canvas flex items-center justify-center">
          <img src={thumbUrl(url) || url} alt="" className="w-full h-full object-cover" loading="lazy" />
        </div>
      ))}
      {avatars.length < 4 && Array.from({ length: 4 - avatars.length }).map((_, i) => (
        <div key={`empty-${i}`} className="bg-canvas flex items-center justify-center">
          <Users size={8} className="text-textMuted/40" />
        </div>
      ))}
    </div>
  )
}

/** 聊天头部群聊头像（w-8 h-8），带点击回调 */
export function GroupAvatarHeader({
  g,
  onClick,
}: {
  g: GroupAvatarData
  onClick?: () => void
}) {
  const mode = g.avatar_mode || 'default'
  const img = (
    <div className="w-8 h-8 rounded-lg overflow-hidden shrink-0 bg-elevated cursor-pointer hover:opacity-80 transition-opacity">
      <img key={g.avatar_url} src={thumbUrl(g.avatar_url) || g.avatar_url} alt="" className="w-full h-full object-cover" loading="lazy" />
    </div>
  )
  const icon = (
    <div className="w-8 h-8 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0 cursor-pointer hover:opacity-80 transition-opacity">
      <Users size={14} className="text-primary-400/70" />
    </div>
  )

  return (
    <button onClick={onClick} className="shrink-0">
      {mode === 'custom' && g.avatar_url ? img : icon}
    </button>
  )
}
