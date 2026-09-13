"""apply_world_block — 应用积木

应用积木：把积木文件直接部署进世界文件夹（blocks/{block_id}/），按返回的 usage 在页面中引入。
"""
import logging

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.services.world.world_blocks import apply_block


logger = logging.getLogger(__name__)


class ApplyWorldBlockTool(WorldToolPlugin):
    name = 'apply_world_block'
    label = '应用积木'
    segment = 'world'

    description = '应用积木：把积木文件直接部署进世界文件夹（blocks/{block_id}/），按返回的 usage 在页面中引入。'

    parameters = {'block_id': {'type': 'string', 'description': '积木 id'}}

    required = ['block_id']

    async def execute(self, ctx: WorldToolContext) -> dict:
        try:
            args = ctx.args
            block_id = str(args.get("block_id", "")).strip()
            if not block_id:
                return {"success": False, "error": "缺少 block_id 参数"}
            result = apply_block(ctx.world.id, block_id)
            # 积木更新（版本变化）→ 懒通知：下次对话注入世界 AI 上下文
            if result.get("is_update") and result.get("version") and result.get("previous_version") and result["version"] != result["previous_version"]:
                try:
                    from app.services.world.world_service import add_pending_notice
                    await add_pending_notice(
                        ctx.world_repo, ctx.world.id, f"blocks/{block_id}/", "积木更新",
                        f"积木「{result.get('name', block_id)}」已更新 v{result['previous_version']} → v{result['version']}；"
                        f"你的 DIY（blocks/{block_id}/diy/）已保留，主文件旧版备份在 .bak/ 可回滚。",
                    )
                except Exception as e:
                    # 通知丢失 → AI 不会知道积木变了；必须留痕
                    logger.warning(f"🌐 世界 #{ctx.world.id} 积木更新通知写入失败（block={block_id}）: {e}")
            return result
        except ValueError as e:
            return {"success": False, "error": str(e)}

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if ok:
            return (
                f"已应用积木「{result.get('name')}」→ {'、'.join(result.get('applied_files', []))}。"
                f"用法：{result.get('usage', '')[:60]}"
            )
        return f"应用积木失败：{result.get('error', '未知错误')}"
