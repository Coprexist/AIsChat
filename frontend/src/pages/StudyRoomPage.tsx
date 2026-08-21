/**
 * 自习室 · 专注 — 独立静态应用（public/study-room/），全屏 iframe 嵌入。
 * 用 iframe 隔离自身样式，避免与主应用主题互相污染。
 */
export default function StudyRoomPage() {
  return (
    <div className="w-full h-full">
      <iframe
        src="/study-room/index.html"
        className="w-full h-full border-none"
        title="自习室 · 专注"
        allow="microphone; autoplay"
      />
    </div>
  )
}
