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
from fastapi import FastAPI, Request, status
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


# 注册中间件与路由在模块导入时立即执行，以便 uvicorn 直接导入 app 使用
register_middlewares(app)

# 自动发现并注册 routers/ 下所有路由模块（含 swagger_docs.py）
for router in get_all_routers():
    app.include_router(router)


# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败时统一返回 422，并过滤 input 字段避免泄露请求体原始数据"""
    # 只返回必要字段，避免泄露请求体内容（input、ctx 中可能包含敏感值）
    errors = [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回 500；完整堆栈仅记录日志，不返回给客户端"""
    # 不能使用 exc_info=True，因为异常处理器中 sys.exc_info() 已清空；
    # 也不能依赖 sys.exc_info()，因此显式传入异常元组
    logger.error(
        "未捕获异常: %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "服务器内部错误"},
    )
