"""数据模型：发票记录、待处理文件项、解析结果容器。

不依赖 Qt，方便单测与命令行自检。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import config


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}"


@dataclass
class InvoiceRecord:
    """一张发票的结构化信息。"""

    number: str = ""          # 发票号码
    code: str = ""            # 发票代码
    date: str = ""            # 开票日期
    amount: Optional[float] = None   # 金额（不含税）
    tax: Optional[float] = None      # 税额
    total: Optional[float] = None    # 价税合计
    seller: str = ""          # 销售方名称
    buyer: str = ""           # 购买方名称
    page: str = ""            # 所在页码
    confidence: float = 0.0   # 置信度 0~1
    source: str = ""          # 来源文件名
    source_path: str = ""     # 来源文件绝对路径
    note: str = ""            # 备注（警告信息合并）
    raw_text: str = ""        # 原始文本（详情面板用）
    highlights: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    manual: bool = False      # 是否被手工修改过
    selected: bool = False    # 是否勾选（用于“仅导出选中项”）

    # ---------------- 导出 ----------------
    def value(self, key: str, formatted: bool = True) -> Any:
        value = getattr(self, key, "")
        if key in config.MONEY_FIELDS:
            if formatted:
                return _fmt_money(value)
            return value
        if key == "confidence":
            try:
                return f"{float(value or 0) * 100:.0f}%"
            except (TypeError, ValueError):
                return ""
        return "" if value is None else value

    def to_export_row(self, keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """导出为一行字典：金额为数值（便于 Excel 合计），其余为字符串。"""
        keys = keys or config.EXPORT_COLUMN_KEYS
        return {config.FIELD_LABELS.get(k, k): self.value(k, formatted=False) for k in keys}

    def to_raw_row(self, keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """导出为一行字典：金额保留数值类型，供 JSON / xlsx 使用。"""
        keys = keys or config.EXPORT_COLUMN_KEYS
        row: Dict[str, Any] = {}
        for key in keys:
            label = config.FIELD_LABELS.get(key, key)
            if key in config.MONEY_FIELDS:
                row[label] = getattr(self, key, None)
            elif key == "confidence":
                row[label] = round(float(self.confidence or 0), 3)
            else:
                row[label] = getattr(self, key, "")
        return row

    def clone(self) -> "InvoiceRecord":
        return InvoiceRecord(**asdict(self))

    @property
    def is_empty(self) -> bool:
        return not (self.number or self.total is not None or self.amount is not None)


@dataclass
class FileItem:
    """文件列表中的一项。"""

    path: str
    status: str = "pending"
    progress: int = 0
    error: str = ""
    engine: str = ""
    invoices: List[InvoiceRecord] = field(default_factory=list)
    char_count: int = 0
    elapsed: float = 0.0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def size_text(self) -> str:
        try:
            size = float(os.path.getsize(self.path))
        except OSError:
            return "-"
        for unit in ("B", "KB", "MB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1].lower()

    @property
    def type_text(self) -> str:
        ext = self.ext
        if ext in config.PDF_EXTS:
            return "PDF"
        if ext in config.IMAGE_EXTS:
            return "图片"
        if ext in config.TABLE_EXTS:
            return "表格"
        if ext in config.TEXT_EXTS:
            return ext.lstrip(".").upper()
        return ext.lstrip(".").upper() or "未知"

    @property
    def status_text(self) -> str:
        return config.STATUS_TEXT.get(self.status, self.status)


@dataclass
class FileResult:
    """一个文件的解析结果。"""

    path: str
    status: str = "done"
    text: str = ""
    engine: str = ""
    error: str = ""
    elapsed: float = 0.0
    invoices: List[InvoiceRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
