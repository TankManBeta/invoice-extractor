"""后台解析线程：批量读取文件 → 解析发票 → 通过信号回传进度与结果。

界面主线程只负责展示，避免 OCR / 大文件解析时卡死。
"""
from __future__ import annotations

from typing import List

import config
import core.reader as reader
from core.models import FileResult
from ui.qt import QtCore, Signal


class BatchWorker(QtCore.QThread):
    """按顺序处理文件列表。"""

    fileStarted = Signal(int, str)                 # 行号, 路径
    fileFinished = Signal(int, object)             # 行号, FileResult
    fileFailed = Signal(int, str, str)             # 行号, 路径, 错误
    progressChanged = Signal(int, int)             # 已完成, 总数
    logMessage = Signal(str)
    finishedAll = Signal(int, int)                 # 成功文件数, 失败文件数

    def __init__(self, files: List[str], options: config.ExtractOptions, parent=None) -> None:
        super().__init__(parent)
        self.files = list(files)
        self.options = options
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop

    def run(self) -> None:  # noqa: D102
        total = len(self.files)
        ok = failed = 0
        for index, path in enumerate(self.files):
            if self._stop:
                self.logMessage.emit("已取消解析")
                break
            self.fileStarted.emit(index, path)
            result: FileResult
            try:
                result = reader.read_file(path, self.options)
            except Exception as exc:  # noqa: BLE001
                result = FileResult(path=path, status="error", error=str(exc))

            if result.status in ("done", "ocr"):
                ok += 1
            else:
                failed += 1
            self.fileFinished.emit(index, result)
            self.progressChanged.emit(index + 1, total)

        self.finishedAll.emit(ok, failed)
