"""
应用配置模块
从环境变量读取配置，提供全局设置
"""
import os
import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局应用配置"""

    # 数据库
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ai_chat:change_me@localhost:5432/ai_group_chat",
    )
    database_url_sync: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://ai_chat:change_me@localhost:5432/ai_group_chat",
    )

    # JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # API 默认配置
    deepseek_base_url: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    default_chat_model: str = "deepseek-v4-flash"
    default_work_model: str = "deepseek-v4-pro"
    # DeepSeek 不提供 embedding API，默认用 OpenAI 兼容模型
    # 设为空字符串可禁用向量检索（纯文本搜索降级）
    default_embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    @property
    def is_deepseek_api(self) -> bool:
        """自动检测当前 API 提供商是否为 DeepSeek"""
        return "deepseek.com" in self.deepseek_base_url

    def get_model_options(self) -> list[dict]:
        """
        返回可用模型选项列表。
        优先读环境变量 MODEL_OPTIONS（JSON），否则按 API 提供商给默认值。
        """
        raw = os.getenv("MODEL_OPTIONS", "")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        # 默认模型列表
        if self.is_deepseek_api:
            return [
                {"value": "deepseek-v4-flash", "label": "DeepSeek V4 Flash（快速）", "provider": "deepseek"},
                {"value": "deepseek-v4-pro", "label": "DeepSeek V4 Pro（高质量）", "provider": "deepseek"},
            ]
        else:
            # 通用 OpenAI 兼容 API：默认给两个常见档位
            return [
                {"value": self.default_chat_model, "label": f"{self.default_chat_model}（默认）", "provider": "generic"},
                {"value": self.default_work_model, "label": f"{self.default_work_model}（工作）", "provider": "generic"},
            ]

    @staticmethod
    def is_thinking_supported_for(base_url: str) -> bool:
        """检查某个 API base URL 是否支持 thinking/reasoning 参数"""
        return "deepseek.com" in base_url

    @property
    def data_dir(self) -> str:
        """容器内文件存储路径（docker-compose bind mount 目标，非宿主机 DATA_DIR）"""
        return "/app/data"

    # 头像
    avatar_max_size_mb: int = int(os.getenv("AVATAR_MAX_SIZE_MB", "10"))

    # 单文件上传大小上限
    upload_max_size_mb: int = int(os.getenv("UPLOAD_MAX_SIZE_MB", "32"))

    # 防滥用
    rate_limit_per_second: int = 2  # 每个 AI 每秒最多发言次数

    # 向量检索默认参数
    default_top_k: int = 10
    vector_weight: float = 0.6
    bm25_weight: float = 0.3
    time_decay_weight: float = 0.1

    # 意愿评分 + 自动免打扰全局默认
    default_auto_dnd_threshold: int = 20   # 意愿分数低于此值自动开 DND
    default_auto_dnd_duration: int = 5     # 自动 DND 时长（分钟）

    # 摘要缓存 TTL（秒）
    summary_cache_ttl: int = 600  # 10 分钟

    # v0.5.0: 系统监控指标保留天数（默认 30，管理员通过环境变量调整）
    agent_metrics_retention_days: int = int(os.getenv("AGENT_METRICS_RETENTION_DAYS", "30"))

    # v0.6.0: 额度消耗比例（1 credit = N tokens）
    credit_per_10k_tokens: int = int(os.getenv("CREDIT_PER_TOKENS", "10000"))

    # OpenCLI 集成
    opencli_global_enabled: bool = False
    opencli_default_rate_limit: int = 5     # 每分钟最多 N 次
    opencli_timeout_seconds: int = 60       # 单个命令超时时间
    opencli_stdout_max_chars: int = 2000    # stdout 截断长度

    # 加密密钥（用于 API Key 加密存储）
    encryption_key: str = os.getenv(
        "ENCRYPTION_KEY", jwt_secret_key
    )  # 默认复用 JWT key

    # 显示时区（用于 AI 系统提示词中的当前时间）
    display_timezone: str = os.getenv("DISPLAY_TIMEZONE", "Asia/Shanghai")

    # 联邦通信 — GitHub 注册表
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    registry_repo: str = os.getenv("REGISTRY_REPO", "ShuAICFR/AIsChat")
    registry_file: str = os.getenv("REGISTRY_FILE", "federation-registry.json")

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()

# 运行时可覆盖的配置（不持久化，重启后恢复为 env 默认值）
_runtime_overrides: dict = {}

def get_runtime_setting(key: str, default=None):
    return _runtime_overrides.get(key, default)

def set_runtime_setting(key: str, value):
    _runtime_overrides[key] = value

def get_effective_avatar_max_size_mb() -> int:
    return int(get_runtime_setting("avatar_max_size_mb", settings.avatar_max_size_mb))
