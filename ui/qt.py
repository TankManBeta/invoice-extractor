"""Qt 绑定兼容层：同一份代码同时支持 PySide6 / PyQt6 / PyQt5。

用法：
    from ui.qt import QtCore, QtGui, QtWidgets, Qt, Signal, Slot, exec_app

设计要点：
1. 每个绑定独立探测，**逐个模块、逐个符号**导入，任何一个名字在不同 Qt 版本里
   被改名或移除（例如 PySide6 6.12 起 QtCore 不再导出 QT_VERSION_STR）都不会
   拖垮整次探测；
2. 探测失败的真实原因会被记录下来，通过 binding_report() / ensure_binding(verbose=True)
   输出，避免再出现"明明装了 Qt 却提示未找到绑定"的黑盒问题。
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

BINDING = ""
QtCore = QtGui = QtWidgets = None
Signal = Slot = Property = pyqtSignal = pyqtSlot = None
Qt = None
QAction = QActionGroup = QThread = QTimer = QSettings = QSize = None
QPoint = QRect = QRectF = QEvent = QUrl = QObject = QAbstractTableModel = None

_FIELDS = (
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Signal",
    "Slot",
    "Property",
    "Qt",
    "QAction",
    "QActionGroup",
    "QThread",
    "QTimer",
    "QSettings",
    "QSize",
    "QPoint",
    "QRect",
    "QRectF",
    "QEvent",
    "QUrl",
    "QObject",
    "QAbstractTableModel",
)
_EXTRA = ("QTextCharFormat", "QColor", "QFont")

_PROBED: List[str] = []
_FAILURES: Dict[str, List[str]] = {}
_ORDER = ("pyside6", "pyqt6", "pyqt5")


class _CompatError(RuntimeError):
    """所有 Qt 绑定都不可用时抛出。"""


def _first_symbol(module, *names):
    """返回模块里第一个存在的符号；全部不存在时返回 None。"""
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    return None


def _commit(update: Dict[str, object]) -> None:
    globals().update(update)


# --------------------------------------------------------------------------
# 各绑定探测
# --------------------------------------------------------------------------
def _try_pyside6() -> Tuple[bool, str]:
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
    except Exception as exc:
        return False, f"导入 PySide6 失败：{type(exc).__name__}: {exc}"

    try:
        from PySide6.QtCore import (  # type: ignore
            Property,
            QAbstractTableModel,
            QEvent,
            QObject,
            QPoint,
            QRect,
            QRectF,
            QSettings,
            QSize,
            QThread,
            QTimer,
            QUrl,
            Qt,
            Signal,
            Slot,
        )
        from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QTextCharFormat  # type: ignore
    except Exception as exc:
        return False, f"导入 PySide6 常用符号失败：{type(exc).__name__}: {exc}"

    try:
        from PySide6.QtCore import __version__ as qt_version  # type: ignore
    except Exception:
        qt_version = str(getattr(PySide6, "__version__", "") or "")

    update = {
        "QtCore": QtCore,
        "QtGui": QtGui,
        "QtWidgets": QtWidgets,
        "Signal": Signal,
        "Slot": Slot,
        "Property": Property,
        "Qt": Qt,
        "QAction": QAction,
        "QActionGroup": QActionGroup,
        "QThread": QThread,
        "QTimer": QTimer,
        "QSettings": QSettings,
        "QSize": QSize,
        "QPoint": QPoint,
        "QRect": QRect,
        "QRectF": QRectF,
        "QEvent": QEvent,
        "QUrl": QUrl,
        "QObject": QObject,
        "QAbstractTableModel": QAbstractTableModel,
        "QTextCharFormat": QTextCharFormat,
        "QColor": QColor,
        "QFont": QFont,
        "QT_VERSION_STR": str(qt_version or ""),
        "BINDING": "PySide6",
    }
    _commit(update)
    return True, f"PySide6 {getattr(PySide6, '__version__', '?')}"


def _try_pyqt6() -> Tuple[bool, str]:
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets  # type: ignore
    except Exception as exc:
        return False, f"导入 PyQt6 失败：{type(exc).__name__}: {exc}"

    try:
        from PyQt6.QtCore import (  # type: ignore
            QAbstractTableModel,
            QEvent,
            QObject,
            QPoint,
            QRect,
            QRectF,
            QSettings,
            QSize,
            QThread,
            QTimer,
            QUrl,
            Qt,
        )
        from PyQt6.QtCore import pyqtProperty as Property  # type: ignore
        from PyQt6.QtCore import pyqtSignal as Signal  # type: ignore
        from PyQt6.QtCore import pyqtSlot as Slot  # type: ignore
        from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QTextCharFormat  # type: ignore
    except Exception as exc:
        return False, f"导入 PyQt6 常用符号失败：{type(exc).__name__}: {exc}"

    _commit(
        {
            "QtCore": QtCore,
            "QtGui": QtGui,
            "QtWidgets": QtWidgets,
            "Signal": Signal,
            "Slot": Slot,
            "Property": Property,
            "Qt": Qt,
            "QAction": QAction,
            "QActionGroup": QActionGroup,
            "QThread": QThread,
            "QTimer": QTimer,
            "QSettings": QSettings,
            "QSize": QSize,
            "QPoint": QPoint,
            "QRect": QRect,
            "QRectF": QRectF,
            "QEvent": QEvent,
            "QUrl": QUrl,
            "QObject": QObject,
            "QAbstractTableModel": QAbstractTableModel,
            "QTextCharFormat": QTextCharFormat,
            "QColor": QColor,
            "QFont": QFont,
            "QT_VERSION_STR": str(getattr(QtCore, "PYQT_VERSION_STR", "") or ""),
            "BINDING": "PyQt6",
        }
    )
    return True, f"PyQt6 {getattr(QtCore, 'PYQT_VERSION_STR', '?')}"


def _try_pyqt5() -> Tuple[bool, str]:
    """PyQt5 兜底（QAction 在 QtWidgets 里，信号名也不同）。"""
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore
    except Exception as exc:
        return False, f"导入 PyQt5 失败：{type(exc).__name__}: {exc}"

    try:
        from PyQt5.QtCore import (  # type: ignore
            QAbstractTableModel,
            QEvent,
            QObject,
            QPoint,
            QRect,
            QRectF,
            QSettings,
            QSize,
            QThread,
            QTimer,
            QUrl,
            Qt,
        )
        from PyQt5.QtCore import pyqtProperty as Property  # type: ignore
        from PyQt5.QtCore import pyqtSignal as Signal  # type: ignore
        from PyQt5.QtCore import pyqtSlot as Slot  # type: ignore
        from PyQt5.QtGui import QColor, QFont, QTextCharFormat  # type: ignore
    except Exception as exc:
        return False, f"导入 PyQt5 常用符号失败：{type(exc).__name__}: {exc}"

    QAction = QtWidgets.QAction
    QActionGroup = getattr(QtWidgets, "QActionGroup", None)

    _commit(
        {
            "QtCore": QtCore,
            "QtGui": QtGui,
            "QtWidgets": QtWidgets,
            "Signal": Signal,
            "Slot": Slot,
            "Property": Property,
            "Qt": Qt,
            "QAction": QAction,
            "QActionGroup": QActionGroup,
            "QThread": QThread,
            "QTimer": QTimer,
            "QSettings": QSettings,
            "QSize": QSize,
            "QPoint": QPoint,
            "QRect": QRect,
            "QRectF": QRectF,
            "QEvent": QEvent,
            "QUrl": QUrl,
            "QObject": QObject,
            "QAbstractTableModel": QAbstractTableModel,
            "QTextCharFormat": QTextCharFormat,
            "QColor": QColor,
            "QFont": QFont,
            "QT_VERSION_STR": str(getattr(QtCore, "PYQT_VERSION_STR", "") or ""),
            "BINDING": "PyQt5",
        }
    )
    return True, f"PyQt5 {getattr(QtCore, 'PYQT_VERSION_STR', '?')}"


_LOADERS = {
    "pyside6": _try_pyside6,
    "pyqt6": _try_pyqt6,
    "pyqt5": _try_pyqt5,
}


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def _probe(name: str) -> Tuple[bool, str]:
    """静默探测某个绑定：只判断是否可用，不写入全局状态。"""
    try:
        ok, message = _LOADERS[name]()
    except Exception as exc:  # noqa: BLE001 - 探测本身不允许抛异常
        return False, f"探测异常：{type(exc).__name__}: {exc}"
    return ok, message


def binding_report() -> List[Tuple[str, bool, str]]:
    """逐个探测所有绑定，返回 [(名称, 是否可用, 说明)]，用于排错。

    探测过程不会影响当前正在使用的绑定（结束后完整还原全局状态）。
    """
    snapshot = {name: globals().get(name) for name in _FIELDS + _EXTRA}
    snapshot["BINDING"] = globals().get("BINDING", "")
    snapshot["QT_VERSION_STR"] = globals().get("QT_VERSION_STR", "")

    report: List[Tuple[str, bool, str]] = []
    for name in _ORDER:
        ok, message = _probe(name)
        report.append((name, ok, message))

    _commit(snapshot)
    return report


def ensure_binding(prefer: str = "", verbose: bool = False) -> str:
    """加载 Qt 绑定并返回绑定名；全部失败时抛出 _CompatError。

    prefer: "" | pyside6 | pyqt6 | pyqt5（也可用环境变量 INVOICE_QT_BINDING）
    """
    global BINDING
    if BINDING and globals().get("QtWidgets") is not None:
        return BINDING

    prefer = (prefer or os.environ.get("INVOICE_QT_BINDING", "")).strip().lower()
    order = ([prefer] if prefer in _LOADERS else []) + [name for name in _ORDER if name != prefer]

    tried: List[str] = []
    failures: List[str] = []
    for name in order:
        if name in tried:
            continue
        tried.append(name)
        try:
            ok, message = _LOADERS[name]()
        except Exception as exc:  # noqa: BLE001
            ok, message = False, f"探测异常：{type(exc).__name__}: {exc}"
        if ok and globals().get("QtWidgets") is not None:
            BINDING = str(globals().get("BINDING") or name)
            if verbose:
                print(f"[Qt] 使用 {message}（python {sys.version.split()[0]}）")
            return BINDING
        _FAILURES.setdefault(name, []).append(message)
        failures.append(f"  - {name}: {message}")

    detail = "\n".join(failures)
    raise _CompatError(
        "未找到可用的 Qt 绑定。\n"
        f"当前 Python：{sys.executable}\n"
        f"探测结果：\n{detail}\n"
        "解决办法（任选其一，装完直接重新运行本程序，无需改代码）：\n"
        "    pip install PySide6      # 推荐\n"
        "    pip install PyQt6        # 更轻量\n"
        "若在虚拟环境中运行，请确认装到了同一个解释器：\n"
        "    python -m pip install PySide6\n"
        "排查详情：python app.py --qt-debug"
    )


def require_binding() -> str:
    """确保绑定已就绪，并返回绑定名（供界面层在构造窗口前调用）。"""
    name = ensure_binding()
    if globals().get("QtWidgets") is None:  # pragma: no cover - 理论不可达
        raise _CompatError(f"{name} 已加载，但 QWidgets 仍不可用，请运行 python app.py --qt-debug 排查")
    return name


def exec_app(app) -> int:
    """兼容 Qt5 的 exec_() 与 Qt6 的 exec()。"""
    runner = getattr(app, "exec", None) or getattr(app, "exec_")
    return runner()


def is_pyside() -> bool:
    return BINDING.startswith("PySide")
