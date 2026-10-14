"""详情面板：展示/校正单张发票，并高亮原始文本中的命中位置。

注意：所有高度/宽度都按**字体度量**计算，而不是写死像素。
否则在系统放大字体或 125%/150% 缩放时，标签文字会溢出、上下行叠在一起。
"""
from __future__ import annotations

import os
from typing import List, Optional

import config
from core.models import InvoiceRecord
from core.textutil import to_float
from ui import styles
from ui.qt import Qt, QtCore, QtGui, QtWidgets, Signal

# (字段键, 显示名, 是否独占整行, 是否右对齐)
FORM_ROWS = [
    ("number", "发票号码", True, False),
    ("code", "发票代码", False, False),
    ("date", "开票日期", False, False),
    ("amount", "金额(不含税)", True, True),
    ("tax", "税额", False, True),
    ("total", "价税合计", False, True),
    ("seller", "销售方", True, False),
    ("buyer", "购买方", True, False),
    ("source", "来源文件", True, False),
    ("page", "页码", False, False),
]

FULL_ROW_KEYS = ("number", "seller", "buyer", "source")
MONEY_KEYS = ("amount", "tax", "total")

ROW_GAP = 8               # 行与行之间的最小间距（像素）


def label_text_width(font: QtGui.QFont, texts: List[str]) -> int:
    """按字体算出最长标签的像素宽度，保证标签不被裁切。"""
    metrics = QtGui.QFontMetrics(font)
    return max(metrics.horizontalAdvance(text) for text in texts) + 8


class DetailPanel(QtWidgets.QWidget):
    """右侧详情面板。"""

    recordEdited = Signal(object)
    reparseRequested = Signal(object)
    copyRequested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.record: Optional[InvoiceRecord] = None
        self._loading = False
        self.editors = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QtWidgets.QVBoxLayout()
        header.setSpacing(6)
        title = QtWidgets.QLabel("发票详情")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        self.headline = QtWidgets.QLabel("未选择记录")
        self.headline.setObjectName("AppSubtitle")
        self.headline.setWordWrap(True)
        header.addWidget(self.headline)
        layout.addLayout(header)

        layout.addWidget(self._build_form())

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)

        text_tab = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_tab)
        text_layout.setContentsMargins(8, 10, 8, 8)
        text_layout.setSpacing(8)
        self.text_edit = QtWidgets.QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("原始文本（PDF 文本层 / OCR 结果）将显示在这里，命中的关键字段会高亮")
        self.text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        text_layout.addWidget(self.text_edit)
        tabs.addTab(text_tab, "原始文本")

        warn_tab = QtWidgets.QWidget()
        warn_layout = QtWidgets.QVBoxLayout(warn_tab)
        warn_layout.setContentsMargins(8, 10, 8, 8)
        warn_layout.setSpacing(8)
        self.warn_label = QtWidgets.QLabel("—")
        self.warn_label.setWordWrap(True)
        self.warn_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.warn_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        warn_layout.addWidget(self.warn_label)
        warn_layout.addStretch(1)
        tabs.addTab(warn_tab, "提示与警告")
        tabs.setMinimumHeight(self._text_metrics_height() + 76)
        layout.addWidget(tabs, 1)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)
        self.btn_reparse = QtWidgets.QPushButton("重新解析该条")
        self.btn_copy = QtWidgets.QPushButton("复制字段")
        self.btn_open = QtWidgets.QPushButton("打开来源文件")
        for button in (self.btn_reparse, self.btn_copy, self.btn_open):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.btn_reparse.clicked.connect(self._on_reparse)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_open.clicked.connect(self._on_open)

        self._apply_font_metrics()
        self.set_record(None)

    # ------------------------------------------------------------------
    # 字体度量
    # ------------------------------------------------------------------
    def _font_metrics(self) -> QtGui.QFontMetrics:
        return QtGui.QFontMetrics(self.font())

    def _editor_height(self) -> int:
        """输入框高度 = 文字高度 + 上下留白（随字体自动变化）。"""
        return max(28, self._font_metrics().height() + 12)

    def _text_metrics_height(self) -> int:
        return max(14, self._font_metrics().height())

    def _apply_font_metrics(self) -> None:
        """按当前字体刷新标签列宽、输入框高度与行距。

        字体（或系统缩放）变化后重新计算，避免标签被裁切或上下行叠在一起。
        """
        grid = getattr(self, "form_grid", None)
        if grid is None:
            return
        metrics = self._font_metrics()
        row_height = self._editor_height()
        label_width = label_text_width(self.font(), [f"{title}：" for _k, title, _f, _r in FORM_ROWS])
        min_editor = max(104, metrics.horizontalAdvance("0000000000"))

        grid.setColumnMinimumWidth(0, label_width)
        grid.setVerticalSpacing(max(ROW_GAP, metrics.height() // 2))
        for key, _title, _full, _right in FORM_ROWS:
            editor = self.editors.get(key)
            if editor is not None:
                editor.setFixedHeight(row_height)
                editor.setMinimumWidth(min_editor)
        for row in range(grid.rowCount()):
            item = grid.itemAtPosition(row, 0)
            label = item.widget() if item is not None else None
            if label is not None:
                label.setMinimumWidth(label_width)
                label.setFixedHeight(row_height)

        needed = label_width + 14 + min_editor + 24
        self.form_box.setMinimumWidth(max(300, needed))
        self.setMinimumWidth(min(max(300, needed) + 40, 520))

    def changeEvent(self, event) -> None:  # noqa: D102
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.FontChange:
            self._apply_font_metrics()

    # ------------------------------------------------------------------
    # 构建"字段校正"表单
    # ------------------------------------------------------------------
    def _build_form(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("字段校正（可直接修改，结果表同步更新）")
        self.form_box = box

        metrics = self._font_metrics()
        row_height = self._editor_height()
        label_width = label_text_width(self.font(), [f"{title}：" for _k, title, _f, _r in FORM_ROWS])

        grid = QtWidgets.QGridLayout(box)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(max(ROW_GAP, metrics.height() // 2))
        grid.setColumnStretch(1, 1)

        # 输入框的最小宽度只保证"能看清单据号"，避免把右侧面板撑宽
        min_editor = max(104, metrics.horizontalAdvance("0000000000"))

        row = 0
        column = 0
        for key, title, full_row, right_align in FORM_ROWS:
            editor = QtWidgets.QLineEdit()
            editor.setPlaceholderText("—")
            editor.setFixedHeight(row_height)
            editor.setMinimumHeight(row_height)
            editor.setMinimumWidth(min_editor)
            if right_align:
                editor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            editor.editingFinished.connect(lambda k=key: self._on_edit_committed(k))
            editor.returnPressed.connect(lambda k=key: self._on_edit_committed(k))
            self.editors[key] = editor

            label = QtWidgets.QLabel(f"{title}：")
            label.setObjectName("FieldLabel")
            label.setFixedHeight(row_height)
            label.setMinimumHeight(row_height)
            label.setMinimumWidth(label_width)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # 一行一组字段：标签固定宽度，输入框占满剩余宽度。
            # 不跨列到"另一组"的列上，避免与相邻标签相撞。
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(editor, row, 1)
            row += 1

        # 面板最小宽度：标签列 + 一个最小输入框 + 间距与边距
        needed = label_width + 14 + min_editor + 24
        box.setMinimumWidth(max(300, needed))
        self.form_grid = grid
        return box

    # ------------------------------------------------------------------
    # 数据绑定
    # ------------------------------------------------------------------
    def set_record(self, record: Optional[InvoiceRecord], text: str = "") -> None:
        self._loading = True
        self.record = record
        enabled = record is not None

        for editor in self.editors.values():
            editor.setEnabled(enabled)
            editor.setStyleSheet("")

        if record is None:
            for editor in self.editors.values():
                editor.clear()
            self.headline.setText("未选择记录")
            self.text_edit.setPlainText("")
            self.warn_label.setText("—")
            self.btn_reparse.setEnabled(False)
            self.btn_copy.setEnabled(False)
            self.btn_open.setEnabled(False)
            self._loading = False
            return

        for key, _title, _full, _right in FORM_ROWS:
            self.editors[key].setText(record.value(key, formatted=True))

        flag = "（手工修改）" if record.manual else ""
        self.headline.setText(
            f"号码 {record.number or '未识别'} ｜ 价税合计 {record.value('total', formatted=True) or '—'} "
            f"｜ 置信度 {record.confidence * 100:.0f}% {flag}"
        )

        raw = record.raw_text or text or ""
        self.text_edit.setPlainText(raw)
        self.warn_label.setText(
            "\n".join(f"• {w}" for w in record.warnings) if record.warnings else "未发现明显问题。"
        )
        self.btn_reparse.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.btn_open.setEnabled(bool(record.source_path and os.path.exists(record.source_path)))
        self._loading = False
        QtCore.QTimer.singleShot(0, self._highlight)

    def _highlight(self) -> None:
        if self.record is None:
            return
        selections: List[QtWidgets.QTextEdit.ExtraSelection] = []
        color = QtGui.QColor("#fff3bf" if styles.current_theme() == "light" else "#5a4a12")
        text = self.text_edit.toPlainText()
        for item in self.record.highlights or []:
            try:
                start = int(item.get("start", -1))
                end = int(item.get("end", -1))
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start or end > len(text):
                continue
            selection = QtWidgets.QTextEdit.ExtraSelection()
            cursor = QtGui.QTextCursor(self.text_edit.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)
            fmt = QtGui.QTextCharFormat()
            fmt.setBackground(QtGui.QBrush(color))
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)
        self.text_edit.setExtraSelections(selections)

    # ------------------------------------------------------------------
    # 编辑
    # ------------------------------------------------------------------
    def _on_edit_committed(self, key: str) -> None:
        if self._loading or self.record is None:
            return
        editor = self.editors[key]
        text = editor.text().strip()
        if key in MONEY_KEYS:
            value = to_float(text) if text else None
            if getattr(self.record, key, None) == value:
                return
            setattr(self.record, key, value)
            editor.setText("" if value is None else f"{value:,.2f}")
        else:
            if getattr(self.record, key, "") == text:
                return
            setattr(self.record, key, text)
        self.record.manual = True
        editor.setStyleSheet("border-color: #f0b429;")
        self.recordEdited.emit(self.record)

    def _on_reparse(self) -> None:
        if self.record is not None:
            self.reparseRequested.emit(self.record)

    def _on_copy(self) -> None:
        if self.record is not None:
            self.copyRequested.emit(self.record)

    def _on_open(self) -> None:
        if self.record is None:
            return
        path = self.record.source_path
        if path and os.path.exists(path):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
