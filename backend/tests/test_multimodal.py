"""附件 → LLM 多模态 content（app/utils/multimodal.py）—— 纯函数 + 真文件，零网络。

本文件第一条用例钉的就是 2026-09-13 的 P0：image_attachments() 直接迭代
normalize_attachments() 的返回值，而后者的契约是 list | None，于是
「不带附件的普通消息」整条路径抛 TypeError（NoneType 不是可迭代对象），群视界每轮必炸。

另有两条产品不变式：
- 没有可用图片时返回**纯字符串**（payload 与不带图时完全一致，prompt cache 友好）；
- 历史消息只给 [图片] 占位、只有最新一条带真实字节（护 cache + 防 token 爆炸）。
"""
import base64
import contextlib
import os
import shutil
import tempfile

from app.utils.multimodal import (
    IMAGE_NOTE_PREFIX,
    IMAGE_PLACEHOLDER,
    VISION_UNSUPPORTED_HINT,
    build_content,
    image_attachments,
    image_note,
    image_placeholder,
    injected_image_count,
    is_image,
    is_vision_unsupported_error,
    messages_have_images,
    strip_image_parts,
)

# 1x1 透明 PNG
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
IMG = {"file_id": 1, "path": "a.png", "name": "a.png", "size": len(PNG_1PX), "mime_type": "image/png"}
TXT = {"file_id": 2, "path": "a.txt", "name": "a.txt", "size": 1, "mime_type": "text/plain"}


@contextlib.contextmanager
def _data_dir(files):
    """临时 data_dir（用完即删）；multimodal 把 path 拼在 data_dir 之下。"""
    root = tempfile.mkdtemp(prefix="multimodal-test-")
    try:
        for rel, blob in files.items():
            physical = os.path.join(root, rel)
            os.makedirs(os.path.dirname(physical), exist_ok=True)
            with open(physical, "wb") as fh:
                fh.write(blob)
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── P0：契约必须兜住 None ────────────────────────────────────────────────

def test_image_attachments_never_raises_on_degenerate_input():
    """P0 本体：契约是 list | None；直接迭代 None 会让群视界每轮必炸"""
    for bad in (None, "坏了", "null", 0, [], ()):
        assert image_attachments(bad) == [], repr(bad)


def test_image_attachments_filters_non_images():
    assert image_attachments([IMG, TXT]) == [IMG]
    assert image_attachments('[]') == []
    assert image_attachments([TXT]) == []


def test_is_image_looks_at_mime_type_only():
    assert is_image({"mime_type": "image/png"})
    assert is_image({"mime_type": "IMAGE/JPEG"})
    assert not is_image({"mime_type": "text/plain"})
    assert not is_image({"name": "a.png"}), "只看 mime_type，不看扩展名"


def test_placeholder_counts_images():
    assert image_placeholder(None) == ""
    assert image_placeholder([TXT]) == ""
    assert image_placeholder([IMG]) == IMAGE_PLACEHOLDER
    assert image_placeholder([IMG, {**IMG, "file_id": 9}]) == IMAGE_PLACEHOLDER + "×2"


# ── build_content ───────────────────────────────────────────────────────

def test_build_content_is_a_plain_string_without_images():
    """无图 → str，不是单元素 parts 列表（payload 与历史完全一致）"""
    assert build_content("你好", None, "/x") == "你好"
    assert build_content("你好", [TXT], "/x") == "你好"
    assert build_content(None, None, "/x") == ""
    assert build_content(None, [TXT], "/x") == ""


def test_build_content_injects_a_real_data_url():
    with _data_dir({"a.png": PNG_1PX}) as data_dir:
        parts = build_content("看图", (IMG,), data_dir)
    assert isinstance(parts, list), "有图时必须变成多模态 parts，否则图片被静默丢弃"
    assert parts[0] == {"type": "text", "text": "看图"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_build_content_uses_placeholder_when_text_is_empty():
    with _data_dir({"a.png": PNG_1PX}) as data_dir:
        parts = build_content("", (IMG,), data_dir)
    assert parts[0] == {"type": "text", "text": IMAGE_PLACEHOLDER}


def test_build_content_falls_back_to_text_when_file_is_gone():
    """图丢了（文件被清）→ 退回纯文本，不能变成残缺多模态让模型 400"""
    assert build_content("看图", (IMG,), "/nonexistent-dir-xyz") == "看图"


def test_build_content_falls_back_when_oversized():
    with _data_dir({"a.png": PNG_1PX}) as data_dir:
        assert build_content("看图", (IMG,), data_dir, max_bytes=1) == "看图"


def test_build_content_declares_skipped_images():
    """单条默认只注入 1 张，其余必须明说「另有 N 张未提供」，否则模型会去找不存在的图"""
    with _data_dir({"a.png": PNG_1PX, "b.png": PNG_1PX}) as data_dir:
        attachments = (IMG, {**IMG, "file_id": 2, "path": "b.png"})
        parts = build_content("看图", attachments, data_dir)
    assert injected_image_count(parts) == 1
    assert any("另有 1 张图片未提供" in p.get("text", "") for p in parts)


# ── 便签与视觉降级 ───────────────────────────────────────────────────────

def test_injected_image_count_only_counts_image_parts():
    assert injected_image_count("纯文本") == 0
    assert injected_image_count(None) == 0
    assert injected_image_count([{"type": "text", "text": "x"}]) == 0
    assert injected_image_count([{"type": "image_url", "image_url": {}}]) == 1


def test_image_note_states_the_platform_fact():
    note = image_note(2)
    assert note.startswith(IMAGE_NOTE_PREFIX)
    assert "2 张图片" in note


def test_strip_image_parts_removes_images_and_rewrites_the_note():
    """图片与「你能看图」便签必须同时消失 —— 留下便签就是对纯文本模型撒谎"""
    messages = [
        {"role": "system", "content": "静态前缀"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这是什么"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ],
        },
        {"role": "system", "content": image_note(1)},
    ]
    degraded, removed = strip_image_parts(messages)

    assert removed == 1
    assert not messages_have_images(degraded)
    assert all(
        not (isinstance(m["content"], str) and m["content"].startswith(IMAGE_NOTE_PREFIX))
        for m in degraded
    ), "便签必须被改写掉"
    assert VISION_UNSUPPORTED_HINT in str(degraded[1]["content"])
    assert "data:image" not in str(degraded), "图片字节必须真的没了"
    assert degraded[0] == messages[0], "无关消息原样保留"


def test_strip_image_parts_leaves_plain_messages_untouched():
    messages = [{"role": "user", "content": "纯文本"}, {"role": "system", "content": "x"}]
    degraded, removed = strip_image_parts(messages)
    assert removed == 0
    assert degraded == messages


def test_is_vision_unsupported_error_matches_real_wording():
    for text in (
        "400 Invalid image_url: this model does not support image input",
        "模型不支持图片输入",
        "unknown modality: image",
    ):
        assert is_vision_unsupported_error(text), text


def test_is_vision_unsupported_error_ignores_unrelated_failures():
    """宁可漏判也不能误判：401/404/429 都不该被当成"模型不吃图"去降级"""
    for text in ("401 Incorrect API key provided", "404 Not Found",
                 "429 rate limit exceeded", "", None):
        assert not is_vision_unsupported_error(text), repr(text)
