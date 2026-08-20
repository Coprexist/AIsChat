// src/index.ts
import http from "node:http";
import z from "@deepseek-ai/schemastery";
import { createReadStream, existsSync, statSync } from "node:fs";
import { join, normalize, extname } from "node:path";
import { fileURLToPath } from "node:url";
var name = "dsh-aischat";
var inject = ["webServer"];
var Config = z.object({
  backendUrl: z.string().default("http://127.0.0.1:5228")
});
var HTTP_PREFIX = "/aischat-api";
var WS_PATH = "/aischat-ws";
var UI_PREFIX = "/aischat-ui";
var UI_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "dist");
var MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8"
};
function serveStatic(req, res) {
  const raw = (req.url ?? "/").split("?")[0];
  const rel = raw === UI_PREFIX || raw === `${UI_PREFIX}/` ? "/index.html" : raw.slice(UI_PREFIX.length);
  const candidate = normalize(join(UI_ROOT, rel));
  if (!candidate.startsWith(UI_ROOT)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  let file = candidate;
  if (!existsSync(file) || statSync(file).isDirectory()) {
    file = join(UI_ROOT, "index.html");
  }
  if (!existsSync(file)) {
    res.writeHead(404);
    res.end("not found");
    return;
  }
  res.writeHead(200, {
    "content-type": MIME[extname(file).toLowerCase()] ?? "application/octet-stream",
    "cache-control": extname(file) === ".html" ? "no-cache" : "public, max-age=31536000, immutable"
  });
  createReadStream(file).pipe(res);
}
var HOP_BY_HOP = /* @__PURE__ */ new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade"
]);
function stripHopByHop(headers) {
  const out = {};
  for (const [key, value] of Object.entries(headers)) {
    if (key === void 0 || value === void 0) continue;
    if (HOP_BY_HOP.has(key.toLowerCase())) continue;
    out[key] = value;
  }
  return out;
}
function proxyHttp(backendUrl, req, res, targetPath) {
  let target;
  try {
    target = new URL(targetPath, backendUrl.endsWith("/") ? backendUrl : `${backendUrl}/`);
  } catch (error) {
    res.writeHead(500, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "invalid proxy target" }));
    return;
  }
  const upstream = http.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === "https:" ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method: req.method ?? "GET",
      headers: {
        ...stripHopByHop(req.headers),
        host: target.host
      }
    },
    (upRes) => {
      res.writeHead(upRes.statusCode ?? 502, upRes.statusMessage ?? "", stripHopByHop(upRes.headers));
      upRes.pipe(res);
    }
  );
  upstream.on("error", () => {
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "backend unreachable" }));
    } else {
      res.destroy();
    }
  });
  req.pipe(upstream);
}
function proxyWs(backendUrl, req, socket, head) {
  let target;
  try {
    target = new URL("/ws", backendUrl.endsWith("/") ? backendUrl : `${backendUrl}/`);
  } catch {
    socket.destroy();
    return;
  }
  const search = req.url?.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const upstream = http.request({
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (target.protocol === "https:" ? 443 : 80),
    path: `/ws${search}`,
    method: "GET",
    headers: {
      ...stripHopByHop(req.headers),
      host: target.host,
      connection: "Upgrade",
      upgrade: "websocket"
    }
  });
  upstream.on("upgrade", (upRes, upSocket, upHead) => {
    const statusLine = `HTTP/1.1 ${upRes.statusCode ?? 101} ${upRes.statusMessage ?? "Switching Protocols"}\r
`;
    let headerText = statusLine;
    for (const [key, value] of Object.entries(upRes.headers)) {
      if (value === void 0) continue;
      headerText += `${key}: ${Array.isArray(value) ? value.join(", ") : value}\r
`;
    }
    headerText += "\r\n";
    socket.write(headerText);
    if (upHead.length > 0) socket.write(upHead);
    upSocket.pipe(socket);
    socket.pipe(upSocket);
    const close = () => {
      upSocket.destroy();
      socket.destroy();
    };
    upSocket.on("error", close);
    socket.on("error", close);
    upSocket.on("close", close);
    socket.on("close", close);
  });
  upstream.on("error", () => {
    socket.destroy();
  });
  upstream.on("response", () => {
    socket.destroy();
  });
  if (head.length > 0) upstream.write(head);
  upstream.end();
}
function apply(ctx, config) {
  const backendUrl = config.backendUrl.replace(/\/+$/, "");
  ctx.webServer.register({
    kind: "prefix",
    path: HTTP_PREFIX,
    handler: (req, res) => {
      const targetPath = req.url ? req.url.slice(HTTP_PREFIX.length) : "/";
      proxyHttp(backendUrl, req, res, targetPath.startsWith("/") ? targetPath : `/${targetPath}`);
    }
  });
  ctx.webServer.register({
    kind: "prefix",
    path: UI_PREFIX,
    handler: serveStatic
  });
  ctx.webServer.registerUpgrade({
    path: WS_PATH,
    handler: (req, socket, head) => {
      proxyWs(backendUrl, req, socket, head);
    }
  });
  ctx.logger?.info?.(`dsh-aischat: proxying /aischat-api and /aischat-ws -> ${backendUrl}; serving /aischat-ui`);
}
export {
  Config,
  apply,
  inject,
  name
};
//# sourceMappingURL=index.js.map
