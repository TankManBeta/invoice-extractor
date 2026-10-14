"""表格模型与委托：带勾选框的结果表、文件列表模型。"""
from __future__ import annotations

import config
from core.models import FileItem, InvoiceRecord
from ui import styles
from ui.qt import Qt, QtCore, QtGui, QtWidgets, Signal


# --------------------------------------------------------------------------
# 结果表：第一列勾选框 + 其后为发票字段
# --------------------------------------------------------------------------
class InvoiceTableModel(QtCore.QAbstractTableModel):
    """发票结果表模型。

    列结构：第 0 列勾选框（显示序号），第 1..n 列为 config.FIELDS 中的字段，
    最后一列隐藏存放 InvoiceRecord 对象（Qt.UserRole）。
    """

    checkChanged = Signal()

    CHECK_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.records: List[InvoiceRecord] = []
        self.visible_fields: List[str] = list(config.DEFAULT_VISIBLE_FIELDS)
        self._field_titles = {key: label for key, label, _w, _right in config.FIELDS}
        self._field_right = {key: right for key, _l, _w, right in config.FIELDS}

    # ---------- 基本接口 ----------
    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else 1 + len(self.visible_fields)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section == 0:
                return "选择"
            key = self.visible_fields[section - 1]
            return self._field_titles.get(key, key)
        return section + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self.records[index.row()]
        if index.column() == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if record.selected else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.DisplayRole:
                return str(index.row() + 1)
            if role == Qt.ItemDataRole.ToolTipRole:
                return "勾选后可用于“仅导出选中项”"
            return None

        key = self.visible_fields[index.column() - 1]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return record.value(key, formatted=True)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if self._field_right.get(key):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and key in ("number", "total"):
            return QtGui.QBrush(QtGui.QColor("#1f2329" if styles.current_theme() == "light" else "#ffffff"))
        if role == Qt.ItemDataRole.FontRole and key in ("number", "total"):
            font = QtGui.QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.ToolTipRole:
            tips = [f"{self._field_titles.get(key, key)}：{record.value(key, formatted=True)}"]
            if key == "number" and record.warnings:
                tips.append("；".join(record.warnings))
            return "\n".join(tips)
        return None

    # ---------- 勾选 ----------
    def set_selection(self, rows: List[int], checked: bool) -> None:
        for row in rows:
            if 0 <= row < len(self.records):
                self.records[row].selected = checked
        if rows:
            top = self.index(min(rows), 0)
            bottom = self.index(max(rows), 0)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.CheckStateRole])
        self.checkChanged.emit()

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        """支持详情面板 / 手工编辑直接改值。"""
        if not index.isValid():
            return False
        record = self.records[index.row()]
        key = self.visible_fields[index.column() - 1] if index.column() > 0 else ""
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            record.selected = value == Qt.CheckState.Checked or value == 2 or value is True
            self.dataChanged.emit(index, index, [role])
            self.checkChanged.emit()
            return True
        if role == Qt.ItemDataRole.EditRole and key:
            text = "" if value is None else str(value)
            if key in config.MONEY_FIELDS:
                from core.textutil import to_float

                setattr(record, key, to_float(text))
            else:
                setattr(record, key, text)
            record.manual = True
            self.dataChanged.emit(index, index)
            return True
        return False

    # ---------- 数据集操作 ----------
    def set_records(self, records: List[InvoiceRecord]) -> None:
        self.beginResetModel()
        self.records = records
        self.endResetModel()
        self.checkChanged.emit()

    def append_records(self, records: List[InvoiceRecord]) -> None:
        if not records:
            return
        start = len(self.records)
        self.beginInsertRows(QtCore.QModelIndex(), start, start + len(records) - 1)
        self.records.extend(records)
        self.endInsertRows()
        self.checkChanged.emit()

    def remove_rows(self, rows: List[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.records):
                self.beginRemoveRows(QtCore.QModelIndex(), row, row)
                del self.records[row]
                self.endRemoveRows()
        self.checkChanged.emit()

    def clear(self) -> None:
        self.set_records([])

    def set_visible_fields(self, fields: List[str]) -> None:
        fields = [f for f in fields if f in config.FIELD_KEYS] or list(config.DEFAULT_VISIBLE_FIELDS)
        self.beginResetModel()
        self.visible_fields = fields
        self.endResetModel()
        self.checkChanged.emit()

    # ---------- 查询 ----------
    def selected_records(self) -> List[InvoiceRecord]:
        return [r for r in self.records if getattr(r, "selected", False)]

    def checked_count(self) -> int:
        return sum(1 for r in self.records if getattr(r, "selected", False))


# --------------------------------------------------------------------------
# 文件列表模型
# --------------------------------------------------------------------------
class FileTableModel(QtCore.QAbstractTableModel):
    HEADERS = ["文件名", "类型", "大小", "状态", "发票数", "识别引擎", "耗时"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: List[FileItem] = []

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return section + 1
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        column = index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if column == 0:
                return item.name
            if column == 1:
                return item.type_text
            if column == 2:
                return item.size_text
            if column == 3:
                return item.status_text
            if column == 4:
                return str(len(item.invoices)) if item.status in ("done", "ocr") else "-"
            if column == 5:
                return item.engine or "-"
            if column == 6:
                return f"{item.elapsed:.2f}s" if item.elapsed else "-"
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{item.path}\n状态：{item.status_text}"
            if item.error:
                tip += f"\n错误：{item.error}"
            return tip
        if role == Qt.ItemDataRole.ForegroundRole:
            colors = {
                "error": "#d9534f",
                "done": "#1f2329" if styles.current_theme() == "light" else "#e4e7ee",
                "ocr": "#b25e09",
                "pending": "#8a93a3",
                "empty": "#b25e09",
                "unsupported": "#8a93a3",
            }
            if column == 3 and item.status in colors:
                return QtGui.QBrush(QtGui.QColor(colors[item.status]))
            if styles.current_theme() == "dark":
                return QtGui.QBrush(QtGui.QColor("#e4e7ee"))
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (1, 2, 4, 6):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def add_items(self, items: List[FileItem]) -> List[int]:
        if not items:
            return []
        start = len(self.items)
        self.beginInsertRows(QtCore.QModelIndex(), start, start + len(items) - 1)
        self.items.extend(items)
        self.endInsertRows()
        return list(range(start, start + len(items)))

    def update_item(self, row: int, item: FileItem) -> None:
        if 0 <= row < len(self.items):
            self.items[row] = item
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.HEADERS) - 1))

    def remove_rows(self, rows: List[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.items):
                self.beginRemoveRows(QtCore.QModelIndex(), row, row)
                del self.items[row]
                self.endRemoveRows()

    def clear(self) -> None:
        self.beginResetModel()
        self.items = []
        self.endResetModel()

    def paths(self) -> List[str]:
        return [item.path for item in self.items]


CHECKED_BG_LIGHT = "#dbe6ff"
CHECKED_BG_DARK = "#2b3a58"
CHECKED_TEXT_LIGHT = "#0b3ea8"
CHECKED_TEXT_DARK = "#cfe0ff"


def checked_background() -> QtGui.QColor:
    return QtGui.QColor(CHECKED_BG_DARK if styles.current_theme() == "dark" else CHECKED_BG_LIGHT)


def checked_foreground() -> QtGui.QColor:
    return QtGui.QColor(CHECKED_TEXT_DARK if styles.current_theme() == "dark" else CHECKED_TEXT_LIGHT)


def _is_checked(index) -> bool:
    state = index.data(Qt.ItemDataRole.CheckStateRole)
    return state == Qt.CheckState.Checked or state == 2


# --------------------------------------------------------------------------
# 委托：整行勾选反馈 + 复选框居中
# --------------------------------------------------------------------------
def _style_enum(*names):
    """兼容不同 Qt 版本的枚举命名（PyQt5 与 Qt6 的 QStyle 枚举名不完全一致）。"""
    for name in names:
        if hasattr(QtWidgets.QStyle, name):
            return getattr(QtWidgets.QStyle, name)
        enum_type = getattr(QtWidgets.QStyle, "PrimitiveElement", None)
        if enum_type is not None and hasattr(enum_type, name):
            return getattr(enum_type, name)
    return None


def _state_flag(name):
    for holder in (QtWidgets.QStyle, getattr(QtWidgets.QStyle, "StateFlag", None)):
        if holder is not None and hasattr(holder, name):
            return getattr(holder, name)
    return None


class CheckColumnDelegate(QtWidgets.QStyledItemDelegate):
    """结果表"选择"列。

    - 用 Qt 标准方式绘制复选框（不用自定义绘制，避免"画的位置"和"点判定位置"不一致）；
    - 显式处理鼠标点击：整个单元格任意位置点击都能切换勾选，且不会误触发编辑。
    """

    def initStyleOption(self, option, index) -> None:  # noqa: D102
        super().initStyleOption(option, index)
        if _is_checked(index) and not (option.state & QtWidgets.QStyle.StateFlag.State_Selected):
            option.backgroundBrush = QtGui.QBrush(checked_background())

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: D102
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            return self._toggle(model, index)
        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            # 双由 editorEvent 收到的是第二次按下，直接视为一次切换并吞掉，避免连带进入编辑
            return self._toggle(model, index)
        if event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Select):
                return self._toggle(model, index)
        return super().editorEvent(event, model, option, index)

    @staticmethod
    def _toggle(model, index) -> bool:
        if index.column() != 0:
            return False
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        checked = state == Qt.CheckState.Checked or state == 2
        new_state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
        return bool(model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole))


class RowHighlightDelegate(QtWidgets.QStyledItemDelegate):
    """普通单元格：勾选后整行浅蓝底，一眼能看出选了哪些。"""

    def initStyleOption(self, option, index) -> None:  # noqa: D102
        super().initStyleOption(option, index)
        state = index.sibling(index.row(), 0).data(Qt.ItemDataRole.CheckStateRole)
        is_checked = state == Qt.CheckState.Checked or state == 2
        if is_checked and not (option.state & QtWidgets.QStyle.StateFlag.State_Selected):
            option.backgroundBrush = QtGui.QBrush(checked_background())


class RowNumberDelegate(QtWidgets.QStyledItemDelegate):
    """文件列表序号列，可选使用。"""

    def initStyleOption(self, option, index) -> None:  # noqa: D102
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter
