"""PDF 读取：优先按坐标重建文本层，扫描件可回退到 OCR。

针对真实发票 PDF 做了两处加固：
1. 有些 PDF 的字体描述符里同时写了 /FontFile2 和 /FontFile3（不规范），
   会让 pypdf 直接抛异常；这里先修掉多余键再提取，避免误判成"扫描件需要 OCR"；
2. 直接用 pypdf 默认顺序提取时，中文常被拆成单字、金额符号错位；
   改用 visitor 按坐标（先上下、再左右）重建行文本，字段更完整。
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import config
from core import ocr as ocr_module
from core.textutil import normalize

ROW_TOLERANCE = 4.0     # 同一行的 y 容差（点）
SPACE_GAP = 4.0         # 同一行内相邻片段间隔超过该值就补一个空格


# --------------------------------------------------------------------------
# 引擎探测
# --------------------------------------------------------------------------
def _pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401

        return True
    except Exception:
        return False


def _pymupdf_available() -> bool:
    try:
        import fitz  # noqa: F401

        return True
    except Exception:
        return False


def pdf_engine_status() -> Dict[str, bool]:
    return {"pypdf": _pypdf_available(), "pymupdf": _pymupdf_available()}


def _choose_engine(preferred: str = "auto") -> str:
    has_pypdf = _pypdf_available()
    has_mupdf = _pymupdf_available()
    if preferred == "pypdf" and has_pypdf:
        return "pypdf"
    if preferred == "pymupdf" and has_mupdf:
        return "pymupdf"
    if has_mupdf:
        return "pymupdf"
    if has_pypdf:
        return "pypdf"
    return ""


# --------------------------------------------------------------------------
# 字体描述符修复
# --------------------------------------------------------------------------
def _repair_font_descriptors(reader: Any) -> int:
    """删掉同一字体描述符里多余的 /FontFile* 键（pypdf 会因此报错）。"""
    fixed = 0
    for page in reader.pages:
        try:
            resources = page.get("/Resources") or {}
            fonts = resources.get("/Font") or {}
        except Exception:
            continue
        for ref in fonts.values():
            try:
                font = ref.get_object()
            except Exception:
                continue
            for descendant in font.get("/DescendantFonts") or []:
                try:
                    descriptor = descendant.get_object().get("/FontDescriptor")
                    if descriptor is None:
                        continue
                    descriptor = descriptor.get_object()
                except Exception:
                    continue
                keys = [k for k in ("/FontFile", "/FontFile2", "/FontFile3") if k in descriptor]
                if len(keys) > 1:
                    keep = "/FontFile2" if "/FontFile2" in keys else keys[0]
                    for key in keys:
                        if key != keep:
                            try:
                                del descriptor[key]
                                fixed += 1
                            except Exception:
                                pass
    return fixed


# --------------------------------------------------------------------------
# 坐标重建
# --------------------------------------------------------------------------
def _rows_from_page(page: Any) -> List[Tuple[float, float, str]]:
    """返回 [(y, x, 文本)] 片段列表（按页内坐标）。"""
    chunks: List[Tuple[float, float, str]] = []

    def visitor(text: str, cm, tm, font_dict, font_size) -> None:
        piece = (text or "").strip()
        if not piece:
            return
        try:
            y = float(tm[5])
            x = float(tm[4])
        except (TypeError, IndexError, ValueError):
            y = x = 0.0
        chunks.append((y, x, piece))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []
    return chunks


def _piece_width(text: str) -> float:
    """粗略估算文本宽度（点）：中日韩全角字符按 12pt，其余按 6pt。"""
    import unicodedata

    width = 0.0
    for char in text:
        if unicodedata.east_asian_width(char) in ("W", "F"):
            width += 12.0
        else:
            width += 6.0
    return width


def _reconstruct_lines(chunks: List[Tuple[float, float, str]]) -> str:
    """按"先上下、再左右"把片段拼回行文本。"""
    if not chunks:
        return ""
    ordered = sorted(chunks, key=lambda item: (-item[0], item[1]))

    lines: List[List[Tuple[float, float, str]]] = []
    for y, x, text in ordered:
        if lines and abs(lines[-1][0][0] - y) <= ROW_TOLERANCE:
            lines[-1].append((y, x, text))
        else:
            lines.append([(y, x, text)])

    out: List[str] = []
    for line in lines:
        line.sort(key=lambda item: item[1])
        buffer = ""
        last_end: Optional[float] = None
        for _y, x, text in line:
            # 只有明显断开（超过半个字宽）才补空格，避免把"名称：公司"拆开
            if last_end is not None and x - last_end > SPACE_GAP and buffer and not buffer.endswith(" "):
                buffer += " "
            buffer += text
            last_end = x + _piece_width(text)
        out.append(buffer.rstrip())
    return "\n".join(line for line in out if line.strip())


# --------------------------------------------------------------------------
# 各引擎读取
# --------------------------------------------------------------------------
def _read_with_pypdf(path: str, max_pages: Optional[int] = None) -> List[str]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    _repair_font_descriptors(reader)

    texts: List[str] = []
    for index, page in enumerate(reader.pages):
        if max_pages is not None and index >= max_pages:
            break
        page_text = ""
        try:
            chunks = _rows_from_page(page)
            if chunks:
                page_text = _reconstruct_lines(chunks)
        except Exception:
            page_text = ""
        if not page_text.strip():
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
        texts.append(page_text)
    return texts


def _read_with_pymupdf(path: str, max_pages: Optional[int] = None) -> List[str]:
    import fitz  # PyMuPDF

    texts: List[str] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            if max_pages is not None and index >= max_pages:
                break
            try:
                texts.append(page.get_text("text") or "")
            except Exception:
                texts.append("")
    return texts


def read_pdf_text(path: str, options: config.ExtractOptions) -> Tuple[str, str, List[str]]:
    """返回 (全文, 使用的引擎, 每页文本)。"""
    engine = _choose_engine(getattr(options, "pdf_engine", "auto"))
    if not engine:
        raise RuntimeError("未安装 PDF 解析库，请执行：pip install pypdf （或 pip install PyMuPDF）")

    try:
        pages = _read_with_pymupdf(path) if engine == "pymupdf" else _read_with_pypdf(path)
    except Exception as exc:
        # 换一个引擎再试一次
        fallback = "pypdf" if engine == "pymupdf" else "pymupdf"
        if _choose_engine(fallback) == fallback:
            try:
                pages = _read_with_pymupdf(path) if fallback == "pymupdf" else _read_with_pypdf(path)
                engine = fallback
            except Exception as exc2:
                raise RuntimeError(f"PDF 解析失败：{exc2}") from exc2
        else:
            raise RuntimeError(f"PDF 解析失败：{exc}") from exc

    pages = [normalize(page) for page in pages]
    text = "\n".join(page for page in pages if page.strip())
    return text, engine, pages


# --------------------------------------------------------------------------
# 扫描件：转图片后 OCR
# --------------------------------------------------------------------------
def _render_with_pymupdf(path: str, dpi: int, max_pages: int) -> List[Any]:
    import fitz

    images = []
    zoom = max(72, int(dpi)) / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
    return images


def _render_with_pypdf(path: str, dpi: int, max_pages: int) -> List[Any]:
    """pypdf 只能抽取内嵌图片，效果有限；作为最后的兜底。"""
    from pypdf import PdfReader

    images = []
    reader = PdfReader(path)
    _repair_font_descriptors(reader)
    for index, page in enumerate(reader.pages):
        if index >= max_pages:
            break
        try:
            for image in page.images:
                images.append(image.data)
        except Exception:
            continue
    return images


def ocr_pdf(path: str, options: config.ExtractOptions) -> Tuple[str, str]:
    """扫描版 PDF：转图片后 OCR。需要 PyMuPDF 渲染。"""
    dpi = int(getattr(options, "ocr_dpi", 300) or 300)
    max_pages = int(getattr(options, "ocr_max_pages", 5) or 5)
    engine = getattr(options, "ocr_engine", "auto")
    if not ocr_module.is_available(engine):
        raise RuntimeError(ocr_module.ocr_hint())

    try:
        blobs = (
            _render_with_pymupdf(path, dpi, max_pages)
            if _pymupdf_available()
            else _render_with_pypdf(path, dpi, max_pages)
        )
    except Exception as exc:
        raise RuntimeError(f"PDF 转图片失败：{exc}") from exc

    texts: List[str] = []
    for blob in blobs:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(blob)) if isinstance(blob, (bytes, bytearray)) else blob
            texts.append(ocr_module.ocr_image(image, engine=engine))
        except Exception:
            texts.append("")
    text = "\n".join(normalize(t) for t in texts if t and t.strip())
    if not text.strip():
        raise RuntimeError("OCR 未识别到文本，请确认扫描件清晰度或语言包是否安装")
    return text, f"OCR({engine})"
