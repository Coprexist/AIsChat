// SPDX-License-Identifier: MIT
/**
 * dsh-aischat — host half.
 *
 * Same-origin gateway for the local AIsChat backend. The browser half never
 * touches the backend address: every HTTP call goes to `/aischat-api/*` and
 * every WebSocket to `/aischat-ws?token=...`, both answered here and proxied
 * to the AIsChat FastAPI service (default http://127.0.0.1:5228, backend WS at
 * /ws). Authentication stays end-to-end: the browser's Authorization header
 * and WS token query are forwarded verbatim and never logged, stored, or
 * echoed back. No public address is ever referenced.
 *
 * Security posture:
 * - The proxy target defaults to the loopback interface and is set through
 *   plugin config, never through a client-supplied value.
 * - Hop-by-hop headers are stripped before forwarding; the browser cannot
 *   smuggle Connection/Transfer-Encoding directives to the backend.
 * - The WS upgrade forwards the client's Sec-WebSocket-Key and replies with
 *   the backend's own 101 handshake; no tokens cross this boundary in plain
 *   logs.
 */

import type { Context } from '@deepseek-ai/cordis'
import type { IncomingMessage, ServerResponse } from 'node:http'
import http from 'node:http'
import type { Duplex } from 'node:stream'
import z from '@deepseek-ai/schemastery'
import { createReadStream, existsSync, statSync, mkdirSync, readFileSync, writeFileSync, realpathSync } from 'node:fs'
import { join, normalize, extname, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import os from 'node:os'

/** Stable Cordis plugin name. */
export const name = 'dsh-aischat'

/** 代理、世界工作区同步与世界操作工具都需要这些服务。 */
export const inject = ['webServer', 'tools', 'systemPrompt']

/** Plugin config: only the local backend base URL. */
export type Config = {
  /** AIsChat backend base URL, e.g. http://127.0.0.1:5228 (loopback only). */
  backendUrl: string
}

export const Config: z<Config> = z.object({
  backendUrl: z.string().default('http://127.0.0.1:5228'),
})

/** Routes owned by this plugin. */
const HTTP_PREFIX = '/aischat-api'
const WS_PATH = '/aischat-ws'
/** 前端静态资源挂载前缀（iframe 嵌入沉浸式界面等页面）。 */
const UI_PREFIX = '/aischat-ui'

/** 静态资源根目录：插件包内 dist/（前端 BASE_URL=/aischat-ui/ 构建产物）。 */
const UI_ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'dist')

/** 静态文件 content-type 表（前端产物常用子集；缺省 application/octet-stream）。 */
const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
}

/**
 * 服务前端静态产物（`/aischat-ui/*`）。路径解析锚定在 dist 根内，杜绝
 * `..` 穿越；SPA 路由（无扩展名的路径）回退到 index.html。
 */
function serveStatic(req: IncomingMessage, res: ServerResponse): void {
  const raw = (req.url ?? '/').split('?')[0]
  const rel = raw === UI_PREFIX || raw === `${UI_PREFIX}/` ? '/index.html' : raw.slice(UI_PREFIX.length)
  const candidate = normalize(join(UI_ROOT, rel))
  if (!candidate.startsWith(UI_ROOT)) {
    res.writeHead(403)
    res.end('forbidden')
    return
  }

  let file = candidate
  if (!existsSync(file) || statSync(file).isDirectory()) {
    // SPA 回退：未知路径一律给 index.html（前端路由接管）
    file = join(UI_ROOT, 'index.html')
  }
  if (!existsSync(file)) {
    res.writeHead(404)
    res.end('not found')
    return
  }

  res.writeHead(200, {
    'content-type': MIME[extname(file).toLowerCase()] ?? 'application/octet-stream',
    'cache-control': extname(file) === '.html' ? 'no-cache' : 'public, max-age=31536000, immutable',
  })
  createReadStream(file).pipe(res)
}

/** Headers that must not be forwarded (RFC 7230 hop-by-hop). */
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
])

/**
 * Strip hop-by-hop headers so only end-to-end headers reach the backend.
 * @param headers - incoming headers object.
 * @returns a plain record safe to forward.
 */
function stripHopByHop(headers: IncomingMessage['headers']): Record<string, string | string[] | undefined> {
  const out: Record<string, string | string[] | undefined> = {}
  for (const [key, value] of Object.entries(headers)) {
    if (key === undefined || value === undefined) continue
    if (HOP_BY_HOP.has(key.toLowerCase())) continue
    out[key] = value
  }
  return out
}

/**
 * Proxy one HTTP request to the AIsChat backend. The request body is piped
 * through untouched; the backend response is streamed back with its status
 * and headers. Errors produce a fixed 502 without echoing internals.
 */
function proxyHttp(
  backendUrl: string,
  req: IncomingMessage,
  res: ServerResponse,
  targetPath: string,
): void {
  let target: URL
  try {
    target = new URL(targetPath, backendUrl.endsWith('/') ? backendUrl : `${backendUrl}/`)
  } catch (error) {
    res.writeHead(500, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'invalid proxy target' }))
    return
  }

  const upstream = http.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method: req.method ?? 'GET',
      headers: {
        ...stripHopByHop(req.headers),
        host: target.host,
        // 告知后端当前部署形态：世界代码注入 window.WORLD_API / WORLD_UI 用
        // （群聊面板、平台菜单等组件据此拼同源代理前缀，避免落到宿主 SPA fallback）。
        'x-aischat-api-prefix': '/aischat-api',
        'x-aischat-ui-prefix': '/aischat-ui',
      },
    },
    (upRes) => {
      const headers = stripHopByHop(upRes.headers)
      // 重定向重写：后端 3xx 的 Location 是站内绝对路径（如 /world/1/files/...），
      // 浏览器按原样跟随会打到宿主自身的 SPA fallback。统一补上 /aischat-api
      // 前缀，让重定向继续走本代理。
      const status = upRes.statusCode ?? 502
      if (status >= 300 && status < 400 && headers.location !== undefined) {
        const loc = Array.isArray(headers.location) ? String(headers.location[0]) : String(headers.location)
        if (loc.startsWith('/') && !loc.startsWith('/aischat-api')) {
          headers.location = `/aischat-api${loc}`
        }
      }
      res.writeHead(status, upRes.statusMessage ?? '', headers)
      upRes.pipe(res)
    },
  )

  upstream.on('error', () => {
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: 'backend unreachable' }))
    } else {
      res.destroy()
    }
  })

  req.pipe(upstream)
}

/**
 * Proxy one WebSocket upgrade to the AIsChat backend. The browser's upgrade
 * request (with its Sec-WebSocket-Key and token query) is replayed against
 * the backend; on the backend's 101 the response headers are written back to
 * the browser socket and both directions are piped until either side closes.
 */
function proxyWs(
  backendUrl: string,
  req: IncomingMessage,
  socket: Duplex,
  head: Buffer,
): void {
  let target: URL
  try {
    target = new URL('/ws', backendUrl.endsWith('/') ? backendUrl : `${backendUrl}/`)
  } catch {
    socket.destroy()
    return
  }

  // Preserve the query string (carries ?token=... to the backend).
  const search = req.url?.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''
  const upstream = http.request({
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (target.protocol === 'https:' ? 443 : 80),
    path: `/ws${search}`,
    method: 'GET',
    headers: {
      ...stripHopByHop(req.headers),
      host: target.host,
      connection: 'Upgrade',
      upgrade: 'websocket',
    },
  })

  upstream.on('upgrade', (upRes, upSocket, upHead) => {
    // Replay the backend's 101 response line and headers to the browser.
    const statusLine = `HTTP/1.1 ${upRes.statusCode ?? 101} ${upRes.statusMessage ?? 'Switching Protocols'}\r\n`
    let headerText = statusLine
    for (const [key, value] of Object.entries(upRes.headers)) {
      if (value === undefined) continue
      headerText += `${key}: ${Array.isArray(value) ? value.join(', ') : value}\r\n`
    }
    headerText += '\r\n'
    socket.write(headerText)
    if (upHead.length > 0) socket.write(upHead)

    upSocket.pipe(socket)
    socket.pipe(upSocket)

    const close = (): void => {
      upSocket.destroy()
      socket.destroy()
    }
    upSocket.on('error', close)
    socket.on('error', close)
    upSocket.on('close', close)
    socket.on('close', close)
  })

  upstream.on('error', () => {
    socket.destroy()
  })

  upstream.on('response', () => {
    // Backend refused the upgrade (e.g. 401 without token): destroy.
    socket.destroy()
  })

  if (head.length > 0) upstream.write(head)
  upstream.end()
}

// ════════════════════════════════════════════════════════════════════════
// 世界工作区（AIC群视界 → DSH Workspace 文件夹 + 会话）
//
// 每个 AIsChat 世界对应 DSH 工作区里一个真实目录：
//   $DSH_HOME/aischat-worlds/AIC群视界-<世界名>/
//     .aischat-world.json  { worldId, name }   ← 世界身份（工具据此路由）
// client 同步流程：列世界 → 建目录 → workspaces.create({path}) →
// connectWorkspace() 得会话 → 上报 {sessionId, token}（token 仅存内存，
// 用于需要 owner 鉴权的写操作，不落盘、不打日志）。
// ════════════════════════════════════════════════════════════════════════

const WORLD_DIR_BASE = join(process.env.DSH_HOME ?? join(os.homedir(), '.dsh'), 'aischat-worlds')
const WORLDS_PREFIX = '/aischat-worlds'

/** sessionId -> { worldId, name }（client 同步时上报）。 */
const sessionWorldMap = new Map<string, { worldId: number; name: string }>()
/** sessionId -> AIsChat token（仅内存，供 owner 鉴权写操作；不落盘）。 */
const sessionTokenMap = new Map<string, string>()

/** 目录名清理：去掉文件系统非法字符，保留中文。 */
function sanitizeDirName(name: string): string {
  return String(name || '').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').trim() || '未命名世界'
}

/** 读取请求 JSON body（小体量，限制 256KB）。 */
function readJsonBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks: Buffer[] = []
    req.on('data', (c: Buffer) => {
      size += c.length
      if (size > 262144) { reject(new Error('body too large')); req.destroy(); return }
      chunks.push(c)
    })
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')) }
      catch { reject(new Error('invalid json')) }
    })
    req.on('error', reject)
  })
}

/** 向 AIsChat 后端发一个请求，返回状态与文本。 */
function backendRequest(
  backendUrl: string,
  method: string,
  path: string,
  opts: { token?: string; headers?: Record<string, string>; json?: unknown } = {},
): Promise<{ status: number; text: string }> {
  return new Promise((resolve, reject) => {
    let target: URL
    try { target = new URL(path, backendUrl.endsWith('/') ? backendUrl : `${backendUrl}/`) }
    catch { reject(new Error('invalid target')); return }
    const data = opts.json === undefined ? null : JSON.stringify(opts.json)
    const req = http.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method,
      headers: {
        'content-type': 'application/json',
        ...(opts.token ? { authorization: `Bearer ${opts.token}` } : {}),
        ...(opts.headers ?? {}),
        ...(data ? { 'content-length': String(Buffer.byteLength(data)) } : {}),
      },
    }, (res) => {
      let text = ''
      res.on('data', (c) => { text += c })
      res.on('end', () => resolve({ status: res.statusCode ?? 502, text }))
    })
    req.on('error', reject)
    if (data) req.write(data)
    req.end()
  })
}

/**
 * 取世界的沙箱 API token（world.config.api_token，经 owner 接口读取）。
 * 世界受控 API（/world/{id}/api/*）只认这个 token（X-World-Token 头）。
 * api_token 仅用于内部调用，绝不回传给模型。
 */
async function resolveWorldApiToken(backendUrl: string, worldId: number, ownerToken?: string): Promise<string | undefined> {
  if (!ownerToken) return undefined
  const res = await backendRequest(backendUrl, 'GET', `/worlds/${worldId}`, { token: ownerToken })
  if (res.status !== 200) return undefined
  try {
    const data = JSON.parse(res.text) as { config?: { api_token?: unknown } }
    const token = data.config?.api_token
    return typeof token === 'string' && token.length > 0 ? token : undefined
  } catch {
    return undefined
  }
}

/** 从工具执行上下文解析所属世界：会话 cwd 必须在 WORLD_DIR_BASE 内。 */
function resolveWorldFromCwd(cwd: string | undefined): { worldId: number; name: string } | null {
  if (!cwd) return null
  try {
    const real = realpathSync(cwd)
    const base = realpathSync(WORLD_DIR_BASE)
    if (real !== base && !real.startsWith(base + sep)) return null
    const metaPath = join(real, '.aischat-world.json')
    if (!existsSync(metaPath)) return null
    const meta = JSON.parse(readFileSync(metaPath, 'utf8')) as { worldId?: unknown; name?: unknown }
    const worldId = Number(meta.worldId)
    if (!Number.isInteger(worldId) || worldId <= 0) return null
    return { worldId, name: String(meta.name ?? `世界${worldId}`) }
  } catch {
    return null
  }
}

/** 工具输出：文本化任意 JSON 值。 */
function textOutput(value: unknown): Array<{ type: 'text'; text: string }> {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return [{ type: 'text', text }]
}

/** @param ctx - harness context exposing the webServer carrier. */
export function apply(ctx: Context, config: Config): void {
  const backendUrl = config.backendUrl.replace(/\/+$/, '')

  ctx.webServer.register({
    kind: 'prefix',
    path: HTTP_PREFIX,
    handler: (req, res) => {
      const targetPath = req.url ? req.url.slice(HTTP_PREFIX.length) : '/'
      proxyHttp(backendUrl, req, res, targetPath.startsWith('/') ? targetPath : `/${targetPath}`)
    },
  })

  ctx.webServer.register({
    kind: 'prefix',
    path: UI_PREFIX,
    handler: serveStatic,
  })

  ctx.webServer.registerUpgrade({
    path: WS_PATH,
    handler: (req, socket, head) => {
      proxyWs(backendUrl, req, socket, head)
    },
  })

  // ── 世界工作区同步端点 ──────────────────────────────────────────────
  ctx.webServer.register({
    kind: 'prefix',
    path: WORLDS_PREFIX,
    handler: (req, res) => {
      const route = (req.url ?? '/').split('?')[0]
      const send = (status: number, json: unknown): void => {
        res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
        res.end(JSON.stringify(json))
      }
      if (req.method === 'POST' && route === `${WORLDS_PREFIX}/dir`) {
        readJsonBody(req).then((body) => {
          const worldId = Number(body.worldId)
          const name = String(body.name ?? '')
          if (!Number.isInteger(worldId) || worldId <= 0) { send(400, { error: 'invalid worldId' }); return }
          const dirName = sanitizeDirName(`AIC群视界-${name || `世界${worldId}`}`)
          const dir = join(WORLD_DIR_BASE, dirName)
          try {
            mkdirSync(dir, { recursive: true })
            const metaPath = join(dir, '.aischat-world.json')
            if (!existsSync(metaPath)) {
              writeFileSync(metaPath, JSON.stringify({ worldId, name }, null, 2), 'utf8')
            } else {
              const prev = JSON.parse(readFileSync(metaPath, 'utf8')) as { worldId?: unknown }
              if (Number(prev.worldId) !== worldId) { send(409, { error: `目录已属于世界 ${prev.worldId}` }); return }
            }
            send(200, { path: dir })
          } catch (e) {
            send(500, { error: String((e as Error).message ?? e) })
          }
        }).catch(() => send(400, { error: 'bad request' }))
        return
      }
      if (req.method === 'POST' && route === `${WORLDS_PREFIX}/token`) {
        readJsonBody(req).then((body) => {
          const sessionId = String(body.sessionId ?? '')
          const token = String(body.token ?? '')
          if (!sessionId) { send(400, { error: 'missing sessionId' }); return }
          sessionTokenMap.set(sessionId, token)
          send(200, { ok: true })
        }).catch(() => send(400, { error: 'bad request' }))
        return
      }
      send(404, { error: 'not found' })
    },
  })

  // ── 世界操作工具（按会话所属世界路由） ─────────────────────────────
  const worldFromExec = (exec: { agent?: { session?: { header?: { cwd?: string }; id?: string } } }): { worldId: number; name: string; token?: string } | null => {
    const session = exec.agent?.session
    const world = resolveWorldFromCwd(session?.header?.cwd)
    if (!world) return null
    const token = session?.id ? sessionTokenMap.get(String(session.id)) : undefined
    return { ...world, token }
  }

  const registerWorldTool = (
    toolName: string,
    description: string,
    parameters: Record<string, unknown>,
    execute: (args: Record<string, unknown>, world: { worldId: number; name: string; token?: string }) => Promise<unknown>,
  ): void => {
    ctx.tools.register({
      name: toolName,
      description,
      parameters,
      output: { schema: { type: 'object' }, render: (_args, value) => textOutput(value) },
      execute: async (rawArgs, exec) => {
        const world = worldFromExec(exec as never)
        if (!world) {
          return { error: '当前会话不属于任何 AIsChat 世界：请先在工作区打开一个「AIC群视界-世界名」会话（该会话目录需含 .aischat-world.json）。' }
        }
        try {
          return await execute((rawArgs ?? {}) as Record<string, unknown>, world)
        } catch (e) {
          return { error: String((e as Error).message ?? e) }
        }
      },
    } as never)
  }

  registerWorldTool(
    'world_list_files',
    '列出当前 AIsChat 群视界世界的文件树（世界页面代码等）。返回文件列表（相对路径、大小、类型）。',
    { type: 'object', properties: { prefix: { type: 'string', description: '可选前缀过滤，如 css/ 或 blocks/' } }, additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: '该世界会话未连接登录态，无法列文件（需 owner 权限）。请重新打开 AIsChat 同步一次。' }
      const prefix = encodeURIComponent(String(args.prefix ?? ''))
      const res = await backendRequest(backendUrl, 'GET', `/worlds/${world.worldId}/files?prefix=${prefix}`, { token: world.token })
      if (res.status !== 200) return { error: `列文件失败 (${res.status})`, detail: res.text.slice(0, 400) }
      try { return JSON.parse(res.text || '{}') as unknown } catch { return { ok: true, content: res.text.slice(0, 4000) } }
    },
  )

  registerWorldTool(
    'world_read_file',
    '读取当前 AIsChat 群视界世界的一个文件内容（如 index.html、script.js、style.css）。',
    { type: 'object', properties: { path: { type: 'string', description: '相对路径，如 index.html 或 blocks/group-chat/chat-panel.js' } }, required: ['path'], additionalProperties: false },
    async (args, world) => {
      const path = String(args.path ?? '')
      if (!path) return { error: '缺少 path' }
      const res = await backendRequest(backendUrl, 'GET', `/world/${world.worldId}/files/${encodeURIComponent(path)}`)
      if (res.status !== 200) return { error: `读文件失败 (${res.status})` }
      return { ok: true, path, content: res.text.slice(0, 60000) }
    },
  )

  registerWorldTool(
    'world_write_file',
    '写入当前 AIsChat 群视界世界的一个文件（覆盖；自动建目录）。用于修改世界页面代码。',
    { type: 'object', properties: { path: { type: 'string', description: '相对路径，如 index.html' }, content: { type: 'string', description: '完整文件内容' } }, required: ['path', 'content'], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: '该世界会话未连接登录态，无法写文件（需 owner 权限）。' }
      const res = await backendRequest(backendUrl, 'PUT', `/worlds/${world.worldId}/files`, {
        token: world.token,
        json: { path: String(args.path ?? ''), content: String(args.content ?? '') },
      })
      if (res.status !== 200) return { error: `写文件失败 (${res.status})`, detail: res.text.slice(0, 400) }
      try { return { ok: true, ...(JSON.parse(res.text || '{}') as object) } } catch { return { ok: true } }
    },
  )

  registerWorldTool(
    'world_delete_file',
    '删除当前 AIsChat 群视界世界的一个文件。',
    { type: 'object', properties: { path: { type: 'string', description: '相对路径' } }, required: ['path'], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: '该世界会话未连接登录态，无法删文件。' }
      const path = encodeURIComponent(String(args.path ?? ''))
      const res = await backendRequest(backendUrl, 'DELETE', `/worlds/${world.worldId}/files?path=${path}`, { token: world.token })
      if (res.status !== 200) return { error: `删文件失败 (${res.status})`, detail: res.text.slice(0, 400) }
      return { ok: true }
    },
  )

  registerWorldTool(
    'world_api',
    '调用当前 AIsChat 群视界世界的受控 API（GET/POST /world/{id}/api/{endpoint}）。常用：world（世界信息）、chat（对话历史）、memories（记忆）、usage（用量）、groups（绑定群列表）、group/messages（群消息）、state（状态）、data/{key}（世界数据）。',
    { type: 'object', properties: { endpoint: { type: 'string', description: 'API 路径，如 world / chat / memories / usage / groups / group/messages / state / data/myk' }, method: { type: 'string', enum: ['GET', 'POST', 'PUT', 'DELETE'], default: 'GET' }, query: { type: 'object', description: '查询参数键值（字符串化）' }, body: { type: 'object', description: 'POST/PUT 请求体' } }, required: ['endpoint'], additionalProperties: false },
    async (args, world) => {
      const endpoint = String(args.endpoint ?? '').replace(/^\/+/, '')
      if (!endpoint) return { error: '缺少 endpoint' }
      const method = String(args.method ?? 'GET').toUpperCase()
      const qs = new URLSearchParams()
      for (const [k, v] of Object.entries((args.query ?? {}) as Record<string, unknown>)) {
        if (v !== undefined && v !== null) qs.set(k, String(v))
      }
      const q = qs.toString()
      // 世界受控 API 认沙箱 api_token（X-World-Token），不认用户 token。
      const apiToken = await resolveWorldApiToken(backendUrl, world.worldId, world.token)
      if (!apiToken) return { error: '无法取得该世界的 API token（需 owner 登录态且世界已初始化）。' }
      const res = await backendRequest(backendUrl, method, `/world/${world.worldId}/api/${endpoint}${q ? `?${q}` : ''}`, {
        headers: { 'x-world-token': apiToken },
        json: method === 'GET' ? undefined : (args.body ?? {}),
      })
      if (res.status >= 400) return { error: `API 调用失败 (${res.status})`, detail: res.text.slice(0, 400) }
      try { return JSON.parse(res.text) as unknown } catch { return { ok: true, content: res.text.slice(0, 60000) } }
    },
  )

  registerWorldTool(
    'world_chat',
    '读写当前 AIsChat 群视界世界绑定群聊的消息。action=read 拉最近消息（groupId 省略时自动取世界绑定的第一个群）；action=send 以世界身份发消息。',
    { type: 'object', properties: { action: { type: 'string', enum: ['read', 'send'] }, groupId: { type: 'number' }, content: { type: 'string', description: 'send 时的消息内容' }, limit: { type: 'number', default: 20 } }, required: ['action'], additionalProperties: false },
    async (args, world) => {
      const apiToken = await resolveWorldApiToken(backendUrl, world.worldId, world.token)
      if (!apiToken) return { error: '无法取得该世界的 API token（需 owner 登录态且世界已初始化）。' }
      const worldHeaders = { 'x-world-token': apiToken }
      const action = String(args.action ?? '')
      let groupId = Number(args.groupId)
      if (!groupId) {
        const g = await backendRequest(backendUrl, 'GET', `/world/${world.worldId}/api/groups`, { headers: worldHeaders })
        if (g.status === 200) {
          try {
            const groups = JSON.parse(g.text) as Array<{ id?: unknown }>
            groupId = Number(groups?.[0]?.id)
          } catch { /* ignore */ }
        }
      }
      if (!groupId) return { error: '该世界未绑定群聊，无法读写消息。' }
      if (action === 'read') {
        const limit = Number(args.limit ?? 20)
        const res = await backendRequest(backendUrl, 'GET', `/world/${world.worldId}/api/group/messages?group_id=${groupId}&limit=${limit}`, { headers: worldHeaders })
        if (res.status !== 200) return { error: `读消息失败 (${res.status})`, detail: res.text.slice(0, 300) }
        try { return JSON.parse(res.text) as unknown } catch { return { ok: true, content: res.text.slice(0, 60000) } }
      }
      if (action === 'send') {
        const content = String(args.content ?? '')
        if (!content) return { error: '缺少 content' }
        const res = await backendRequest(backendUrl, 'POST', `/world/${world.worldId}/api/group/messages`, {
          headers: worldHeaders,
          json: { group_id: groupId, content },
        })
        if (res.status >= 400) return { error: `发消息失败 (${res.status})`, detail: res.text.slice(0, 300) }
        return { ok: true, sent: content }
      }
      return { error: 'action 必须是 read 或 send' }
    },
  )

  registerWorldTool(
    'world_lifecycle',
    '唤醒或休眠当前 AIsChat 群视界世界（wake 应用离线时间补偿并启动常驻；sleep 休眠）。',
    { type: 'object', properties: { action: { type: 'string', enum: ['wake', 'sleep'] } }, required: ['action'], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: '该世界会话未连接登录态，无法控制世界生命周期。' }
      const action = String(args.action ?? '')
      if (action !== 'wake' && action !== 'sleep') return { error: 'action 必须是 wake 或 sleep' }
      const res = await backendRequest(backendUrl, 'POST', `/worlds/${world.worldId}/${action}`, { token: world.token })
      if (res.status >= 400) return { error: `${action} 失败 (${res.status})`, detail: res.text.slice(0, 400) }
      try { return JSON.parse(res.text) as unknown } catch { return { ok: true } }
    },
  )

  // ── 世界会话提示词（泛化引导，不依赖具体会话） ─────────────────────
  ctx.systemPrompt.section({
    name: 'aischat-world-context',
    order: 150,
    text: '如果你的会话工作目录位于 aischat-worlds 目录下（目录名以「AIC群视界-」开头），你正在操作一个 AIsChat 群视界世界：' +
      '该世界的页面代码、数据与群聊都属于它。可用 world_* 系列工具读写世界文件、调用世界 API、收发绑定群聊消息、唤醒/休眠世界。' +
      '世界是用户嵌入 DSH 的「可操作对象」——你的推理与工具仍走 DSH 体系，只是操作目标属于 AIsChat。',
  })

  ctx.logger?.info?.(`dsh-aischat: proxying /aischat-api and /aischat-ws -> ${backendUrl}; serving /aischat-ui; world sync at ${WORLDS_PREFIX}`)
}
