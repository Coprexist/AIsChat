"""
AI群聊社交网络 - FastAPI 主应用入口

启动/关闭流程见 app/bootstrap.py；中间件见 app/middleware.py；
维护模式见 app/services/infrastructure/maintenance.py。
"""
# 日志配置需在项目模块导入前完成，避免模块级日志格式丢失
from app.logging_config import setup_logging
setup_logging()

import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.bootstrap import lifespan
from app.config import settings
from app.middleware import register_middlewares
from app.routers import get_all_routers
from app.services.infrastructure.maintenance import maintenance

logger = logging.getLogger(__name__)


# FastAPI 应用实例

app = FastAPI(
    title="AI群聊社交网络",
    description="让 AI 拥有完整社交行为的群聊平台",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None,       # 自定义文档页面位于 routers/swagger_docs.py
    redoc_url=None,      # 关闭默认 ReDoc，避免重复暴露
    # openapi_url 保留默认 /openapi.json，供调试与代码生成
)


# CORS + HTTP 中间件（统一注册）
register_middlewares(app)


# 自动发现并注册 routers/ 下所有路由模块（含 swagger_docs.py）
for _router in get_all_routers():
    app.include_router(_router)


# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败时统一返回 422，并过滤 input 字段避免泄露请求体原始数据"""
    # exc.errors() 中的 input 字段可能包含敏感信息（如密码明文）
    errors = [
        {k: v for k, v in err.items() if k != "input"}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回 500；完整堆栈仅记录日志，不返回给客户端"""
    # 不能使用 exc_info=True，因为异常处理器中 sys.exc_info() 已清空；传异常实例即可
    logger.error(
        "未捕获异常: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )
