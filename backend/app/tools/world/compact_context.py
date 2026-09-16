"""compact_context — 压缩上下文

压缩对话上下文：把**保留窗口之外**的对话总结为摘要，释放模型上下文空间。
实现只有一处（world_chat_compact.compact_session），用户敲 /compact 走的是同一份——
不存在"命令压一次、工具压一次"两套口径。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext


class CompactContextTool(WorldToolPlugin):
    name = 'compact_context'
    label = '压缩上下文'
    segment = 'self'

    description = (
        '压缩对话上下文：把保留窗口之外的对话总结成摘要（最近几条会原样保留，不会被摘要掉）。\n'
        '用户说"压缩一下 / 收拢上下文 / 太长了你记不住"时调用它；系统提示接近上限时也该调用。\n'
        '注意：模型真正带的是**用户与你的对话**——工具卡片和思考过程不进模型上下文，'
        '所以"卡片很多"不等于"上下文很大"，调完看结果里的数字就知道实际压了多少。'
    )

    parameters = {}

    required = []

    async def execute(self, ctx: WorldToolContext) -> dict:
        from app.services.world.world_chat_compact import compact_session
        return await compact_session(ctx.world_repo, ctx.world)

    def summary(self, result: dict) -> str:
        """卡片那一行（唯一文案来源：/compact 命令也读这里）"""
        if not result.get("success"):
            return f"上下文压缩失败：{result.get('error', '未知错误')}"
        if result.get("skipped"):
            return (f"无需压缩：模型带的对话共 {result.get('real_messages', 0)} 条，"
                    f"最近 {result.get('keep_last', 0)} 条本来就会原样带上"
                    f"（工具卡片与思考不进模型上下文）")
        merged = "，已并入上次摘要" if result.get("merged_previous") else ""
        return (f"上下文已压缩：窗口外 {result.get('compressible', 0)} 条 → 摘要{merged}"
                f"（{result.get('before_tokens', 0)} → {result.get('after_tokens', 0)} tokens，"
                f"压掉 {result.get('compression_ratio_pct', 0)}%）")
