/**
 * 容器内滚动工具
 *
 * 背景：scrollIntoView() 会滚动所有可滚动祖先（包括 overflow-hidden 的容器，
 * 它只是隐藏滚动条，JS 依然能设置 scrollTop）。在聊天页里这会把外层 main/Layout
 * 连带滚动，导致标题栏被滚出视口。
 *
 * 这个函数只滚动指定容器本身，不碰祖先链。
 */

/** 计算 target 在 container 内应处的 scrollTop（不执行滚动） */
export function scrollTopInContainer(container: HTMLElement, target: HTMLElement, offset = 0): number {
  return container.scrollTop + (target.getBoundingClientRect().top - container.getBoundingClientRect().top) + offset
}

/** 滚动容器，使 target 出现在容器顶部（offset 可微调，如居中/留白） */
export function scrollToInContainer(
  container: HTMLElement,
  target: HTMLElement,
  options: { offset?: number; smooth?: boolean } = {},
): void {
  const { offset = 0, smooth = false } = options
  const top = scrollTopInContainer(container, target, offset)
  if (smooth) {
    container.scrollTo({ top, behavior: 'smooth' })
  } else {
    container.scrollTop = top
  }
}
