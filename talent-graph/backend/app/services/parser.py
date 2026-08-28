"""简历文件文本提取：PDF/Word 直取文本，图片与扫描件走 PaddleOCR。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ocr_engine = None  # PaddleOCR 懒加载


def _extract_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    text = "\n".join(text_parts).strip()
    if len(text) < 50:  # 判定为扫描件，回退 OCR
        logger.info("PDF 文本过少，按扫描件走 OCR: %s", path.name)
        return _extract_pdf_ocr(path)
    return text


def _extract_pdf_ocr(path: Path) -> str:
    import fitz

    texts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            texts.append(_ocr_image_bytes(img_bytes))
    return "\n".join(texts)


def _extract_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _ocr_image_bytes(img_bytes: bytes) -> str:
    global _ocr_engine
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        raise ValueError(
            "该文件为扫描件/图片，需要 OCR 才能解析，但当前环境未安装 OCR 依赖"
            "（numpy / Pillow / paddleocr）。请在 backend 环境执行："
            "pip install numpy Pillow paddlepaddle paddleocr 后重新解析。"
        ) from e
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise ValueError(
                "该文件为扫描件/图片，需要 OCR 才能解析，但当前环境未安装 paddleocr。"
                "请在 backend 环境执行：pip install paddlepaddle paddleocr 后重新解析。"
            ) from e
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    import io

    img = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
    result = _ocr_engine.ocr(img, cls=True)
    lines: list[str] = []
    for block in result or []:
        for line in block or []:
            lines.append(line[1][0])
    return "\n".join(lines)


def extract_text(path: str | Path) -> str:
    """按扩展名分发提取。支持 .pdf/.docx/.doc(提示转docx)/.png/.jpg。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in (".docx",):
        return _extract_docx(path)
    if suffix in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        return _ocr_image_bytes(path.read_bytes())
    if suffix == ".doc":
        raise ValueError("旧版 .doc 请先转换为 .docx 再上传")
    raise ValueError(f"不支持的文件类型: {suffix}")
