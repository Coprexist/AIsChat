"""
自定义 Swagger UI 文档路由（语言选择 + 快捷登录）

从 main.py 拆出，通过 get_all_routers() 自动发现注册。
"""
from fastapi import APIRouter, HTTPException, Request

from app.config import settings

router = APIRouter(tags=["文档"])


def _ensure_docs_enabled() -> None:
    """生产环境不提供接口文档（与 main.py 的 openapi_url 同步关闭）"""
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/docs", include_in_schema=False)
async def custom_swagger_ui(req: Request):
    _ensure_docs_enabled()
    from app.utils.docs_customizer import get_custom_swagger_html
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@router.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    _ensure_docs_enabled()
    from app.utils.docs_customizer import get_custom_swagger_html
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")
