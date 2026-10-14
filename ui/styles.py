"""界面主题（QSS）：浅色 / 深色两套，支持一键切换。"""
from __future__ import annotations

LIGHT_QSS = """
* { outline: 0; }

QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1f2329;
}
QMainWindow, QDialog { background: #f2f4f7; }
QWidget#Central { background: #f2f4f7; }
QWidget#Card {
    background: #ffffff;
    border: 1px solid #e3e7ee;
    border-radius: 10px;
}
QLabel#AppTitle { font-size: 19px; font-weight: 700; color: #101828; }
QLabel#AppSubtitle { color: #7b8494; font-size: 12px; line-height: 170%; }
QLabel#SectionTitle { font-size: 13px; font-weight: 700; color: #344054; }
QLabel#FieldLabel { color: #4b5563; font-weight: 600; }
QLabel#Hint { color: #8a93a3; font-size: 12px; }
QLabel#Chip {
    background: #eef3ff; color: #2f6fed; border: 1px solid #d6e2ff;
    border-radius: 9px; padding: 2px 10px; font-size: 12px;
}
QLabel#ChipWarn { background: #fff5e8; color: #b25e09; border: 1px solid #ffe0b8;
    border-radius: 9px; padding: 2px 10px; font-size: 12px; }
QLabel#ChipOk { background: #e9f9f0; color: #12805c; border: 1px solid #c3ecd8;
    border-radius: 9px; padding: 2px 10px; font-size: 12px; }

QToolBar { background: #ffffff; border: none; border-bottom: 1px solid #e3e7ee; spacing: 4px; padding: 6px 8px; }
QToolBar::separator { background: #e3e7ee; width: 1px; margin: 4px 6px; }
QToolButton {
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 5px 10px; color: #344054;
}
QToolButton:hover { background: #f0f3f9; border-color: #dfe4ee; }
QToolButton:pressed { background: #e6ebf5; }
QToolButton:disabled { color: #b6bcc7; }
QToolButton#Primary { background: #2f6fed; color: #ffffff; border: 1px solid #2f6fed; font-weight: 600; }
QToolButton#Primary:hover { background: #2560d8; }
QToolButton#Primary:disabled { background: #b7c8f4; border-color: #b7c8f4; color: #ffffff; }

QPushButton {
    background: #ffffff; border: 1px solid #d6dbe5; border-radius: 6px; padding: 6px 14px; color: #344054;
}
QPushButton:hover { background: #f7f9fc; border-color: #c3cbd9; }
QPushButton:pressed { background: #eef1f7; }
QPushButton:disabled { color: #b6bcc7; background: #f5f6f8; }
QPushButton#Primary { background: #2f6fed; border-color: #2f6fed; color: #ffffff; font-weight: 600; }
QPushButton#Primary:hover { background: #2560d8; }
QPushButton#Primary:disabled { background: #b7c8f4; border-color: #b7c8f4; }
QPushButton#Danger { color: #c0392b; border-color: #f0c4bd; }
QPushButton#Danger:hover { background: #fdf1ef; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background: #ffffff; border: 1px solid #d6dbe5; border-radius: 6px; padding: 5px 8px;
    selection-background-color: #2f6fed; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #2f6fed; }
QLineEdit#Search { padding-left: 10px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #ffffff; border: 1px solid #d6dbe5; selection-background-color: #eef3ff;
    selection-color: #1f2329; outline: 0;
}

QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; border: none; padding: 7px 14px; margin-right: 4px;
    color: #667085; border-radius: 6px; font-weight: 600;
}
QTabBar::tab:hover { background: #e9edf6; color: #344054; }
QTabBar::tab:selected { background: #ffffff; color: #2f6fed; }

QTableView, QTableWidget, QTreeView, QListView {
    background: #ffffff; border: 1px solid #e3e7ee; border-radius: 8px;
    gridline-color: #eef1f6; selection-background-color: #dbe6ff; selection-color: #101828;
    alternate-background-color: #fafbfd;
}
QTableView::item:selected, QTableWidget::item:selected { background: #dbe6ff; color: #101828; }
QTableView::item:selected:active, QTableWidget::item:selected:active { background: #d2e0ff; color: #101828; }
QTableView::item, QTableWidget::item { padding: 4px 6px; border: none; }
QHeaderView::section {
    background: #f7f9fc; color: #5b6474; border: none; border-bottom: 1px solid #e3e7ee;
    border-right: 1px solid #eef1f6; padding: 7px 6px; font-weight: 600;
}
QHeaderView::section:hover { background: #eef1f7; }
QTableCornerButton::section { background: #f7f9fc; border: none; }

QProgressBar {
    background: #e9edf4; border: none; border-radius: 6px; height: 12px; text-align: center;
    color: #344054; font-size: 11px;
}
QProgressBar::chunk { background: #2f6fed; border-radius: 6px; }

QStatusBar { background: #ffffff; border-top: 1px solid #e3e7ee; color: #5b6474; }
QStatusBar::item { border: none; }

QSplitter::handle { background: #e9edf4; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }

QGroupBox {
    border: 1px solid #e3e7ee; border-radius: 8px; margin-top: 12px; padding: 10px 12px 12px 12px;
    background: #ffffff; font-weight: 600; color: #344054;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QCheckBox, QRadioButton { spacing: 6px; color: #344054; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QCheckBox::indicator { border: 1px solid #c3cbd9; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked { background: #2f6fed; border-color: #2f6fed; image: none; }
QRadioButton::indicator { border: 1px solid #c3cbd9; border-radius: 8px; background: #ffffff; }
QRadioButton::indicator:checked { background: #2f6fed; border: 3px solid #ffffff; outline: 1px solid #2f6fed; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #ccd3df; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #b4bdcb; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #ccd3df; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMenuBar { background: #ffffff; border-bottom: 1px solid #e3e7ee; }
QMenuBar::item { padding: 6px 10px; background: transparent; border-radius: 5px; }
QMenuBar::item:selected { background: #eef3ff; color: #2f6fed; }
QMenu { background: #ffffff; border: 1px solid #e3e7ee; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 26px 6px 22px; border-radius: 5px; }
QMenu::item:selected { background: #eef3ff; color: #2f6fed; }
QMenu::separator { height: 1px; background: #eef1f6; margin: 5px 8px; }

QToolTip { background: #1f2329; color: #ffffff; border: none; padding: 5px 8px; border-radius: 4px; }
"""

DARK_QSS = """
* { outline: 0; }
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px; color: #e4e7ee;
}
QMainWindow, QDialog, QWidget#Central { background: #1b1e26; }
QWidget#Card { background: #232733; border: 1px solid #313746; border-radius: 10px; }
QLabel#AppTitle { font-size: 19px; font-weight: 700; color: #ffffff; }
QLabel#AppSubtitle, QLabel#Hint { color: #8f97a8; font-size: 12px; line-height: 170%; }
QLabel#SectionTitle { font-size: 13px; font-weight: 700; color: #cdd3e0; }
QLabel#FieldLabel { color: #b9c1d0; font-weight: 600; }
QLabel#Chip { background: #24304a; color: #8fb4ff; border: 1px solid #33456b; border-radius: 9px; padding: 2px 10px; font-size: 12px; }
QLabel#ChipWarn { background: #3a2f22; color: #e8b273; border: 1px solid #59452c; border-radius: 9px; padding: 2px 10px; font-size: 12px; }
QLabel#ChipOk { background: #1f3730; color: #6fd0a6; border: 1px solid #2c5348; border-radius: 9px; padding: 2px 10px; font-size: 12px; }
QToolBar { background: #232733; border: none; border-bottom: 1px solid #313746; spacing: 4px; padding: 6px 8px; }
QToolBar::separator { background: #313746; width: 1px; margin: 4px 6px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 10px; color: #cdd3e0; }
QToolButton:hover { background: #2c3140; border-color: #39404f; }
QToolButton#Primary { background: #3b7bf0; color: #ffffff; border-color: #3b7bf0; font-weight: 600; }
QToolButton#Primary:disabled { background: #39445c; border-color: #39445c; color: #8d95a8; }
QPushButton { background: #2a2f3c; border: 1px solid #3a4152; border-radius: 6px; padding: 6px 14px; color: #e4e7ee; }
QPushButton:hover { background: #313747; }
QPushButton#Primary { background: #3b7bf0; border-color: #3b7bf0; color: #ffffff; font-weight: 600; }
QPushButton#Danger { color: #ef8b7d; border-color: #5a3a37; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background: #1e2230; border: 1px solid #3a4152; border-radius: 6px; padding: 5px 8px; color: #e4e7ee;
    selection-background-color: #3b7bf0;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #3b7bf0; }
QComboBox QAbstractItemView { background: #232733; border: 1px solid #3a4152; selection-background-color: #2f3a52; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; border: none; padding: 7px 14px; margin-right: 4px; color: #8f97a8; border-radius: 6px; font-weight: 600; }
QTabBar::tab:hover { background: #2a2f3c; color: #cdd3e0; }
QTabBar::tab:selected { background: #232733; color: #8fb4ff; }
QTableView, QTableWidget, QTreeView, QListView {
    background: #1e2230; border: 1px solid #313746; border-radius: 8px;
    gridline-color: #2a2f3c; selection-background-color: #2b3a58; selection-color: #ffffff;
    alternate-background-color: #21252f;
}
QTableView::item:selected, QTableWidget::item:selected { background: #2b3a58; color: #ffffff; }
QHeaderView::section { background: #262b37; color: #9aa3b4; border: none; border-bottom: 1px solid #313746; border-right: 1px solid #2a2f3c; padding: 7px 6px; font-weight: 600; }
QProgressBar { background: #2a2f3c; border: none; border-radius: 6px; height: 12px; color: #cdd3e0; font-size: 11px; }
QProgressBar::chunk { background: #3b7bf0; border-radius: 6px; }
QStatusBar { background: #232733; border-top: 1px solid #313746; color: #9aa3b4; }
QSplitter::handle { background: #2a2f3c; }
QGroupBox { border: 1px solid #313746; border-radius: 8px; margin-top: 12px; padding: 10px; background: #232733; font-weight: 600; color: #cdd3e0; }
QMenuBar { background: #232733; border-bottom: 1px solid #313746; }
QMenuBar::item:selected { background: #2f3a52; color: #8fb4ff; }
QMenu { background: #232733; border: 1px solid #313746; border-radius: 8px; padding: 5px; }
QMenu::item:selected { background: #2f3a52; color: #8fb4ff; }
QToolTip { background: #101319; color: #ffffff; border: none; padding: 5px 8px; border-radius: 4px; }
"""


def qss(theme: str = "light") -> str:
    return DARK_QSS if str(theme).lower() == "dark" else LIGHT_QSS


_current = "light"


def set_theme(theme: str) -> None:
    global _current
    _current = "dark" if str(theme).lower() == "dark" else "light"


def current_theme() -> str:
    return _current
