"""授权边界的静态守卫 —— 权限判定只允许走统一入口。

背景（2026-09-13 公网自测报告）：/fs/public/{file_id} 匿名拖全站文件、
/gm/{group_id}/messages 越权读任意群、WS subscribe 无成员校验、
/admin/tools/backpack 漏挂管理员鉴权、require_agent_access 信 JWT 里的 role。

修完之后把「漏挂」变成会红的用例：路由清单里少一个依赖就报错，而不是等下一次渗透测试。
约定见 docs/guides/安全与权限模型.md。

本文件只做静态检查与纯函数验证（不连库、不建表）。
"""
import inspect
import json
import os
import tempfile

from app.main import app


def _dependency_names(route) -> set[str]:
    """递归收集路由依赖链上的可调用对象名"""
    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        call = getattr(dependant, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", str(call)))
        stack.extend(getattr(dependant, "dependencies", []) or [])
    return names


def _find_route(path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route
    return None


def _routes_missing_dependency(dependency: str, prefix: str) -> list[str]:
    """prefix 下缺少指定依赖的 HTTP 路由（WebSocket 路由不走 Depends，另行用例）"""
    missing: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        if not path.startswith(prefix):
            continue
        methods = sorted(getattr(route, "methods", None) or ())
        if not methods:
            continue
        if dependency not in _dependency_names(route):
            missing.append(",".join(methods) + " " + path)
    return sorted(missing)


async def test_admin_routes_all_require_admin():
    """/admin 下不允许漏挂管理员鉴权（自测报告 #6）"""
    missing = _routes_missing_dependency("require_admin", "/admin")
    assert not missing, "以下 /admin 路由缺少 require_admin：" + repr(missing)


async def test_group_read_routes_require_membership():
    """群消息 / 群详情 / 群成员只对群成员开放（自测报告 #2）"""
    for path in (
        "/gm/{group_id}/messages",
        "/groups/{group_id}",
        "/groups/{group_id}/members",
    ):
        route = _find_route(path)
        assert route is not None, path + " 未注册"
        assert "require_group_member" in _dependency_names(route), (
            path + " 缺少 require_group_member：任意登录用户可读任意群"
        )


async def test_ws_group_subscribe_checks_membership():
    """WS 订阅群与 REST 同口径（自测报告 #2 的实时入口）"""
    from app.routers import ws

    src = inspect.getsource(ws.websocket_endpoint)
    assert "is_group_member" in src, "WS 群订阅必须校验成员身份，否则可越权听任意群直播"


async def test_chat_user_routes_require_login():
    """用户信息与好友列表不得匿名可读（自测报告 #5、#9）"""
    for path in ("/chat/user/{user_id}", "/chat/user/{user_id}/friends"):
        route = _find_route(path)
        assert route is not None, path + " 未注册"
        assert "get_current_user" in _dependency_names(route), path + " 缺少登录校验"


async def test_agent_access_rechecks_role_from_db():
    """JWT 里的 role 是签发快照，权限判定必须回查 DB（自测报告 #8）"""
    from app.routers import deps
    from app.utils import auth

    assert "load_user_role" in inspect.getsource(deps.require_agent_access)
    assert "load_user_role" in inspect.getsource(auth.require_admin)


async def test_public_file_route_checks_maintenance_whitelist():
    """匿名下载只放行维护弹窗图片（自测报告 #1）"""
    from app.routers import files

    src = inspect.getsource(files.download_public_file)
    assert "is_public_file" in src, "/fs/public 必须走维护图片白名单，否则等于匿名拖全站文件"


def test_public_file_id_parsing():
    """白名单 URL 解析：只认 /fs/public/{id} 形态"""
    from app.services.infrastructure.maintenance import parse_public_file_id

    assert parse_public_file_id("/fs/public/12") == 12
    assert parse_public_file_id("/fs/public/12?thumb=1") == 12
    assert parse_public_file_id("/fs/public/abc") is None
    assert parse_public_file_id("https://cdn.example.com/a.png") is None
    assert parse_public_file_id("") is None


def test_whitelist_denies_by_default_and_allows_listed_files():
    """白名单语义：默认拒；只有维护图片列表里的 file_id 才放行"""
    from app.services.infrastructure.maintenance import MaintenanceManager

    with tempfile.TemporaryDirectory() as tmp:
        manager = MaintenanceManager(maint_dir=tmp, data_dir=tmp)
        assert manager.is_public_file(6) is False, "空列表必须全部拒绝"
        with open(os.path.join(tmp, "maintenance_images.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(["/fs/public/6", "https://cdn.example.com/a.png"]))
        assert manager.is_public_file(6) is True
        assert manager.is_public_file(7) is False, "未列入的文件必须拒绝"


async def test_docs_closed_in_production():
    """生产环境不暴露接口文档（自测报告 #4）"""
    from fastapi import HTTPException

    from app.config import settings
    from app.routers.swagger_docs import _ensure_docs_enabled

    original = settings.environment
    settings.environment = "production"
    try:
        try:
            _ensure_docs_enabled()
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("生产环境 /docs 必须 404")
    finally:
        settings.environment = original


async def test_federation_outbound_tls_verification_enabled():
    """联邦出站不得关闭 TLS 校验；自签对端走 FEDERATION_CA_BUNDLE（自测报告 #7）"""
    import importlib

    from app.services.federation import federation_service

    src = inspect.getsource(federation_service.peer_http_client)
    assert "verify" in src and "federation_ca_bundle" in src
    for module_name in ("app.services.federation.federation_manager", "app.routers.federation_ws"):
        module = importlib.import_module(module_name)
        assert "verify=False" not in inspect.getsource(module), (
            module_name + " 又出现了 verify=False，联邦出站请走 peer_http_client()"
        )
