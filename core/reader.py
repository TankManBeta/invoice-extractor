"""文件读取调度层：判断文件类型 → 抽取文本 → 调用解析器 → 返回结果。

对界面和命令行自检都是同一入口：read_file(path, options) -> FileResult
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import time
from typing import Any, Dict, List, Optional

import config
from core import extract as extract_module
from core import ocr as ocr_module
from core import pdf as pdf_module
from core import tablereader
from core.models import FileItem, FileResult, InvoiceRecord
from core.textutil import normalize, to_float

_FILE_ERRORS: Dict[str, str] = {
    ".xlsx": "读取表格需要 openpyxl：pip install openpyxl",
    ".xls": "读取 .xls 需要 xlrd：pip install xlrd",
}


def guess_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in config.PDF_EXTS:
        return "pdf"
    if ext in config.IMAGE_EXTS:
        return "image"
    if ext in config.TABLE_EXTS:
        return "table"
    if ext in config.TEXT_EXTS:
        return "text"
    return "unsupported"


# --------------------------------------------------------------------------
# 结构化台账（Excel / CSV）→ 发票记录
# --------------------------------------------------------------------------
def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _cell_to_date(value: Any) -> str:
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.strftime("%Y-%m-%d")
    text = _cell_to_text(value)
    match = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", text)
    if match:
        year, month, day = (int(x) for x in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    # Excel 日期序列号
    number = to_float(text)
    if number is not None and 20000 < number < 60000 and text.replace(".", "").isdigit():
        base = _dt.date(1899, 12, 30)
        try:
            return (base + _dt.timedelta(days=int(number))).strftime("%Y-%m-%d")
        except Exception:
            return text
    return text


def rows_to_records(
    headers: List[str], rows: List[List[Any]], mapping: Dict[int, str], source: str, source_path: str
) -> List[InvoiceRecord]:
    records: List[InvoiceRecord] = []
    for row_index, row in enumerate(rows, start=1):
        record = InvoiceRecord(source=source, source_path=source_path, page=str(row_index), confidence=0.9)
        for column, key in mapping.items():
            if column >= len(row):
                continue
            raw = row[column]
            if key in config.MONEY_FIELDS:
                setattr(record, key, to_float(_cell_to_text(raw)))
            elif key == "date":
                record.date = _cell_to_date(raw)
            elif key == "confidence":
                continue
            else:
                setattr(record, key, _cell_to_text(raw))
        if record.number:
            record.number = re.sub(r"\D", "", record.number) or record.number
        if record.is_empty:
            continue
        if record.total is None and record.amount is not None and record.tax is not None:
            record.total = round(record.amount + record.tax, 2)
        if record.amount is None and record.total is not None and record.tax is not None:
            record.amount = round(record.total - record.tax, 2)
        records.append(record)
    return records


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def _parse_pdf(path: str, options: config.ExtractOptions, name: str) -> FileResult:
    text, engine, pages = pdf_module.read_pdf_text(path, options)
    if not text.strip() and getattr(options, "ocr_fallback", True):
        text, engine = pdf_module.ocr_pdf(path, options)

    invoices: List[InvoiceRecord] = []
    for index, page_text in enumerate(pages if pages else [text], start=1):
        if not page_text or not page_text.strip():
            continue
        invoices.extend(
            extract_module.parse_text(page_text, source=name, source_path=path, options=options)
        )
    if not invoices and text.strip():
        invoices = extract_module.parse_text(
            text, source=name, source_path=path, options=options, keep_empty=True
        )
    return FileResult(path=path, status="done", text=text, engine=engine, invoices=invoices)


def _parse_image(path: str, options: config.ExtractOptions, name: str) -> FileResult:
    engine = getattr(options, "ocr_engine", "auto")
    if not ocr_module.is_available(engine):
        raise RuntimeError(ocr_module.ocr_hint())
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("处理图片需要 Pillow，请执行：pip install pillow") from exc

    with Image.open(path) as image:
        text = normalize(ocr_module.ocr_image(image, engine=engine))
    invoices = extract_module.parse_text(
        text, source=name, source_path=path, options=options, keep_empty=True
    )
    result = FileResult(path=path, status="ocr", text=text, engine=f"OCR({engine})", invoices=invoices)
    if not text.strip():
        result.status = "empty"
        result.invoices = []
        result.warnings.append("OCR 未识别到文本")
    return result


def _parse_table(path: str, options: config.ExtractOptions, name: str) -> FileResult:
    data = tablereader.read_table_file(path)
    invoices: List[InvoiceRecord] = []
    if data["structured"]:
        invoices = rows_to_records(data["headers"], data["rows"], data["mapping"], name, path)
    if not invoices:
        invoices = extract_module.parse_text(data["text"], source=name, source_path=path, options=options)
    result = FileResult(path=path, status="done", text=data["text"], engine="表格", invoices=invoices)
    if data["structured"]:
        result.engine = "表格(结构化)"
    return result


def _parse_text(path: str, options: config.ExtractOptions, name: str) -> FileResult:
    text = tablereader.read_text_file(path)
    invoices = extract_module.parse_text(
        text, source=name, source_path=path, options=options, keep_empty=True
    )
    return FileResult(path=path, status="done", text=text, engine="文本", invoices=invoices)


def read_file(path: str, options: Optional[config.ExtractOptions] = None) -> FileResult:
    """读取单个文件并解析出发票记录。异常会被包装成 status="error" 的结果。"""
    options = options or config.ExtractOptions()
    name = os.path.basename(path)
    started = time.time()

    if not os.path.exists(path):
        return FileResult(path=path, status="error", error="文件不存在", elapsed=0.0)

    kind = guess_kind(path)
    try:
        if kind == "pdf":
            result = _parse_pdf(path, options, name)
        elif kind == "image":
            result = _parse_image(path, options, name)
        elif kind == "table":
            result = _parse_table(path, options, name)
        elif kind == "text":
            result = _parse_text(path, options, name)
        else:
            result = FileResult(path=path, status="unsupported", error=f"暂不支持的文件格式：{os.path.splitext(path)[1]}")
    except Exception as exc:  # noqa: BLE001 - 统一转成界面可展示的错误
        message = str(exc) or exc.__class__.__name__
        result = FileResult(path=path, status="error", error=message)

    result.elapsed = round(time.time() - started, 3)
    if result.status == "done" and not result.invoices:
        result.status = "empty"
        result.warnings.append("未识别到发票信息")
    for record in result.invoices:
        record.source = name
        record.source_path = path
    return result


def collect_files(paths: List[str], recursive: bool = True) -> List[str]:
    """展开目录，过滤出受支持的文件，去重并保持稳定顺序。"""
    collected: List[str] = []
    seen = set()

    def push(file_path: str) -> None:
        real = os.path.normcase(os.path.abspath(file_path))
        if real in seen:
            return
        seen.add(real)
        collected.append(os.path.abspath(file_path))

    for path in paths:
        if os.path.isdir(path):
            if recursive:
                for root, _dirs, files in os.walk(path):
                    for file_name in sorted(files):
                        full = os.path.join(root, file_name)
                        if os.path.splitext(full)[1].lower() in config.SUPPORTED_EXTS:
                            push(full)
            else:
                for file_name in sorted(os.listdir(path)):
                    full = os.path.join(path, file_name)
                    if os.path.isfile(full) and os.path.splitext(full)[1].lower() in config.SUPPORTED_EXTS:
                        push(full)
        elif os.path.isfile(path):
            push(path)
    return collected


def file_stat_text(path: str) -> str:
    return FileItem(path).size_text
