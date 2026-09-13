"""run_world_code — 跑世界代码

在沙箱中运行本世界的 Python 代码（测试用）：可直接跑一段脚本（code），或触发入口 main.py 的 handle(event)（给 event 即触发模式）。世界代码运行在隔离沙箱（内存/CPU/超时受限，
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class RunWorldCodeTool(WorldToolPlugin):
    name = 'run_world_code'
    label = '跑世界代码'
    segment = 'world'

    description = (
        '在沙箱中运行本世界的 Python 代码（测试用）：可直接跑一段脚本（code），或触发入口 main.py 的 handle(event)（给 event 即触发模式）。世界代码运行在隔离沙箱（内存/CPU/超时受限，'
        '无网络）。'
    )

    parameters = {'code': {'type': 'string', 'description': '可选：直接执行的 Python 脚本'},
     'entry': {'type': 'string', 'description': '可选：世界文件夹内入口文件（默认 main.py，触发模式用）'},
     'event': {'type': 'object', 'description': '可选：触发事件 dict；给了就执行入口的 handle(event) 并返回结果'}}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        # 2.1/2.2：沙箱执行世界代码（code 脚本）或触发入口 handle(event)
        try:
            args = ctx.args
            # 确保沙箱 env 注入 WORLD_API_TOKEN / WORLD_API_BASE（懒生成，worlds.config.api_token）
            from app.routers.world_proxy import ensure_world_api_token
            await ensure_world_api_token(ctx.world_repo.session, ctx.world)
            await ctx.world_repo.commit()
            from app.services.world.world_sandbox import run_world_code as _run_code, run_world_trigger as _run_trigger
            # 分阶段进度（2026-08-13：耗时工具多状态——创建→运行→返回）
            await ctx.progress("正在创建脚本…")
            if args.get("event") is not None:
                entry = str(args.get("entry") or "main.py").strip()
                await ctx.progress("触发世界入口执行中…")
                return await _run_trigger(ctx.world, event=args.get("event"), entry=entry)
            code = args.get("code")
            entry = str(args.get("entry") or "").strip() or None
            await ctx.progress("脚本运行中…")
            return await _run_code(ctx.world, code=code if isinstance(code, str) else None, entry=entry)
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            if "result" in result:
                return f"世界代码触发成功：{str(result.get('result'))[:120]}"
            out = (result.get('stdout') or '').strip().splitlines()
            return f"世界代码运行成功（{result.get('duration_ms', 0)}ms）：" + (out[-1][:120] if out else "无输出")
        return f"世界代码执行失败：{result.get('error', '未知错误')}"
