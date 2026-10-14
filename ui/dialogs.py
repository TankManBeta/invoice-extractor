"""导出对话框与设置对话框。"""
from __future__ import annotations

import os
from typing import List, Optional

import config
from ui.qt import Qt, QtWidgets

FORMATS = [
    ("Excel 工作簿 (*.xlsx)", "xlsx"),
    ("CSV 文本 (*.csv)", "csv"),
    ("JSON 数据 (*.json)", "json"),
]

ENCODINGS = [
    ("UTF-8 带 BOM（Excel 推荐）", "utf-8-sig"),
    ("UTF-8", "utf-8"),
    ("GB18030（部分国产软件）", "gb18030"),
]


class ExportDialog(QtWidgets.QDialog):
    """导出选项：范围、格式、列、是否附加合计行。"""

    def __init__(
        self,
        parent=None,
        *,
        selected_count: int = 0,
        total_count: int = 0,
        default_format: str = "xlsx",
        visible_fields: Optional[List[str]] = None,
        default_dir: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出发票信息")
        self.setMinimumWidth(520)
        self.selected_count = selected_count
        self.total_count = total_count

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        # 范围
        scope_box = QtWidgets.QGroupBox("导出范围")
        scope_layout = QtWidgets.QVBoxLayout(scope_box)
        self.radio_selected = QtWidgets.QRadioButton(f"仅导出选中项（{selected_count} 条）")
        self.radio_all = QtWidgets.QRadioButton(f"导出全部（{total_count} 条）")
        if selected_count > 0:
            self.radio_selected.setChecked(True)
        else:
            self.radio_all.setChecked(True)
            self.radio_selected.setEnabled(False)
        scope_layout.addWidget(self.radio_selected)
        scope_layout.addWidget(self.radio_all)
        layout.addWidget(scope_box)

        # 格式与路径
        file_box = QtWidgets.QGroupBox("输出文件")
        file_layout = QtWidgets.QGridLayout(file_box)
        self.combo_format = QtWidgets.QComboBox()
        for label, key in FORMATS:
            self.combo_format.addItem(label, key)
        index = self.combo_format.findData(default_format)
        if index >= 0:
            self.combo_format.setCurrentIndex(index)

        self.edit_path = QtWidgets.QLineEdit()
        self.edit_path.setPlaceholderText("选择保存位置…")
        default_name = f"{config.default_export_name()}.{self.combo_format.currentData()}"
        if default_dir:
            self.edit_path.setText(os.path.join(default_dir, default_name))
        else:
            self.edit_path.setText(default_name)

        self.btn_browse = QtWidgets.QPushButton("浏览…")
        self.btn_browse.clicked.connect(self._browse)

        self.combo_encoding = QtWidgets.QComboBox()
        for label, key in ENCODINGS:
            self.combo_encoding.addItem(label, key)

        file_layout.addWidget(QtWidgets.QLabel("格式"), 0, 0)
        file_layout.addWidget(self.combo_format, 0, 1, 1, 2)
        file_layout.addWidget(QtWidgets.QLabel("保存到"), 1, 0)
        file_layout.addWidget(self.edit_path, 1, 1)
        file_layout.addWidget(self.btn_browse, 1, 2)
        file_layout.addWidget(QtWidgets.QLabel("CSV 编码"), 2, 0)
        file_layout.addWidget(self.combo_encoding, 2, 1, 1, 2)
        layout.addWidget(file_box)

        self.combo_format.currentIndexChanged.connect(self._on_format_changed)

        # 列
        column_box = QtWidgets.QGroupBox("导出列")
        column_layout = QtWidgets.QGridLayout(column_box)
        self.column_boxes = {}
        for position, (key, label) in enumerate(config.EXPORT_COLUMNS):
            box = QtWidgets.QCheckBox(label)
            box.setChecked(key in (visible_fields or config.EXPORT_COLUMN_KEYS))
            self.column_boxes[key] = box
            column_layout.addWidget(box, position // 3, position % 3)
        column_layout.setColumnStretch(3, 1)

        buttons_row = QtWidgets.QHBoxLayout()
        btn_all = QtWidgets.QPushButton("全选列")
        btn_none = QtWidgets.QPushButton("全不选")
        btn_default = QtWidgets.QPushButton("默认列")
        btn_all.clicked.connect(lambda: self._set_columns(True))
        btn_none.clicked.connect(lambda: self._set_columns(False))
        btn_default.clicked.connect(lambda: self._set_columns(None))
        buttons_row.addWidget(btn_all)
        buttons_row.addWidget(btn_none)
        buttons_row.addWidget(btn_default)
        buttons_row.addStretch(1)
        column_layout.addLayout(buttons_row, (len(config.EXPORT_COLUMNS) + 2) // 3, 0, 1, 3)
        layout.addWidget(column_box)

        self.check_summary = QtWidgets.QCheckBox("附加“合计”行（金额 / 税额 / 价税合计）")
        self.check_summary.setChecked(True)
        layout.addWidget(self.check_summary)

        # 按钮
        buttons = QtWidgets.QDialogButtonBox()
        self.btn_ok = buttons.addButton("开始导出", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_ok.setObjectName("Primary")
        buttons.addButton("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_format_changed()

    # ---------- 交互 ----------
    def _set_columns(self, value: Optional[bool]) -> None:
        for key, box in self.column_boxes.items():
            box.setChecked(True if value is None and key in config.EXPORT_COLUMN_KEYS else bool(value))

    def _on_format_changed(self) -> None:
        fmt = self.combo_format.currentData()
        self.combo_encoding.setEnabled(fmt == "csv")
        self.check_summary.setEnabled(fmt != "json")
        path = self.edit_path.text().strip()
        if path:
            base = os.path.splitext(path)[0]
            self.edit_path.setText(f"{base}.{fmt}")

    def _browse(self) -> None:
        fmt = self.combo_format.currentData()
        filters = {
            "xlsx": "Excel 工作簿 (*.xlsx)",
            "csv": "CSV 文本 (*.csv)",
            "json": "JSON 数据 (*.json)",
        }
        start = self.edit_path.text().strip() or config.default_export_name()
        path, _selected = QtWidgets.QFileDialog.getSaveFileName(self, "保存导出文件", start, filters.get(fmt, "*.*"))
        if path:
            self.edit_path.setText(path)
            if not os.path.splitext(path)[1]:
                self.edit_path.setText(f"{path}.{fmt}")

    # ---------- 结果 ----------
    def result_options(self) -> dict:
        columns = [key for key, box in self.column_boxes.items() if box.isChecked()]
        return {
            "mode": "selected" if self.radio_selected.isChecked() else "all",
            "path": self.edit_path.text().strip(),
            "columns": columns,
            "encoding": self.combo_encoding.currentData(),
            "with_summary": self.check_summary.isChecked(),
        }

    def accept(self) -> None:  # noqa: D102
        options = self.result_options()
        if not options["path"]:
            QtWidgets.QMessageBox.warning(self, "提示", "请先选择保存位置。")
            return
        if not options["columns"]:
            QtWidgets.QMessageBox.warning(self, "提示", "请至少选择一个导出列。")
            return
        super().accept()


class SettingsDialog(QtWidgets.QDialog):
    """解析设置：PDF 引擎、OCR 引擎与回退策略、严格模式等。"""

    def __init__(self, parent=None, options: Optional[config.ExtractOptions] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("解析设置")
        self.setMinimumWidth(480)
        self.options = options or config.ExtractOptions()

        from core import ocr as ocr_module
        from core import pdf as pdf_module

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        pdf_box = QtWidgets.QGroupBox("PDF 解析")
        pdf_layout = QtWidgets.QFormLayout(pdf_box)
        status = pdf_module.pdf_engine_status()
        self.combo_pdf = QtWidgets.QComboBox()
        self.combo_pdf.addItem("自动（优先 PyMuPDF）", "auto")
        self.combo_pdf.addItem(f"pypdf{'（已安装）' if status['pypdf'] else '（未安装）'}", "pypdf")
        self.combo_pdf.addItem(f"PyMuPDF{'（已安装）' if status['pymupdf'] else '（未安装）'}", "pymupdf")
        index = self.combo_pdf.findData(self.options.pdf_engine)
        if index >= 0:
            self.combo_pdf.setCurrentIndex(index)
        pdf_layout.addRow("解析引擎", self.combo_pdf)
        layout.addWidget(pdf_box)

        ocr_box = QtWidgets.QGroupBox("扫描件 / 图片 OCR")
        ocr_layout = QtWidgets.QFormLayout(ocr_box)
        ocr_status = ocr_module.get_engine_status()
        self.combo_ocr = QtWidgets.QComboBox()
        self.combo_ocr.addItem("自动选择可用引擎", "auto")
        self.combo_ocr.addItem(
            f"Tesseract{'（可用）' if ocr_status['tesseract']['available'] else '（不可用）'}", "tesseract"
        )
        self.combo_ocr.addItem(f"PaddleOCR{'（可用）' if ocr_status['paddle']['available'] else '（不可用）'}", "paddle")
        self.combo_ocr.addItem("关闭 OCR", "off")
        index = self.combo_ocr.findData(self.options.ocr_engine)
        if index >= 0:
            self.combo_ocr.setCurrentIndex(index)
        ocr_layout.addRow("识别引擎", self.combo_ocr)

        self.check_fallback = QtWidgets.QCheckBox("PDF 文本层为空时自动 OCR")
        self.check_fallback.setChecked(bool(self.options.ocr_fallback))
        ocr_layout.addRow("", self.check_fallback)

        self.spin_dpi = QtWidgets.QSpinBox()
        self.spin_dpi.setRange(100, 600)
        self.spin_dpi.setSingleStep(50)
        self.spin_dpi.setValue(int(self.options.ocr_dpi))
        ocr_layout.addRow("渲染分辨率 DPI", self.spin_dpi)

        self.spin_pages = QtWidgets.QSpinBox()
        self.spin_pages.setRange(1, 200)
        self.spin_pages.setValue(int(self.options.ocr_max_pages))
        ocr_layout.addRow("单文件最多 OCR 页数", self.spin_pages)

        self.ocr_hint = QtWidgets.QLabel(ocr_module.status_summary() + "\n" + ("" if ocr_module.is_available("auto") else ocr_module.ocr_hint()))
        self.ocr_hint.setObjectName("Hint")
        self.ocr_hint.setWordWrap(True)
        ocr_layout.addRow("", self.ocr_hint)
        layout.addWidget(ocr_box)

        adv_box = QtWidgets.QGroupBox("解析策略")
        adv_layout = QtWidgets.QVBoxLayout(adv_box)
        self.check_auto_total = QtWidgets.QCheckBox("价税合计缺失时用「金额 + 税额」计算")
        self.check_auto_total.setChecked(bool(self.options.auto_total))
        self.check_strict = QtWidgets.QCheckBox("严格金额模式（不使用“取最大金额”兜底）")
        self.check_strict.setChecked(bool(self.options.strict_amount))
        self.check_raw = QtWidgets.QCheckBox("在详情面板保留原始文本")
        self.check_raw.setChecked(bool(self.options.keep_raw_text))
        for box in (self.check_auto_total, self.check_strict, self.check_raw):
            adv_layout.addWidget(box)
        layout.addWidget(adv_box)

        buttons = QtWidgets.QDialogButtonBox()
        ok = buttons.addButton("保存", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("Primary")
        buttons.addButton("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_options(self) -> config.ExtractOptions:
        return config.ExtractOptions(
            pdf_engine=self.combo_pdf.currentData(),
            ocr_engine=self.combo_ocr.currentData(),
            ocr_fallback=self.check_fallback.isChecked(),
            ocr_dpi=int(self.spin_dpi.value()),
            ocr_max_pages=int(self.spin_pages.value()),
            auto_total=self.check_auto_total.isChecked(),
            strict_amount=self.check_strict.isChecked(),
            keep_raw_text=self.check_raw.isChecked(),
        )


class LogPanel(QtWidgets.QWidget):
    """简易运行日志，便于排查解析失败原因。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("运行日志")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_clear = QtWidgets.QPushButton("清空")
        self.btn_clear.clicked.connect(lambda: self.text.clear())
        header.addWidget(self.btn_clear)
        layout.addLayout(header)

        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setMaximumBlockCount(2000)
        layout.addWidget(self.text)

    def append(self, message: str, level: str = "info") -> None:
        import datetime as _dt

        prefix = {"info": "·", "ok": "✓", "warn": "!", "error": "✗"}.get(level, "·")
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText(f"[{stamp}] {prefix} {message}")
