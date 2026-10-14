"""全局配置：字段定义、文件格式、业务规则、主题与持久化设置。

本模块**不依赖任何 Qt 绑定**，可以被界面层、解析层、命令行自检共同引用。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Tuple

APP_NAME = "发票号码及金额提取工具"
APP_NAME_EN = "Invoice Extractor"
APP_VERSION = "0.1.0"
ORG_NAME = "InvoiceExtractor"

# 是否使用内置演示数据（首次打开界面想看效果时可用命令行 --demo 触发）
SAMPLE_DIR = "samples"

# --------------------------------------------------------------------------
# 文件格式
# --------------------------------------------------------------------------
PDF_EXTS = (".pdf",)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
TEXT_EXTS = (".txt", ".log", ".json", ".xml", ".md", ".csv")
TABLE_EXTS = (".xlsx", ".xls", ".xlsm")
SUPPORTED_EXTS: Tuple[str, ...] = PDF_EXTS + IMAGE_EXTS + TEXT_EXTS + TABLE_EXTS

# 导入对话框的过滤器
IMPORT_FILTER = (
    "所有支持的文件 (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.txt *.xml *.json *.md *.csv *.xlsx *.xls *.xlsm);;"
    "PDF 文件 (*.pdf);;"
    "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;"
    "文本 / XML 文件 (*.txt *.xml *.json *.md *.csv);;"
    "表格台账 (*.xlsx *.xls *.xlsm);;"
    "所有文件 (*.*)"
)

# 状态展示文案
STATUS_TEXT = {
    "pending": "等待解析",
    "parsing": "解析中…",
    "done": "解析完成",
    "ocr": "OCR 识别完成",
    "empty": "未识别到文本",
    "error": "解析失败",
    "unsupported": "格式不支持",
    "skipped": "已取消",
}

# --------------------------------------------------------------------------
# 发票字段定义：(键, 表头中文, 宽度, 数字右对齐)
# --------------------------------------------------------------------------
FIELDS: List[Tuple[str, str, int, bool]] = [
    ("number", "发票号码", 165, False),
    ("code", "发票代码", 130, False),
    ("date", "开票日期", 105, False),
    ("amount", "金额(不含税)", 110, True),
    ("tax", "税额", 100, True),
    ("total", "价税合计", 110, True),
    ("seller", "销售方名称", 210, False),
    ("buyer", "购买方名称", 210, False),
    ("source", "来源文件", 190, False),
    ("page", "页码", 60, False),
    ("confidence", "置信度", 70, False),
]
FIELD_LABELS: Dict[str, str] = {k: label for k, label, _w, _r in FIELDS}
FIELD_KEYS: List[str] = [k for k, _l, _w, _r in FIELDS]
DEFAULT_VISIBLE_FIELDS: List[str] = [k for k in FIELD_KEYS if k != "page"]

# 导出时可用的列（键 -> 中文表头）
EXPORT_COLUMNS: List[Tuple[str, str]] = [
    ("number", "发票号码"),
    ("code", "发票代码"),
    ("date", "开票日期"),
    ("amount", "金额(不含税)"),
    ("tax", "税额"),
    ("total", "价税合计"),
    ("seller", "销售方名称"),
    ("buyer", "购买方名称"),
    ("source", "来源文件"),
    ("source_path", "文件路径"),
    ("page", "页码"),
    ("confidence", "置信度"),
    ("note", "备注"),
]
EXPORT_COLUMN_KEYS: List[str] = [k for k, _l in EXPORT_COLUMNS]

# 金额字段（导出/校验时按数值处理）
MONEY_FIELDS = ("amount", "tax", "total")

# 金额合计允许的相对 / 绝对误差
AMOUNT_TOLERANCE = 0.02

# 发票号码合法位数（数电票 20 位、传统票 8 位、部分老票 10/12 位）
NUMBER_LENGTHS = (8, 10, 12, 20)


# --------------------------------------------------------------------------
# 表头别名：导出/导入表格台账时用于自动识别列
# --------------------------------------------------------------------------
def build_header_aliases() -> Dict[str, List[str]]:
    aliases = {
        "number": ["发票号码", "发票号", "号码", "票号", "invoice number", "invoice_no", "number", "no"],
        "code": ["发票代码", "代码", "invoice code", "code"],
        "date": ["开票日期", "日期", "date", "issue date"],
        "amount": ["金额", "金额(不含税)", "不含税金额", "合计金额", "amount", "net"],
        "tax": ["税额", "税金", "tax"],
        "total": ["价税合计", "价税合计(小写)", "合计", "总金额", "含税金额", "total", "grand total"],
        "seller": ["销售方名称", "销售方", "销方名称", "销方", "seller", "vendor"],
        "buyer": ["购买方名称", "购买方", "购方名称", "购方", "buyer", "customer"],
        "source": ["来源文件", "文件名", "文件", "source", "file"],
        "page": ["页码", "页", "page"],
        "confidence": ["置信度", "confidence"],
        "note": ["备注", "说明", "note", "remark"],
    }
    return {k: [a.strip().lower() for a in v] for k, v in aliases.items()}


HEADER_ALIASES: Dict[str, List[str]] = build_header_aliases()


# --------------------------------------------------------------------------
# 运行时选项（PDF 解析器、OCR 引擎、是否 OCR 回退等）
# --------------------------------------------------------------------------
@dataclass
class ExtractOptions:
    """解析选项：界面上的"设置"对话框会生成这个对象。"""

    pdf_engine: str = "auto"            # auto | pypdf | pymupdf
    ocr_engine: str = "auto"            # auto | tesseract | paddle | off
    ocr_fallback: bool = True           # PDF 文本层为空时自动 OCR
    ocr_dpi: int = 300                  # PDF 转图片 OCR 的分辨率
    ocr_max_pages: int = 5              # 单个文件最多 OCR 的页数
    auto_total: bool = True             # 价税合计缺失时用 金额+税额 计算
    keep_raw_text: bool = True          # 在详情面板保留原始文本
    strict_amount: bool = False         # 严格模式：金额必须在标签附近

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractOptions":
        opts = cls()
        for key, value in (data or {}).items():
            if hasattr(opts, key):
                setattr(opts, key, value)
        return opts


# --------------------------------------------------------------------------
# 主题（浅色 / 深色）
# --------------------------------------------------------------------------
THEME = "light"          # light | dark
DENSITY = "comfortable"  # comfortable | compact


@dataclass
class AppSettings:
    """需要持久化的用户设置（存到注册表 / ini）。"""

    theme: str = THEME
    last_import_dir: str = ""
    last_export_dir: str = ""
    last_export_format: str = "xlsx"
    export_encoding: str = "utf-8-sig"
    export_only_visible: bool = False
    visible_fields: List[str] = field(default_factory=lambda: list(DEFAULT_VISIBLE_FIELDS))
    export_columns: List[str] = field(default_factory=lambda: list(EXPORT_COLUMN_KEYS))
    extract: Dict[str, Any] = field(default_factory=lambda: ExtractOptions().to_dict())
    recent_files: List[str] = field(default_factory=list)

    def options(self) -> ExtractOptions:
        return ExtractOptions.from_dict(self.extract)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_export_name() -> str:
    import datetime as _dt

    return f"发票信息_{_dt.datetime.now():%Y%m%d_%H%M%S}"


def app_data_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".invoice-extractor")
