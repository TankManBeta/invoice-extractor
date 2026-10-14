"""导入区：文件列表（支持拖拽导入、增删、状态展示）。"""
from __future__ import annotations

import os
from typing import List

import config
import core.reader as reader
from core.models import FileItem
from ui.canvas import FileTableModel
from ui.qt import Qt, QtWidgets, Signal
from ui.widgets import DropTableWidget


class FileListPanel(QtWidgets.QWidget):
    """左侧“待处理文件”面板。"""

    requestImport = Signal()
    requestImportFolder = Signal()
    requestRemove = Signal()
    requestClear = Signal()
    filesDropped = Signal(list)
    selectionChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = FileTableModel(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 顶部操作条
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        self.btn_import = QtWidgets.QPushButton("＋ 添加文件")
        self.btn_import.setObjectName("Primary")
        self.btn_folder = QtWidgets.QPushButton("添加文件夹")
        self.btn_remove = QtWidgets.QPushButton("移除")
        self.btn_clear = QtWidgets.QPushButton("清空")
        for widget in (self.btn_import, self.btn_folder, self.btn_remove, self.btn_clear):
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(widget)
        bar.addStretch(1)
        layout.addLayout(bar)

        # 表格
        self.table = DropTableWidget(self)
        self.table.setModel(self.model)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 110)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.hint = QtWidgets.QLabel("提示：把 PDF / 图片 / 文本 / Excel 台账直接拖到这里，或点击“添加文件”。支持一次选择多个文件。")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        # 信号
        self.btn_import.clicked.connect(self.requestImport.emit)
        self.btn_folder.clicked.connect(self.requestImportFolder.emit)
        self.btn_remove.clicked.connect(self.requestRemove.emit)
        self.btn_clear.clicked.connect(self.requestClear.emit)
        self.table.filesDropped.connect(self.filesDropped.emit)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.selectionChanged.emit())

    # ---------- 数据操作 ----------
    def add_paths(self, paths: List[str], recursive: bool = True) -> int:
        """展开目录、过滤重复项后加入列表，返回新增数量。"""
        files = reader.collect_files(paths, recursive=recursive)
        existing = {os.path.normcase(p) for p in self.model.paths()}
        new_files = [f for f in files if os.path.normcase(os.path.abspath(f)) not in existing]
        skipped = len(files) - len(new_files)

        items = [FileItem(path=path) for path in new_files]
        self.model.add_items(items)
        self._update_layout()
        self.hint.setText(self._summary(skipped))
        return len(new_files)

    def _update_layout(self) -> None:
        count = self.model.rowCount()
        self.table.setVisible(True)
        self.btn_remove.setEnabled(count > 0)
        self.btn_clear.setEnabled(count > 0)

    def _summary(self, skipped: int = 0) -> str:
        count = self.model.rowCount()
        text = f"已加入 {count} 个文件。把 PDF / 图片 / 文本 / 表格直接拖进来也可以。"
        if skipped:
            text += f"（已忽略 {skipped} 个重复或不支持的文件）"
        return text

    def selected_rows(self) -> List[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def remove_selected(self) -> int:
        rows = self.selected_rows()
        if not rows:
            return 0
        self.model.remove_rows(rows)
        self._update_layout()
        self.hint.setText(self._summary())
        return len(rows)

    def clear(self) -> None:
        self.model.clear()
        self._update_layout()
        self.hint.setText(self._summary())

    def remove_row(self, row: int) -> None:
        self.model.remove_rows([row])
        self._update_layout()

    def set_status(self, row: int, status: str, progress: int = 0, error: str = "") -> None:
        if 0 <= row < self.model.rowCount():
            item = self.model.items[row]
            item.status = status
            item.progress = progress
            item.error = error
            self.model.update_item(row, item)

    def set_result(self, row: int, result) -> None:
        if not (0 <= row < self.model.rowCount()):
            return
        item = self.model.items[row]
        item.status = result.status
        item.error = result.error
        item.engine = result.engine
        item.invoices = list(result.invoices)
        item.char_count = len(result.text or "")
        item.elapsed = result.elapsed
        item.progress = 100
        self.model.update_item(row, item)

    def item_at(self, row: int):
        if 0 <= row < self.model.rowCount():
            return self.model.items[row]
        return None

    def all_paths(self) -> List[str]:
        return self.model.paths()

    def path_at(self, row: int) -> str:
        item = self.item_at(row)
        return item.path if item else ""

    def count(self) -> int:
        return self.model.rowCount()

    def mark_pending(self) -> None:
        for row, item in enumerate(self.model.items):
            item.status = "pending"
            item.progress = 0
            item.error = ""
            self.model.update_item(row, item)
