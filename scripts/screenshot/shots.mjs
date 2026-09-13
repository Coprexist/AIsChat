/**
 * 截图清单 —— 顺序即 README / 文档里的阅读顺序。
 *
 * 每条：
 *   name     输出文件名（不含扩展名）
 *   path     站内路由
 *   settle   等页面稳定（毫秒）
 *   prepare  截图前的页面操作（点击文件树、滚到底、隐藏调试信息）
 */

export const VIEWPORT = { width: 1440, height: 900 }

/** 点击文件树/列表里文本完全匹配的叶子节点 */
const clickText = (text) => '(() => {' +
  'const hits = [...document.querySelectorAll("button, li, a, span, div")]' +
  '.filter(e => e.textContent.trim() === ' + JSON.stringify(text) + ');' +
  'const el = hits[hits.length - 1];' +
  'if (!el) return false;' +
  '(el.closest("button") || el).click(); return true })()'

/** 把所有可滚动容器拉到底（聊天记录默认停在最新一条） */
const scrollBottom = '(() => {' +
  'const els = [...document.querySelectorAll("*")].filter(e => e.scrollHeight > e.clientHeight + 40);' +
  'els.forEach(e => { e.scrollTop = e.scrollHeight }); return els.length })()'

/** 世界页面会带上内部调试标记，截图里不出现 */
const hideWorldDebug = '(() => {' +
  'const kill = (doc) => { doc.querySelectorAll("*").forEach(el => {' +
  'if (el.children.length === 0 && /^WORLD_ID/.test((el.textContent || "").trim())) el.style.visibility = "hidden" }) };' +
  'kill(document); document.querySelectorAll("iframe").forEach(f => { try { kill(f.contentDocument) } catch (e) {} });' +
  'return true })()'

export const SHOTS = [
  { name: 'chat', path: '/chat/gm/1', settle: 4500, prepare: [clickText('在此标准界面打开'), scrollBottom] },
  { name: 'worlds', path: '/worlds', settle: 4500 },
  { name: 'design', path: '/worlds/34/design', settle: 6000, prepare: [clickText('main.py'), scrollBottom] },
  { name: 'world', path: '/world-view/34', settle: 6500, prepare: hideWorldDebug, format: 'jpeg', quality: 86 },
  { name: 'market', path: '/market', settle: 5000 },
  { name: 'agents', path: '/agents', settle: 4500 },
  { name: 'study', path: '/study', settle: 4000 },
  { name: 'me', path: '/me', settle: 4500 },
];
