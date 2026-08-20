// SPDX-License-Identifier: MIT
/**
 * dsh-aischat — browser half.
 *
 * AIsChat as a first-class sidebar board, like the Workspace board:
 *
 * - `sidebar.footer.action` `aischat-entry`: toggles the AIsChat board.
 * - `shell.overlay` `aischat-board`: while the board is open it covers the
 *   whole frame and renders its own left rail (联系人板块: 置顶/私信/群聊,
 *   expanded like workspace folders) beside the conversation column (messages
 *   + composer). Opening the board hides the Workspace board; closing it
 *   restores DSH. No DSH session or composer semantics are touched — the
 *   composer inside the board sends to the selected AIsChat conversation.
 * - `settings.section` `aischat`: settings page (login / sign-out / note).
 *
 * All traffic is same-origin: HTTP `/aischat-api/*`, WS
 * `/aischat-ws?token=...`, both proxied by the host half to the local AIsChat
 * backend. The token lives in browser localStorage only.
 *
 * @module dsh-aischat/client
 */
const React = require('react')
const { useEffect, useState, useRef, useCallback, useMemo } = React
// Reuse the shipped DSH Markdown renderer (GFM + KaTeX math + safe-HTML
// filtering) so AIsChat messages render exactly like conversation text.
// 我方与对方消息都用 MarkdownText（完整 GFM/LaTeX，我方保留 DSH 用户
// 气泡样式）——任何针对 DSH 对话渲染风格的主题/插件改动都会自动作用到
// AIsChat。
const { MarkdownText } = require('@deepseek-ai/dsh-client-ui-primitives')

/** Plugin identity. */
const PLUGIN_ID = 'dsh-aischat'

/** Same-origin API base answered by the host half. */
const API = '/aischat-api'
/** WebSocket endpoint answered by the host half (upgrade proxy). */
const WS_BASE = '/aischat-ws'

/** Browser-local storage keys (guarded read/write). */
const K_TOKEN = 'aisc.token'
const K_USER = 'aisc.user'

/** Module-level store: survives view re-mounts within one page lifetime. */
const store = {
  token: guardedGet(K_TOKEN),
  user: parseUser(guardedGet(K_USER)),
  contacts: null,
  contactsLoadedAt: 0,
  nameCache: {}, // sender_id -> display name
  active: null,  // { kind: 'group'|'dm', id: number|string, title: string }
  messages: null,
  ws: null,
}

function guardedGet(key) {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}
function guardedSet(key, value) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* private mode: session-lifetime only */
  }
}
function parseUser(raw) {
  try {
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** Notify every mounted surface (settings page, board) to re-read state. */
function broadcast(what) {
  window.dispatchEvent(new CustomEvent('aischat:' + what))
}

/**
 * Same-origin JSON fetch through the host proxy. The Authorization header is
 * attached when a token exists; the proxy forwards it to the backend.
 */
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.json !== undefined) headers['Content-Type'] = 'application/json'
  if (store.token) headers['Authorization'] = `Bearer ${store.token}`
  const res = await fetch(`${API}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.json !== undefined ? JSON.stringify(options.json) : options.body,
    cache: 'no-store',
  })
  let data = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    // 已登录状态下收到 401：token 失效/被拒 → 自动登出回到登录页，而不是
    // 让调用方把失败静默吞成"暂无联系人"之类的假空态。登录接口自身的 401
    // 是凭据错误，由 LoginForm 展示，不触发登出。
    if (res.status === 401 && store.token && !path.startsWith('/auth/login')) {
      doLogout()
    }
    const detail = data && (data.detail || data.message)
    const err = new Error(typeof detail === 'string' ? detail : `request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

/** Load contacts once per page (cached; refresh() re-fetches). */
async function loadContacts(force = false) {
  if (!store.token) return
  if (!force && store.contacts && Date.now() - store.contactsLoadedAt < 30_000) return store.contacts
  const [groups, dms] = await Promise.all([
    api('/groups').catch(() => []),
    api('/dm/sessions').catch(() => []),
  ])
  store.contacts = { groups: Array.isArray(groups) ? groups : [], dms: Array.isArray(dms) ? dms : [] }
  store.contactsLoadedAt = Date.now()
  return store.contacts
}

/** Load message history for the active conversation (newest 50). */
async function loadMessages(active) {
  if (!active) return []
  let list = []
  if (active.kind === 'group') {
    const data = await api(`/chat/messages?group_id=${encodeURIComponent(active.id)}&limit=50&offset=0`)
    list = (data && data.messages) || []
  } else {
    // DM 专用接口：带认证的游标分页（/chat/messages 的 dm 分支会把
    // user_id 硬编码为 0，永远无权访问，不能用于私信）
    list = await api(`/dm/${encodeURIComponent(active.id)}/messages?limit=50`)
  }
  store.messages = list
  warmNameCache(list)
  return list
}

/**
 * Resolve display names for senders appearing in a message list. REST history
 * carries sender_name: null (the DB has no such column), so names are looked
 * up once per sender via /chat/user/{id} and cached. AI senders fall back to
 * their agent name when resolvable, else a neutral label.
 */
async function warmNameCache(messages) {
  if (!store.token || !Array.isArray(messages)) return
  const ids = new Set()
  for (const m of messages) {
    if (m && m.sender_id != null && store.nameCache[m.sender_id] === undefined) ids.add(m.sender_id)
  }
  for (const id of ids) {
    if (!store.token) break
    try {
      const u = await api(`/chat/user/${encodeURIComponent(id)}`)
      store.nameCache[id] = (u && (u.username || u.name)) || `用户${id}`
    } catch {
      store.nameCache[id] = `用户${id}`
    }
  }
}

/** Display name for a message sender. */
function senderName(m, user) {
  if (m == null) return ''
  if (m.sender_id != null && String(m.sender_type) !== 'ai' && String(m.sender_id) === String(user ? user.id : '')) return '我'
  if (m.sender_name) return m.sender_name
  if (m.sender_id != null && store.nameCache[m.sender_id]) return store.nameCache[m.sender_id]
  if (String(m.sender_type) === 'ai') return 'AI'
  return '用户' + (m.sender_id != null ? m.sender_id : '')
}

/** Build the WS URL for this origin (same-origin upgrade proxy). */
function wsUrl(token) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}${WS_BASE}?token=${encodeURIComponent(token)}`
}

/**
 * Rewrite an AIsChat media URL for the DSH same-origin proxy.
 * AIsChat stores relative paths like `/api/fs/download-avatar/x.png` that its
 * own frontend serves through a vite proxy stripping the `/api` prefix. In
 * DSH the host half strips `/aischat-api`, so `/api/...` maps 1:1 to
 * `/aischat-api/...`. Absolute URLs (external avatars) pass through untouched.
 */
function mediaUrl(url) {
  if (!url || typeof url !== 'string') return url
  if (url.startsWith('/api/')) return url.replace(/^\/api\//, API + '/')
  // 后端其他相对路径（如 /fs/download/{id}）走同源代理前缀
  if (url.startsWith('/') && !url.startsWith(API + '/')) return API + url
  return url
}

/** Avatar URL with thumbnail hint for the backend's `?thumb=1` support. */
function avatarUrl(url) {
  const rewritten = mediaUrl(url)
  if (!rewritten) return rewritten
  if (rewritten.includes('/download-avatar/') && !/\.gif($|\?)/i.test(rewritten) && !rewritten.includes('thumb=')) {
    return rewritten + (rewritten.includes('?') ? '&thumb=1' : '?thumb=1')
  }
  return rewritten
}

/**
 * 消息附件图片：后端 /fs/download/{file_id} 需要认证，`<img>` 标签无法带
 * Authorization，所以用带 token 的 fetch 拉取 blob → objectURL 再展示。
 * objectURL 按 file_id 缓存（跨消息列表重渲染复用），卸载/不再使用时 revoke。
 */
const attachmentBlobCache = new Map() // fileId -> objectURL

function AttachmentImage({ fileId, name, style: imgStyle }) {
  const [src, setSrc] = useState(() => attachmentBlobCache.get(String(fileId)) || null)
  useEffect(() => {
    const key = String(fileId)
    if (attachmentBlobCache.has(key)) {
      setSrc(attachmentBlobCache.get(key))
      return
    }
    let url = null
    let cancelled = false
    ;(async () => {
      try {
        const headers = {}
        if (store.token) headers['Authorization'] = `Bearer ${store.token}`
        const res = await fetch(`${API}/fs/download/${encodeURIComponent(fileId)}`, { headers, cache: 'no-store' })
        if (!res.ok || cancelled) return
        const blob = await res.blob()
        url = URL.createObjectURL(blob)
        attachmentBlobCache.set(key, url)
        if (!cancelled) setSrc(url)
      } catch {
        /* 加载失败保持占位 */
      }
    })()
    return () => {
      cancelled = true
      /* 缓存里的 objectURL 由后续组件复用，不在此 revoke */
    }
  }, [fileId])
  return src
    ? h('img', { src, alt: name || '', style: imgStyle })
    : h('div', { style: { ...imgStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--dsw-alias-label-tertiary)', fontSize: 12, background: 'var(--dsw-alias-interactive-bg-hover)' } }, '…')
}

/**
 * Prepare message text for the shipped Markdown renderer: it only displays
 * absolute HTTP(S) images and disables relative links, while AIsChat stores
 * media as relative `/api/...` paths. Rewrite markdown link/image targets to
 * absolute same-origin URLs (through the host proxy) so they render.
 */
function mdText(content) {
  const raw = String(content || '')
  return raw.replace(/(!?\[[^\]]*\]\()([^)\s]*)(\))/g, (_all, pre, url, post) => {
    if (!url || /^[a-z]+:/i.test(url) || url.startsWith('//') || url.startsWith('#') || url.startsWith('data:')) {
      return _all
    }
    const rewritten = mediaUrl(url)
    const absolute = rewritten.startsWith('/') ? window.location.origin + rewritten : rewritten
    return pre + absolute + post
  })
}

/** Open the WS, subscribe to the active conversation, wire message handling. */
function connectWs() {
  if (!store.token) return
  closeWs()
  let ws
  try {
    ws = new WebSocket(wsUrl(store.token))
  } catch {
    return
  }
  store.ws = ws
  ws.onopen = () => {
    subscribeActive()
  }
  ws.onmessage = (event) => {
    let msg
    try {
      msg = JSON.parse(event.data)
    } catch {
      return
    }
    if (!msg || typeof msg !== 'object') return
    if (msg.type === 'ping') {
      try { ws.send(JSON.stringify({ type: 'pong' })) } catch { /* noop */ }
      return
    }
    if (msg.type === 'error') {
      broadcast('error:' + (msg.message || msg.code || 'unknown'))
      return
    }
    if (msg.type !== 'message' && msg.type !== 'ai_response') return
    const data = msg.data
    if (!data) return
    // Only append when the pushed message belongs to the active conversation.
    const active = store.active
    if (!active) return
    // Prefer the outer conversation_type; fall back to the id key present.
    const ctype = msg.conversation_type || (data.session_id !== undefined ? 'dm' : 'group')
    const matches = active.kind === 'group'
      ? (ctype === 'group' || String(data.group_id) === String(active.id))
      : (ctype === 'dm' || String(data.session_id || data.dm_session_id) === String(active.id))
    if (!matches) return
    const list = store.messages || []
    if (!list.some((m) => m && m.id === data.id)) {
      list.push(data)
      store.messages = list
      warmNameCache([data])
      broadcast('message')
    }
  }
  ws.onclose = () => {
    if (store.ws === ws) {
      store.ws = null
      // Reconnect with backoff when token still present (clean 4001 auth close: no).
      if (store.token) setTimeout(() => { if (store.token && !store.ws) connectWs() }, 3000)
    }
  }
  ws.onerror = () => { /* onclose handles it */ }
}

function closeWs() {
  if (store.ws) {
    try { store.ws.close(1000) } catch { /* noop */ }
    store.ws = null
  }
}

function subscribeActive() {
  const ws = store.ws
  const active = store.active
  if (!ws || ws.readyState !== WebSocket.OPEN || !active) return
  const payload = { type: 'subscribe' }
  if (active.kind === 'group') payload.group_id = active.id
  else payload.session_id = active.id
  ws.send(JSON.stringify(payload))
}

/** Send a message: WS when open, HTTP fallback. */
async function sendMessage(content) {
  const active = store.active
  if (!active || !content) return
  if (store.ws && store.ws.readyState === WebSocket.OPEN) {
    const payload = { type: 'send', content }
    if (active.kind === 'group') payload.group_id = active.id
    else payload.session_id = active.id
    store.ws.send(JSON.stringify(payload))
    return
  }
  const query = active.kind === 'group'
    ? `group_id=${encodeURIComponent(active.id)}`
    : null
  const params = new URLSearchParams({
    sender_type: 'user',
    sender_id: String(store.user ? store.user.id : ''),
    content,
  })
  if (query) {
    await api(`/chat/message?${query}&${params.toString()}`, { method: 'POST' })
  } else {
    // DM 专用接口（/chat/message 的签名没有 dm_session_id 参数，会 500）
    await api(`/dm/${encodeURIComponent(active.id)}/messages`, {
      method: 'POST',
      json: { content },
    })
  }
}

async function doLogin(loginId, password) {
  const data = await api('/auth/login', {
    method: 'POST',
    json: { login_id: loginId, password, method: 'direct' },
  })
  store.token = data.access_token
  store.user = { id: data.user_id, name: data.username, role: data.role }
  guardedSet(K_TOKEN, store.token)
  guardedSet(K_USER, JSON.stringify(store.user))
  store.contacts = null
  store.nameCache = {}
  connectWs()
  broadcast('auth')
}

function doLogout() {
  closeWs()
  store.token = null
  store.user = null
  store.contacts = null
  store.active = null
  store.messages = null
  store.nameCache = {}
  guardedSet(K_TOKEN, '')
  guardedSet(K_USER, '')
  broadcast('auth')
}

// ── tiny React helpers (no JSX in this bundle) ────────────────────────────

function h(type, props, ...children) {
  return React.createElement(type, props, ...children)
}

const style = {
  board: { position: 'fixed', inset: 0, zIndex: 30, display: 'flex', background: 'var(--dsw-alias-bg-base)', fontFamily: 'var(--ds-font-family, system-ui, sans-serif)', color: 'var(--dsw-alias-label-primary)' },
  rail: { width: 264, flex: 'none', borderRight: '1px solid var(--dsw-alias-border-l2)', display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--dsw-specific-sidebar-fill)', padding: '8px 0' },
  railHead: { padding: '10px 14px 8px', fontSize: 15, fontWeight: 600, color: 'var(--dsw-alias-label-primary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  railUser: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderTop: '1px solid var(--dsw-alias-border-l2)' },
  group: { padding: '2px 0' },
  groupLabel: { padding: '6px 14px 4px', fontSize: 12, color: 'var(--dsw-alias-label-secondary)', fontWeight: 600, letterSpacing: '.02em' },
  row: { display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', cursor: 'pointer', fontSize: 13, color: 'var(--dsw-alias-label-primary)', border: 'none', background: 'transparent', width: '100%', textAlign: 'left', boxSizing: 'border-box' },
  rowHover: { background: 'var(--dsw-alias-interactive-bg-hover)' },
  rowActive: { background: 'var(--dsw-alias-interactive-bg-hover-solid, var(--dsw-alias-interactive-bg-hover))' },
  avatar: { width: 28, height: 28, borderRadius: '50%', flex: 'none', background: 'var(--dsw-alias-state-business-tertiary)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, color: 'var(--dsw-alias-label-primary)', overflow: 'hidden' },
  rowText: { minWidth: 0, flex: 1 },
  rowTitle: { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  rowSub: { fontSize: 11, color: 'var(--dsw-alias-label-tertiary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  badge: { flex: 'none', minWidth: 16, height: 16, borderRadius: 8, background: 'var(--dsw-alias-state-danger-primary, #e5484d)', color: '#fff', fontSize: 10, lineHeight: '16px', textAlign: 'center', padding: '0 5px', boxSizing: 'border-box' },
  main: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 },
  mainHead: { padding: '12px 20px', borderBottom: '1px solid var(--dsw-alias-border-l2)', fontSize: 14, fontWeight: 600, color: 'var(--dsw-alias-label-primary)', flex: 'none', display: 'flex', alignItems: 'center', gap: 8 },
  msgs: { flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 },
  msgRow: { display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: 8, width: '100%' },
  msgMine: { justifyContent: 'flex-end' },
  msgOther: { justifyContent: 'flex-start' },
  msgCol: { display: 'flex', flexDirection: 'column', minWidth: 0, alignItems: 'flex-start' },
  msgColMine: { alignItems: 'flex-end' },
  // 我方消息：完全照搬 DSH 用户气泡（gdEzaW_bubble）——专用气泡 token +
  // label-primary 文字 + 22px 圆角 + 16/24 排版，随主题/风格插件联动。
  msgMineBubble: { background: 'var(--dsw-specific-bubble)', color: 'var(--dsw-alias-label-primary)', maxWidth: 'min(525px, 100%)', borderRadius: 22, padding: '10px 16px', fontSize: 16, lineHeight: '24px', wordBreak: 'break-word' },
  // 对方消息：DSH AI 消息同款——无气泡，MarkdownText 原生排版。
  msgOtherBubble: { color: 'var(--dsw-alias-label-primary)', maxWidth: 'min(720px, 100%)', fontSize: 15, lineHeight: '24px', wordBreak: 'break-word' },
  msgMeta: { fontSize: 11, color: 'var(--dsw-alias-label-tertiary)', marginBottom: 3, padding: '0 4px' },
  msgImages: { display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 6, maxWidth: 'min(525px, 100%)' },
  msgImage: { maxWidth: 240, maxHeight: 240, borderRadius: 12, objectFit: 'cover', cursor: 'zoom-in' },
  inviteCard: { display: 'flex', flexDirection: 'column', gap: 8, minWidth: 260, maxWidth: 320, borderRadius: 14, border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-layer-2)', padding: '12px 14px', color: 'var(--dsw-alias-label-primary)' },
  inviteHead: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 600 },
  inviteBody: { fontSize: 13, lineHeight: '20px', color: 'var(--dsw-alias-label-secondary)' },
  inviteActions: { display: 'flex', gap: 8, marginTop: 2 },
  inviteBtn: { flex: 1, height: 30, borderRadius: 8, border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  inviteAccept: { background: 'var(--dsw-alias-state-business-primary)', color: '#fff' },
  inviteReject: { background: 'var(--dsw-alias-interactive-bg-hover)', color: 'var(--dsw-alias-label-primary)' },
  inviteStatus: { fontSize: 12, color: 'var(--dsw-alias-label-tertiary)', paddingTop: 2 },
  composer: { flex: 'none', display: 'flex', gap: 8, padding: '12px 20px', borderTop: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-base)' },
  input: { flex: 1, minHeight: 38, borderRadius: 12, border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-specific-input-major, var(--dsw-alias-bg-base))', color: 'var(--dsw-alias-label-primary)', padding: '8px 14px', fontSize: 13, outline: 'none', fontFamily: 'inherit' },
  send: { flex: 'none', padding: '0 18px', height: 38, borderRadius: 12, border: 'none', background: 'var(--dsw-alias-state-business-primary)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  empty: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--dsw-alias-label-tertiary)', fontSize: 13 },
  login: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0 },
  loginCard: { width: 320, padding: '24px 24px 20px', borderRadius: 14, border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-base)', boxShadow: 'var(--dsw-shadow-lv2)' },
  loginTitle: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--dsw-alias-label-primary)' },
  field: { width: '100%', marginBottom: 10, padding: '8px 12px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-specific-input-major, var(--dsw-alias-bg-base))', color: 'var(--dsw-alias-label-primary)', fontSize: 13, boxSizing: 'border-box', outline: 'none', fontFamily: 'inherit' },
  btn: { width: '100%', padding: '8px 0', borderRadius: 8, border: 'none', background: 'var(--dsw-alias-state-business-primary)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  err: { color: 'var(--dsw-alias-state-error-primary)', fontSize: 12, margin: '6px 0 0' },
  hint: { color: 'var(--dsw-alias-label-tertiary)', fontSize: 12, marginTop: 10, lineHeight: 1.5 },
  footBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, border: 'none', background: 'transparent', color: 'var(--dsw-alias-label-primary)', cursor: 'pointer', fontSize: 13, width: '100%' },
  closeBtn: { flex: 'none', padding: '4px 10px', borderRadius: 8, border: '1px solid var(--dsw-alias-border-l2)', background: 'transparent', color: 'var(--dsw-alias-label-secondary)', cursor: 'pointer', fontSize: 12 },
  scroll: { flex: 1, minHeight: 0, overflowY: 'auto' },
}

function initials(name) {
  if (!name) return '?'
  const parts = String(name).trim().split(/\s+/)
  return (parts[0][0] || '?').toUpperCase()
}

/** Format `"2026-08-11 10:24:36.320007"` backend timestamps. */
function fmtTime(raw) {
  if (!raw) return ''
  const m = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  if (!m) return ''
  const [, , month, day, hh, mm] = m
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const datePart = `${m[1]}-${month}-${day}`
  const hm = `${hh}:${mm}`
  return datePart === today ? hm : `${month}-${day} ${hm}`
}

// ── components ────────────────────────────────────────────────────────────

function LoginForm() {
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const submit = async () => {
    setBusy(true)
    setErr(null)
    try {
      await doLogin(id, pw)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }
  return h('div', { style: style.login },
    h('div', { style: style.loginCard },
      h('div', { style: style.loginTitle }, 'AIsChat 登录'),
      h('input', { style: style.field, placeholder: '用户名 / 邮箱', value: id, onChange: (e) => setId(e.target.value), onKeyDown: (e) => { if (e.key === 'Enter') submit() } }),
      h('input', { style: style.field, placeholder: '密码', type: 'password', value: pw, onChange: (e) => setPw(e.target.value), onKeyDown: (e) => { if (e.key === 'Enter') submit() } }),
      h('button', { style: style.btn, onClick: submit, disabled: busy }, busy ? '登录中…' : '登录'),
      err ? h('div', { style: style.err }, err) : null,
      h('div', { style: style.hint }, '凭据仅保存在本机浏览器，通过本地同源代理访问 AIsChat 服务。'),
    ),
  )
}

function ContactRow({ contact, kind, active, onPick }) {
  const title = kind === 'group' ? contact.name : (contact.partner && contact.partner.name) || '私信'
  const sub = contact.last_message_preview || (contact.last_message_at ? '' : '')
  const unread = Number(contact.unread_count || 0)
  const avatarText = kind === 'group'
    ? initials(title)
    : initials(contact.partner && contact.partner.name)
  const avatarSrc = kind === 'group'
    ? avatarUrl(contact.avatar_url)
    : avatarUrl(contact.partner && contact.partner.avatar_url)
  const isActive = active && active.kind === kind && String(active.id) === String(kind === 'group' ? contact.id : contact.session_id)
  return h('button', {
    style: { ...style.row, ...(isActive ? style.rowActive : {}) },
    onMouseEnter: (e) => { if (!isActive) e.currentTarget.style.background = style.rowHover.background },
    onMouseLeave: (e) => { if (!isActive) e.currentTarget.style.background = 'transparent' },
    onClick: () => onPick(kind, kind === 'group' ? contact.id : contact.session_id, title),
  },
    avatarSrc
      ? h('img', { src: avatarSrc, style: { ...style.avatar, objectFit: 'cover' }, alt: '' })
      : h('span', { style: style.avatar }, avatarText),
    h('span', { style: style.rowText },
      h('div', { style: style.rowTitle }, title),
      sub ? h('div', { style: style.rowSub }, sub) : null,
    ),
    unread > 0 ? h('span', { style: style.badge }, unread > 99 ? '99+' : String(unread)) : null,
  )
}

/**
 * 提取消息中的图片附件（attachments 数组里 mime_type 为 image/* 的项）。
 * 下载走后端 /fs/download/{file_id}（通过同源代理），与 DSH 附件一致。
 */
function imageAttachments(m) {
  const atts = m && m.attachments
  if (!Array.isArray(atts)) return []
  return atts.filter((a) => a && (a.mime_type || '').startsWith('image/') && a.file_id != null)
}

/** 群聊邀请附件（message_type === 'group_invitation' 的卡片数据）。 */
function invitationAttachment(m) {
  if (!m || String(m.message_type) !== 'group_invitation') return null
  const atts = m.attachments
  if (!Array.isArray(atts)) return null
  return atts.find((a) => a && a.type === 'group_invitation') || null
}

/** 接受/拒绝群聊邀请（POST /group-invitations/{id}/accept|reject）。 */
async function respondInvitation(inv, accept) {
  if (!inv || !inv.invitation_id) return
  try {
    await api(`/group-invitations/${encodeURIComponent(inv.invitation_id)}/${accept ? 'accept' : 'reject'}`, { method: 'POST' })
    broadcast('message')
  } catch (e) {
    window.dispatchEvent(new CustomEvent('aischat:error:' + (e.message || '操作失败')))
  }
}

const INVITE_STATUS_LABEL = { pending: '待处理', accepted: '已接受', rejected: '已拒绝' }

/** 群聊邀请卡片（自定义样式：独立卡片 + 接受/拒绝按钮 + 状态）。 */
function InviteCard({ inv }) {
  const label = INVITE_STATUS_LABEL[inv.status] || inv.status || ''
  const pending = inv.status === 'pending'
  return h('div', { style: style.inviteCard },
    h('div', { style: style.inviteHead },
      h('span', { style: { fontSize: 16 } }, '📨'),
      h('span', {}, '群聊邀请'),
    ),
    h('div', { style: style.inviteBody },
      (inv.inviter_name || '有人') + ' 邀请你加入群聊「' + (inv.group_name || '未知群组') + '」',
    ),
    pending
      ? h('div', { style: style.inviteActions },
          h('button', { style: { ...style.inviteBtn, ...style.inviteAccept }, onClick: () => respondInvitation(inv, true) }, '接受'),
          h('button', { style: { ...style.inviteBtn, ...style.inviteReject }, onClick: () => respondInvitation(inv, false) }, '拒绝'),
        )
      : h('div', { style: style.inviteStatus }, label),
  )
}

function MsgList({ messages, user }) {
  if (!messages || messages.length === 0) {
    return h('div', { style: style.empty }, '暂无消息，发送第一条吧')
  }
  return h('div', { style: style.msgs },
    messages.map((m) => {
      const mine = String(m.sender_type) === 'user' || String(m.sender_type) === 'human'
        ? String(m.sender_id) === String(user ? user.id : '')
        : false
      const name = senderName(m, user)
      const avatarSrc = mine ? null : avatarUrl(m.sender_avatar_url)
      const images = imageAttachments(m)
      const inv = invitationAttachment(m)
      const hasText = String(m.content || '').trim() !== ''

      // 内容主体：邀请卡片 > 图片 > 文本
      let body = null
      if (inv) {
        body = h(InviteCard, { inv })
      } else {
        if (hasText) {
          body = h('div', { style: mine ? style.msgMineBubble : style.msgOtherBubble },
            h(MarkdownText, { text: mdText(m.content) }),
          )
        }
        if (images.length > 0) {
          const gallery = h('div', { style: style.msgImages },
            images.map((img) => h(AttachmentImage, {
              key: String(img.file_id),
              fileId: img.file_id,
              name: img.name || '',
              style: style.msgImage,
            })),
          )
          body = body
            ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 'min(525px, 100%)' } }, body, gallery)
            : gallery
        }
        if (!body) body = h('div', { style: mine ? style.msgMineBubble : style.msgOtherBubble }, '')
      }

      // 对方消息带头像；我方名称靠右对齐（msgCol alignItems flex-end）
      return h('div', { key: m.id, style: { ...style.msgRow, ...(mine ? style.msgMine : style.msgOther) } },
        !mine && avatarSrc ? h('img', { src: avatarSrc, style: { ...style.avatar, width: 26, height: 26 }, alt: '' }) : null,
        h('div', { style: { ...style.msgCol, ...(mine ? style.msgColMine : {}) } },
          h('div', { style: style.msgMeta }, name + (m.created_at ? ' · ' + fmtTime(m.created_at) : '')),
          body,
        ),
      )
    }),
  )
}

/** The conversation column: message list + composer (sends to AIsChat). */
function ConversationColumn({ refresh }) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const active = store.active
  const user = store.user
  const messages = store.messages

  const send = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    try {
      await sendMessage(text)
      setDraft('')
      if (!store.ws || store.ws.readyState !== WebSocket.OPEN) {
        await loadMessages(active).catch(() => {})
        refresh()
      }
    } catch (e) {
      window.dispatchEvent(new CustomEvent('aischat:error:' + (e.message || 'send failed')))
    } finally {
      setSending(false)
    }
  }

  if (!active) {
    return h('div', { style: style.main },
      h('div', { style: style.mainHead }, 'AIsChat'),
      h('div', { style: style.empty }, '从左侧选择一个对话'),
    )
  }

  return h('div', { style: style.main },
    h('div', { style: style.mainHead },
      h('span', { style: { fontWeight: 600 } }, active.title),
      h('span', { style: { fontSize: 12, color: 'var(--dsw-alias-label-tertiary)' } }, active.kind === 'group' ? '群聊' : '私信'),
    ),
    h(MsgList, { messages, user }),
    h('div', { style: style.composer },
      h('input', {
        style: style.input,
        placeholder: '输入消息，回车发送',
        value: draft,
        onChange: (e) => setDraft(e.target.value),
        onKeyDown: (e) => { if (e.key === 'Enter') send() },
      }),
      h('button', { style: style.send, onClick: send, disabled: sending }, sending ? '…' : '发送'),
    ),
  )
}

/** The AIsChat board: covers the whole frame like the Workspace board. */
function AisChatBoard({ onClose }) {
  const [, force] = useState(0)
  const refresh = useCallback(() => force((n) => n + 1), [])
  const user = store.user

  useEffect(() => {
    const onMsg = () => refresh()
    window.addEventListener('aischat:message', onMsg)
    window.addEventListener('aischat:auth', onMsg)
    window.addEventListener('aischat:error', (e) => { console.warn('[aischat]', e.detail) })
    return () => {
      window.removeEventListener('aischat:message', onMsg)
      window.removeEventListener('aischat:auth', onMsg)
    }
  }, [refresh])

  useEffect(() => {
    if (store.token) {
      loadContacts().then(() => refresh()).catch(() => {})
      connectWs()
    }
    return () => { /* WS stays alive across board closes */ }
  }, [refresh])

  const pick = async (kind, id, title) => {
    store.active = { kind, id, title }
    store.messages = null
    refresh()
    try {
      const list = await loadMessages(store.active)
      store.messages = list
      refresh()
    } catch { /* keep null; input still usable via WS */ }
    connectWs()
  }

  if (!user || !store.token) {
    return h('div', { style: style.board },
      h('div', { style: style.rail },
        h('div', { style: style.railHead },
          h('span', {}, 'AIsChat'),
          h('button', { style: style.closeBtn, onClick: onClose }, '返回工作区'),
        ),
      ),
      h(LoginForm, null),
    )
  }

  const contacts = store.contacts
  const pinnedGroups = (contacts && contacts.groups || []).filter((g) => g.is_pinned)
  const pinnedDms = (contacts && contacts.dms || []).filter((d) => d.is_pinned)
  const restGroups = (contacts && contacts.groups || []).filter((g) => !g.is_pinned)
  const restDms = (contacts && contacts.dms || []).filter((d) => !d.is_pinned)

  const section = (label, items, kind) => items.length
    ? h('div', { style: style.group },
        h('div', { style: style.groupLabel }, label),
        items.map((it) => h(ContactRow, { key: kind === 'group' ? String(it.id) : String(it.session_id), contact: it, kind, active: store.active, onPick: pick })))
    : null

  return h('div', { style: style.board },
    h('div', { style: style.rail },
      h('div', { style: style.railHead },
        h('span', {}, 'AIsChat'),
        h('button', { style: style.closeBtn, onClick: onClose }, '返回工作区'),
      ),
      h('div', { style: style.railUser },
        h('span', { style: style.avatar }, initials(user.name)),
        h('span', { style: { flex: 1, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, user.name),
        h('button', { style: { ...style.closeBtn, fontSize: 11 }, onClick: doLogout, title: '退出登录' }, '退出'),
      ),
      h('div', { style: style.scroll },
        section('置顶私信', pinnedDms, 'dm'),
        section('置顶群聊', pinnedGroups, 'group'),
        section('私信', restDms, 'dm'),
        section('群聊', restGroups, 'group'),
        (!pinnedDms.length && !pinnedGroups.length && !restDms.length && !restGroups.length)
          ? h('div', { style: { ...style.empty, padding: 24 } }, '暂无联系人')
          : null,
      ),
    ),
    h(ConversationColumn, { refresh }),
  )
}

function SettingsPage() {
  const [, force] = useState(0)
  const refresh = useCallback(() => force((n) => n + 1), [])
  const user = store.user

  useEffect(() => {
    window.addEventListener('aischat:auth', refresh)
    return () => window.removeEventListener('aischat:auth', refresh)
  }, [refresh])

  if (!user || !store.token) {
    return h('div', { style: { padding: 20, maxWidth: 420 } },
      h('div', { style: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--dsw-alias-label-primary)' } }, 'AIsChat'),
      h('div', { style: { ...style.hint, marginTop: 0 } }, '登录 AIsChat 后即可在侧边栏使用聊天。凭据仅保存在本机浏览器。'),
      h(LoginForm, null),
    )
  }

  return h('div', { style: { padding: 20, maxWidth: 420 } },
    h('div', { style: { fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--dsw-alias-label-primary)' } }, 'AIsChat'),
    h('div', { style: { ...style.row, padding: '8px 0' } },
      h('span', { style: style.avatar }, initials(user.name)),
      h('div', { style: style.rowText },
        h('div', { style: style.rowTitle }, user.name),
        h('div', { style: style.rowSub }, '已登录'),
      ),
    ),
    h('button', { style: { ...style.btn, background: 'var(--dsw-alias-state-danger-primary, #e5484d)', marginTop: 16 }, onClick: doLogout }, '退出登录'),
    h('div', { style: style.hint }, '服务通过本机同源代理访问，无公网地址参与。'),
  )
}

function FooterButton() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onRefresh = () => setOpen(boardOpenRef.current)
    window.addEventListener('aischat:board-refresh', onRefresh)
    return () => window.removeEventListener('aischat:board-refresh', onRefresh)
  }, [])
  const toggle = () => {
    const next = !open
    setOpen(next)
    window.dispatchEvent(new CustomEvent('aischat:board-toggle', { detail: next }))
  }
  return h('button', { style: { ...style.footBtn, ...(open ? { background: 'var(--dsw-alias-interactive-bg-hover-solid, var(--dsw-alias-interactive-bg-hover))' } : {}) }, onClick: toggle, title: 'AIsChat 聊天' },
    h('span', { style: { fontSize: 14 } }, '💬'),
    h('span', { style: { fontWeight: 500 } }, 'AIsChat'),
  )
}

/** Shared board-open flag readable by the footer button's state sync. */
const boardOpenRef = { current: false }

// ── plugin entry ──────────────────────────────────────────────────────────

module.exports = {
  name: 'dsh-aischat',
  inject: ['slots'],
  apply(ctx) {
    let boardOpen = false

    const bump = () => {
      boardOpenRef.current = boardOpen
      window.dispatchEvent(new CustomEvent('aischat:board-refresh'))
    }

    window.addEventListener('aischat:board-toggle', (e) => {
      boardOpen = !!e.detail
      bump()
    })

    // Surface transient errors as console warnings (no intrusive toasts).
    window.addEventListener('aischat:error', (e) => {
      console.warn('[aischat]', e.detail)
    })

    const disposers = []
    disposers.push(ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register(
      { name: 'sidebar.footer.action', id: 'aischat-entry', order: 10, label: 'AIsChat' },
      FooterButton,
    )))

    // The board: a frame-wide overlay rendered only while the AIsChat board is
    // open. Registered once; the entry component reads the open flag from the
    // module store and renders null when closed.
    const BoardEntry = () => {
      const [openState, setOpenState] = useState(false)
      const [, force] = useState(0)
      useEffect(() => {
        const onRefresh = () => {
          setOpenState(boardOpen)
          force((n) => n + 1)
        }
        window.addEventListener('aischat:board-refresh', onRefresh)
        return () => window.removeEventListener('aischat:board-refresh', onRefresh)
      }, [])
      if (!openState) return null
      return h(AisChatBoard, {
        onClose: () => {
          boardOpen = false
          bump()
        },
      })
    }
    disposers.push(ctx.slots.inject('shell.overlay', () => ctx.slots.register(
      { name: 'shell.overlay', id: 'aischat-board', order: 30 },
      BoardEntry,
    )))

    disposers.push(ctx.slots.inject('settings.section', () => ctx.slots.register(
      { name: 'settings.section', id: 'aischat', order: 40, label: 'AIsChat' },
      SettingsPage,
    )))

    // Reconnect on window focus if the WS dropped while hidden.
    window.addEventListener('focus', () => {
      if (store.token && !store.ws) connectWs()
    })

    return () => {
      for (const dispose of disposers.splice(0)) dispose()
      closeWs()
    }
  },
}
