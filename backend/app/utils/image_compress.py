"""
图片压缩工具 —— 上传后自动压缩，减少存储占用。
无数据库/网络依赖，纯函数。

策略：
- 有透明通道（RGBA/PA）→ 保持 PNG，缩尺寸 + optimize
- 无透明通道 → JPEG，逐级降质量保证 ≤ 2MB（头像）/ 合理大小（普通图）
"""
import io
import logging

logger = logging.getLogger(__name__)

AVATAR_MAX_PX = 4096  # 与前端 AvatarCropModal.tsx AVATAR_MAX_PX 保持一致
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2MB
IMAGE_MAX_WIDTH = 1920
JPEG_QUALITY = 85


def _has_transparency(img) -> bool:
    """判断图片是否有 alpha 通道"""
    mode = getattr(img, 'mode', '')
    if mode in ('RGBA', 'PA', 'LA'):
        return True
    if mode == 'P':
        # 调色板模式可能有透明色
        try:
            transparency = img.info.get('transparency')
            return transparency is not None
        except Exception:
            return False
    return False


THUMBNAIL_PX = 128


def make_avatar_thumbnail(content: bytes) -> bytes:
    """生成 64x64 缩略图。GIF 返回原图。"""
    if _is_gif(content):
        return content
    from PIL import Image
    import io
    try:
        img = Image.open(io.BytesIO(content))
        img.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX), Image.LANCZOS)
        out = io.BytesIO()
        if _has_transparency(img):
            img.save(out, format='PNG', optimize=True)
        else:
            if img.mode not in ('RGB',): img = img.convert('RGB')
            img.save(out, format='JPEG', quality=75, optimize=True)
        return out.getvalue()
    except Exception:
        return content


def compress_image(content: bytes, mime_type: str = "", max_px: int = IMAGE_MAX_WIDTH) -> bytes:
    """
    压缩普通图片（最大宽度 max_px，等比缩放）。
    返回: 压缩后的字节（保持原格式或转 JPEG）
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

    w, h = img.size
    transparent = _has_transparency(img)

    # 等比缩放
    if max_px > 0 and max(w, h) > max_px:
        ratio = max_px / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        try:
            resample = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', Image.BICUBIC))
        except Exception:
            resample = Image.BICUBIC
        img = img.resize(new_size, resample)

    out = io.BytesIO()
    if transparent:
        # 保持 PNG 透明
        img.save(out, format="PNG", optimize=True)
    else:
        if img.mode not in ('RGB',):
            img = img.convert('RGB')
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    result = out.getvalue()
    saved_pct = (1 - len(result) / max(len(content), 1)) * 100
    logger.info(f"图片压缩: {len(content)}→{len(result)} bytes ({saved_pct:.0f}%), {w}x{h}→{img.size[0]}x{img.size[1]}, {'PNG' if transparent else 'JPEG'}")

    return result


def _is_gif(content: bytes) -> bool:
    """检测是否为 GIF 动图（GIF87a / GIF89a）"""
    return content[:6] in (b'GIF87a', b'GIF89a')


def compress_avatar(content: bytes) -> bytes:
    """
    压缩头像：最大 256px + 最大 2MB。
    GIF 动图直接返回原图保留动画。
    有透明通道 → PNG；无透明 → JPEG 逐级降质量。
    """
    if _is_gif(content):
        return content  # 保留动画
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow 未安装，跳过头像压缩")
        return content

    try:
        img = Image.open(io.BytesIO(content))
    except Exception as e:
        logger.warning(f"头像打开失败，保留原图: {e}")
        return content

    w, h = img.size
    transparent = _has_transparency(img)

    # 等比缩放到 256px
    if max(w, h) > AVATAR_MAX_PX:
        ratio = AVATAR_MAX_PX / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        try:
            resample = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', Image.BICUBIC))
        except Exception:
            resample = Image.BICUBIC
        img = img.resize(new_size, resample)

    out = io.BytesIO()

    if transparent:
        # PNG 保持透明，optimize 减体积
        img.save(out, format="PNG", optimize=True)
        result = out.getvalue()
        # PNG 仍超 2MB → 降颜色数
        if len(result) > AVATAR_MAX_BYTES:
            try:
                img_q = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT) if img.mode == 'RGBA' else img
                out2 = io.BytesIO()
                img_q.save(out2, format="PNG", optimize=True)
                result = out2.getvalue()
            except Exception:
                pass
    else:
        if img.mode not in ('RGB',):
            img = img.convert('RGB')
        # JPEG 逐级降质量
        for q in range(JPEG_QUALITY, 15, -15):
            out.seek(0)
            out.truncate()
            img.save(out, format="JPEG", quality=q, optimize=True)
            result = out.getvalue()
            if len(result) <= AVATAR_MAX_BYTES:
                break

    saved_pct = (1 - len(result) / max(len(content), 1)) * 100
    logger.info(f"头像压缩: {len(content)}→{len(result)} bytes ({saved_pct:.0f}%), {w}x{h}→{img.size[0]}x{img.size[1]}, {'PNG' if transparent else 'JPEG'}")

    return result
