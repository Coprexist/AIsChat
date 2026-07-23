"""
LLM 厂商预设 — 常用 API 提供商的默认配置
每个预设含：base_url、聊天/工作/embedding 模型、是否支持深度推理、可用模型列表
"""

from typing import TypedDict


class ProviderPreset(TypedDict):
    key: str
    label: str
    base_url: str
    api_key_url: str  # 获取 API Key 的官网链接
    chat_model: str
    work_model: str
    embedding_model: str
    thinking_supported: bool
    models: list[dict]  # {value, label}


PRESETS: dict[str, ProviderPreset] = {
    # ── DeepSeek ──
    "deepseek": {
        "key": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key_url": "https://platform.deepseek.com/api_keys",
        "chat_model": "deepseek-v4-flash",
        "work_model": "deepseek-v4-pro",
        "embedding_model": "deepseek-embed",
        "thinking_supported": True,
        "models": [
            {"value": "deepseek-v4-flash", "label": "DeepSeek V4 Flash（快速）"},
            {"value": "deepseek-v4-pro", "label": "DeepSeek V4 Pro（高质量）"},
        ],
    },

    # ── OpenAI ──
    "openai": {
        "key": "openai",
        "label": "OpenAI / ChatGPT",
        "base_url": "https://api.openai.com",
        "api_key_url": "https://platform.openai.com/api-keys",
        "chat_model": "gpt-4o",
        "work_model": "gpt-4o",
        "embedding_model": "text-embedding-3-small",
        "thinking_supported": False,
        "models": [
            {"value": "gpt-4o", "label": "GPT-4o（推荐）"},
            {"value": "gpt-4o-mini", "label": "GPT-4o Mini（快速廉价）"},
            {"value": "gpt-4.1", "label": "GPT-4.1"},
            {"value": "o4-mini", "label": "o4 Mini（推理）"},
        ],
    },

    # ── Ollama 本地 ──
    "ollama": {
        "key": "ollama",
        "label": "Ollama（本地）",
        "base_url": "http://localhost:11434",
        "api_key_url": "",
        "chat_model": "qwen3",
        "work_model": "qwen3:14b",
        "embedding_model": "nomic-embed-text",
        "thinking_supported": False,
        "models": [
            {"value": "qwen3", "label": "Qwen3"},
            {"value": "qwen3:14b", "label": "Qwen3 14B"},
            {"value": "llama4", "label": "Llama 4"},
            {"value": "mistral", "label": "Mistral"},
            {"value": "deepseek-r1:8b", "label": "DeepSeek R1 8B"},
        ],
    },

    # ── 通义千问 / DashScope ──
    "qwen": {
        "key": "qwen",
        "label": "通义千问（阿里云 DashScope）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_url": "https://dashscope.console.aliyun.com/apiKey",
        "chat_model": "qwen-plus",
        "work_model": "qwen-max",
        "embedding_model": "text-embedding-v3",
        "thinking_supported": True,
        "models": [
            {"value": "qwen-plus", "label": "Qwen Plus（均衡）"},
            {"value": "qwen-max", "label": "Qwen Max（最强）"},
            {"value": "qwen-turbo", "label": "Qwen Turbo（快速）"},
            {"value": "qwq-plus", "label": "QwQ Plus（深度推理）"},
        ],
    },

    # ── Kimi / Moonshot ──
    "kimi": {
        "key": "kimi",
        "label": "Kimi（月之暗面 Moonshot）",
        "base_url": "https://api.moonshot.cn",
        "api_key_url": "https://platform.moonshot.cn/console/api-keys",
        "chat_model": "moonshot-v1-8k",
        "work_model": "moonshot-v1-32k",
        "embedding_model": "",
        "thinking_supported": False,
        "models": [
            {"value": "moonshot-v1-8k", "label": "Moonshot 8K"},
            {"value": "moonshot-v1-32k", "label": "Moonshot 32K"},
            {"value": "moonshot-v1-128k", "label": "Moonshot 128K"},
            {"value": "kimi-latest", "label": "Kimi Latest"},
        ],
    },

    # ── 智谱 GLM ──
    "zhipu": {
        "key": "zhipu",
        "label": "智谱 AI（GLM）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "chat_model": "glm-4-flash",
        "work_model": "glm-4",
        "embedding_model": "embedding-2",
        "thinking_supported": False,
        "models": [
            {"value": "glm-4-flash", "label": "GLM-4 Flash（快速）"},
            {"value": "glm-4", "label": "GLM-4（均衡）"},
            {"value": "glm-4-plus", "label": "GLM-4 Plus（高质量）"},
        ],
    },

    # ── 硅基流动 SiliconFlow ──
    "siliconflow": {
        "key": "siliconflow",
        "label": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn",
        "api_key_url": "https://cloud.siliconflow.cn/account/ak",
        "chat_model": "Qwen/Qwen3-8B",
        "work_model": "deepseek-ai/DeepSeek-V3",
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "thinking_supported": False,
        "models": [
            {"value": "Qwen/Qwen3-8B", "label": "Qwen3 8B"},
            {"value": "deepseek-ai/DeepSeek-V3", "label": "DeepSeek V3"},
            {"value": "deepseek-ai/DeepSeek-R1", "label": "DeepSeek R1"},
            {"value": "meta-llama/Llama-4-Maverick-17B-128E-Instruct", "label": "Llama 4 Maverick"},
        ],
    },
}


def get_preset(key: str) -> ProviderPreset | None:
    """获取指定厂商预设"""
    return PRESETS.get(key)


def get_all_presets() -> list[ProviderPreset]:
    """获取所有厂商预设（简要，不含 models 详情）"""
    return [
        {
            "key": p["key"],
            "label": p["label"],
            "base_url": p["base_url"],
            "api_key_url": p["api_key_url"],
            "chat_model": p["chat_model"],
            "work_model": p["work_model"],
            "embedding_model": p["embedding_model"],
            "thinking_supported": p["thinking_supported"],
            "models": p["models"],
        }
        for p in PRESETS.values()
    ]
