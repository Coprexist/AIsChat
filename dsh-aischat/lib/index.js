// src/index.ts
import http from "node:http";
import z from "@deepseek-ai/schemastery";
var name = "dsh-aischat";
var inject = ["webServer"];
var Config = z.object({
  backendUrl: z.string().default("http://127.0.0.1:5228")
});
var HTTP_PREFIX = "/aischat-api";
var WS_PATH = "/aischat-ws";
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
  ctx.webServer.registerUpgrade({
    path: WS_PATH,
    handler: (req, socket, head) => {
      proxyWs(backendUrl, req, socket, head);
    }
  });
  ctx.logger?.info?.(`dsh-aischat: proxying /aischat-api and /aischat-ws -> ${backendUrl}`);
}
export {
  Config,
  apply,
  inject,
  name
};
//# sourceMappingURL=index.js.map
