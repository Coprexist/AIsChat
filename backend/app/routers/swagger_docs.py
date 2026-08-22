"""
自定义 Swagger UI 文档路由（语言选择 + 快捷登录）

从 main.py 拆出，通过 get_all_routers() 自动发现注册。
"""
from fastapi import APIRouter, Request

router = APIRouter(tags=["文档"])


@router.get("/docs", include_in_schema=False)
async def custom_swagger_ui(req: Request):
    from app.utils.docs_customizer import get_custom_swagger_html
    lang = req.query_params.get("lang", "en")
    if lang not in ("zh", "en"):
        lang = "en"
    return get_custom_swagger_html(openapi_url="/openapi.json", lang=lang)


@router.get("/docs/zh", include_in_schema=False)
async def swagger_ui_zh():
    from app.utils.docs_customizer import get_custom_swagger_html
    return get_custom_swagger_html(openapi_url="/openapi.json", lang="zh")
