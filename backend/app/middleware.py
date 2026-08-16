"""
HTTP 中间件 — 请求 IP 追踪与维护模式拦截。

IP 追踪只取 uvicorn 解析后的 request.client，不自行解析 X-Forwarded-For：
uvicorn 的 ProxyHeadersMiddleware 仅信任 --forwarded-allow-ips 内的代理
（默认 127.0.0.1，即默认不信任任何代理头），自行解析会绕过该可信检查。

注意：当前 docker 端口映射部署下（浏览器 → docker-proxy 网关 → vite → backend），
vite 看到的客户端源是网关 IP，后端审计 IP 为网关地址；要还原真实客户端 IP，
需在宿主层加反向代理并配置 uvicorn --forwarded-allow-ips 指向该代理。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.infrastructure.maintenance import maintenance
from app.utils.auth import set_current_request_ip

logger = logging.getLogger(__name__)

# 硬维护放行路径：健康检查/文档/管理/认证/维护消息本身/维护弹窗公开图片
_EXACT_BYPASS = ("/health", "/", "/docs", "/openapi.json")
_PREFIX_BYPASS = ("/admin", "/auth", "/maintenance-msg", "/fs/public")


async def client_ip_middleware(request: Request, call_next):
    """记录请求 IP 到 contextvar（供审计日志使用）"""
    try:
        set_current_request_ip(request.client.host if request.client else None)
    except Exception as e:
        logger.exception(f"client_ip_middleware error: {e}")
    return await call_next(request)


async def maintenance_middleware(request: Request, call_next):
    """维护模式拦截（硬维护 503；软维护响应带头，前端据此显隐提示）"""
    path = request.url.path
    bypass = path in _EXACT_BYPASS or path.startswith(_PREFIX_BYPASS)

    # 硬维护（自动启动/关闭 或 管理员手动）：503 拦截
    is_hard = maintenance.hard_active()
    if is_hard and not bypass:
        msg = maintenance.get_msg()
        return JSONResponse(
            status_code=503,
            content={"detail": msg["hard_body"], "maintenance": True, "hard": True, "msg": msg}
        )

    # 软维护（手动）：API 正常但前端显示提示。
    # 状态查询走 manager 的 TTL 缓存，开关切换（manager 写入）即时失效缓存。
    response = await call_next(request)
    if maintenance.is_soft():
        # 所有响应（含 bypass）都带维护头，前端据此显隐提示且不会误判"已关闭"
        response.headers["X-Maintenance"] = "true"
        if not path.startswith("/maintenance-msg"):
            response.headers["X-Maintenance-Hard"] = str(is_hard)
    return response


def register_middlewares(app: FastAPI) -> None:
    """注册 HTTP 中间件（Starlette 后注册者先执行：maintenance 先于 client_ip，
    与历史行为一致——被维护拦截的请求不进入 IP 追踪）"""
    app.middleware("http")(client_ip_middleware)
    app.middleware("http")(maintenance_middleware)
