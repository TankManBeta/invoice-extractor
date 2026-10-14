"""结果区：发票表格（勾选 / 排序 / 筛选）、字段显示开关、导出操作。"""
from __future__ import annotations

from typing import List, Optional

import config
from core.models import InvoiceRecord
from ui.canvas import CheckColumnDelegate, InvoiceTableModel, RowHighlightDelegate
from ui.qt import Qt, QtCore, QtWidgets, Signal
from ui.widgets import FlowLayout, SearchBox


class ResultHeaderView(QtWidgets.QHeaderView):
    """表头：第 0 列（选择）不可排序，避免误点把行顺序打乱。"""

    def __init__(self, orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self._locked_columns = {0}

    def sectionClicked(self, index: int) -> None:  # noqa: D102
        if index in self._locked_columns:
            return
        super().sectionClicked(index)


class CheckableTableView(QtWidgets.QTableView):
    """结果表：单击"选择"列任意位置即可切换该行勾选状态，并有即时视觉反馈。

    默认的 QTableView 只在精确点到复选框图标那一小块时才切换勾选，
    体验很差；这里改为整列可点。
    """

    cellClicked = Signal(QtCore.QModelIndex)

    def mouseReleaseEvent(self, event) -> None:  # noqa: D102
        index = self.indexAt(event.position().toPoint() if hasattr(event, "position") else event.pos())
        is_left = event.button() == Qt.MouseButton.LeftButton
        moved = getattr(self, "_press_pos", None)
        released = event.position().toPoint() if hasattr(event, "position") else event.pos()
        dragged = moved is not None and (released - moved).manhattanLength() > 6
        super().mouseReleaseEvent(event)
        if is_left and index.isValid() and not dragged:
            self.cellClicked.emit(index)

    def mousePressEvent(self, event) -> None:  # noqa: D102
        self._press_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        super().mousePressEvent(event)


class ConfidenceFilterProxy(QtCore.QSortFilterProxyModel):
    """按关键词 + 最低置信度 + 仅看异常 过滤结果表。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.keyword = ""
        self.min_confidence = 0.0
        self.only_problem = False
        self.show_empty = True
        self.setDynamicSortFilter(True)

    def set_keyword(self, text: str) -> None:
        self.keyword = (text or "").strip().lower()
        self.invalidateFilter()

    def set_min_confidence(self, value: float) -> None:
        self.min_confidence = float(value)
        self.invalidateFilter()

    def set_only_problem(self, value: bool) -> None:
        self.only_problem = bool(value)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: D102
        model = self.sourceModel()
        if model is None or source_row >= len(model.records):
            return False
        record: InvoiceRecord = model.records[source_row]
        if not self.show_empty and record.is_empty:
            return False
        if record.confidence < self.min_confidence:
            return False
        if self.only_problem and not (record.warnings or record.is_empty or record.manual):
            return False
        if self.keyword:
            haystack = " ".join(
                str(record.value(key, formatted=True)) for key in config.FIELD_KEYS
            ).lower()
            if self.keyword not in haystack:
                return False
        return True


class ResultsPanel(QtWidgets.QWidget):
    """右侧/下方“发票结果”面板。"""

    exportRequested = Signal(str)          # "selected" | "all"
    copyRequested = Signal(str)
    deleteRequested = Signal()
    selectionChanged = Signal()
    visibleFieldsChanged = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = InvoiceTableModel(self)
        self.proxy = ConfidenceFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addLayout(self._build_filter_bar())
        layout.addLayout(self._build_field_bar())
        self.table = self._build_table()
        layout.addWidget(self.table, 1)
        layout.addLayout(self._build_action_bar())

        self.model.checkChanged.connect(self._refresh_counts)
        self.model.checkChanged.connect(self.selectionChanged.emit)
        self.model.rowsInserted.connect(lambda *_: self._refresh_counts())
        self.model.rowsRemoved.connect(lambda *_: self._refresh_counts())
        self.model.modelReset.connect(lambda *_: self._refresh_counts())
        self.model.dataChanged.connect(lambda *_: self._refresh_counts())
        self._refresh_counts()

    # ---------- 子控件 ----------
    def _build_filter_bar(self) -> QtWidgets.QVBoxLayout:
        """筛选区拆成两行：第一行搜索框独占，第二行放筛选与勾选按钮。

        这样搜索框不会被旁边的控件压扁（窄窗口下尤其明显）。
        """
        bar = QtWidgets.QVBoxLayout()
        bar.setSpacing(8)

        # 第一行：搜索
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(8)
        self.search = SearchBox("搜索发票号码 / 销售方 / 购买方 / 文件名…")
        self.search.setMinimumWidth(240)
        self.search.setMaximumWidth(16777215)
        self.search.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(self.proxy.set_keyword)
        row1.addWidget(self.search, 1)
        bar.addLayout(row1)

        # 第二行：筛选条件 + 勾选按钮
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(8)

        label = QtWidgets.QLabel("置信度 ≥")
        row2.addWidget(label)
        self.confidence = QtWidgets.QComboBox()
        for text, value in [("全部", 0.0), ("30%", 0.3), ("50%", 0.5), ("70%", 0.7), ("90%", 0.9)]:
            self.confidence.addItem(text, value)
        self.confidence.setMinimumWidth(88)
        self.confidence.currentIndexChanged.connect(
            lambda: self.proxy.set_min_confidence(self.confidence.currentData())
        )
        row2.addWidget(self.confidence)

        self.only_problem = QtWidgets.QCheckBox("仅看需复核")
        self.only_problem.setToolTip("只显示有警告、未识别或已手工修改的记录")
        self.only_problem.toggled.connect(self.proxy.set_only_problem)
        row2.addWidget(self.only_problem)
        row2.addSpacing(12)

        self.btn_all = QtWidgets.QPushButton("全选")
        self.btn_invert = QtWidgets.QPushButton("反选")
        self.btn_none = QtWidgets.QPushButton("全不选")
        for button in (self.btn_all, self.btn_invert, self.btn_none):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row2.addWidget(button)
        row2.addStretch(1)

        self.btn_all.clicked.connect(lambda: self._check_rows(None, True))
        self.btn_none.clicked.connect(lambda: self._check_rows(None, False))
        self.btn_invert.clicked.connect(self._invert_checks)
        bar.addLayout(row2)
        return bar

    def _build_field_bar(self) -> QtWidgets.QVBoxLayout:
        """字段显示开关：放进自动换行布局，窗口变窄也不会把文字挤没。"""
        bar = QtWidgets.QVBoxLayout()
        bar.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        label = QtWidgets.QLabel("显示字段")
        label.setObjectName("SectionTitle")
        header.addWidget(label)
        hint = QtWidgets.QLabel("（勾选后表格立即增减该列）")
        hint.setObjectName("Hint")
        header.addWidget(hint)
        header.addStretch(1)

        self.btn_columns_default = QtWidgets.QPushButton("恢复默认字段")
        self.btn_columns_all = QtWidgets.QPushButton("显示全部字段")
        for button in (self.btn_columns_default, self.btn_columns_all):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            header.addWidget(button)
        bar.addLayout(header)

        self.flow_host = QtWidgets.QWidget()
        self.flow = FlowLayout(self.flow_host, margin=0, h_spacing=16, v_spacing=8)
        self.field_boxes = {}
        default_visible = set(config.DEFAULT_VISIBLE_FIELDS)
        for key, title, _width, _right in config.FIELDS:
            box = QtWidgets.QCheckBox(title)
            box.setChecked(key in default_visible)
            box.setMinimumHeight(22)
            box.toggled.connect(self._on_fields_changed)
            self.field_boxes[key] = box
            self.flow.addWidget(box)
        bar.addWidget(self.flow_host)

        self.btn_columns_default.clicked.connect(self.reset_fields)
        self.btn_columns_all.clicked.connect(self.show_all_fields)
        QtCore.QTimer.singleShot(0, self._adjust_field_bar_height)
        return bar

    def _adjust_field_bar_height(self) -> None:
        """让字段区按需要占 1~3 行高度：既不把文字挤没，也不留大片空白。"""
        host = getattr(self, "flow_host", None)
        flow = getattr(self, "flow", None)
        if host is None or flow is None:
            return
        if host.width() <= 10:
            # 尚未显示：不固定高度，交给布局按 heightForWidth 自行计算
            host.setMinimumHeight(0)
            host.setMaximumHeight(16777215)
            return
        height = flow.heightForWidth(host.width())
        host.setFixedHeight(max(24, min(height, 116)))

    def _build_table(self) -> QtWidgets.QTableView:
        table = CheckableTableView(self)
        table.setHorizontalHeader(ResultHeaderView(Qt.Orientation.Horizontal, table))
        table.setModel(self.proxy)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
            | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
        )
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setItemDelegateForColumn(0, CheckColumnDelegate(table))
        table.setItemDelegate(RowHighlightDelegate(table))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.doubleClicked.connect(self._on_double_click)
        table.selectionModel().selectionChanged.connect(lambda *_: self.selectionChanged.emit())
        self._apply_column_widths(table)
        return table

    def _apply_column_widths(self, table: QtWidgets.QTableView) -> None:
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 58)
        table.setSortingEnabled(True)
        # 第 0 列不排序（见 ResultHeaderView）；默认排序列从第 1 列开始
        if header.sortIndicatorSection() == 0:
            table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
            table.setSortingEnabled(True)
        widths = {key: width for key, _l, width, _r in config.FIELDS}
        for index, key in enumerate(self.model.visible_fields, start=1):
            header.setSectionResizeMode(index, QtWidgets.QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(index, widths.get(key, 120))

    def _build_action_bar(self) -> QtWidgets.QHBoxLayout:
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(8)

        self.btn_export_selected = QtWidgets.QPushButton("导出选中项")
        self.btn_export_selected.setObjectName("Primary")
        self.btn_export_all = QtWidgets.QPushButton("导出全部")
        self.btn_copy = QtWidgets.QPushButton("复制选中（制表符）")
        self.btn_delete = QtWidgets.QPushButton("删除选中行")
        self.btn_delete.setObjectName("Danger")
        for button in (self.btn_export_selected, self.btn_export_all, self.btn_copy, self.btn_delete):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(button)
        bar.addStretch(1)

        self.count_label = QtWidgets.QLabel()
        self.count_label.setObjectName("SectionTitle")
        bar.addWidget(self.count_label)

        self.btn_export_selected.clicked.connect(lambda: self.exportRequested.emit("selected"))
        self.btn_export_all.clicked.connect(lambda: self.exportRequested.emit("all"))
        self.btn_copy.clicked.connect(lambda: self.copyRequested.emit("selected"))
        self.btn_delete.clicked.connect(self.deleteRequested.emit)
        return bar

    # ---------- 交互 ----------
    def _on_fields_changed(self) -> None:
        fields = [key for key, box in self.field_boxes.items() if box.isChecked()]
        if not fields:
            fields = ["number", "total"]
            self.field_boxes["number"].setChecked(True)
            self.field_boxes["total"].setChecked(True)
        self.model.set_visible_fields(fields)
        self._apply_column_widths(self.table)
        self.visibleFieldsChanged.emit(fields)

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        self._adjust_field_bar_height()

    def reset_fields(self) -> None:
        for key, box in self.field_boxes.items():
            box.setChecked(key in config.DEFAULT_VISIBLE_FIELDS)

    def show_all_fields(self) -> None:
        for box in self.field_boxes.values():
            box.setChecked(True)

    def set_visible_fields(self, fields: List[str]) -> None:
        for key, box in self.field_boxes.items():
            box.blockSignals(True)
            box.setChecked(key in (fields or config.DEFAULT_VISIBLE_FIELDS))
            box.blockSignals(False)
        self.model.set_visible_fields(list(fields or config.DEFAULT_VISIBLE_FIELDS))
        self._apply_column_widths(self.table)

    def visible_fields(self) -> List[str]:
        return [key for key, box in self.field_boxes.items() if box.isChecked()]

    def _visible_source_rows(self) -> List[int]:
        rows = []
        for proxy_row in range(self.proxy.rowCount()):
            source_index = self.proxy.mapToSource(self.proxy.index(proxy_row, 0))
            rows.append(source_index.row())
        return rows

    def _check_rows(self, rows: Optional[List[int]], checked: bool) -> None:
        self.model.set_selection(rows if rows is not None else list(range(self.model.rowCount())), checked)

    def _invert_checks(self) -> None:
        for record in self.model.records:
            record.selected = not record.selected
        if self.model.rowCount():
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(self.model.rowCount() - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.model.checkChanged.emit()

    def check_visible(self, checked: bool = True) -> None:
        self._check_rows(self._visible_source_rows(), checked)

    def _on_double_click(self, index) -> None:
        """双击"选择"列也当作一次切换（单击由委托的 editorEvent 处理）。"""
        if index.column() == 0:
            source_row = self.proxy.mapToSource(self.proxy.index(index.row(), 0)).row()
            record = self.record_at_proxy_row(index.row())
            if record is not None:
                self.model.set_selection([source_row], not record.selected)

    # ---------- 数据 ----------
    def record_at_proxy_row(self, proxy_row: int) -> Optional[InvoiceRecord]:
        if 0 <= proxy_row < self.proxy.rowCount():
            source_row = self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row()
            if 0 <= source_row < len(self.model.records):
                return self.model.records[source_row]
        return None

    def current_record(self) -> Optional[InvoiceRecord]:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        return self.record_at_proxy_row(index.row())

    def selected_records(self) -> List[InvoiceRecord]:
        return self.model.selected_records()

    def all_records(self) -> List[InvoiceRecord]:
        return list(self.model.records)

    def export_records(self, mode: str) -> List[InvoiceRecord]:
        return self.selected_records() if mode == "selected" else self.all_records()

    def delete_selected(self) -> int:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        source_rows = []
        for proxy_row in rows:
            source_rows.append(self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row())
        if source_rows:
            self.model.remove_rows(source_rows)
        return len(source_rows)

    def clear(self) -> None:
        self.model.clear()

    def _refresh_counts(self) -> None:
        total = self.model.rowCount()
        checked = self.model.checked_count()
        visible = self.proxy.rowCount()
        text = f"共 {total} 条，勾选 {checked} 条"
        if visible != total:
            text += f"，当前显示 {visible} 条"
        self.count_label.setText(text)
        self.btn_export_selected.setEnabled(checked > 0)
        self.btn_export_all.setEnabled(total > 0)
        self.btn_delete.setEnabled(self.table.selectionModel().hasSelection())
