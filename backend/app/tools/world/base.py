"""群视界世界工具的插件基类与注册中心。

一个工具一个文件（app/tools/world/<name>.py）：schema、执行、展示三件事写在同一个类里，
子类被定义时自动注册。展示文案因此不可能漏——没实现 summary() 的类根本注册不进来。

运行期开销不比原来那条 if 链差：分发是字典查表，schema 定义列表首次构建后缓存。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# 工具分组：管理面板 / 卡片归类用，纯展示，不参与执行
SEGMENTS: dict[str, str] = {
    "file": "世界文件",
    "group": "群聊",
    "memory": "记忆",
    "net": "网络",
    "world": "世界",
    "self": "自我管理",
}

# 详情里的结果裁剪长度：详情是给人看的，不该把整篇文章塞进卡片
_DETAIL_LIMIT = 4000

# 结果里可以当「一句话」用的字段，按优先级
_GIST_KEYS = ("result", "message", "output", "summary", "note", "data", "stdout")


def result_gist(result: dict, limit: int = 120) -> str:
    """从工具返回值里抠一句人话；都没有就退化成其余字段的截断 JSON。"""
    for key in _GIST_KEYS:
        value = result.get(key)
        if value in (None, "", [], {}):
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        text = " ".join(text.split())
        if text:
            return text[:limit] + ("…" if len(text) > limit else "")
    rest = {k: v for k, v in result.items() if k not in ("success", "skipped")}
    if not rest:
        return ""
    text = " ".join(json.dumps(rest, ensure_ascii=False).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def default_detail(args: dict, result: dict) -> str:
    """通用详情渲染：参数 + 结果原文（截断保护）"""
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if len(text) > _DETAIL_LIMIT:
        text = text[:_DETAIL_LIMIT] + "\n…（已截断）"
    return f"参数\n{json.dumps(args, ensure_ascii=False, indent=2)}\n\n结果\n{text}"


@dataclass(slots=True)
class WorldToolContext:
    """一次工具调用的全部输入（省得每个 execute 都拖一长串同名参数）"""

    world_repo: Any
    world: Any
    arguments: str                      # 原始 JSON 字符串（少数工具自己解析）
    args: dict                          # 已解析的参数
    turn_state: dict | None = None
    on_progress: Callable[[str], Awaitable[None]] | None = None

    async def progress(self, note: str) -> None:
        """耗时工具的分阶段进度回调（转发为 [TOOL_UPDATE] update 事件）"""
        if self.on_progress is not None:
            await self.on_progress(note)


class WorldToolPlugin:
    """世界工具插件：一个类 = 一个工具"""

    # ── 必须声明 ──
    name: str = ""                      # 工具名（LLM function name）
    label: str = ""                     # 中文名，卡片标题
    segment: str = ""                   # 分组，见 SEGMENTS
    description: str = ""               # 给 LLM 看的说明
    parameters: dict = {}               # JSON Schema properties
    required: list = []

    # ── 可选 ──
    exposed: bool = True                # False：只由斜杠命令/内部调用触发，不发给 LLM

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.name:
            WorldToolRegistry.register(cls)

    @classmethod
    def to_definition(cls) -> dict:
        """OpenAI Function Calling 定义"""
        return {
            "type": "function",
            "segment": cls.segment,
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": {
                    "type": "object",
                    "properties": cls.parameters,
                    "required": cls.required,
                },
            },
        }

    async def execute(self, ctx: WorldToolContext) -> dict:
        raise NotImplementedError(f"{self.name}.execute() 未实现")

    def summary(self, result: dict) -> str:
        """卡片折叠态那一行。每个工具必须自己定义，不做通用兜底。"""
        raise NotImplementedError(f"{self.name}.summary() 未实现")

    def detail(self, args: dict, result: dict) -> str:
        """卡片展开后的详细说明。默认给「参数 + 结果」；想更好读就覆盖它。"""
        return default_detail(args, result)


class WorldToolRegistry:
    """世界工具注册中心（定义即注册，无手工清单）"""

    _plugins: dict[str, WorldToolPlugin] = {}
    _definitions: list[dict] | None = None

    @classmethod
    def register(cls, plugin_cls: type[WorldToolPlugin]) -> None:
        if plugin_cls.summary is WorldToolPlugin.summary:
            raise TypeError(f"世界工具 {plugin_cls.name} 必须实现 summary()（卡片那一行显示什么）")
        if not plugin_cls.label:
            raise TypeError(f"世界工具 {plugin_cls.name} 必须声明 label（中文名）")
        if plugin_cls.segment not in SEGMENTS:
            raise TypeError(f"世界工具 {plugin_cls.name} 的 segment 非法：{plugin_cls.segment!r}")
        if plugin_cls.exposed and not plugin_cls.description:
            raise TypeError(f"世界工具 {plugin_cls.name} 对外暴露，必须声明 description（给 LLM 看的说明）")
        if not isinstance(plugin_cls.parameters, dict):
            raise TypeError(f"世界工具 {plugin_cls.name} 的 parameters 必须是 dict（无参数就用 {{}}）")

        existing = cls._plugins.get(plugin_cls.name)
        if existing is not None:
            if type(existing) is plugin_cls:
                return                                  # 重复导入（如热重载），静默跳过
            logger.warning(f"世界工具 {plugin_cls.name} 重复注册（不同类），已覆盖")
        cls._plugins[plugin_cls.name] = plugin_cls()
        cls._definitions = None                          # 定义列表惰性重建

    @classmethod
    def get(cls, name: str) -> WorldToolPlugin | None:
        return cls._plugins.get(name)

    @classmethod
    def all(cls) -> list[WorldToolPlugin]:
        return list(cls._plugins.values())

    @classmethod
    def definitions(cls) -> list[dict]:
        """给 LLM 的工具定义（只含对外暴露的；结果缓存，别在热路径里重建）"""
        if cls._definitions is None:
            cls._definitions = [
                p.to_definition() for p in cls._plugins.values() if p.exposed
            ]
        return cls._definitions

    @classmethod
    def reset(cls) -> None:
        """测试用：清空注册表"""
        cls._plugins = {}
        cls._definitions = None
