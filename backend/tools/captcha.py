"""CAPTCHA recognition tool using ddddocr (offline OCR + slide gap detection).

Single-function entry point::

    result = await captcha(type="ocr", image_bytes="iVBOR...")
    result = await captcha(type="slide", image_bytes="...",
                           background_bytes="...")
"""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

_DDDDOCR: Any = None
_OCR: Any = None
_SLIDE: Any = None
_ocr_lock = asyncio.Lock()
_slide_lock = asyncio.Lock()
_ddddocr_lock = asyncio.Lock()

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


async def _get_ddddocr():
    global _DDDDOCR
    if _DDDDOCR is None:
        async with _ddddocr_lock:
            if _DDDDOCR is None:
                import ddddocr
                _DDDDOCR = ddddocr
    return _DDDDOCR


async def _get_ocr():
    global _OCR
    if _OCR is None:
        async with _ocr_lock:
            if _OCR is None:
                ddddocr = await _get_ddddocr()
                _OCR = ddddocr.DdddOcr(show_ad=False)
    return _OCR


async def _get_slide():
    global _SLIDE
    if _SLIDE is None:
        async with _slide_lock:
            if _SLIDE is None:
                ddddocr = await _get_ddddocr()
                _SLIDE = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
    return _SLIDE


def _strip_data_prefix(s: str) -> str:
    m = re.match(r"^data:image/[a-z0-9+.-]+;base64,", s)
    if m:
        return s[m.end():]
    return s


def _decode_image_bytes(image_bytes: str) -> bytes:
    try:
        raw = base64.b64decode(_strip_data_prefix(image_bytes))
    except Exception as e:
        raise ValueError(f"image_bytes base64 解码失败: {e}")
    if not raw:
        raise ValueError("image_bytes 解码后为空")
    return raw


def _read_image_path(image_path: str) -> bytes:
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")
    if p.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的图片格式: {p.suffix}，"
            f"仅支持 {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )
    return p.read_bytes()


def _resolve_image(image_bytes: str | None, image_path: str | None) -> bytes:
    if image_bytes:
        return _decode_image_bytes(image_bytes)
    if image_path:
        return _read_image_path(image_path)
    raise ValueError("必须提供 image_bytes 或 image_path")


async def captcha(
    type: str,
    image_bytes: str | None = None,
    image_path: str | None = None,
    background_bytes: str | None = None,
) -> dict[str, Any]:
    if type not in ("ocr", "slide"):
        return {"ok": False, "error": f"不支持的验证码类型: {type}，仅支持 ocr 或 slide"}

    try:
        img = _resolve_image(image_bytes, image_path)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}

    if type == "ocr":
        try:
            ocr = await _get_ocr()
            text = await asyncio.to_thread(ocr.classification, img)
        except Exception as e:
            logger.debug("captcha ocr failed: %s", e)
            return {"ok": False, "error": f"OCR 识别失败: {e}"}

        if not text:
            return {"ok": False, "error": "OCR 识别结果为空"}
        return {"ok": True, "result": {"text": text}}

    if type == "slide":
        if not background_bytes:
            return {"ok": False, "error": "slide 模式必须提供 background_bytes"}

        try:
            bg = _decode_image_bytes(background_bytes)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        try:
            slide = await _get_slide()
            res = await asyncio.to_thread(slide.slide_match, img, bg)
        except Exception as e:
            logger.debug("captcha slide_match failed: %s", e)
            return {"ok": False, "error": f"滑块缺口检测失败: {e}"}

        target = res.get("target")
        if not isinstance(target, (list, tuple)) or len(target) != 4:
            return {"ok": False, "error": f"滑块缺口检测返回异常数据: {res}"}

        x1, y1, x2, y2 = target
        target_x = (x1 + x2) // 2
        target_y = (y1 + y2) // 2
        return {"ok": True, "result": {"target_x": target_x, "target_y": target_y}}

    return {"ok": False, "error": f"未知的验证码类型: {type}"}
