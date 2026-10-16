"""主窗口：把文件导入、解析、结果展示、导出串起来。"""
from __future__ import annotations

import os
import time
from typing import List, Optional

import config
import core.exporter as exporter
import core.ocr as ocr_module
import core.pdf as pdf_module
from core.extract import parse_invoice
from core.models import FileResult, InvoiceRecord
from ui import styles
from ui.detail_panel import DetailPanel
from ui.dialogs import ExportDialog, LogPanel, SettingsDialog
from ui.files_panel import FileListPanel
from ui.qt import QAction, Qt, QtCore, QtGui, QtWidgets, Slot
from ui.results_panel import ResultsPanel
from ui.widgets import Card, chip
from ui.workers import BatchWorker


class MainWindow(QtWidgets.QMainWindow):
    """主窗口：左侧导入列表、中间结果表、右侧详情与日志。"""

    def __init__(self, settings: Optional[config.AppSettings] = None, demo: bool = False) -> None:
        super().__init__()
        self.settings = settings or config.AppSettings()
        self.options = self.settings.options()
        self.worker: Optional[BatchWorker] = None
        self.invoices: List[InvoiceRecord] = []
        self._current_rows: List[int] = []
        self._started_at = 0.0
        self._settings_store = QtCore.QSettings(config.ORG_NAME, config.APP_NAME_EN)

        self.setWindowTitle(f"{config.APP_NAME} v{config.APP_VERSION}")
        self.resize(1500, 920)
        self.setMinimumSize(1180, 700)

        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_statusbar()
        self._connect_signals()
        self._restore_settings()
        self._update_engine_chips()

        if demo:
            self.load_demo()

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        self.main_splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        # 左：文件队列
        left_card = Card()
        left_card.setMinimumWidth(320)
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)
        left_title = QtWidgets.QLabel("① 导入文件")
        left_title.setObjectName("SectionTitle")
        left_layout.addWidget(left_title)
        self.files_panel = FileListPanel()
        left_layout.addWidget(self.files_panel, 1)
        self.main_splitter.addWidget(left_card)

        # 中：结果
        middle_card = Card()
        middle_card.setMinimumWidth(430)
        middle_layout = QtWidgets.QVBoxLayout(middle_card)
        middle_layout.setContentsMargins(12, 12, 12, 12)
        middle_layout.setSpacing(8)
        middle_title = QtWidgets.QLabel("② 提取结果（勾选后可只导出选中项）")
        middle_title.setObjectName("SectionTitle")
        middle_layout.addWidget(middle_title)
        self.results_panel = ResultsPanel()
        middle_layout.addWidget(self.results_panel, 1)
        self.main_splitter.addWidget(middle_card)

        # 右：详情 + 日志
        right_card = Card()
        right_card.setMinimumWidth(360)
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)
        self.right_splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.detail_panel = DetailPanel()
        self.detail_panel.setMinimumWidth(300)
        self.right_splitter.addWidget(self.detail_panel)
        self.log_panel = LogPanel()
        self.right_splitter.addWidget(self.log_panel)
        self.right_splitter.setSizes([620, 220])
        right_layout.addWidget(self.right_splitter, 1)
        self.main_splitter.addWidget(right_card)

        self.main_splitter.setSizes([400, 580, 460])
        root.addWidget(self.main_splitter, 1)

    def _build_header(self) -> QtWidgets.QWidget:
        card = Card()
        layout = QtWidgets.QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        title = QtWidgets.QLabel(config.APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QtWidgets.QLabel(
            "支持 PDF / 扫描件图片 / Excel 台账 / 文本，一次可导入多个文件；提取发票号码与金额后可勾选导出。"
        )
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.chip_qt = chip("")
        self.chip_pdf = chip("")
        self.chip_ocr = chip("")
        for widget in (self.chip_qt, self.chip_pdf, self.chip_ocr):
            layout.addWidget(widget)
        return card

    def _build_actions(self) -> None:
        self.act_import = QAction("添加文件", self)
        self.act_import.setShortcut(QtGui.QKeySequence("Ctrl+O"))
        self.act_import.setToolTip("添加一个或多个文件（Ctrl+O）")
        self.act_import.triggered.connect(self.import_files)

        self.act_import_dir = QAction("添加文件夹", self)
        self.act_import_dir.setShortcut(QtGui.QKeySequence("Ctrl+Shift+O"))
        self.act_import_dir.setToolTip("导入文件夹（含子目录，自动过滤支持的类型）")
        self.act_import_dir.triggered.connect(self.import_folder)

        self.act_remove = QAction("移除所选", self)
        self.act_remove.setShortcut(QtGui.QKeySequence("Delete"))
        self.act_remove.triggered.connect(self.remove_files)

        self.act_clear = QAction("清空列表", self)
        self.act_clear.triggered.connect(self.clear_files)

        self.act_run = QAction("▶ 开始提取", self)
        self.act_run.setShortcut(QtGui.QKeySequence("F5"))
        self.act_run.setToolTip("解析所有待处理文件（F5）")
        self.act_run.triggered.connect(self.start_extraction)

        self.act_stop = QAction("停止", self)
        self.act_stop.setShortcut(QtGui.QKeySequence("Esc"))
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self.stop_extraction)

        self.act_export_selected = QAction("导出选中项…", self)
        self.act_export_selected.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.act_export_selected.setToolTip("只导出勾选的发票记录（Ctrl+E）")
        self.act_export_selected.triggered.connect(lambda: self.export("selected"))

        self.act_export_all = QAction("导出全部…", self)
        self.act_export_all.setShortcut(QtGui.QKeySequence("Ctrl+Shift+E"))
        self.act_export_all.triggered.connect(lambda: self.export("all"))

        self.act_copy = QAction("复制选中（制表符）", self)
        self.act_copy.setShortcut(QtGui.QKeySequence("Ctrl+C"))
        self.act_copy.setToolTip("复制勾选记录，可直接粘贴到 Excel")
        self.act_copy.triggered.connect(lambda: self.copy_records("selected"))

        self.act_settings = QAction("解析设置…", self)
        self.act_settings.triggered.connect(self.open_settings)

        self.act_theme = QAction("切换深色主题", self)
        self.act_theme.setCheckable(True)
        self.act_theme.toggled.connect(self.toggle_theme)

        self.act_demo = QAction("载入内置演示数据", self)
        self.act_demo.triggered.connect(self.load_demo)

        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self.show_about)

        self.act_check_all = QAction("勾选全部结果", self)
        self.act_check_all.triggered.connect(lambda: self.results_panel.check_visible(True))
        self.act_uncheck_all = QAction("取消全部勾选", self)
        self.act_uncheck_all.triggered.connect(lambda: self.results_panel.check_visible(False))

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addAction(self.act_import)
        file_menu.addAction(self.act_import_dir)
        file_menu.addSeparator()
        file_menu.addAction(self.act_remove)
        file_menu.addAction(self.act_clear)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_selected)
        file_menu.addAction(self.act_export_all)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QtGui.QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        extract_menu = self.menuBar().addMenu("提取(&R)")
        extract_menu.addAction(self.act_run)
        extract_menu.addAction(self.act_stop)
        extract_menu.addSeparator()
        extract_menu.addAction(self.act_settings)

        select_menu = self.menuBar().addMenu("选择(&S)")
        select_menu.addAction(self.act_check_all)
        select_menu.addAction(self.act_uncheck_all)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addAction(self.act_theme)
        help_menu.addAction(self.act_demo)
        help_menu.addAction(self.act_about)

        toolbar = QtWidgets.QToolBar("主工具栏")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addAction(self.act_import)
        toolbar.addAction(self.act_import_dir)
        toolbar.addSeparator()
        toolbar.addAction(self.act_remove)
        toolbar.addAction(self.act_clear)
        toolbar.addSeparator()
        toolbar.addAction(self.act_run)
        toolbar.addAction(self.act_stop)
        toolbar.addSeparator()
        toolbar.addAction(self.act_export_selected)
        toolbar.addAction(self.act_export_all)

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # 主要按钮使用蓝色高亮样式
        for action in (self.act_run, self.act_export_selected):
            button = toolbar.widgetForAction(action)
            if button is not None:
                button.setObjectName("Primary")

    def _build_statusbar(self) -> None:
        bar = self.statusBar()
        self.lbl_status = QtWidgets.QLabel("就绪：请先添加文件，然后点击“开始提取”。")
        bar.addWidget(self.lbl_status, 1)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setFixedWidth(240)
        self.progress.setTextVisible(True)
        self.progress.setVisible(False)
        bar.addPermanentWidget(self.progress)

        self.lbl_summary = QtWidgets.QLabel("文件 0 ｜ 发票 0 ｜ 合计 0.00")
        bar.addPermanentWidget(self.lbl_summary)

    def _connect_signals(self) -> None:
        self.files_panel.requestImport.connect(self.import_files)
        self.files_panel.requestImportFolder.connect(self.import_folder)
        self.files_panel.requestRemove.connect(self.remove_files)
        self.files_panel.requestClear.connect(self.clear_files)
        self.files_panel.filesDropped.connect(self.add_paths)
        self.files_panel.selectionChanged.connect(self._on_file_selection)

        self.results_panel.exportRequested.connect(self.export)
        self.results_panel.copyRequested.connect(self.copy_records)
        self.results_panel.deleteRequested.connect(self.delete_result_rows)
        self.results_panel.selectionChanged.connect(self._on_result_selection)
        self.results_panel.visibleFieldsChanged.connect(self._on_visible_fields_changed)
        # 勾选状态变化 -> 状态栏的"勾选 N"即时更新
        self.results_panel.model.checkChanged.connect(self._refresh_summary)

        self.detail_panel.recordEdited.connect(self._on_record_edited)
        self.detail_panel.reparseRequested.connect(self._on_reparse_record)
        self.detail_panel.copyRequested.connect(self._copy_record_fields)

    # ==================================================================
    # 导入
    # ==================================================================
    def import_files(self) -> None:
        start_dir = self.settings.last_import_dir or os.path.expanduser("~")
        paths, _selected = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择发票文件（可多选）", start_dir, config.IMPORT_FILTER
        )
        if paths:
            self.settings.last_import_dir = os.path.dirname(paths[0])
            self.add_paths(paths)

    def import_folder(self) -> None:
        start_dir = self.settings.last_import_dir or os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "选择文件夹（含子目录）", start_dir)
        if folder:
            self.settings.last_import_dir = folder
            self.add_paths([folder])

    def add_paths(self, paths: List[str]) -> None:
        added = self.files_panel.add_paths(paths)
        if added:
            self.log(f"已添加 {added} 个文件", "ok")
        else:
            self.log("没有新增文件（重复或不支持的格式）", "warn")
        self._refresh_summary()

    def remove_files(self) -> None:
        removed = self.files_panel.remove_selected()
        if removed:
            self.log(f"已移除 {removed} 个文件")
        self._refresh_summary()

    def clear_files(self) -> None:
        if self.files_panel.count() and QtWidgets.QMessageBox.question(
            self, "确认", "确定要清空导入列表和解析结果吗？"
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.files_panel.clear()
        self.results_panel.clear()
        self.invoices = []
        self.detail_panel.set_record(None)
        self.log("已清空列表与结果")
        self._refresh_summary()

    # ==================================================================
    # 解析
    # ==================================================================
    def pending_rows(self) -> List[int]:
        rows = []
        for row in range(self.files_panel.count()):
            item = self.files_panel.item_at(row)
            if item is not None and item.status in ("pending", "error", "empty", "unsupported"):
                rows.append(row)
        return rows

    def start_extraction(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.log("解析正在进行中", "warn")
            return
        rows = self.pending_rows()
        if not rows:
            if self.files_panel.count():
                self.log("所有文件都已解析完成；如需重跑请先“清空列表”后重新导入", "warn")
            else:
                self.log("请先添加文件", "warn")
                self.import_files()
            return

        paths = [self.files_panel.path_at(row) for row in rows]
        self._current_rows = rows
        for row in rows:
            self.files_panel.set_status(row, "parsing", 0)

        self._started_at = time.time()
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.setFormat(f"0 / {len(paths)}")
        self._set_running(True)
        self.log(f"开始提取：共 {len(paths)} 个文件", "ok")

        self.worker = BatchWorker(paths, self.options, self)
        self.worker.fileFinished.connect(self._on_file_finished)
        self.worker.progressChanged.connect(self._on_progress)
        self.worker.logMessage.connect(lambda msg: self.log(msg, "warn"))
        self.worker.finishedAll.connect(self._on_all_finished)
        self.worker.start()

    def stop_extraction(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.log("正在停止…", "warn")

    def _set_running(self, running: bool) -> None:
        for action in (
            self.act_run,
            self.act_import,
            self.act_import_dir,
            self.act_clear,
            self.act_export_selected,
            self.act_export_all,
            self.act_copy,
        ):
            action.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.files_panel.btn_import.setEnabled(not running)
        self.files_panel.btn_folder.setEnabled(not running)
        self.files_panel.btn_clear.setEnabled(not running and self.files_panel.count() > 0)
        self.files_panel.btn_remove.setEnabled(not running and self.files_panel.count() > 0)

    @Slot(int, object)
    def _on_file_finished(self, index: int, result: FileResult) -> None:
        row = self._current_rows[index] if index < len(self._current_rows) else index
        self.files_panel.set_result(row, result)

        item = self.files_panel.item_at(row)
        name = item.name if item is not None else os.path.basename(result.path)

        if result.status in ("done", "ocr") and result.invoices:
            for record in result.invoices:
                self.invoices.append(record)
                self.results_panel.model.append_records([record])
            total = sum(r.total or 0 for r in result.invoices)
            self.log(
                f"{name}：识别 {len(result.invoices)} 张，价税合计 {total:,.2f}"
                f"（{result.engine}，{result.elapsed:.2f}s）",
                "ok",
            )
        elif result.status == "error":
            self.log(f"{name}：解析失败 —— {result.error}", "error")
        elif result.status == "unsupported":
            self.log(f"{name}：不支持的格式", "warn")
        else:
            self.log(f"{name}：未识别到发票信息", "warn")

        if result.invoices and self.detail_panel.record is None:
            self.detail_panel.set_record(result.invoices[0], result.text)

        self._refresh_summary()

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.setFormat(f"{done} / {total}")

    def _on_all_finished(self, ok: int, failed: int) -> None:
        elapsed = time.time() - self._started_at
        self._set_running(False)
        self.progress.setVisible(False)
        self.lbl_status.setText(f"解析完成：成功 {ok} 个文件，异常 {failed} 个，用时 {elapsed:.1f} 秒")
        self.log(f"解析结束：成功 {ok} 个，异常 {failed} 个，用时 {elapsed:.1f} 秒", "ok" if failed == 0 else "warn")
        self._refresh_summary()
        self.worker = None

    # ==================================================================
    # 结果交互
    # ==================================================================
    def _on_file_selection(self) -> None:
        rows = self.files_panel.selected_rows()
        if not rows:
            return
        item = self.files_panel.item_at(rows[0])
        if item is not None and item.invoices:
            self.detail_panel.set_record(item.invoices[0])

    def _on_result_selection(self) -> None:
        record = self.results_panel.current_record()
        if record is not None:
            self.detail_panel.set_record(record)

    def _on_visible_fields_changed(self, fields: List[str]) -> None:
        self.settings.visible_fields = list(fields)
        self._save_settings()

    def _on_record_edited(self, record: InvoiceRecord) -> None:
        records = self.results_panel.model.records
        if record in records:
            index = records.index(record)
            top = self.results_panel.model.index(index, 0)
            bottom = self.results_panel.model.index(index, self.results_panel.model.columnCount() - 1)
            self.results_panel.model.dataChanged.emit(top, bottom)
        self._refresh_summary()

    def _on_reparse_record(self, record: InvoiceRecord) -> None:
        if not record.raw_text:
            self.log("该记录没有可用的原始文本，无法重新解析", "warn")
            return
        fresh = parse_invoice(
            record.raw_text,
            source=record.source,
            source_path=record.source_path,
            page=record.page,
            options=self.options,
            already_normalized=True,
        )
        for field in config.STORED_FIELD_KEYS:
            if field in ("source", "page", "confidence"):
                continue
            setattr(record, field, getattr(fresh, field, getattr(record, field)))
        record.warnings = list(fresh.warnings)
        record.note = fresh.note
        record.confidence = fresh.confidence
        record.highlights = list(fresh.highlights)
        record.manual = False
        self.detail_panel.set_record(record)
        self._on_record_edited(record)
        self.log(f"已重新解析：{record.number or '（未识别号码）'}", "ok")

    def delete_result_rows(self) -> int:
        removed = self.results_panel.delete_selected()
        if removed:
            self.invoices = list(self.results_panel.all_records())
            self.log(f"已删除 {removed} 条结果记录")
            self._refresh_summary()
            self.detail_panel.set_record(None)
        return removed

    # ==================================================================
    # 导出 / 复制
    # ==================================================================
    def export(self, mode: str) -> None:
        if mode == "selected" and not self.results_panel.selected_records():
            QtWidgets.QMessageBox.information(
                self, "提示", "当前没有勾选任何记录。\n可先“全选”，或改用“导出全部”。"
            )
            return
        records = self.results_panel.export_records(mode)
        if not records:
            QtWidgets.QMessageBox.information(self, "提示", "没有可导出的记录，请先提取发票信息。")
            return

        dialog = ExportDialog(
            self,
            selected_count=len(self.results_panel.selected_records()),
            total_count=len(self.results_panel.all_records()),
            default_format=self.settings.last_export_format or "xlsx",
            visible_fields=self.settings.export_columns,
            default_dir=self.settings.last_export_dir,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        options = dialog.result_options()
        path = options["path"]
        if not os.path.splitext(path)[1]:
            path += ".xlsx"

        try:
            exporter.export(
                path,
                records,
                options["columns"],
                encoding=options["encoding"],
                with_summary=options["with_summary"],
            )
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "导出失败", str(exc))
            self.log(f"导出失败：{exc}", "error")
            return

        self.settings.last_export_dir = os.path.dirname(path)
        self.settings.last_export_format = os.path.splitext(path)[1].lstrip(".") or "xlsx"
        self.settings.export_columns = options["columns"]
        self.settings.export_encoding = options["encoding"]
        self._save_settings()

        self.log(f"已导出 {len(records)} 条记录 → {path}", "ok")
        self.lbl_status.setText(f"已导出 {len(records)} 条记录：{path}")

        answer = QtWidgets.QMessageBox.question(
            self, "导出完成", f"已导出 {len(records)} 条记录到：\n{path}\n\n是否打开所在文件夹？"
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            folder = os.path.dirname(os.path.abspath(path))
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

    def copy_records(self, mode: str) -> None:
        records = self.results_panel.export_records(mode)
        if not records:
            self.log("没有可复制的记录", "warn")
            return
        QtWidgets.QApplication.clipboard().setText(self._records_to_tsv(records))
        self.log(f"已复制 {len(records)} 条记录到剪贴板（可直接粘贴到 Excel）", "ok")

    def _records_to_tsv(self, records: List[InvoiceRecord]) -> str:
        available = dict(config.EXPORT_COLUMNS)
        keys = [key for key in self.results_panel.visible_fields() if key in available]
        for extra in ("source", "source_path"):
            if extra not in keys and extra in available:
                keys.append(extra)
        lines = ["\t".join(available.get(key, key) for key in keys)]
        for record in records:
            lines.append("\t".join(str(record.value(key, formatted=True)) for key in keys))
        return "\n".join(lines)

    def _copy_record_fields(self, record: InvoiceRecord) -> None:
        if record in self.results_panel.selected_records():
            self.copy_records("selected")
        else:
            QtWidgets.QApplication.clipboard().setText(self._records_to_tsv([record]))
            self.log("已复制该条记录的字段", "ok")

    # ==================================================================
    # 设置 / 主题 / 帮助
    # ==================================================================
    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.options)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.options = dialog.result_options()
            self.settings.extract = self.options.to_dict()
            self._save_settings()
            self._update_engine_chips()
            self.log("解析设置已更新（对后续提取生效）", "ok")

    def toggle_theme(self, dark: bool) -> None:
        self.settings.theme = "dark" if dark else "light"
        self._apply_theme()
        self._save_settings()
        self.log(f"已切换到{'深色' if dark else '浅色'}主题")

    def _apply_theme(self) -> None:
        styles.set_theme(self.settings.theme)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setStyleSheet(styles.qss(self.settings.theme))
        self.act_theme.setChecked(self.settings.theme == "dark")
        self.act_theme.setText("切换浅色主题" if self.settings.theme == "dark" else "切换深色主题")

    def show_about(self) -> None:
        status = pdf_module.pdf_engine_status()
        if status["pymupdf"]:
            pdf_text = "PyMuPDF"
        elif status["pypdf"]:
            pdf_text = "pypdf"
        else:
            pdf_text = "未安装（pip install pypdf）"
        text = (
            f"<b>{config.APP_NAME}</b> v{config.APP_VERSION}<br><br>"
            "功能：批量导入发票文件 → 提取发票号码与金额 → 勾选 / 全部导出。<br><br>"
            f"Qt 绑定：{self._binding_name()}<br>"
            f"PDF 引擎：{pdf_text}<br>"
            f"OCR：{ocr_module.status_summary()}<br><br>"
            "提示：导出的金额为数值，可直接在 Excel 中求和；扫描件需要安装 OCR 引擎。"
        )
        QtWidgets.QMessageBox.about(self, "关于", text)

    def _binding_name(self) -> str:
        try:
            from ui import qt as qt_module

            return qt_module.BINDING or "-"
        except Exception:
            return "-"

    # ==================================================================
    # 演示数据 / 日志 / 统计
    # ==================================================================
    def load_demo(self) -> None:
        from core.sample_data import SAMPLES

        folder = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", config.SAMPLE_DIR))
        os.makedirs(folder, exist_ok=True)
        paths = []
        for name, text in SAMPLES:
            path = os.path.join(folder, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            paths.append(path)
        self.add_paths(paths)
        self.log(f"已生成并导入 {len(paths)} 个演示文件：{folder}", "ok")

    def log(self, message: str, level: str = "info") -> None:
        self.log_panel.append(message, level)

    def _refresh_summary(self) -> None:
        files = self.files_panel.count()
        records = self.results_panel.model.records
        total = sum(record.total or 0 for record in records)
        checked = self.results_panel.model.checked_count()
        self.lbl_summary.setText(
            f"文件 {files} ｜ 发票 {len(records)} ｜ 合计 {total:,.2f} ｜ 勾选 {checked}"
        )
        self.files_panel.btn_clear.setEnabled(files > 0)
        self.files_panel.btn_remove.setEnabled(files > 0)

    def _update_engine_chips(self) -> None:
        status = pdf_module.pdf_engine_status()
        if status["pymupdf"]:
            pdf_text = "PDF：PyMuPDF"
        elif status["pypdf"]:
            pdf_text = "PDF：pypdf"
        else:
            pdf_text = "PDF：未安装解析库"
        self._set_chip(self.chip_qt, f"界面：{self._binding_name()}", "ok")
        self._set_chip(
            self.chip_pdf, pdf_text, "ok" if (status["pypdf"] or status["pymupdf"]) else "warn"
        )
        ocr_ok = ocr_module.is_available(self.options.ocr_engine)
        self._set_chip(self.chip_ocr, ocr_module.status_summary(), "ok" if ocr_ok else "warn")

    def _set_chip(self, label: QtWidgets.QLabel, text: str, kind: str = "") -> None:
        label.setText(text)
        label.setObjectName("ChipOk" if kind == "ok" else ("ChipWarn" if kind == "warn" else "Chip"))
        label.style().unpolish(label)
        label.style().polish(label)

    # ==================================================================
    # 设置持久化 / 关闭
    # ==================================================================
    def _restore_settings(self) -> None:
        store = self._settings_store
        geometry = store.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = store.value("window/state")
        if state is not None:
            self.restoreState(state)
        for key, attribute in (
            ("window/splitter", self.main_splitter),
            ("window/right_splitter", self.right_splitter),
        ):
            sizes = store.value(key)
            if not sizes:
                continue
            try:
                attribute.setSizes([int(x) for x in sizes])
            except Exception:
                pass

        theme = store.value("ui/theme", self.settings.theme)
        self.settings.theme = "dark" if str(theme) == "dark" else "light"

        fields = store.value("ui/visible_fields")
        if fields:
            if isinstance(fields, str):
                fields = [item for item in fields.split(",") if item]
            self.settings.visible_fields = [str(item) for item in fields]
        self.results_panel.set_visible_fields(self.settings.visible_fields)

        columns = store.value("export/columns")
        if columns:
            if isinstance(columns, str):
                columns = [item for item in columns.split(",") if item]
            self.settings.export_columns = [str(item) for item in columns]

        self.settings.last_export_dir = str(store.value("export/last_dir", "") or "")
        self.settings.last_export_format = str(store.value("export/last_format", "xlsx") or "xlsx")
        self.settings.last_import_dir = str(store.value("import/last_dir", "") or "")
        stored_options = store.value("extract/options")
        if isinstance(stored_options, dict):
            self.options = config.ExtractOptions.from_dict(stored_options)
            self.settings.extract = self.options.to_dict()

        self._apply_theme()

    def _save_settings(self) -> None:
        store = self._settings_store
        store.setValue("window/geometry", self.saveGeometry())
        store.setValue("window/state", self.saveState())
        store.setValue("window/splitter", self.main_splitter.sizes())
        store.setValue("window/right_splitter", self.right_splitter.sizes())
        store.setValue("ui/theme", self.settings.theme)
        store.setValue("ui/visible_fields", self.settings.visible_fields)
        store.setValue("extract/options", self.options.to_dict())
        store.setValue("export/columns", self.settings.export_columns)
        store.setValue("export/last_dir", self.settings.last_export_dir)
        store.setValue("export/last_format", self.settings.last_export_format)
        store.setValue("import/last_dir", self.settings.last_import_dir)

    def closeEvent(self, event) -> None:  # noqa: D102
        if self.worker is not None and self.worker.isRunning():
            answer = QtWidgets.QMessageBox.question(self, "确认退出", "解析仍在进行，确定要退出吗？")
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.stop()
            self.worker.wait(3000)
        self._save_settings()
        super().closeEvent(event)
