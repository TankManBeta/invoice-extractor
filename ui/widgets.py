"""可复用的小部件：支持拖拽的文件列表、无边框分组卡片等。"""
from __future__ import annotations

import os
from typing import List

import config
from ui.qt import Qt, QtCore, QtGui, QtWidgets, Signal


class DropTableWidget(QtWidgets.QTableView):
    """支持把文件 / 文件夹直接拖进来的表格视图（配合自定义 model 使用）。"""
    filesDropped = Signal(list)   # List[str] 绝对路径

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    # ---------- 拖拽 ----------
    def dragEnterEvent(self, event) -> None:  # noqa: D102
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: D102
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: D102
        paths: List[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and os.path.exists(local):
                paths.append(local)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            super().dropEvent(event)


class SearchBox(QtWidgets.QLineEdit):
    """带清除按钮与占位符的搜索框（宽度由使用方决定，默认不设上限）。"""

    def __init__(self, placeholder: str = "搜索…", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(200)


class Card(QtWidgets.QFrame):
    """带白色背景与圆角的内容卡片。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)


class FlowLayout(QtWidgets.QLayout):
    """自动换行的横向布局：用于"显示字段"这类数量多、宽度不定的勾选项。

    窗口变窄时控件自动排到下一行，不会把文字挤没。
    """

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 14, v_spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: List[QtWidgets.QLayoutItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._dirty = True
        self._cached_width = -1
        self._cached_height = 0
        self.setContentsMargins(margin, margin, margin, margin)

    # ---- QLayout 必须实现的接口 ----
    def addItem(self, item) -> None:  # noqa: D102
        self._items.append(item)
        self._dirty = True

    def count(self) -> int:  # noqa: D102
        return len(self._items)

    def itemAt(self, index: int):  # noqa: D102
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: D102
        if 0 <= index < len(self._items):
            self._dirty = True
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: D102
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: D102
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: D102
        return self._layout(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:  # noqa: D102
        self._dirty = self._dirty or rect.width() != getattr(self, "_last_width", -1)
        self._last_width = rect.width()
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):  # noqa: D102
        return self.minimumSize()

    def minimumSize(self):  # noqa: D102
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        # 高度按"一行放一个"的最坏情况估算，避免被父布局压扁
        return QtCore.QSize(size.width(), size.height())

    # ---- 内部排版 ----
    def _layout(self, rect, apply: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if apply:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def hline() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line.setObjectName("HLine")
    line.setStyleSheet("color: #e3e7ee; background: #e3e7ee; max-height: 1px;")
    return line


def chip(text: str, kind: str = "") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    if kind == "ok":
        label.setObjectName("ChipOk")
    elif kind == "warn":
        label.setObjectName("ChipWarn")
    else:
        label.setObjectName("Chip")
    return label
