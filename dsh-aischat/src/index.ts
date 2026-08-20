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

/** Stable Cordis plugin name. */
export const name = 'dsh-aischat'

/** The proxy needs the HTTP carrier; nothing else. */
export const inject = ['webServer']

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
      },
    },
    (upRes) => {
      res.writeHead(upRes.statusCode ?? 502, upRes.statusMessage ?? '', stripHopByHop(upRes.headers))
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

  ctx.webServer.registerUpgrade({
    path: WS_PATH,
    handler: (req, socket, head) => {
      proxyWs(backendUrl, req, socket, head)
    },
  })

  ctx.logger?.info?.(`dsh-aischat: proxying /aischat-api and /aischat-ws -> ${backendUrl}`)
}
