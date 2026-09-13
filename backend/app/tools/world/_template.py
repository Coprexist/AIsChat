"""世界工具模板 —— 复制本文件为 <工具名>.py 即可，下划线开头的文件不会被自动加载。

写完不用改任何清单：app/tools/__init__.py 会自动导入 app/tools/world/ 下的每个模块，
WorldToolPlugin 的子类在定义时自注册。注册表会当场校验下面的规矩，不满足直接报错，
不会出现"工具默默失效"。

规矩：
1. 文件名 = 工具名；一个文件一个工具
2. 必须声明 name / label（中文名）/ segment / description / parameters / required
   - segment 取值：file（世界文件）/ group（群聊）/ memory（记忆）/ net（网络）/ world（世界）/ self（自我管理）
   - 无参数的工具写 parameters = {}
   - 只给斜杠命令用的内部工具加 exposed = False（不发给 LLM，但 description 仍必填可留空串？不需要 description）
3. 必须实现 execute(ctx)：返回 dict，成功带 success=True
4. 必须实现 summary(result)：卡片折叠时显示的那一行——写清楚"刚刚做了什么结果如何"
5. 可选 detail(args, result)：点开卡片后的详细说明，默认渲染「参数 + 结果」
6. 耗时工具用 await ctx.progress("正在…") 报进度，前端原地更新同一张卡片
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext


class MyTool(WorldToolPlugin):
    name = "my_tool"                 # 工具名（LLM function name，也是前端卡片的数据键）
    label = "我的工具"                # 卡片标题的中文名
    segment = "world"
    description = "一句话说清这个工具做什么、什么时候该用（写给 LLM 看的）"

    parameters = {
        "path": {"type": "string", "description": "参数说明"},
    }
    required = ["path"]

    async def execute(self, ctx: WorldToolContext) -> dict:
        # ctx.args       已解析好的参数 dict
        # ctx.world      当前世界（World 模型）
        # ctx.world_repo 世界仓储（读写数据库走它，别自己开 session）
        path = str(ctx.args.get("path") or "")
        await ctx.progress(f"正在处理 {path}")
        return {"success": True, "path": path, "note": "处理完成"}

    def summary(self, result: dict) -> str:
        if not result.get("success"):
            return f"处理失败：{result.get('error', '未知错误')}"
        return f"已处理 {result.get('path')}"

    # def detail(self, args: dict, result: dict) -> str:
    #     return "想给人看更好读的展开说明时覆盖它（默认渲染 参数 + 结果）"
