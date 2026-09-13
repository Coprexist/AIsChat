"""LLM 端点拼接（app/utils/pure/llm_endpoint.py）—— 纯函数，零 IO。

守 2026-09-13 的两起真实事故：
1. 小米 MiMo 的 /models 是 404（漏了 /v1）→ 绑定 API Key **必失败**；
2. 通义千问的 preset base_url 自带 /v1，再被补一次 → /v1/v1/chat/completions 404。

规则本身只有一句话：**base_url 末尾已有版本段（/vN）就不再补，否则补 /v1**。
本文件既钉死这条规则，也用真实 PRESETS 做一次全覆盖（新增预设写错 base_url 会当场红）。
"""
from app.services.agent.provider_presets import PRESETS
from app.utils.pure.llm_endpoint import (
    api_root,
    chat_completions_url,
    embeddings_url,
    models_url,
)


def test_appends_v1_when_missing():
    """MiMo 事故：不补 /v1 会让 /models 变成 404（openresty 直接 404）"""
    assert api_root("https://api.xiaomimimo.com") == "https://api.xiaomimimo.com/v1"
    assert models_url("https://api.xiaomimimo.com") == "https://api.xiaomimimo.com/v1/models"


def test_does_not_append_when_version_present():
    """通义千问事故：base_url 自带 /v1，再补就成 /v1/v1 → 404（此前聊天一直是坏的）"""
    dashscope = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert api_root(dashscope) == dashscope, "自带 /v1 的 base_url 不能再补一次"
    assert chat_completions_url(dashscope) == dashscope + "/chat/completions"


def test_keeps_non_v1_version_segment():
    """智谱的版本段是 v4，不是 v1 —— 不能假设版本号一定是 1"""
    zhipu = "https://open.bigmodel.cn/api/paas/v4"
    assert chat_completions_url(zhipu) == zhipu + "/chat/completions"


def test_strips_trailing_slash():
    assert api_root("https://api.deepseek.com/") == "https://api.deepseek.com/v1"
    assert api_root("https://api.deepseek.com///") == "https://api.deepseek.com/v1"


def test_empty_or_none_base_url_does_not_crash():
    assert api_root("") == "/v1"
    assert api_root(None) == "/v1"
    assert chat_completions_url(None) == "/v1/chat/completions"


def test_embeddings_accepts_a_full_path():
    """embedding 的 base_url 允许直接给到 /embeddings，不能再给它拼一层"""
    full = "http://localhost:11434/v1/embeddings"
    assert embeddings_url(full) == full
    assert embeddings_url("http://localhost:11434/v1") == full
    assert embeddings_url("http://localhost:11434") == full


def test_every_preset_produces_a_wellformed_endpoint():
    """真实预设全覆盖：chat / models 端点都不能出现重复版本段"""
    assert PRESETS, "预设列表不该为空"
    for key, preset in PRESETS.items():
        base = preset["base_url"]
        assert base.startswith(("http://", "https://")), key
        for url in (chat_completions_url(base), models_url(base)):
            assert "/v1/v1" not in url, f"{key} 重复版本段: {url}"
            assert url.count("/v1/") <= 1, f"{key} 多个版本段: {url}"

        chat = chat_completions_url(base)
        assert chat.endswith("/chat/completions"), f"{key}: {chat}"
        assert chat.count("/chat/completions") == 1, f"{key}: {chat}"
