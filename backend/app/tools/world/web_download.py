"""web_download — 下载文件

下载网络文件（网页 HTML / CSS / JS / 图片等）保存到世界文件夹。
"""
from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import web_download


class WebDownloadTool(WorldToolPlugin):
    name = 'web_download'
    label = '下载文件'
    segment = 'net'

    description = (
        '下载网络文件（网页 HTML / CSS / JS / 图片等）保存到世界文件夹。\n注意：首次调用会返回 need_confirm + confirm_id——你必须先在回复里询问用户是否允许下载（说明是什么文件、'
        '大概多大），用户同意后再用同样的 url + confirm_id + confirmed=true 调用第二次完成下载。'
    )

    parameters = {'url': {'type': 'string', 'description': '下载链接（http/https）'},
     'path': {'type': 'string', 'description': '世界文件夹内保存路径（可选，如 assets/style.css；不填自动按文件名/类型命名）'},
     'confirm_id': {'type': 'string', 'description': '用户确认后第二次调用时携带（第一次返回的 confirm_id）'},
     'confirmed': {'type': 'boolean', 'description': '用户确认后传 true'}}

    required = ['url']

    async def execute(self, ctx: WorldToolContext) -> dict:
        return await web_download(ctx.world, ctx.arguments)

    def summary(self, result: dict) -> str:
        ok = bool(result.get("success"))
        if result.get("status") == "need_confirm":
            return f"下载请求待确认（{result.get('url', '')[:60]}，保存到 {result.get('path', '')}）——请询问用户是否允许"
        if ok:
            return f"已下载到世界文件夹：{result.get('path', '')}（{result.get('size', 0)}B）"
        return f"下载失败：{result.get('error', '未知错误')}"
