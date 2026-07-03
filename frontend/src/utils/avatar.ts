/**
 * 头像渐变类名（纯函数）
 *
 * 返回完整 Tailwind 渐变字符串：
 * - 自己（右侧）：紫色渐变 (primary)
 * - 对方（左侧）：绿色渐变 (teal)
 * - 系统：红色渐变 (rose)
 * - 有头像时 to- 色带 /30 透明度，无头像时完全不透明
 */
export function avatarGradient(
  senderType: string | undefined,
  isMine: boolean,
  hasAvatar: boolean,
): string {
  const dir = isMine ? 'bg-gradient-to-br' : 'bg-gradient-to-bl'
  if (senderType === 'system') {
    return hasAvatar
      ? `${dir} from-rose-400 to-rose-600/30`
      : `${dir} from-rose-400 to-rose-600`
  }
  if (isMine) {
    return hasAvatar
      ? `${dir} from-primary-500 to-primary-700/30`
      : `${dir} from-primary-500 to-primary-700`
  }
  return hasAvatar
    ? `${dir} from-teal-400 to-teal-600/30`
    : `${dir} from-teal-400 to-teal-600`
}

/** 头像阴影色 */
export function avatarShadowColor(
  senderType: string | undefined,
  isMine: boolean,
): string {
  if (isMine) return 'shadow-primary-500/15'
  if (senderType === 'system') return 'shadow-rose-400/15'
  return 'shadow-teal-400/10'
}
