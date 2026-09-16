"""web_download — 下载文件

从网络下载文件（网页 HTML / CSS / JS / 图片 / 代码等）保存到世界固定目录 downloads/。
"""

from app.tools.world.base import WorldToolPlugin, WorldToolContext
from app.tools.world.shared import web_download


class WebDownloadTool(WorldToolPlugin):
    name = 'web_download'
    label = '下载文件'
    segment = 'net'

    description = (
        '从网络下载文件（网页 HTML / CSS / JS / 图片 / 代码等），一律保存到世界固定目录 downloads/。\n'
        '支持代码站：GitHub 的 blob 页面链接会自动转成 raw 直链，可直接下载源码。\n'
        '硬性规则：\n'
        '1. 严禁下载色情、暴力、违法内容——平台会按链接/文件名/正文拦截并记录，命中即失败；\n'
        '2. 严禁下载可执行文件、安装包、脚本（.exe/.msi/.dll/.bat/.cmd/.sh/.ps1/.vbs/.jar/.apk 等）'
        '——创建即拒绝，遗留的会被强制删除；代码只允许 .js/.py 与纯文本源码（.ts/.css/.md/.json 等）。\n'
        '审阅模式下平台会自动弹窗请用户确认下载，你不用自己问、也不用等——直接调用即可。'
    )

    parameters = {
        'url': {'type': 'string', 'description': '下载链接（http/https；GitHub blob 链接会自动转 raw）'},
        'path': {'type': 'string', 'description': '相对 downloads/ 的子路径（如 vue/vue.js）；不填自动按文件名/类型命名'},
    }

    required = ['url']

    async def execute(self, ctx: WorldToolContext) -> dict:
        return await web_download(ctx.world, ctx.arguments, approved=ctx.approved)

    def summary(self, result: dict) -> str:
        if result.get("success"):
            via = f"（经镜像 {result['via']}）" if result.get("via") else ""
            return f"已下载到 {result.get('path', '')}（{result.get('size', 0)}B）{via}"
        return f"下载失败：{result.get('error', '未知错误')}"
