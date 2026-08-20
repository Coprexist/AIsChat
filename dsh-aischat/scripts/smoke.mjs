// Smoke test: mount the host half against a mock webServer carrier and verify
// HTTP proxying + WS upgrade proxying against a real local target.
import http from 'node:http'
import { createServer } from 'node:http'
import { createHash } from 'node:crypto'

const BACKEND_PORT = 59228
const GATEWAY_PORT = 59229

// Mock backend: HTTP /health + /echo, WS /ws echo server.
const backend = createServer((req, res) => {
  if (req.url.startsWith('/health')) {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ status: 'ok' }))
    return
  }
  res.writeHead(404)
  res.end()
})
// Minimal unmasked text frame writer for the mock WS server.
function serverFrame(text) {
  const payload = Buffer.from(text, 'utf8')
  const header = [0x81]
  if (payload.length < 126) header.push(payload.length)
  else if (payload.length < 65536) header.push(126, payload.length >> 8, payload.length & 0xff)
  else header.push(127, 0, 0, 0, 0, Math.floor(payload.length / 0x100000000), (payload.length >> 16) & 0xff, (payload.length >> 8) & 0xff, payload.length & 0xff)
  return Buffer.concat([Buffer.from(header), payload])
}
backend.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key']
  const accept = createHash('sha1')
    .update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64')
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n')
  socket.on('data', () => { socket.write(serverFrame('pong')) })
})
await new Promise((r) => backend.listen(BACKEND_PORT, '127.0.0.1', r))

// Mock webServer service: prefix + upgrade registries.
const registrations = { prefix: null, upgrade: null }
const webServer = {
  register(route) {
    if (route.kind === 'prefix') registrations.prefix = route
  },
  registerUpgrade(route) { registrations.upgrade = route },
}

// Import built host half and apply it.
const mod = await import('../lib/index.js')
mod.apply(
  {
    webServer,
    logger: { info: () => {} },
    effect: () => () => {},
  },
  { backendUrl: `http://127.0.0.1:${BACKEND_PORT}` },
)

// Gateway server: dispatch to registered handlers.
const gateway = createServer((req, res) => {
  const r = registrations.prefix
  if (r && req.url.startsWith(r.path)) {
    r.handler(req, res)
    return
  }
  res.writeHead(404)
  res.end()
})
gateway.on('upgrade', (req, socket, head) => {
  const r = registrations.upgrade
  if (r && req.url.startsWith(r.path)) r.handler(req, socket, head)
  else socket.destroy()
})
await new Promise((r) => gateway.listen(GATEWAY_PORT, '127.0.0.1', r))

// 1. HTTP proxy
const res = await fetch(`http://127.0.0.1:${GATEWAY_PORT}/aischat-api/health`)
const body = await res.json()
console.log('HTTP proxy /aischat-api/health ->', res.status, JSON.stringify(body))
if (res.status !== 200 || body.status !== 'ok') throw new Error('HTTP proxy failed')

// 2. WS upgrade proxy
const ws = new WebSocket(`ws://127.0.0.1:${GATEWAY_PORT}/aischat-ws?token=test`)
await new Promise((resolve, reject) => {
  ws.onopen = () => resolve()
  ws.onerror = () => reject(new Error('ws open failed'))
  setTimeout(() => reject(new Error('ws open timeout')), 3000)
})
console.log('WS open OK')
ws.send('hello')
const reply = await new Promise((resolve) => {
  ws.onmessage = (e) => resolve(String(e.data))
  setTimeout(() => resolve('timeout'), 3000)
})
console.log('WS reply ->', JSON.stringify(reply))
if (reply !== 'pong') throw new Error('WS proxy failed: ' + reply)
ws.close()

await new Promise((r) => setTimeout(r, 200))
gateway.close()
backend.close()
console.log('SMOKE OK')
process.exit(0)
