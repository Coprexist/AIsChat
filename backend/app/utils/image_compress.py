"""
图片压缩工具 —— 上传后自动压缩，减少存储占用。
无数据库/网络依赖，纯函数。
"""
import io
import logging

logger = logging.getLogger(__name__)

# 压缩目标：头像 256x256 + 最大 2MB，普通图片 1920 宽
AVATAR_MAX_PX = 256
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2MB
IMAGE_MAX_WIDTH = 1920
JPEG_QUALITY = 85


def compress_image(content: bytes, mime_type: str = "", max_px: int = IMAGE_MAX_WIDTH) -> bytes:
    """
    压缩图片（纯函数，零 IO 依赖）。

    参数:
        content: 原始图片字节
        mime_type: 图片类型（image/png, image/jpeg, image/webp 等）
        max_px: 最大宽/高像素，超过则等比缩放

    返回: 压缩后的字节（JPEG 格式）
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow 未安装，跳过图片压缩")
        return content

    try:
        img = Image.open(io.BytesIO(content))
    except Exception as e:
        logger.warning(f"图片打开失败，保留原图: {e}")
        return content

    # 转换为 RGB（去除 alpha 通道，JPEG 不支持）
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # 等比缩放
    w, h = img.size
    if max_px > 0 and max(w, h) > max_px:
        ratio = max_px / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        try:
            # 优先用 LANCZOS，失败回退 ANTIALIAS
            resample = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', Image.BICUBIC))
        except Exception:
            resample = Image.BICUBIC
        img = img.resize(new_size, resample)

    # 输出为 JPEG
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    result = out.getvalue()

    saved_pct = (1 - len(result) / max(len(content), 1)) * 100
    logger.info(f"图片压缩: {len(content)}→{len(result)} bytes ({saved_pct:.0f}% 缩减), {w}x{h}→{img.size[0]}x{img.size[1]}")

    return result


def compress_avatar(content: bytes) -> bytes:
    """压缩头像图片（最大 256px + 2MB，逐级降质量直至达标）"""
    result = compress_image(content, mime_type="image/jpeg", max_px=AVATAR_MAX_PX)
    # 如果仍超 2MB，逐级降 JPEG 质量
    quality = JPEG_QUALITY
    while len(result) > AVATAR_MAX_BYTES and quality > 20:
        quality -= 15
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            if img.mode in ("RGBA", "P", "LA"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > AVATAR_MAX_PX:
                ratio = AVATAR_MAX_PX / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), getattr(Image, 'LANCZOS', Image.BICUBIC))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            result = out.getvalue()
        except Exception:
            break
    return result
