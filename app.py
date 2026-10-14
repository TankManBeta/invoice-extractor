"""发票号码及金额提取工具 —— 程序入口。

用法：
    python app.py                  # 启动图形界面
    python app.py --demo           # 启动并载入内置演示数据
    python app.py --self-test      # 不启动界面，仅自检解析引擎
    python app.py --selftest       # 同上（别名）

环境变量：
    INVOICE_QT_BINDING=pyqt6       # 强制指定 Qt 绑定（pyside6 / pyqt6 / pyqt5）
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

# 允许在任意工作目录下用 `python 路径/app.py` 启动
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402


# --------------------------------------------------------------------------
# 解析自检（不需要 Qt，方便在没有图形环境的机器上验证）
# --------------------------------------------------------------------------
def run_self_test() -> int:
    from core.extract import parse_text
    from core.sample_data import CHECK_CASES

    print(f"== {config.APP_NAME} v{config.APP_VERSION} 解析自检 ==")
    passed = failed = 0
    for name, text, expect in CHECK_CASES:
        records = parse_text(text, source=f"{name}.txt")
        problems = []

        if "count" in expect and len(records) != expect["count"]:
            problems.append(f"识别条数={len(records)}（期望 {expect['count']}）")

        fields = {k: v for k, v in expect.items() if k != "count"}
        if fields:
            if not records:
                problems.append("未识别到任何记录")
            else:
                record = records[0]
                for key, expected in fields.items():
                    actual = getattr(record, key, None)
                    if isinstance(expected, float):
                        if actual is None or abs(float(actual) - expected) > 0.01:
                            problems.append(f"{key}={actual}（期望 {expected}）")
                    elif str(actual) != str(expected):
                        problems.append(f"{key}={actual!r}（期望 {expected!r}）")

        ok = not problems
        detail = "全部字段匹配" if ok else "；".join(problems)
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}: {detail}")
        passed += 1 if ok else 0
        failed += 0 if ok else 1

    print(f"-- 自检结果：通过 {passed}，失败 {failed} --")
    return 0 if failed == 0 else 1


# --------------------------------------------------------------------------
# 依赖自检信息
# --------------------------------------------------------------------------
def print_environment() -> None:
    from core import ocr as ocr_module
    from core import pdf as pdf_module

    pdf_status = pdf_module.pdf_engine_status()
    print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
    print(f"PDF 引擎    : pypdf={'OK' if pdf_status['pypdf'] else '未安装'}  PyMuPDF={'OK' if pdf_status['pymupdf'] else '未安装'}")
    print(f"OCR         : {ocr_module.status_summary()}")
    try:
        import openpyxl  # noqa: F401

        print("Excel 导出  : openpyxl OK")
    except Exception:
        print("Excel 导出  : 未安装 openpyxl（导出 .xlsx 时需要，也可改用 CSV）")
    print(f"Qt 绑定     : 环境变量 INVOICE_QT_BINDING={os.environ.get('INVOICE_QT_BINDING') or '（未设置，自动探测）'}")
    print_binding_report()


def print_binding_report() -> None:
    """逐个探测 Qt 绑定并打印结果（排查"明明装了却提示未找到绑定"）。"""
    try:
        from ui import qt as qt_module
    except Exception as exc:  # pragma: no cover
        print(f"无法导入 ui.qt：{exc}")
        return

    print("Qt 绑定探测 :")
    available = []
    for name, ok, message in qt_module.binding_report():
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] {name:8s} {message}")
        if ok:
            available.append(name)
    best = available[0] if available else ""
    print(f"  -> 可用：{', '.join(available) if available else '无'}；将使用：{best or '（无，请先安装 PySide6 或 PyQt6）'}")


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=f"{config.APP_NAME} v{config.APP_VERSION}")
    parser.add_argument("files", nargs="*", help="启动时直接导入的文件或文件夹")
    parser.add_argument("--demo", action="store_true", help="启动后载入内置演示数据")
    parser.add_argument("--self-test", "--selftest", dest="self_test", action="store_true", help="仅运行解析自检")
    parser.add_argument("--binding", default="", help="指定 Qt 绑定：pyside6 / pyqt6 / pyqt5")
    parser.add_argument("--env", action="store_true", help="打印环境依赖信息后退出")
    parser.add_argument("--qt-debug", dest="qt_debug", action="store_true", help="逐个探测 Qt 绑定并打印结果后退出")
    parser.add_argument("--reset-layout", dest="reset_layout", action="store_true", help="清除保存的窗口布局/设置，恢复默认界面")
    args = parser.parse_args(argv)

    if args.reset_layout:
        try:
            from ui import qt as qt_module

            qt_module.ensure_binding(args.binding)
            store = qt_module.QtCore.QSettings(config.ORG_NAME, config.APP_NAME_EN)
            store.clear()
            store.sync()
            print("已清除保存的窗口布局与界面设置，下次启动即为默认布局。")
            return 0
        except Exception as exc:
            print(f"[警告] 清除界面设置失败：{exc}", file=sys.stderr)

    if args.self_test:
        return run_self_test()

    if args.env:
        print_environment()
        return 0

    if args.qt_debug:
        print_binding_report()
        return 0

    # 注意：必须先用模块方式导入 ui.qt，再调用 ensure_binding()，
    # 最后才通过 qt.QtWidgets 取真实对象；否则会拿到绑定加载前的 None。
    from ui import qt as qt_module

    try:
        qt_module.ensure_binding(args.binding, verbose=True)
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    QtWidgets = qt_module.QtWidgets
    exec_app = qt_module.exec_app
    if QtWidgets is None:  # 兜底：理论上不会发生
        print("[错误] Qt 绑定加载后仍未获得 QtWidgets，请运行 python app.py --qt-debug 排查", file=sys.stderr)
        return 2

    from ui.main_window import MainWindow
    from ui import styles

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)

    settings = config.AppSettings()
    styles.set_theme(settings.theme)
    app.setStyleSheet(styles.qss(settings.theme))

    window = MainWindow(settings=settings, demo=bool(args.demo))
    if args.files:
        window.add_paths(list(args.files))
    window.show()
    return exec_app(app)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # pragma: no cover
        traceback.print_exc()
        sys.exit(1)
