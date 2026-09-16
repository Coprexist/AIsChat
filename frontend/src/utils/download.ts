/**
 * 本地落盘（唯一入口）
 *
 * 分两层，别混：
 * - **前端自己生成的内容**（导出成 md/json 字符串、本地备份 blob）→ 这里的 saveText / saveBlob
 * - **从后端取文件**（带鉴权、解析 Content-Disposition）→ `api.download()`（内部也用 saveBlob）
 *
 * 为什么要有它：原来 9 处各写一遍 createObjectURL + <a>.click()，
 * 连"要不要先 appendChild 再点"都各写各的——游离节点在部分浏览器上不触发下载（2026-09-16 收敛）。
 */

/** 把已有 Blob 落盘 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)      // 别省：游离节点在部分浏览器上不触发下载
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 把一段文本落盘（md/json/csv 这类本地导出的常用形态） */
export function saveText(text: string, filename: string, mime = 'text/plain;charset=utf-8'): void {
  saveBlob(new Blob([text], { type: mime }), filename)
}
