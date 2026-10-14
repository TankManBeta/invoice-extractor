"""布局回归测试：确认界面在"窗口变窄"和"系统字体放大"两种压力下都不截断、不重叠。

用法（Windows PowerShell）：
    $env:QT_QPA_PLATFORM="offscreen"
    python scripts/layout_check.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import config  # noqa: E402
from ui import qt as qt_module  # noqa: E402

qt_module.ensure_binding()

QtCore = qt_module.QtCore
QtGui = qt_module.QtGui
QtWidgets = qt_module.QtWidgets

from core.models import InvoiceRecord  # noqa: E402
from ui import styles  # noqa: E402
from ui.detail_panel import DetailPanel, FORM_ROWS  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def pump(app, seconds: float = 0.2) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        QtCore.QThread.msleep(5)


def sample_record() -> InvoiceRecord:
    return InvoiceRecord(
        number="25312000000012345678",
        code="031002100311",
        date="2025-03-12",
        amount=10000.0,
        tax=600.0,
        total=10600.0,
        seller="上海瀚海电子科技有限公司",
        buyer="杭州云帆网络科技有限公司",
        source="数电票_示例A.txt",
        page="1",
        confidence=0.95,
        raw_text="电子发票（增值税专用发票）\n发票号码：25312000000012345678\n价税合计（大写）壹万零陆佰元整 （小写）¥10600.00",
    )


class Checker:
    def __init__(self) -> None:
        self.failures = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.failures.append(name)


def _rects_overlap(a, b) -> bool:
    """两个矩形是否实质性重叠（允许 1px 误差）。"""
    return not (
        a.x() + a.width() <= b.x() + 1
        or b.x() + b.width() <= a.x() + 1
        or a.y() + a.height() <= b.y() + 1
        or b.y() + b.height() <= a.y() + 1
    )


def check_detail_panel(app, checker: Checker, font_pt: int, width: int) -> None:
    """详情面板：标签/输入框高度够不够、行与行是否重叠、控件是否互相压住。"""
    panel = DetailPanel()
    font = panel.font()
    font.setPointSize(font_pt)
    panel.setFont(font)
    panel.resize(width, 760)
    panel.show()
    panel.set_record(sample_record())
    pump(app, 0.25)

    metrics = QtGui.QFontMetrics(panel.font())
    need_label = metrics.ascent() + metrics.descent()
    grid = panel.form_grid

    rows = {}
    for key, title, _full, _right in FORM_ROWS:
        row, col, _rs, _cs = grid.getItemPosition(grid.indexOf(panel.editors[key]))
        rows.setdefault(row, []).append((key, title))

    label_heights = []
    problems = []
    label_widgets = []  # [(名称, 控件)]，同一控件只收一次

    # 单列结构：标签在 col 0，输入框在 col 1
    for row in range(grid.rowCount()):
        item = grid.itemAtPosition(row, 0)
        widget = item.widget() if item is not None else None
        if not isinstance(widget, QtWidgets.QLabel):
            continue
        if any(widget is existing for _n, existing in label_widgets):
            continue
        rect = widget.geometry()
        label_widgets.append((widget.text(), widget))
        label_heights.append(rect.height())
        text_width = metrics.horizontalAdvance(widget.text())
        if rect.height() < need_label:
            problems.append(f"{widget.text()} 高{rect.height()}<需{need_label}")
        if rect.width() < text_width + 2:
            problems.append(f"{widget.text()} 宽{rect.width()}<需{text_width}")

    # 标签互相之间、标签与同行输入框之间都不允许重叠
    rects = [(name, widget.geometry()) for name, widget in label_widgets]
    for row in range(grid.rowCount()):
        editor_item = grid.itemAtPosition(row, 1)
        editor = editor_item.widget() if editor_item is not None else None
        if editor is not None:
            rects.append((f"第{row}行输入框", editor.geometry()))
    rects = [(name, rect) for name, rect in rects if rect.width() > 0 and rect.height() > 0]

    overlaps = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            name_a, rect_a = rects[i]
            name_b, rect_b = rects[j]
            if _rects_overlap(rect_a, rect_b):
                overlaps.append(f"{name_a} ↔ {name_b}")

    checker.check(
        f"详情行高随字体变化 @{font_pt}pt/{width}px",
        min(label_heights) >= need_label if label_heights else False,
        f"最小行高 {min(label_heights) if label_heights else 0}px，字体需要 {need_label}px",
    )
    checker.check(
        f"详情控件不重叠 @{font_pt}pt/{width}px",
        not overlaps,
        "；".join(sorted(set(overlaps))[:4]) if overlaps else "无重叠",
    )
    checker.check(
        f"详情标签完整（不裁切/不压字）@{font_pt}pt/{width}px",
        not problems,
        "；".join(problems[:3]) if problems else "全部完整",
    )
    panel.close()


def check_main_window(app, checker: Checker, font_pt: int, width: int) -> None:
    window = MainWindow(settings=config.AppSettings(), demo=True)
    font = window.font()
    font.setPointSize(font_pt)
    window.setFont(font)
    app.setFont(font)
    window.resize(width, 900)
    window.show()
    pump(app, 0.4)

    window.start_extraction()
    deadline = time.monotonic() + 30
    while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
        pump(app, 0.1)
    pump(app, 0.3)

    panel = window.results_panel
    clipped = []
    for box in panel.field_boxes.values():
        if box.width() < box.sizeHint().width() - 1:
            clipped.append(f"{box.text()}({box.width()}<{box.sizeHint().width()})")
    checker.check(
        f"字段勾选框不被截断 @{font_pt}pt/{width}px",
        not clipped,
        f"被截断：{clipped}" if clipped else f"{len({b.y() for b in panel.field_boxes.values()})} 行，全部完整",
    )

    search_need = panel.search.fontMetrics().horizontalAdvance("搜索发票号码 / 销售方 / 购买方 / 文件名")
    checker.check(
        f"搜索框宽度足够 @{font_pt}pt/{width}px",
        panel.search.width() >= min(search_need + 30, panel.width() - 20),
        f"宽 {panel.search.width()}px（需要约 {search_need + 30}px）",
    )

    table = panel.table
    headers_bad = []
    for column in range(panel.model.columnCount()):
        text = panel.model.headerData(column, qt_module.Qt.Orientation.Horizontal)
        if text is None:
            continue
        need = table.fontMetrics().horizontalAdvance(str(text)) + 18
        if table.columnWidth(column) < need:
            headers_bad.append(f"{text}({table.columnWidth(column)}<{need})")
    checker.check(
        f"表头文字完整 @{font_pt}pt/{width}px",
        not headers_bad,
        f"问题：{headers_bad}" if headers_bad else "全部完整",
    )

    window.close()


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    styles.set_theme("light")
    app.setStyleSheet(styles.qss("light"))
    checker = Checker()

    print("=== 详情面板：字体 9pt / 12pt / 16pt × 宽度 700/500/400 ===")
    for font_pt in (9, 12, 16):
        for width in (700, 500, 400):
            check_detail_panel(app, checker, font_pt, width)

    print("=== 主窗口：字体 9pt / 12pt / 16pt × 宽度 1500/1300/1180 ===")
    for font_pt in (9, 12, 16):
        for width in (1500, 1300, 1180):
            check_main_window(app, checker, font_pt, width)

    print(f"-- 布局检查：{'全部通过' if not checker.failures else '失败项 ' + str(checker.failures)} --")
    return 0 if not checker.failures else 1


if __name__ == "__main__":
    sys.exit(main())
