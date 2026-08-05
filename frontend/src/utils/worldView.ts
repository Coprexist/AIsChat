/**
 * 世界沉浸视图打开助手 — 统一「独立窗口 vs 应用内跳转」策略
 *
 * 背景：沉浸界面优先独立窗口（按世界复用），但 Android WebView / 应用壳（如"一个木函"网页转应用）
 * 不支持 window.open（或返回假的 WindowProxy，点开无反应）→ 必须回退应用内跳转。
 * Tauri 桌面端走 WebviewWindow（在调用方处理，不在此处）。
 */

/** 是否运行在 WebView / 应用壳里（不支持 window.open 的环境） */
export function isWebView(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent.toLowerCase()
  // Android WebView 经典标记 "; wv)"；另有 wv / webview / 应用壳常见标识
  return /; wv\)/.test(ua) || /(^|[^a-z])wv([^a-z]|$)/.test(ua) || ua.includes('webview')
}

/**
 * 尝试独立窗口打开世界沉浸视图。
 * @returns true=已开窗；false=被拦截/环境不支持 → 调用方应改用应用内跳转
 */
export function tryOpenWorldWindow(wid: number, groupId?: number | null): boolean {
  if (isWebView()) return false
  const url = `/world-view/${wid}${groupId ? `?group_id=${groupId}` : ''}`
  const win = window.open(url, `world-immersive-${wid}`)
  return !!win
}

/** 打开世界沉浸视图：独立窗口优先，失败/WebView 回退应用内跳转 */
export function openWorldView(wid: number, groupId?: number | null): void {
  const url = `/world-view/${wid}${groupId ? `?group_id=${groupId}` : ''}`
  if (!tryOpenWorldWindow(wid, groupId)) {
    window.location.href = url
  }
}
