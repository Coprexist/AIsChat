"""
通用配置持久化服务（system_settings.*_config JSONB）

把「前端图形化修改配置（DB 覆盖 env）」泛化为多配置组机制：
每个组 = system_settings 的一个 JSONB 列 + 字段 schema 声明。
加一组配置 = 在 CONFIG_GROUPS 里加一个声明，前后端自动支持。

现有组：
- embedding:  Embedding 提供方配置（embedding_config 列）
- runtime:    运行时参数（runtime_config 列）——检索参数/时区/摘要 TTL 等

机制：
- 加载：启动时读 DB → 解密敏感字段 → 填入缓存（settings 自动生效）
- 保存：管理 API 写入 → 加密敏感字段 → 更新 DB + 同步缓存（热生效）
- 恢复默认：清 DB 字段 + 清缓存（回到 env/默认值）
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_config_source import set_db_overrides, clear_db_overrides
from app.utils.crypto import encrypt_api_key, decrypt_api_key

logger = logging.getLogger(__name__)


def _refresh_settings() -> None:
    """重建全局 settings 实例（DB 覆盖热更新生效）。

    pydantic-settings 实例在创建时固定 source 快照，运行时改缓存后
    必须重建 Settings() 并替换模块级引用，现有 settings.xxx 读取才生效。
    """
    import app.config as config_module
    new_settings = config_module.Settings()
    config_module.settings = new_settings
    logger.info("🔄 settings 已重建（DB 配置覆盖生效）")


# ═══════════════════════════════════════════════════════════════
# 配置组 Schema 声明（加新配置组只需在这里加一个声明）
# ═══════════════════════════════════════════════════════════════

#: 字段类型 → 前端渲染控件映射（前端按此自动渲染表单）
FIELD_TYPES = ("select", "number", "float", "text", "secret", "boolean")

#: 说明文案用「」包裹中文引号，避免与 Python 字符串界定符冲突
CONFIG_GROUPS: dict[str, dict] = {
    # ── Embedding 提供方配置（已上线）──
    "embedding": {
        "column": "embedding_config",
        "label": "Embedding 向量配置",
        "hint": "控制 AI 记忆的「语义搜索」能力。改这里不需要懂代码——选一个后端、填地址、保存即可。",
        "fields": {
            "embedding_backend": {
                "type": "select",
                "label": "后端类型",
                "hint": "选择用谁来生成「向量」（记忆搜索的钥匙）。不启用 = 只用文字匹配，记忆功能正常但搜得没那么准。",
                "options": [
                    {"value": "disabled", "label": "不启用（纯文本检索）"},
                    {"value": "ollama", "label": "Ollama（本地）"},
                    {"value": "api", "label": "OpenAI 兼容 API"},
                    {"value": "local", "label": "本地模型（fastembed）"},
                ],
            },
            "embedding_base_url": {
                "type": "text", "label": "API 地址 (Base URL)",
                "hint": "向量服务在哪。Ollama 填 http://127.0.0.1:11434（本机）；用厂商 API 填 https://地址/v1。",
            },
            "embedding_api_key": {
                "type": "secret", "label": "API Key",
                "hint": "只有用「OpenAI 兼容 API」才需要。Ollama 和本地模型不用填。密钥加密保存，不会明文显示。",
            },
            "embedding_model": {
                "type": "text", "label": "模型",
                "hint": "具体用哪个模型。Ollama 常用 nomic-embed-text；不知道填什么就留空用默认。",
            },
            "embedding_dimension": {
                "type": "number", "label": "向量维度",
                "hint": "数字越大搜得越准、越占空间；越小越快越省。需与模型匹配（nomic-embed-text=768）。改这里一般不用动。",
            },
        },
        "encrypted": ["embedding_api_key"],  # 加密存储的字段（缓存里放明文）
    },
    # ── 运行时参数（第二批：检索调参 + 时区 + 摘要 TTL）──
    "runtime": {
        "column": "runtime_config",
        "label": "运行时参数",
        "hint": "调整 AI 检索记忆和展示时间的细节。这些是「锦上添花」的选项，不调也完全能用。",
        "fields": {
            "default_top_k": {
                "type": "number", "label": "默认检索条数 (top_k)",
                "hint": "AI 每次从记忆里翻出几条来参考。条数多 = 参考更全面但更费 token；少 = 更快更省。",
            },
            "vector_weight": {
                "type": "float", "label": "向量权重", "step": 0.05, "min": 0, "max": 1,
                "hint": "检索时「意思相近」的结果占多大比重。调高 = 更看重语义相似。",
            },
            "bm25_weight": {
                "type": "float", "label": "BM25 权重", "step": 0.05, "min": 0, "max": 1,
                "hint": "检索时「字面相同」的结果占多大比重。调高 = 更看重关键词完全一致。",
            },
            "time_decay_weight": {
                "type": "float", "label": "时间衰减权重", "step": 0.05, "min": 0, "max": 1,
                "hint": "最近的记忆占多大比重。调高 = 更优先最近的事。",
            },
            "display_timezone": {
                "type": "text", "label": "显示时区",
                "hint": "AI 看到的时间用哪个时区，如 Asia/Shanghai（中国）或 UTC。",
            },
            "summary_cache_ttl": {
                "type": "number", "label": "摘要缓存 TTL（秒）",
                "hint": "对话摘要缓存多久。600 = 10 分钟。调大省 token，调小更实时。",
            },
        },
        "encrypted": [],
    },
}


def get_group_schema(group: str) -> dict | None:
    """返回配置组 schema；未知组返回 None"""
    return CONFIG_GROUPS.get(group)


def _editable_keys(group: str) -> list[str]:
    return list(CONFIG_GROUPS[group]["fields"].keys())


# ═══════════════════════════════════════════════════════════════
# 通用读写
# ═══════════════════════════════════════════════════════════════

async def load_group_config(db: AsyncSession, group: str) -> None:
    """启动时加载某个配置组的 DB 覆盖进缓存（幂等）"""
    schema = CONFIG_GROUPS.get(group)
    if not schema:
        return
    from app.models.system_settings import SystemSettings
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return
    raw = getattr(row, schema["column"], None)
    if not raw:
        return
    cfg = dict(raw)
    # 解密敏感字段（存的是加密值，缓存里放明文供业务用）
    for field in schema.get("encrypted", []):
        enc_key = f"{field}_encrypted"
        if enc_key in cfg:
            try:
                cfg[field] = decrypt_api_key(cfg.pop(enc_key))
            except Exception as e:
                logger.warning(f"解密 {group}.{field} 失败: {e}")
    set_db_overrides(cfg)
    _refresh_settings()
    logger.info(f"🗄️ 已从 DB 加载配置覆盖 [{group}]: {list(cfg.keys())}")


async def load_all_configs(db: AsyncSession) -> None:
    """启动时加载全部配置组（main.py lifespan 调用）"""
    for group in CONFIG_GROUPS:
        await load_group_config(db, group)


async def save_group_config(db: AsyncSession, group: str, values: dict) -> dict:
    """保存某组配置（DB 持久化 + 缓存热更新）。返回保存后的缓存值。"""
    schema = CONFIG_GROUPS.get(group)
    if not schema:
        raise ValueError(f"未知配置组: {group}")
    from app.models.system_settings import SystemSettings

    editable = set(_editable_keys(group))
    clean = {k: v for k, v in values.items() if k in editable}
    if not clean:
        raise ValueError("没有可保存的配置项")

    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SystemSettings(id=1)
        db.add(row)

    # 合并现有配置（保留未提交的键）
    merged = dict(getattr(row, schema["column"], None) or {})
    for k, v in clean.items():
        merged[k] = v

    # 敏感字段单独加密存储
    for field in schema.get("encrypted", []):
        if field in merged:
            raw_key = merged.pop(field)
            if raw_key:
                merged[f"{field}_encrypted"] = encrypt_api_key(str(raw_key))
            else:
                merged.pop(f"{field}_encrypted", None)

    setattr(row, schema["column"], merged)
    await db.commit()

    # 同步缓存（敏感字段用明文进缓存）
    cache_cfg = {k: v for k, v in merged.items() if not k.endswith("_encrypted")}
    for field in schema.get("encrypted", []):
        enc_key = f"{field}_encrypted"
        if enc_key in merged:
            try:
                cache_cfg[field] = decrypt_api_key(merged[enc_key])
            except Exception:
                pass
    set_db_overrides(cache_cfg)
    _refresh_settings()
    logger.info(f"💾 配置已保存 [{group}]: {list(clean.keys())}")
    return cache_cfg


async def clear_group_config(db: AsyncSession, group: str) -> dict:
    """恢复默认：清 DB 字段 + 清缓存（回到 env/默认值）"""
    schema = CONFIG_GROUPS.get(group)
    if not schema:
        raise ValueError(f"未知配置组: {group}")
    from app.models.system_settings import SystemSettings
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is not None and getattr(row, schema["column"], None):
        setattr(row, schema["column"], None)
        await db.commit()
    clear_db_overrides()
    _refresh_settings()
    logger.info(f"🗑️ 配置已恢复默认 [{group}]")
    return {}


async def get_effective_config(db: AsyncSession, group: str) -> dict:
    """返回某组当前生效配置（DB 覆盖 + env 兜底，敏感字段脱敏）"""
    schema = CONFIG_GROUPS.get(group)
    if not schema:
        raise ValueError(f"未知配置组: {group}")
    from app.config import settings
    from app.db_config_source import get_db_override

    result: dict = {}
    for field in schema["fields"]:
        value = getattr(settings, field, None)
        # 敏感字段只报告是否已设置
        if field in schema.get("encrypted", []):
            result[f"{field}_set"] = bool(value)
        else:
            result[field] = value
    result["source"] = {
        f: ("db" if get_db_override(f) is not None else "env")
        for f in schema["fields"]
    }
    return result


# ═══════════════════════════════════════════════════════════════
# 兼容层（原 embedding_config_service 的接口，迁移期保留）
# ═══════════════════════════════════════════════════════════════

async def load_db_config(db: AsyncSession) -> None:
    """[兼容] 加载 embedding 配置（等价 load_group_config('embedding')）"""
    await load_group_config(db, "embedding")


async def save_db_config(db: AsyncSession, values: dict) -> dict:
    """[兼容] 保存 embedding 配置"""
    return await save_group_config(db, "embedding", values)


async def clear_db_config(db: AsyncSession) -> dict:
    """[兼容] 恢复 embedding 默认"""
    return await clear_group_config(db, "embedding")


async def get_effective_embedding_config(db: AsyncSession) -> dict:
    """[兼容] 获取 embedding 生效配置"""
    return await get_effective_config(db, "embedding")
