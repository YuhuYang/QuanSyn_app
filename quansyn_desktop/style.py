from __future__ import annotations


APP_STYLE = """
QWidget {
    background: #1d2027;
    color: #d7dde8;
    font-family: "Segoe UI", "Source Sans 3", "Noto Sans";
    font-size: 19px;
}

QMainWindow {
    background: #1d2027;
}

QWidget#windowRoot {
    background: #1d2027;
}

QFrame#appShell {
    background: #1d2027;
    border: none;
    border-radius: 0px;
}

QWidget#titleBar {
    background: #262a33;
    border-bottom: 1px solid #3a404d;
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
}

QWidget#titleBar QToolButton#titleBarButton,
QWidget#titleBar QToolButton#titleBarControl,
QWidget#titleBar QToolButton#titleBarClose {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #d7dde8;
    padding: 4px 10px;
    font-size: 19px;
}

QWidget#titleBar QToolButton#titleBarButton:hover,
QWidget#titleBar QToolButton#titleBarControl:hover {
    background: #353b49;
}

QWidget#titleBar QToolButton#titleBarClose:hover {
    background: #c42b1c;
    color: #ffffff;
}

QWidget#titleBar QToolButton#titleBarButton::menu-indicator {
    image: none;
    width: 0px;
}

QFrame#titleBarSeparator {
    background: #3a404d;
    min-height: 1px;
    max-height: 1px;
    border: none;
}

QMenuBar {
    background: #242833;
    color: #d7dde8;
    border-bottom: 1px solid #3a404d;
    font-size: 19px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 8px;
}

QMenuBar::item:selected {
    background: #353b49;
}

QMenu {
    background: #262b36;
    border: 1px solid #3a404d;
    font-size: 19px;
}

QMenu::item:selected {
    background: #353b49;
}

QToolBar {
    background: #262a33;
    border: none;
    border-bottom: 1px solid #3a404d;
    spacing: 4px;
    padding: 3px 6px;
    font-size: 19px;
}

QToolBar QToolButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px 8px;
}

QToolBar QToolButton:hover {
    background: #353b49;
    border: none;
}

QFrame#iconSidebar {
    background: #232732;
    border: none;
    border-right: 1px solid #3a404d;
    border-bottom-left-radius: 0px;
}

QFrame#iconSidebar QToolButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0px;
}

QFrame#iconSidebar QToolButton:hover {
    background: #333948;
    border: none;
}

QFrame#iconSidebar QToolButton:checked {
    background: rgba(103, 126, 164, 0.34);
    border: none;
}

QFrame#topStatus {
    background: #2a2f3a;
    border: none;
}

QFrame#bottomStatus {
    background: #2a2f3a;
    border-top: 1px solid #3a404d;
    font-size: 17px;
    border-bottom-right-radius: 0px;
}

QFrame#bottomStatus QLabel,
QFrame#bottomStatus QProgressBar {
    font-size: 17px;
}

QFrame#bottomStatus QProgressBar {
    background: #1d2027;
    border: 1px solid #3a404d;
    border-radius: 4px;
}

QFrame#bottomStatus QProgressBar::chunk {
    background: #4f72a8;
}

QToolButton, QPushButton {
    background: #4f72a8;
    border: 1px solid #5e82b9;
    border-radius: 8px;
    color: #ffffff;
    padding: 4px 8px;
}

QToolButton:hover, QPushButton:hover {
    background: #5e82b9;
}

QToolButton:checked {
    background: #426393;
    border-color: #5e82b9;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #8c97a9;
    border-radius: 0px;
    background: #1f232d;
}

QCheckBox::indicator:hover {
    border: 1px solid #a7b3c6;
}

QCheckBox::indicator:checked {
    background: #4f72a8;
    border: 1px solid #9fb0cc;
}

QLabel#panelTitle {
    font-family: "Source Serif 4", "Noto Serif";
    font-size: 21px;
    color: #f3f7ff;
}

QLabel#sectionTitle {
    color: #b8c8df;
    font-size: 19px;
    font-weight: 600;
}

QLabel#statusInfo {
    color: #9ab0cf;
}

QLineEdit, QComboBox, QListWidget, QTextEdit, QTableWidget, QTableView, QTabWidget::pane {
    background: #2a2f3b;
    border: 1px solid #424b5b;
    border-radius: 0px;
    font-size: 19px;
}

QTableWidget, QTableView {
    gridline-color: #424b5b;
    selection-background-color: #3f5f90;
    selection-color: #f1f6ff;
}

QTableWidget::item, QTableView::item {
    background: #2a2f3b;
    color: #d7dde8;
}

QTableWidget::item:selected, QTableView::item:selected {
    background: #3f5f90;
    color: #f1f6ff;
}

QHeaderView::section {
    background: #333947;
    color: #d7dde8;
    border: 1px solid #424b5b;
    padding: 3px;
    font-size: 19px;
}

QTabBar::tab {
    background: #333947;
    color: #c8d1df;
    border: 1px solid #424b5b;
    padding: 6px 12px;
    margin-right: 1px;
    font-size: 19px;
}

QTabBar::tab:selected {
    background: #2a2f3b;
    color: #f1f6ff;
    border-bottom: 1px solid #1e2638;
}

QFrame#depvalDrawer {
    background: #2f3542;
    border: 1px solid #4a5364;
}

QPushButton#drawerHandle {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: transparent;
    padding: 0;
}

QPushButton#drawerOverlay {
    background: rgba(0, 0, 0, 35);
    border: none;
    border-radius: 8px;
}

QFrame#plotCard {
    background: #272d38;
    border: 1px solid #4a5364;
    border-radius: 12px;
}

QWidget#plotCanvas {
    background: transparent;
    border: none;
}

QFrame#vizParamWrap QLabel,
QFrame#vizParamWrap QComboBox,
QFrame#vizParamWrap QPushButton {
    font-size: 19px;
}

QTextEdit#depvalReportBox {
    background: #1f242e;
    border: 1px solid #42516a;
    color: #a8bfde;
}

QTextEdit#reportBox {
    background: #1f242e;
    border: 1px solid #42516a;
    color: #a8bfde;
}

QSplitter::handle {
    background: rgba(148, 156, 170, 0.35);
}

QSplitter::handle:horizontal {
    width: 1px;
}

QSplitter::handle:vertical {
    height: 1px;
}

QPushButton#accentButton {
    background: #4f72a8;
    border-color: #5e82b9;
    border-radius: 14px;
    color: #ffffff;
    font-weight: 600;
    padding: 6px 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
    border: none;
}

QScrollBar::handle:vertical {
    background: rgba(163, 173, 189, 108);
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(163, 173, 189, 152);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    background: transparent;
    border: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 4px 2px 4px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: rgba(163, 173, 189, 108);
    min-width: 28px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: rgba(163, 173, 189, 152);
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    background: transparent;
    border: none;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""


LIGHT_STYLE = """
QWidget {
    background: #e8edf3;
    color: #1f2a3a;
    font-family: "Segoe UI", "Source Sans 3", "Noto Sans";
    font-size: 19px;
}

QMainWindow, QWidget#windowRoot, QFrame#appShell {
    background: #e8edf3;
}

QWidget#titleBar {
    background: #e7ebf1;
    border-bottom: 1px solid #cfd6e0;
}

QFrame#titleBarSeparator {
    background: #cfd6e0;
    min-height: 1px;
    max-height: 1px;
    border: none;
}

QWidget#titleBar QToolButton#titleBarButton,
QWidget#titleBar QToolButton#titleBarControl,
QWidget#titleBar QToolButton#titleBarClose {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #2d3b50;
    padding: 4px 10px;
    font-size: 19px;
}

QWidget#titleBar QToolButton#titleBarButton:hover,
QWidget#titleBar QToolButton#titleBarControl:hover {
    background: #dfe6f2;
}

QWidget#titleBar QToolButton#titleBarClose:hover {
    background: #c42b1c;
    color: #ffffff;
}

QFrame#iconSidebar {
    background: #dde4ee;
    border: none;
    border-right: 1px solid #b9c4d3;
}

QFrame#iconSidebar QToolButton {
    background: #e9eef5;
    border: none;
    border-radius: 8px;
    color: #234064;
}

QFrame#iconSidebar QToolButton:hover {
    background: #d3deec;
}

QFrame#iconSidebar QToolButton:checked {
    background: #bfd1e7;
}

QFrame#topStatus {
    background: #dfe6ef;
}

QFrame#bottomStatus {
    background: #d8e0ea;
    border-top: 1px solid #cfd6e0;
    font-size: 17px;
}

QFrame#bottomStatus QLabel,
QFrame#bottomStatus QProgressBar {
    font-size: 17px;
}

QFrame#bottomStatus QProgressBar {
    background: #f9fbfd;
    border: 1px solid #c5cfdb;
    border-radius: 4px;
}

QFrame#bottomStatus QProgressBar::chunk {
    background: #5a79a7;
}

QToolButton, QPushButton {
    background: #5879aa;
    border: 1px solid #4f6f9e;
    border-radius: 8px;
    color: #ffffff;
    padding: 4px 8px;
}

QToolButton:hover, QPushButton:hover {
    background: #4f6f9e;
}

QToolButton:checked {
    background: #466290;
    border-color: #4f6f9e;
}

QLabel#panelTitle {
    font-family: "Source Serif 4", "Noto Serif";
    font-size: 21px;
    color: #152941;
}

QLabel#sectionTitle {
    color: #233a58;
    font-size: 19px;
    font-weight: 600;
}

QLabel#statusInfo {
    color: #4f6485;
}

QLineEdit, QComboBox, QListWidget, QTextEdit, QTableWidget, QTableView, QTabWidget::pane {
    background: #eef3f8;
    border: 1px solid #cdd4df;
    border-radius: 0px;
    color: #1f2937;
    font-size: 19px;
}

QTableWidget, QTableView {
    gridline-color: #cdd4df;
    selection-background-color: #c8dbf2;
    selection-color: #1f2a3a;
}

QTableWidget::item, QTableView::item {
    background: #eef3f8;
    color: #1f2937;
}

QTableWidget::item:selected, QTableView::item:selected {
    background: #c8dbf2;
    color: #1f2a3a;
}

QHeaderView::section {
    background: #e4e9f0;
    color: #223248;
    border: 1px solid #cdd4df;
    padding: 3px;
    font-size: 19px;
}

QTabBar::tab {
    background: #e4e9f0;
    color: #3f4f66;
    border: 1px solid #cdd4df;
    padding: 6px 12px;
    margin-right: 1px;
    font-size: 19px;
}

QTabBar::tab:selected {
    background: #edf2f8;
    color: #2b4671;
    border-bottom: 1px solid #edf2f8;
}

QFrame#depvalDrawer {
    background: #dfe7f2;
    border: 1px solid #b7c4d6;
}

QPushButton#drawerHandle {
    background: transparent;
    border: none;
    color: transparent;
}

QPushButton#drawerOverlay {
    background: rgba(33, 44, 61, 20);
    border: none;
}

QFrame#plotCard {
    background: #f7f9fc;
    border: 1px solid #cdd4df;
    border-radius: 12px;
}

QTextEdit#depvalReportBox,
QTextEdit#reportBox {
    background: #e6edf6;
    border: 1px solid #c3ccd9;
    color: #2f4f7e;
}

QSplitter::handle {
    background: rgba(137, 145, 159, 0.35);
}

QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

QPushButton#accentButton {
    background: #5879aa;
    border-color: #4f6f9e;
    border-radius: 14px;
    color: #ffffff;
    font-weight: 600;
    padding: 6px 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
    border: none;
}

QScrollBar::handle:vertical {
    background: rgba(121, 132, 147, 104);
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(121, 132, 147, 148);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 4px 2px 4px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: rgba(121, 132, 147, 104);
    min-width: 28px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: rgba(121, 132, 147, 148);
}
"""


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def build_app_style(theme: str = "Dark", ui_scale: float = 1.0, font_size: int = 12) -> str:
    """Return QSS sized for the current display and user font preference."""
    try:
        scale = max(0.58, min(1.0, float(ui_scale)))
    except Exception:
        scale = 1.0
    try:
        base_font = int(font_size)
    except Exception:
        base_font = 12
    base_font = _clamp_int(base_font, 10, 22)

    main_px = _clamp_int(round(base_font * 1.35 * scale), 14, 19)
    title_px = _clamp_int(main_px + 2, 15, 21)
    section_px = _clamp_int(main_px, 13, 19)
    status_px = _clamp_int(main_px - 2, 12, 17)
    pad_v = _clamp_int(round(4 * scale), 3, 4)
    pad_h = _clamp_int(round(8 * scale), 6, 8)
    tab_v = _clamp_int(round(6 * scale), 4, 6)
    tab_h = _clamp_int(round(12 * scale), 8, 12)
    button_min_h = _clamp_int(round((main_px + 15) * scale), 28, 34)
    input_min_h = _clamp_int(round((main_px + 13) * scale), 27, 32)
    radius = _clamp_int(round(8 * scale), 5, 8)

    style = LIGHT_STYLE if str(theme or "").strip().lower() == "light" else APP_STYLE
    return (
        style
        + f"""

/* Runtime display scaling overrides. */
QWidget {{
    font-size: {main_px}px;
}}

QWidget#titleBar QToolButton#titleBarButton,
QWidget#titleBar QToolButton#titleBarControl,
QWidget#titleBar QToolButton#titleBarClose,
QMenuBar,
QMenu,
QToolBar,
QFrame#vizParamWrap QLabel,
QFrame#vizParamWrap QComboBox,
QFrame#vizParamWrap QPushButton {{
    font-size: {main_px}px;
}}

QFrame#bottomStatus,
QFrame#bottomStatus QLabel,
QFrame#bottomStatus QProgressBar {{
    font-size: {status_px}px;
}}

QLabel#panelTitle {{
    font-size: {title_px}px;
}}

QLabel#sectionTitle {{
    font-size: {section_px}px;
}}

QToolButton,
QPushButton {{
    border-radius: {radius}px;
    min-height: {button_min_h}px;
    padding: {pad_v}px {pad_h}px;
}}

QToolBar QToolButton,
QWidget#titleBar QToolButton#titleBarButton,
QWidget#titleBar QToolButton#titleBarControl,
QWidget#titleBar QToolButton#titleBarClose {{
    min-height: {max(22, button_min_h - 4)}px;
    padding: {max(2, pad_v - 1)}px {pad_h}px;
}}

QFrame#iconSidebar QToolButton#sidebarButton {{
    min-height: 0px;
    padding: 0px;
    margin: 0px;
    border: none;
}}

QFrame#iconSidebar QToolButton#sidebarButton:checked {{
    padding: 0px;
    margin: 0px;
    border: none;
}}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {{
    min-height: {input_min_h}px;
    padding: {max(2, pad_v - 1)}px {pad_h}px;
}}

QLineEdit, QComboBox, QListWidget, QTextEdit, QTableWidget, QTableView, QTabWidget::pane {{
    font-size: {main_px}px;
}}

QHeaderView::section {{
    font-size: {main_px}px;
    padding: {max(2, pad_v - 1)}px;
}}

QTabBar::tab {{
    font-size: {main_px}px;
    padding: {tab_v}px {tab_h}px;
}}
"""
    )
