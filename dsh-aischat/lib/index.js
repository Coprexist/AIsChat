// src/index.ts
import http from "node:http";
import z from "@deepseek-ai/schemastery";
import { createReadStream, existsSync, statSync, mkdirSync, readFileSync, writeFileSync, realpathSync, readdirSync, unlinkSync } from "node:fs";
import { join, normalize, extname, sep } from "node:path";
import { fileURLToPath } from "node:url";
import os from "node:os";
var name = "dsh-aischat";
var inject = ["webServer", "tools", "systemPrompt"];
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
        host: target.host,
        // 告知后端当前部署形态：世界代码注入 window.WORLD_API / WORLD_UI 用
        // （群聊面板、平台菜单等组件据此拼同源代理前缀，避免落到宿主 SPA fallback）。
        "x-aischat-api-prefix": "/aischat-api",
        "x-aischat-ui-prefix": "/aischat-ui"
      }
    },
    (upRes) => {
      const headers = stripHopByHop(upRes.headers);
      const status = upRes.statusCode ?? 502;
      if (status >= 300 && status < 400 && headers.location !== void 0) {
        const loc = Array.isArray(headers.location) ? String(headers.location[0]) : String(headers.location);
        if (loc.startsWith("/") && !loc.startsWith("/aischat-api")) {
          headers.location = `/aischat-api${loc}`;
        }
      }
      res.writeHead(status, upRes.statusMessage ?? "", headers);
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
var WORLD_DIR_BASE = join(process.env.DSH_HOME ?? join(os.homedir(), ".dsh"), "aischat-worlds");
var WORLDS_PREFIX = "/aischat-worlds";
var worldTokenMap = /* @__PURE__ */ new Map();
var sessionTokenMap = /* @__PURE__ */ new Map();
function sanitizeDirName(name2) {
  return String(name2 || "").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").trim() || "\u672A\u547D\u540D\u4E16\u754C";
}
function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (c) => {
      size += c.length;
      if (size > 262144) {
        reject(new Error("body too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"));
      } catch {
        reject(new Error("invalid json"));
      }
    });
    req.on("error", reject);
  });
}
function backendRequest(backendUrl, method, path, opts = {}) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL(path, backendUrl.endsWith("/") ? backendUrl : `${backendUrl}/`);
    } catch {
      reject(new Error("invalid target"));
      return;
    }
    const data = opts.json === void 0 ? null : JSON.stringify(opts.json);
    const req = http.request({
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === "https:" ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method,
      headers: {
        "content-type": "application/json",
        ...opts.token ? { authorization: `Bearer ${opts.token}` } : {},
        ...opts.headers ?? {},
        ...data ? { "content-length": String(Buffer.byteLength(data)) } : {}
      }
    }, (res) => {
      let text = "";
      res.on("data", (c) => {
        text += c;
      });
      res.on("end", () => resolve({ status: res.statusCode ?? 502, text }));
    });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}
async function resolveWorldApiToken(backendUrl, worldId, ownerToken) {
  if (!ownerToken) return void 0;
  const res = await backendRequest(backendUrl, "GET", `/worlds/${worldId}`, { token: ownerToken });
  if (res.status !== 200) return void 0;
  try {
    const data = JSON.parse(res.text);
    const token = data.config?.api_token;
    return typeof token === "string" && token.length > 0 ? token : void 0;
  } catch {
    return void 0;
  }
}
function resolveWorldFromCwd(cwd) {
  if (!cwd) return null;
  try {
    const real = realpathSync(cwd);
    const base = realpathSync(WORLD_DIR_BASE);
    if (real !== base && !real.startsWith(base + sep)) return null;
    const metaPath = join(real, ".aischat-world.json");
    if (!existsSync(metaPath)) return null;
    const meta = JSON.parse(readFileSync(metaPath, "utf8"));
    const worldId = Number(meta.worldId);
    if (!Number.isInteger(worldId) || worldId <= 0) return null;
    return { worldId, name: String(meta.name ?? `\u4E16\u754C${worldId}`) };
  } catch {
    return null;
  }
}
function textOutput(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return [{ type: "text", text }];
}
function listWorldDirs() {
  const out = [];
  try {
    if (!existsSync(WORLD_DIR_BASE)) return out;
    for (const entry of readdirSync(WORLD_DIR_BASE, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const metaPath = join(WORLD_DIR_BASE, entry.name, ".aischat-world.json");
      let worldId = null;
      let name2 = "";
      try {
        const meta = JSON.parse(readFileSync(metaPath, "utf8"));
        worldId = Number(meta.worldId) || null;
        name2 = String(meta.name ?? "");
      } catch {
      }
      out.push({ dir: entry.name, worldId, name: name2 });
    }
  } catch {
  }
  return out;
}
function isMirrorExcluded(relPath) {
  const base = relPath.split("/").pop() ?? relPath;
  if (relPath === ".aischat-world.json") return true;
  if (base === "__pycache__" || relPath.includes("/__pycache__/")) return true;
  if (base.endsWith(".pyc")) return true;
  if (base === ".DS_Store") return true;
  return false;
}
function worldDirFor(worldId) {
  try {
    if (!existsSync(WORLD_DIR_BASE)) return null;
    for (const entry of readdirSync(WORLD_DIR_BASE, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const metaPath = join(WORLD_DIR_BASE, entry.name, ".aischat-world.json");
      try {
        const meta = JSON.parse(readFileSync(metaPath, "utf8"));
        if (Number(meta.worldId) === worldId) return join(WORLD_DIR_BASE, entry.name);
      } catch {
      }
    }
  } catch {
  }
  return null;
}
var SNAPSHOT_FILE = ".aischat-sync.json";
function readSnapshot(dir) {
  try {
    const parsed = JSON.parse(readFileSync(join(dir, SNAPSHOT_FILE), "utf8"));
    if (parsed && parsed.v === 1 && parsed.files && typeof parsed.files === "object") return parsed;
  } catch {
  }
  return { v: 1, files: {} };
}
function writeSnapshot(dir, snap) {
  try {
    writeFileSync(join(dir, SNAPSHOT_FILE), JSON.stringify(snap, null, 2), "utf8");
  } catch {
  }
}
function statMtime(p) {
  try {
    return statSync(p).mtimeMs;
  } catch {
    return 0;
  }
}
function compareMirror(remoteTree, dir, snap) {
  const remote = /* @__PURE__ */ new Map();
  for (const f of remoteTree) if (f.path && !isMirrorExcluded(f.path)) remote.set(f.path, f.mtime);
  const localFiles = walkDir(dir).filter((p) => !isMirrorExcluded(p));
  const local = /* @__PURE__ */ new Map();
  for (const p of localFiles) local.set(p, statMtime(join(dir, p)));
  const out = { added: [], removed: [], changedRemote: [], changedLocal: [], conflict: [] };
  const seen = /* @__PURE__ */ new Set();
  for (const [p, rm] of remote) {
    seen.add(p);
    const rec = snap.files[p];
    const localMtime = local.get(p) ?? 0;
    if (rec === void 0) {
      if (localMtime === 0) out.added.push(p);
      else out.changedLocal.push(p);
      continue;
    }
    const remoteChanged = rm !== rec.rm;
    const localChanged = localMtime !== rec.lm;
    if (remoteChanged && localChanged) out.conflict.push(p);
    else if (remoteChanged) out.changedRemote.push(p);
    else if (localChanged) out.changedLocal.push(p);
  }
  for (const p of local.keys()) {
    if (seen.has(p)) continue;
    if (snap.files[p] === void 0) out.changedLocal.push(p);
    else out.removed.push(p);
  }
  return out;
}
async function fetchRemoteTree(backendUrl, worldId, token) {
  if (!token) return null;
  const tree = await backendRequest(backendUrl, "GET", `/worlds/${worldId}/files?prefix=`, { token });
  if (tree.status !== 200) return null;
  try {
    const files = JSON.parse(tree.text || "{}").files ?? [];
    return files.map((f) => ({ path: String(f.path ?? ""), mtime: Number(f.mtime) || 0 }));
  } catch {
    return null;
  }
}
async function pullWithSnapshot(backendUrl, worldId, dir, token, force = false) {
  const snap = readSnapshot(dir);
  const tree = await fetchRemoteTree(backendUrl, worldId, token);
  if (!tree) return { ok: false, message: "\u65E0\u6CD5\u83B7\u53D6\u4E16\u754C\u6587\u4EF6\u6811\uFF08\u9700\u767B\u5F55\u6001\uFF09" };
  const cmp = compareMirror(tree, dir, snap);
  if (!force && (cmp.changedLocal.length > 0 || cmp.conflict.length > 0)) {
    return {
      ok: false,
      message: "\u672C\u5730\u6709\u672A\u63A8\u9001\u7684\u4FEE\u6539\u6216\u51B2\u7A81\uFF0C\u5DF2\u53D6\u6D88\u62C9\u53D6\uFF08\u4E0D\u4F1A\u8986\u76D6\u4F60\u7684\u6539\u52A8\uFF09",
      conflict: cmp.conflict
    };
  }
  const pullTargets = [...cmp.added, ...cmp.changedRemote];
  let pulled = 0;
  let skipped = 0;
  for (const rel of pullTargets) {
    try {
      const res = await backendRequest(backendUrl, "GET", `/world/${worldId}/files/${encodeURIComponent(rel)}`);
      if (res.status !== 200) {
        skipped++;
        continue;
      }
      const target = join(dir, rel);
      mkdirSync(join(target, ".."), { recursive: true });
      writeFileSync(target, res.text, "utf8");
      pulled++;
    } catch {
      skipped++;
    }
  }
  for (const rel of cmp.removed) {
    if (force || !cmp.changedLocal.includes(rel)) {
      try {
        unlinkSync(join(dir, rel));
        pulled++;
      } catch {
        skipped++;
      }
    }
  }
  const nextSnap = { v: 1, files: {} };
  const localFiles = walkDir(dir);
  for (const p of localFiles) {
    if (isMirrorExcluded(p)) continue;
    const rm = tree.find((t) => t.path === p)?.mtime ?? snap.files[p]?.rm ?? 0;
    nextSnap.files[p] = { lm: statMtime(join(dir, p)), rm };
  }
  for (const t of tree) {
    if (isMirrorExcluded(t.path) || nextSnap.files[t.path]) continue;
    nextSnap.files[t.path] = { lm: 0, rm: t.mtime };
  }
  writeSnapshot(dir, nextSnap);
  const parts = [];
  if (cmp.added.length) parts.push(`+${cmp.added.length} \u65B0\u589E`);
  if (cmp.changedRemote.length) parts.push(`~${cmp.changedRemote.length} \u4FEE\u6539`);
  if (cmp.removed.length) parts.push(`-${cmp.removed.length} \u5220\u9664`);
  return {
    ok: true,
    pulled,
    skipped,
    conflict: cmp.conflict,
    message: `\u5DF2\u62C9\u53D6\u4E16\u754C\u6700\u65B0\u6587\u4EF6${parts.length ? `\uFF1A${parts.join(" ")}` : "\uFF08\u65E0\u53D8\u5316\uFF09"}`
  };
}
async function pushWithSnapshot(backendUrl, worldId, dir, token, force = false) {
  if (!token) return { ok: false, message: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u63A8\u9001\uFF08\u9700 owner \u6743\u9650\uFF09" };
  const snap = readSnapshot(dir);
  const tree = await fetchRemoteTree(backendUrl, worldId, token);
  if (!tree) return { ok: false, message: "\u65E0\u6CD5\u83B7\u53D6\u4E16\u754C\u6587\u4EF6\u6811\uFF08\u9700\u767B\u5F55\u6001\uFF09" };
  const cmp = compareMirror(tree, dir, snap);
  const pushTargets = /* @__PURE__ */ new Set([...cmp.changedLocal, ...cmp.added]);
  let pushed = 0;
  let skipped = 0;
  const errors = [];
  const localFiles = walkDir(dir);
  for (const rel of localFiles) {
    if (!pushTargets.has(rel) || isMirrorExcluded(rel)) continue;
    if (cmp.conflict.includes(rel) && !force) {
      errors.push(`${rel}\uFF08\u51B2\u7A81\uFF0C\u8FDC\u7AEF\u4E5F\u6539\u8FC7\u2014\u2014\u8BF7\u5148\u88C1\u51B3\u6216\u7528 force \u8986\u76D6\uFF09`);
      continue;
    }
    try {
      const content = readFileSync(join(dir, rel), "utf8");
      const res = await backendRequest(backendUrl, "PUT", `/worlds/${worldId}/files`, { token, json: { path: rel, content } });
      if (res.status === 200) pushed++;
      else errors.push(`${rel} (${res.status})`);
    } catch {
      errors.push(`${rel}\uFF08\u8BFB\u5199\u5931\u8D25\uFF09`);
    }
  }
  for (const p of cmp.removed) {
    if (!force && cmp.conflict.includes(p)) continue;
    const res = await backendRequest(backendUrl, "DELETE", `/worlds/${worldId}/files?path=${encodeURIComponent(p)}`, { token });
    if (res.status === 200) pushed++;
    else errors.push(`${p} (\u5220\u9664 ${res.status})`);
  }
  const nextSnap = { v: 1, files: {} };
  for (const p of localFiles) {
    if (isMirrorExcluded(p)) continue;
    const rm = tree.find((t) => t.path === p)?.mtime ?? 0;
    nextSnap.files[p] = { lm: statMtime(join(dir, p)), rm };
  }
  writeSnapshot(dir, nextSnap);
  return {
    ok: true,
    pushed,
    skipped,
    conflict: cmp.conflict,
    message: `\u5DF2\u540C\u6B65\u5230\u4E16\u754C${pushed ? `\uFF08${pushed} \u4E2A\u6587\u4EF6\uFF09` : "\uFF08\u65E0\u53D8\u5316\uFF09"}`
  };
}
function walkDir(root) {
  const out = [];
  const visit = (dir) => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const full = join(dir, e.name);
      const rel = full.slice(root.length).replace(/^[/\\]/, "");
      if (e.isDirectory()) {
        if (e.name === "__pycache__") continue;
        visit(full);
      } else if (e.isFile() || e.isSymbolicLink()) {
        out.push(rel);
      }
    }
  };
  visit(root);
  return out;
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
  ctx.webServer.register({
    kind: "prefix",
    path: WORLDS_PREFIX,
    handler: (req, res) => {
      const route = (req.url ?? "/").split("?")[0];
      const send = (status, json) => {
        res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
        res.end(JSON.stringify(json));
      };
      if (req.method === "POST" && route === `${WORLDS_PREFIX}/dir`) {
        readJsonBody(req).then((body) => {
          const worldId = Number(body.worldId);
          const name2 = String(body.name ?? "");
          if (!Number.isInteger(worldId) || worldId <= 0) {
            send(400, { error: "invalid worldId" });
            return;
          }
          const dirName = sanitizeDirName(`AIC\u7FA4\u89C6\u754C-${name2 || `\u4E16\u754C${worldId}`}`);
          const dir = join(WORLD_DIR_BASE, dirName);
          try {
            mkdirSync(dir, { recursive: true });
            const metaPath = join(dir, ".aischat-world.json");
            if (!existsSync(metaPath)) {
              writeFileSync(metaPath, JSON.stringify({ worldId, name: name2 }, null, 2), "utf8");
            } else {
              const prev = JSON.parse(readFileSync(metaPath, "utf8"));
              if (Number(prev.worldId) !== worldId) {
                send(409, { error: `\u76EE\u5F55\u5DF2\u5C5E\u4E8E\u4E16\u754C ${prev.worldId}` });
                return;
              }
            }
            send(200, { path: dir });
          } catch (e) {
            send(500, { error: String(e.message ?? e) });
          }
        }).catch(() => send(400, { error: "bad request" }));
        return;
      }
      if (req.method === "POST" && route === `${WORLDS_PREFIX}/token`) {
        readJsonBody(req).then((body) => {
          const worldId = Number(body.worldId);
          const token = String(body.token ?? "");
          if (!Number.isInteger(worldId) || worldId <= 0) {
            send(400, { error: "missing worldId" });
            return;
          }
          if (!token) {
            send(400, { error: "missing token" });
            return;
          }
          worldTokenMap.set(worldId, token);
          ctx.logger?.info?.(`dsh-aischat: token registered for world ${worldId}`);
          send(200, { ok: true });
        }).catch(() => send(400, { error: "bad request" }));
        return;
      }
      if (req.method === "GET" && route === `${WORLDS_PREFIX}/status`) {
        send(200, {
          tokenWorlds: [...worldTokenMap.keys()],
          worldDirs: listWorldDirs()
        });
        return;
      }
      if (req.method === "POST" && route === `${WORLDS_PREFIX}/pull`) {
        readJsonBody(req).then(async (body) => {
          const worldId = Number(body.worldId);
          if (!Number.isInteger(worldId) || worldId <= 0) {
            send(400, { error: "invalid worldId" });
            return;
          }
          const dir = worldDirFor(worldId);
          if (!dir) {
            send(404, { error: `\u5DE5\u4F5C\u533A\u6CA1\u6709\u4E16\u754C ${worldId} \u7684\u76EE\u5F55\uFF08\u8BF7\u5148\u540C\u6B65\uFF09` });
            return;
          }
          const result = await pullWithSnapshot(backendUrl, worldId, dir, worldTokenMap.get(worldId));
          send(result.ok ? 200 : 409, result);
        }).catch(() => send(400, { error: "bad request" }));
        return;
      }
      send(404, { error: "not found" });
    }
  });
  const worldFromExec = (exec) => {
    const session = exec.agent?.session;
    const world = resolveWorldFromCwd(session?.header?.cwd);
    if (!world) return null;
    const token = worldTokenMap.get(world.worldId) ?? (session?.id ? sessionTokenMap.get(String(session.id)) : void 0);
    return { ...world, token };
  };
  const registerWorldTool = (toolName, description, parameters, execute) => {
    ctx.tools.register({
      name: toolName,
      description,
      parameters,
      output: { schema: { type: "object" }, render: (_args, value) => textOutput(value) },
      execute: async (rawArgs, exec) => {
        const world = worldFromExec(exec);
        if (!world) {
          return { error: "\u5F53\u524D\u4F1A\u8BDD\u4E0D\u5C5E\u4E8E\u4EFB\u4F55 AIsChat \u4E16\u754C\uFF1A\u8BF7\u5148\u5728\u5DE5\u4F5C\u533A\u6253\u5F00\u4E00\u4E2A\u300CAIC\u7FA4\u89C6\u754C-\u4E16\u754C\u540D\u300D\u4F1A\u8BDD\uFF08\u8BE5\u4F1A\u8BDD\u76EE\u5F55\u9700\u542B .aischat-world.json\uFF09\u3002" };
        }
        try {
          const result = await execute(rawArgs ?? {}, world);
          if (result && typeof result === "object" && !toolName.startsWith("world_pull") && !toolName.startsWith("world_push")) {
            const dir = worldDirFor(world.worldId);
            if (dir) {
              try {
                const snap = readSnapshot(dir);
                const tree = await fetchRemoteTree(backendUrl, world.worldId, world.token);
                if (tree) {
                  const cmp = compareMirror(tree, dir, snap);
                  const updateCount = cmp.added.length + cmp.changedRemote.length;
                  if (updateCount > 0) {
                    result.updateHint = `\u4E16\u754C\u6709 ${updateCount} \u4E2A\u6587\u4EF6\u66F4\u65B0\u672A\u62C9\u53D6\uFF08\u7528 world_pull \u83B7\u53D6\u6700\u65B0\uFF1B\u82E5\u4F60\u521A\u6539\u8FC7\u6587\u4EF6\uFF0C\u5148 world_push\uFF09`;
                  }
                  if (cmp.conflict.length > 0) {
                    result.conflictHint = `\u4EE5\u4E0B\u6587\u4EF6\u5B58\u5728\u540C\u6B65\u51B2\u7A81\uFF1A${cmp.conflict.slice(0, 5).join(", ")}\uFF08\u7528 world_pull / world_push \u7684 force \u88C1\u51B3\uFF09`;
                  }
                }
              } catch {
              }
            }
          }
          return result;
        } catch (e) {
          return { error: String(e.message ?? e) };
        }
      }
    });
  };
  registerWorldTool(
    "world_list_files",
    "\u5217\u51FA\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7684\u6587\u4EF6\u6811\uFF08\u4E16\u754C\u9875\u9762\u4EE3\u7801\u7B49\uFF09\u3002\u8FD4\u56DE\u6587\u4EF6\u5217\u8868\uFF08\u76F8\u5BF9\u8DEF\u5F84\u3001\u5927\u5C0F\u3001\u7C7B\u578B\uFF09\u3002",
    { type: "object", properties: { prefix: { type: "string", description: "\u53EF\u9009\u524D\u7F00\u8FC7\u6EE4\uFF0C\u5982 css/ \u6216 blocks/" } }, additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u5217\u6587\u4EF6\uFF08\u9700 owner \u6743\u9650\uFF09\u3002\u8BF7\u91CD\u65B0\u6253\u5F00 AIsChat \u540C\u6B65\u4E00\u6B21\u3002" };
      const prefix = encodeURIComponent(String(args.prefix ?? ""));
      const res = await backendRequest(backendUrl, "GET", `/worlds/${world.worldId}/files?prefix=${prefix}`, { token: world.token });
      if (res.status !== 200) return { error: `\u5217\u6587\u4EF6\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return JSON.parse(res.text || "{}");
      } catch {
        return { ok: true, content: res.text.slice(0, 4e3) };
      }
    }
  );
  registerWorldTool(
    "world_read_file",
    "\u8BFB\u53D6\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7684\u4E00\u4E2A\u6587\u4EF6\u5185\u5BB9\uFF08\u5982 index.html\u3001script.js\u3001style.css\uFF09\u3002",
    { type: "object", properties: { path: { type: "string", description: "\u76F8\u5BF9\u8DEF\u5F84\uFF0C\u5982 index.html \u6216 blocks/group-chat/chat-panel.js" } }, required: ["path"], additionalProperties: false },
    async (args, world) => {
      const path = String(args.path ?? "");
      if (!path) return { error: "\u7F3A\u5C11 path" };
      const res = await backendRequest(backendUrl, "GET", `/world/${world.worldId}/files/${encodeURIComponent(path)}`);
      if (res.status !== 200) return { error: `\u8BFB\u6587\u4EF6\u5931\u8D25 (${res.status})` };
      return { ok: true, path, content: res.text.slice(0, 6e4) };
    }
  );
  registerWorldTool(
    "world_write_file",
    "\u5199\u5165\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7684\u4E00\u4E2A\u6587\u4EF6\uFF08\u8986\u76D6\uFF1B\u81EA\u52A8\u5EFA\u76EE\u5F55\uFF09\u3002\u7528\u4E8E\u4FEE\u6539\u4E16\u754C\u9875\u9762\u4EE3\u7801\u3002",
    { type: "object", properties: { path: { type: "string", description: "\u76F8\u5BF9\u8DEF\u5F84\uFF0C\u5982 index.html" }, content: { type: "string", description: "\u5B8C\u6574\u6587\u4EF6\u5185\u5BB9" } }, required: ["path", "content"], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u5199\u6587\u4EF6\uFF08\u9700 owner \u6743\u9650\uFF09\u3002" };
      const res = await backendRequest(backendUrl, "PUT", `/worlds/${world.worldId}/files`, {
        token: world.token,
        json: { path: String(args.path ?? ""), content: String(args.content ?? "") }
      });
      if (res.status !== 200) return { error: `\u5199\u6587\u4EF6\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return { ok: true, ...JSON.parse(res.text || "{}") };
      } catch {
        return { ok: true };
      }
    }
  );
  registerWorldTool(
    "world_delete_file",
    "\u5220\u9664\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7684\u4E00\u4E2A\u6587\u4EF6\u3002",
    { type: "object", properties: { path: { type: "string", description: "\u76F8\u5BF9\u8DEF\u5F84" } }, required: ["path"], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u5220\u6587\u4EF6\u3002" };
      const path = encodeURIComponent(String(args.path ?? ""));
      const res = await backendRequest(backendUrl, "DELETE", `/worlds/${world.worldId}/files?path=${path}`, { token: world.token });
      if (res.status !== 200) return { error: `\u5220\u6587\u4EF6\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      return { ok: true };
    }
  );
  registerWorldTool(
    "world_api",
    "\u8C03\u7528\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7684\u53D7\u63A7 API\uFF08GET/POST /world/{id}/api/{endpoint}\uFF09\u3002\u5E38\u7528\uFF1Aworld\uFF08\u4E16\u754C\u4FE1\u606F\uFF09\u3001chat\uFF08\u5BF9\u8BDD\u5386\u53F2\uFF09\u3001memories\uFF08\u8BB0\u5FC6\uFF09\u3001usage\uFF08\u7528\u91CF\uFF09\u3001groups\uFF08\u7ED1\u5B9A\u7FA4\u5217\u8868\uFF09\u3001group/messages\uFF08\u7FA4\u6D88\u606F\uFF09\u3001state\uFF08\u72B6\u6001\uFF09\u3001data/{key}\uFF08\u4E16\u754C\u6570\u636E\uFF09\u3002",
    { type: "object", properties: { endpoint: { type: "string", description: "API \u8DEF\u5F84\uFF0C\u5982 world / chat / memories / usage / groups / group/messages / state / data/myk" }, method: { type: "string", enum: ["GET", "POST", "PUT", "DELETE"], default: "GET" }, query: { type: "object", description: "\u67E5\u8BE2\u53C2\u6570\u952E\u503C\uFF08\u5B57\u7B26\u4E32\u5316\uFF09" }, body: { type: "object", description: "POST/PUT \u8BF7\u6C42\u4F53" } }, required: ["endpoint"], additionalProperties: false },
    async (args, world) => {
      const endpoint = String(args.endpoint ?? "").replace(/^\/+/, "");
      if (!endpoint) return { error: "\u7F3A\u5C11 endpoint" };
      const method = String(args.method ?? "GET").toUpperCase();
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(args.query ?? {})) {
        if (v !== void 0 && v !== null) qs.set(k, String(v));
      }
      const q = qs.toString();
      const apiToken = await resolveWorldApiToken(backendUrl, world.worldId, world.token);
      if (!apiToken) return { error: "\u65E0\u6CD5\u53D6\u5F97\u8BE5\u4E16\u754C\u7684 API token\uFF08\u9700 owner \u767B\u5F55\u6001\u4E14\u4E16\u754C\u5DF2\u521D\u59CB\u5316\uFF09\u3002" };
      const res = await backendRequest(backendUrl, method, `/world/${world.worldId}/api/${endpoint}${q ? `?${q}` : ""}`, {
        headers: { "x-world-token": apiToken },
        json: method === "GET" ? void 0 : args.body ?? {}
      });
      if (res.status >= 400) return { error: `API \u8C03\u7528\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return JSON.parse(res.text);
      } catch {
        return { ok: true, content: res.text.slice(0, 6e4) };
      }
    }
  );
  registerWorldTool(
    "world_chat",
    "\u8BFB\u5199\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\u7ED1\u5B9A\u7FA4\u804A\u7684\u6D88\u606F\u3002action=read \u62C9\u6700\u8FD1\u6D88\u606F\uFF08groupId \u7701\u7565\u65F6\u81EA\u52A8\u53D6\u4E16\u754C\u7ED1\u5B9A\u7684\u7B2C\u4E00\u4E2A\u7FA4\uFF09\uFF1Baction=send \u4EE5\u4E16\u754C\u8EAB\u4EFD\u53D1\u6D88\u606F\u3002",
    { type: "object", properties: { action: { type: "string", enum: ["read", "send"] }, groupId: { type: "number" }, content: { type: "string", description: "send \u65F6\u7684\u6D88\u606F\u5185\u5BB9" }, limit: { type: "number", default: 20 } }, required: ["action"], additionalProperties: false },
    async (args, world) => {
      const apiToken = await resolveWorldApiToken(backendUrl, world.worldId, world.token);
      if (!apiToken) return { error: "\u65E0\u6CD5\u53D6\u5F97\u8BE5\u4E16\u754C\u7684 API token\uFF08\u9700 owner \u767B\u5F55\u6001\u4E14\u4E16\u754C\u5DF2\u521D\u59CB\u5316\uFF09\u3002" };
      const worldHeaders = { "x-world-token": apiToken };
      const action = String(args.action ?? "");
      let groupId = Number(args.groupId);
      if (!groupId) {
        const g = await backendRequest(backendUrl, "GET", `/world/${world.worldId}/api/groups`, { headers: worldHeaders });
        if (g.status === 200) {
          try {
            const groups = JSON.parse(g.text);
            groupId = Number(groups?.[0]?.id);
          } catch {
          }
        }
      }
      if (!groupId) return { error: "\u8BE5\u4E16\u754C\u672A\u7ED1\u5B9A\u7FA4\u804A\uFF0C\u65E0\u6CD5\u8BFB\u5199\u6D88\u606F\u3002" };
      if (action === "read") {
        const limit = Number(args.limit ?? 20);
        const res = await backendRequest(backendUrl, "GET", `/world/${world.worldId}/api/group/messages?group_id=${groupId}&limit=${limit}`, { headers: worldHeaders });
        if (res.status !== 200) return { error: `\u8BFB\u6D88\u606F\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 300) };
        try {
          return JSON.parse(res.text);
        } catch {
          return { ok: true, content: res.text.slice(0, 6e4) };
        }
      }
      if (action === "send") {
        const content = String(args.content ?? "");
        if (!content) return { error: "\u7F3A\u5C11 content" };
        const res = await backendRequest(backendUrl, "POST", `/world/${world.worldId}/api/group/messages`, {
          headers: worldHeaders,
          json: { group_id: groupId, content }
        });
        if (res.status >= 400) return { error: `\u53D1\u6D88\u606F\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 300) };
        return { ok: true, sent: content };
      }
      return { error: "action \u5FC5\u987B\u662F read \u6216 send" };
    }
  );
  registerWorldTool(
    "world_lifecycle",
    "\u5524\u9192\u6216\u4F11\u7720\u5F53\u524D AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\uFF08wake \u5E94\u7528\u79BB\u7EBF\u65F6\u95F4\u8865\u507F\u5E76\u542F\u52A8\u5E38\u9A7B\uFF1Bsleep \u4F11\u7720\uFF09\u3002",
    { type: "object", properties: { action: { type: "string", enum: ["wake", "sleep"] } }, required: ["action"], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u63A7\u5236\u4E16\u754C\u751F\u547D\u5468\u671F\u3002" };
      const action = String(args.action ?? "");
      if (action !== "wake" && action !== "sleep") return { error: "action \u5FC5\u987B\u662F wake \u6216 sleep" };
      const res = await backendRequest(backendUrl, "POST", `/worlds/${world.worldId}/${action}`, { token: world.token });
      if (res.status >= 400) return { error: `${action} \u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return JSON.parse(res.text);
      } catch {
        return { ok: true };
      }
    }
  );
  registerWorldTool(
    "world_pull",
    "\u628A AIsChat \u4E16\u754C\u7684\u6700\u65B0\u6587\u4EF6\u62C9\u53D6\u5230\u5F53\u524D\u5DE5\u4F5C\u533A\u76EE\u5F55\uFF08\u672C\u5730\u4E16\u754C\u955C\u50CF\uFF09\u3002\u5E26\u51B2\u7A81\u4FDD\u62A4\uFF1A\u672C\u5730\u6709\u672A\u63A8\u9001\u7684\u4FEE\u6539\u6216\u51B2\u7A81\u6587\u4EF6\u65F6\u4F1A\u62D2\u7EDD\u5E76\u62A5\u544A\uFF0C\u7EDD\u4E0D\u8986\u76D6\u4F60\u7684\u6539\u52A8\uFF1Bforce=true \u65F6\u5F3A\u5236\u4EE5\u4E16\u754C\u4E3A\u51C6\u8986\u76D6\u3002\u62C9\u53D6\u540E\u8FD4\u56DE\u53D8\u5316\u6E05\u5355\uFF08\u65B0\u589E/\u4FEE\u6539/\u5220\u9664\uFF09\u3002",
    { type: "object", properties: { force: { type: "boolean", description: "true \u65F6\u5F3A\u5236\u4EE5\u4E16\u754C\u4E3A\u51C6\u8986\u76D6\u672C\u5730\uFF08\u542B\u51B2\u7A81\uFF09" } }, additionalProperties: false },
    async (args, world) => {
      const dir = worldDirFor(world.worldId);
      if (!dir) return { error: "\u627E\u4E0D\u5230\u8BE5\u4E16\u754C\u7684\u5DE5\u4F5C\u533A\u76EE\u5F55\u3002" };
      const result = await pullWithSnapshot(backendUrl, world.worldId, dir, world.token, args.force === true);
      return result.ok ? { ok: true, message: result.message, pulled: result.pulled, skipped: result.skipped, conflict: result.conflict } : { error: result.message, conflict: result.conflict };
    }
  );
  registerWorldTool(
    "world_push",
    "\u628A\u5F53\u524D\u5DE5\u4F5C\u533A\u76EE\u5F55\uFF08\u672C\u5730\u4E16\u754C\u955C\u50CF\uFF09\u7684\u5168\u90E8\u6539\u52A8\u540C\u6B65\u56DE AIsChat \u4E16\u754C\u3002\u53EA\u63A8\u9001\u672C\u5730\u4FEE\u6539\u8FC7\u7684\u6587\u4EF6\uFF08\u5E26\u5FEB\u7167\u5BF9\u6BD4\uFF09\uFF1B\u51B2\u7A81\u6587\u4EF6\uFF08\u8FDC\u7AEF\u4E5F\u6539\u8FC7\uFF09\u9ED8\u8BA4\u8DF3\u8FC7\u5E76\u62A5\u544A\uFF0Cforce=true \u65F6\u4EE5\u672C\u5730\u4E3A\u51C6\u8986\u76D6\u3002\u6392\u9664\u672C\u5730\u5143\u6570\u636E .aischat-world.json \u4E0E __pycache__\u3002\u4F60\uFF08agent\uFF09\u7528 DSH \u539F\u751F read/write/edit/bash \u4FEE\u6539\u5DE5\u4F5C\u533A\u6587\u4EF6\u540E\u8C03\u7528\u672C\u5DE5\u5177\u8BA9\u6539\u52A8\u5728 AIsChat \u4E2D\u751F\u6548\u3002",
    { type: "object", properties: { force: { type: "boolean", description: "true \u65F6\u4EE5\u672C\u5730\u4E3A\u51C6\u5F3A\u5236\u8986\u76D6\u51B2\u7A81\u6587\u4EF6" } }, additionalProperties: false },
    async (args, world) => {
      const dir = worldDirFor(world.worldId);
      if (!dir) return { error: "\u627E\u4E0D\u5230\u8BE5\u4E16\u754C\u7684\u5DE5\u4F5C\u533A\u76EE\u5F55\u3002" };
      const result = await pushWithSnapshot(backendUrl, world.worldId, dir, world.token, args.force === true);
      return result.ok ? { ok: true, message: result.message, pushed: result.pushed, skipped: result.skipped, conflict: result.conflict } : { error: result.message, conflict: result.conflict };
    }
  );
  registerWorldTool(
    "world_run",
    "\u5728 AIsChat \u540E\u7AEF\u6C99\u7BB1\u4E2D\u8FD0\u884C\u4E00\u6BB5 Python \u4EE3\u7801\uFF08\u4E16\u754C\u4E0A\u4E0B\u6587\uFF1A\u6CE8\u5165 WORLD_ID/WORLD_API_TOKEN \u7B49\u73AF\u5883\uFF1B\u914D\u989D\u9ED8\u8BA4 24MB/10s\uFF09\u3002\u9002\u5408\u6D4B\u8BD5\u4E16\u754C\u903B\u8F91\uFF1B\u5B8C\u6574\u7684\u9875\u9762/\u903B\u8F91\u6539\u52A8\u8BF7\u7528 DSH \u539F\u751F\u5DE5\u5177\u6539\u5DE5\u4F5C\u533A\u6587\u4EF6 + world_push\u3002",
    { type: "object", properties: { code: { type: "string", description: "\u8981\u8FD0\u884C\u7684 Python \u4EE3\u7801" }, entry: { type: "string", description: "\u53EF\u9009\u5165\u53E3\uFF0C\u5982 main.py" } }, required: ["code"], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u8FD0\u884C\u4E16\u754C\u4EE3\u7801\uFF08\u9700 owner \u6743\u9650\uFF09\u3002" };
      const res = await backendRequest(backendUrl, "POST", `/worlds/${world.worldId}/run`, {
        token: world.token,
        json: { code: String(args.code ?? ""), entry: args.entry ? String(args.entry) : void 0 }
      });
      if (res.status >= 400) return { error: `\u8FD0\u884C\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return JSON.parse(res.text);
      } catch {
        return { ok: true, content: res.text.slice(0, 6e4) };
      }
    }
  );
  registerWorldTool(
    "world_trigger",
    "\u89E6\u53D1\u5F53\u524D AIsChat \u4E16\u754C\u5165\u53E3\u7684 handle(event)\uFF08\u4E16\u754C\u6C99\u7BB1\uFF09\uFF0C\u7528\u4E8E\u6D4B\u8BD5\u4E16\u754C\u5BF9\u4E8B\u4EF6\u7684\u54CD\u5E94\u3002",
    { type: "object", properties: { event: { type: "object", description: '\u4E8B\u4EF6\u8F7D\u8377\uFF0C\u5982 {type: "message", ...}' }, entry: { type: "string", description: "\u53EF\u9009\u5165\u53E3\uFF0C\u5982 main.py" } }, required: ["event"], additionalProperties: false },
    async (args, world) => {
      if (!world.token) return { error: "\u8BE5\u4E16\u754C\u4F1A\u8BDD\u672A\u8FDE\u63A5\u767B\u5F55\u6001\uFF0C\u65E0\u6CD5\u89E6\u53D1\u4E16\u754C\uFF08\u9700 owner \u6743\u9650\uFF09\u3002" };
      const res = await backendRequest(backendUrl, "POST", `/worlds/${world.worldId}/trigger`, {
        token: world.token,
        json: { event: args.event ?? {}, entry: args.entry ? String(args.entry) : void 0 }
      });
      if (res.status >= 400) return { error: `\u89E6\u53D1\u5931\u8D25 (${res.status})`, detail: res.text.slice(0, 400) };
      try {
        return JSON.parse(res.text);
      } catch {
        return { ok: true, content: res.text.slice(0, 6e4) };
      }
    }
  );
  ctx.systemPrompt.section({
    name: "aischat-world-context",
    order: 150,
    text: "\u5982\u679C\u4F60\u7684\u4F1A\u8BDD\u5DE5\u4F5C\u76EE\u5F55\u4F4D\u4E8E aischat-worlds \u76EE\u5F55\u4E0B\uFF08\u76EE\u5F55\u540D\u4EE5\u300CAIC\u7FA4\u89C6\u754C-\u300D\u5F00\u5934\uFF09\uFF0C\u4F60\u6B63\u5728\u64CD\u4F5C\u4E00\u4E2A AIsChat \u7FA4\u89C6\u754C\u4E16\u754C\uFF1A\u8BE5\u5DE5\u4F5C\u76EE\u5F55\u662F\u4E16\u754C\u7684\u300C\u672C\u5730\u955C\u50CF\u300D\u2014\u2014\u4E16\u754C\u9875\u9762\u4EE3\u7801\u3001\u6570\u636E\u6587\u4EF6\u90FD\u5728\u91CC\u9762\uFF0C\u4F60\u53EF\u4EE5\u76F4\u63A5\u7528 DSH \u539F\u751F\u7684 read/write/edit/glob/grep/bash \u5DE5\u5177\u8BFB\u5199\u5B83\u4EEC\uFF08bash \u53EF\u76F4\u63A5\u8FD0\u884C\u4E16\u754C Python \u4EE3\u7801\u6D4B\u8BD5\uFF09\u3002\u4FEE\u6539\u5B8C\u6210\u540E\u8C03\u7528 world_push \u628A\u6539\u52A8\u540C\u6B65\u56DE AIsChat \u4E16\u754C\uFF1B\u82E5\u4E16\u754C\u5728\u522B\u5904\u88AB\u6539\u8FC7\u3001\u9700\u8981\u6700\u65B0\u6587\u4EF6\u65F6\u7528 world_pull \u4E3B\u52A8\u62C9\u53D6\u3002\u7CBE\u786E\u64CD\u4F5C\uFF08\u4E16\u754C API\u3001\u7ED1\u5B9A\u7FA4\u804A\u6D88\u606F\u3001\u5524\u9192/\u4F11\u7720\u3001\u6C99\u7BB1\u8FD0\u884C\uFF09\u7528 world_* \u7CFB\u5217\u5DE5\u5177\u3002\u4E16\u754C\u662F\u7528\u6237\u5D4C\u5165 DSH \u7684\u300C\u53EF\u64CD\u4F5C\u5BF9\u8C61\u300D\u2014\u2014\u4F60\u7684\u63A8\u7406\u4E0E\u5DE5\u5177\u4ECD\u8D70 DSH \u4F53\u7CFB\uFF0C\u53EA\u662F\u64CD\u4F5C\u76EE\u6807\u5C5E\u4E8E AIsChat\u3002"
  });
  ctx.logger?.info?.(`dsh-aischat: proxying /aischat-api and /aischat-ws -> ${backendUrl}; serving /aischat-ui; world sync at ${WORLDS_PREFIX}`);
}
export {
  Config,
  apply,
  inject,
  name
};
//# sourceMappingURL=index.js.map
