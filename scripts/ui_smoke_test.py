"""界面冒烟测试：在无显示环境下把主界面完整跑一遍（含导出）。

用法（Windows PowerShell）：
    $env:QT_QPA_PLATFORM="offscreen"
    python scripts/ui_smoke_test.py

会依次验证：加载演示文件 → 后台解析 → 结果统计 → 勾选 → 复制 → 导出 CSV/XLSX/JSON。
仅用于开发自测，不影响正常使用。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import config  # noqa: E402
from ui import qt as qt_module  # noqa: E402

qt_module.ensure_binding(verbose=True)

# 注意：必须在绑定加载完成后，才通过 qt_module 取 Qt 子模块
QtCore = qt_module.QtCore
QtWidgets = qt_module.QtWidgets

# QtTest 用于发送真实鼠标事件（验证单击勾选等交互）
if qt_module.BINDING.startswith("PySide"):
    from PySide6 import QtTest  # type: ignore  # noqa: E402
else:
    from PyQt6 import QtTest  # type: ignore  # noqa: E402

from ui import styles  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def process_events(app: QtWidgets.QApplication, seconds: float = 0.1) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        QtCore.QThread.msleep(5)


def wait_worker(window: MainWindow, app: QtWidgets.QApplication, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
        process_events(app, 0.1)
    process_events(app, 0.3)
    return window.worker is None


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    styles.set_theme("light")
    app.setStyleSheet(styles.qss("light"))

    window = MainWindow(settings=config.AppSettings())
    window.show()
    failures = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    try:
        # 1) 演示数据 + 解析
        window.load_demo()
        check("导入演示文件", window.files_panel.count() == 4, f"文件数={window.files_panel.count()}")
        window.start_extraction()
        check("后台解析结束", wait_worker(window, app), "worker 已回收")

        records = window.results_panel.all_records()
        check("结果条数", len(records) == 5, f"识别到 {len(records)} 条（期望 5）")
        if records:
            numbers = sorted(r.number for r in records)
            check("发票号码提取", all(numbers), f"号码={numbers}")
            totals = sorted(round(r.total or 0, 2) for r in records)
            check("金额提取", totals == [560.0, 1280.0, 3390.0, 9605.0, 10600.0], f"价税合计={totals}")
            check("销售方提取", any(r.seller for r in records), f"示例={records[0].seller}")
            check("置信度", all(0 <= r.confidence <= 1 for r in records), f"首条={records[0].confidence}")
            check("文件状态", all(
                window.files_panel.item_at(row).status in ("done", "ocr")
                for row in range(window.files_panel.count())
            ), "4 个文件均已解析")

        # 2) 勾选：用真实鼠标事件点击，避免"只有双击才生效"这类问题回归
        def click_cell(row: int, column: int, dx: float = 0.5) -> None:
            view = window.results_panel.table
            proxy = window.results_panel.proxy
            rect = view.visualRect(proxy.index(row, column))
            point = QtCore.QPoint(int(rect.x() + rect.width() * dx), int(rect.y() + rect.height() / 2))
            QtTest.QTest.mouseClick(
                view.viewport(),
                QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.KeyboardModifier.NoModifier,
                point,
            )
            process_events(app, 0.2)

        model = window.results_panel.model
        click_cell(0, 0, 0.14)
        check("单击复选框图标位置可勾选", model.checked_count() == 1, f"勾选 {model.checked_count()} 条")
        check("状态栏勾选计数联动", "勾选 1" in window.lbl_summary.text(), window.lbl_summary.text())
        click_cell(0, 0, 0.14)
        check("再点一次可取消勾选", model.checked_count() == 0, f"勾选 {model.checked_count()} 条")
        for frac in (0.02, 0.30, 0.95):
            window.results_panel.check_visible(False)
            process_events(app, 0.1)
            click_cell(2, 0, frac)
            check(f"选择列 {int(frac * 100)}% 处也可点", model.checked_count() == 1, f"勾选 {model.checked_count()} 条")
        window.results_panel.check_visible(False)
        process_events(app, 0.1)
        checked_before = model.checked_count()
        click_cell(2, 3)
        check("点普通列不影响勾选", model.checked_count() == checked_before)

        window.results_panel.check_visible(True)
        check(
            "全选勾选",
            model.checked_count() == len(records),
            f"勾选={model.checked_count()}",
        )
        model.set_selection([0], False)
        check("取消单条勾选", model.checked_count() == len(records) - 1)

        # 3) 字段显示开关
        window.results_panel.field_boxes["code"].setChecked(False)
        check("隐藏字段", "code" not in window.results_panel.visible_fields())
        window.results_panel.field_boxes["code"].setChecked(True)

        # 4) 复制到剪贴板
        window.copy_records("selected")
        clipboard = QtWidgets.QApplication.clipboard().text()
        check("复制到剪贴板", clipboard.count("\n") >= 1, f"表头={clipboard.splitlines()[:1]}")

        # 5) 导出三种格式
        out_dir = tempfile.mkdtemp(prefix="invoice-smoke-")
        import core.exporter as exporter

        for ext in ("csv", "xlsx", "json"):
            path = os.path.join(out_dir, f"发票信息.{ext}")
            try:
                exporter.export(path, records, config.EXPORT_COLUMN_KEYS)
                size = os.path.getsize(path) if os.path.exists(path) else 0
                check(f"导出 {ext}", size > 0, f"{size} 字节")
            except Exception as exc:  # noqa: BLE001
                check(f"导出 {ext}", False, str(exc))

        # 6) 详情面板 + 手工校正 + 重新解析
        if records:
            window.detail_panel.set_record(records[0])
            check(
                "详情面板加载",
                window.detail_panel.headline.text().startswith("号码"),
                window.detail_panel.headline.text(),
            )
            editor = window.detail_panel.editors["number"]
            editor.setText("99999999999999999999")
            window.detail_panel._on_edit_committed("number")
            check("手工修改字段", records[0].number == "99999999999999999999" and records[0].manual)
            window._on_reparse_record(records[0])
            check("重新解析还原", records[0].number != "99999999999999999999", records[0].number)

        # 7) 主题切换
        window.toggle_theme(True)
        window.toggle_theme(False)
        check("主题切换", styles.current_theme() == "light")

        # 8) 筛选代理
        window.results_panel.search.setText("杭州")
        process_events(app, 0.05)
        filtered = window.results_panel.proxy.rowCount()
        check("关键词筛选", 0 < filtered <= max(1, len(records)), f"命中 {filtered} 条")
        window.results_panel.search.clear()
        process_events(app, 0.05)

        # 9) 删除结果行
        if records:
            before = window.results_panel.model.rowCount()
            window.results_panel.table.selectRow(0)
            removed = window.delete_result_rows()
            after = window.results_panel.model.rowCount()
            check("删除结果行", removed >= 1 and after == before - removed, f"删除 {removed}，剩余 {after}")

        print(f"-- 导出目录：{out_dir} --")
    finally:
        if window.worker is not None and window.worker.isRunning():
            window.worker.stop()
            window.worker.wait(5000)
        window.close()

    print(f"-- 界面冒烟测试：{'全部通过' if not failures else '失败项 ' + str(failures)} --")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
