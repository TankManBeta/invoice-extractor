"""核心包：解析、读取、OCR、导出。

仅 core.models / core.extract 等模块本身不依赖 Qt，便于命令行自检与单元测试。
"""
from __future__ import annotations

__all__ = [
    "models",
    "textutil",
    "extract",
    "ocr",
    "pdf",
    "tablereader",
    "reader",
    "exporter",
]
