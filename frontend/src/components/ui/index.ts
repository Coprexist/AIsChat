/**
 * 统一 UI 组件库出口
 *
 * 全站唯一的视觉实现来源：
 *   PageShell  页面骨架（根容器 + 标题栏 + 内容宽度）
 *   PageHeader 页面标题栏
 *   Button / IconButton  按钮与图标按钮
 *   Input / Select       表单控件
 *   Card                 卡片区块
 *   Modal / Dialog       弹窗（带卡片 / 只有遮罩）
 *   EmptyState           空状态
 *   Badge                胶囊标签
 *   confirmAsync / ConfirmDialogHost  确认弹窗
 *
 * 视觉规范定义在 index.css 的 @layer components（.btn / .field / .card / .chip /
 * .icon-btn），组件只是它的 React 外壳；手写标签请直接用语义类，不要再写裸 Tailwind 组合。
 */
export { default as Button } from './Button'
export { default as IconButton } from './IconButton'
export { default as Input } from './Input'
export { default as Modal } from './Modal'
export { default as Select } from './Select'
export { default as Card } from './Card'
export { default as Badge } from './Badge'
export { default as Dialog } from './Dialog'
export { default as EmptyState } from './EmptyState'
export { default as PageHeader } from './PageHeader'
export { default as PageShell } from './PageShell'
export { confirmAsync, ConfirmDialogHost } from './ConfirmDialog'
