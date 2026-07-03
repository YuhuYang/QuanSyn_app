from __future__ import annotations

import csv
import base64
import hashlib
import html
import importlib
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from ..style import build_app_style

from PyQt6.QtCore import QAbstractTableModel, QByteArray, QEvent, QModelIndex, QPoint, QEasingCurve, QPropertyAnimation, QRect, QSize, QSizeF, QStringListModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPdfWriter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsPixmapItem,
    QGridLayout,
    QGraphicsOpacityEffect,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


class NumericSortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):  # type: ignore[override]
        if isinstance(other, QTableWidgetItem):
            try:
                return float(self.text()) < float(other.text())
            except Exception:
                return self.text() < other.text()
        return super().__lt__(other)


class ResultTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], rows: list[list[object]], row_groups: list[str] | None = None):
        super().__init__()
        self.headers = [str(h) for h in headers]
        self.rows = [[self._stringify(v) for v in row] for row in rows]
        self.row_groups = list(row_groups or [])
        self.filters: dict[int, set[str]] = {}
        self.filtered_rows = list(range(len(self.rows)))
        self._group_toggles = self._build_group_toggles()

    @staticmethod
    def _stringify(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    def _build_group_toggles(self) -> list[int]:
        toggles: list[int] = []
        current = None
        toggle = 0
        for idx in range(len(self.rows)):
            group = self.row_groups[idx] if idx < len(self.row_groups) else f"row-{idx}"
            if current is None:
                current = group
            elif group != current:
                toggle = 1 - toggle
                current = group
            toggles.append(toggle)
        return toggles

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.filtered_rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.filtered_rows) or col < 0 or col >= len(self.headers):
            return None
        source_row = self.filtered_rows[row]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole, int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.EditRole)):
            try:
                return self.rows[source_row][col]
            except Exception:
                return ""
        if role in (Qt.ItemDataRole.BackgroundRole, int(Qt.ItemDataRole.BackgroundRole)) and len(self.rows) <= 2500:
            toggle = self._group_toggles[source_row] if source_row < len(self._group_toggles) else 0
            return QColor("#14181e" if toggle == 0 else "#344050")
        if role in (Qt.ItemDataRole.ForegroundRole, int(Qt.ItemDataRole.ForegroundRole)) and len(self.rows) <= 2500:
            return QColor("#E6EAF0")
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)):  # type: ignore[override]
        if role not in (Qt.ItemDataRole.DisplayRole, int(Qt.ItemDataRole.DisplayRole)):
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                suffix = " *" if self.filters.get(section) else ""
                return f"{self.headers[section]}{suffix}"
            return ""
        return str(section + 1)

    def flags(self, index: QModelIndex):  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def set_filter(self, column: int, values: set[str] | None) -> None:
        if values:
            self.filters[int(column)] = {str(v) for v in values}
        else:
            self.filters.pop(int(column), None)
        self._rebuild_filtered_rows()

    def set_filters(self, filters: dict[int, set[str] | None]) -> None:
        self.filters.clear()
        for column, values in filters.items():
            if values:
                self.filters[int(column)] = {str(v) for v in values}
        self._rebuild_filtered_rows()

    def _rebuild_filtered_rows(self) -> None:
        self.beginResetModel()
        if not self.filters:
            self.filtered_rows = list(range(len(self.rows)))
        else:
            out: list[int] = []
            for r, row in enumerate(self.rows):
                ok = True
                for c, values in self.filters.items():
                    val = row[c] if 0 <= c < len(row) else ""
                    if val not in values:
                        ok = False
                        break
                if ok:
                    out.append(r)
            self.filtered_rows = out
        self.endResetModel()
        if self.headers:
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self.headers) - 1)

    def distinct_values(self, column: int) -> list[str]:
        seen: set[str] = set()
        values: list[str] = []
        for row in self.rows:
            val = row[column] if 0 <= column < len(row) else ""
            if val not in seen:
                seen.add(val)
                values.append(val)
        return values

    def to_rows(self, scope: str = "filtered") -> tuple[list[str], list[list[str]]]:
        if str(scope).strip().lower() == "all":
            indices = range(len(self.rows))
        else:
            indices = self.filtered_rows
        return list(self.headers), [list(self.rows[i]) for i in indices]

    def to_dataframe(self, scope: str = "filtered"):
        if pd is None:
            return None
        headers, rows = self.to_rows(scope)
        return pd.DataFrame([dict(zip(headers, row)) for row in rows])


class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#ffffff"))

    def wheelEvent(self, event):  # type: ignore[override]
        # Keep size responsive to the viewport; disable wheel-based zoom.
        event.ignore()

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        scene = self.scene()
        if scene is not None and not scene.sceneRect().isNull():
            self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class ThemedDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drag_active = False
        self._drag_offset = QPoint(0, 0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        src = _dialog_theme_source(parent)
        if src is not None:
            try:
                self.setWindowIcon(src.windowIcon())
            except Exception:
                pass

        shell = QFrame()
        shell.setObjectName("dialogShell")
        outer.addWidget(shell)

        shell_l = QVBoxLayout(shell)
        shell_l.setContentsMargins(0, 0, 0, 0)
        shell_l.setSpacing(0)

        self._title_bar = QFrame()
        self._title_bar.setObjectName("dialogTitleBar")
        title_l = QHBoxLayout(self._title_bar)
        title_l.setContentsMargins(10, 6, 8, 6)
        title_l.setSpacing(8)
        self._title_label = QLabel(title)
        title_l.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignLeft)
        title_l.addStretch(1)
        self._close_btn = QToolButton()
        self._close_btn.setText("x")
        self._close_btn.clicked.connect(self.reject)
        title_l.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignRight)
        shell_l.addWidget(self._title_bar, 0)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(8)
        shell_l.addWidget(self.content, 1)

        self._apply_chrome_colors(src)
        self._title_bar.installEventFilter(self)

    def _apply_chrome_colors(self, src: QWidget | None) -> None:
        def _contrast_fg(bg: QColor) -> QColor:
            # WCAG-style relative luminance approximation for selecting readable text color.
            r, g, b = bg.red() / 255.0, bg.green() / 255.0, bg.blue() / 255.0
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            return QColor("#0b1220") if lum > 0.55 else QColor("#f8fafc")

        pal = src.palette() if isinstance(src, QWidget) else self.palette()
        base = QColor(pal.window().color())
        if not base.isValid():
            base = QColor("#f3f4f6")
        title_bg = base.darker(108) if base.lightness() > 120 else base.lighter(115)
        border = base.darker(125) if base.lightness() > 120 else base.lighter(130)
        hover = title_bg.darker(112) if title_bg.lightness() > 120 else title_bg.lighter(118)
        strong_text = _contrast_fg(base)
        title_text = _contrast_fg(title_bg)
        accent_text = QColor("#1d4ed8") if strong_text.name().lower() == "#0b1220" else QColor("#93c5fd")
        hover_text = _contrast_fg(hover)
        self.setStyleSheet(
            "QFrame#dialogShell{"
            f"background:{base.name()};border:1px solid {border.name()};"
            "}"
            "QFrame#dialogTitleBar{"
            f"background:{title_bg.name()};border-bottom:1px solid {border.name()};"
            "}"
            f"QLabel{{color:{strong_text.name()};}}"
            "QToolButton{"
            f"border:none;color:{title_text.name()};padding:2px 6px;"
            "}"
            f"QToolButton:hover{{background:{hover.name()};color:{hover_text.name()};}}"
            f"QLabel#dialogContext{{color:{accent_text.name()};font-weight:600;}}"
            f"QLabel#dialogBody{{color:{strong_text.name()};font-weight:600;}}"
            f"QPushButton{{color:{strong_text.name()};}}"
        )
        self._title_label.setStyleSheet(f"font-weight:700;color:{title_text.name()};")

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self._title_bar:
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_active = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == event.Type.MouseMove and self._drag_active:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if event.type() == event.Type.MouseButtonRelease:
                self._drag_active = False
                return True
        return super().eventFilter(obj, event)


class ThemedMessageDialog(ThemedDialog):
    def __init__(self, context: str, text: str, is_warning: bool, parent: QWidget | None = None):
        super().__init__("QuanSyn Studio", parent)
        self.resize(520, 180)
        body = QLabel(str(text))
        body.setObjectName("dialogBody")
        body.setWordWrap(True)
        self.content_layout.addWidget(body, 1)
        if context:
            info = QLabel(str(context))
            info.setObjectName("dialogContext")
            info.setWordWrap(True)
            self.content_layout.addWidget(info, 0)
        btn_row = QWidget()
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(0, 4, 0, 0)
        btn_l.addStretch(1)
        ok = QPushButton("OK")
        ok.setObjectName("accentButton")
        ok.clicked.connect(self.accept)
        btn_l.addWidget(ok, 0, Qt.AlignmentFlag.AlignRight)
        self.content_layout.addWidget(btn_row, 0)


def _dialog_theme_source(parent: QWidget | None) -> QWidget | None:
    if isinstance(parent, QWidget):
        w = parent
        while isinstance(w, QWidget) and w.parentWidget() is not None:
            w = w.parentWidget()
        return w
    active = QApplication.activeWindow()
    return active if isinstance(active, QWidget) else None


def _apply_dialog_chrome(dialog: QDialog | QMessageBox, parent: QWidget | None) -> None:
    src = _dialog_theme_source(parent)
    if src is not None:
        try:
            dialog.setWindowIcon(src.windowIcon())
        except Exception:
            pass
        try:
            style = src.styleSheet()
            if style:
                dialog.setStyleSheet(style)
        except Exception:
            pass
        try:
            app_title = str(src.windowTitle() or "").strip()
            if app_title:
                dialog.setWindowTitle(app_title)
        except Exception:
            pass
    if not str(dialog.windowTitle() or "").strip():
        dialog.setWindowTitle("QuanSyn Studio")


def _reject_web_fullscreen(view: object) -> None:
    try:
        page = view.page() if hasattr(view, "page") else None
    except Exception:
        page = None
    if page is None:
        return
    try:
        sig = getattr(page, "fullScreenRequested", None)
        if sig is None:
            return

        def _on_req(req):
            try:
                req.reject()
            except Exception:
                pass

        sig.connect(_on_req)
    except Exception:
        pass


def _lets_plot_local_js_uri() -> str:
    try:
        import lets_plot as _lp  # type: ignore

        lp_root = Path(_lp.__file__).resolve().parent
        js_path = lp_root / "package_data" / "lets-plot.min.js"
        if js_path.exists():
            return QUrl.fromLocalFile(str(js_path)).toString()
    except Exception:
        pass
    return ""


def _lets_plot_html_with_local_js(plot_obj) -> str:
    html_text = ""
    try:
        html_text = str(plot_obj.to_html() or "")
    except Exception:
        return ""
    if not html_text:
        return ""
    local_js = _lets_plot_local_js_uri()
    if local_js:
        return re.sub(
            r"(<script[^>]*data-lets-plot-script=\"library\"[^>]*src=\")([^\"]+)(\"[^>]*></script>)",
            rf"\1{local_js}\3",
            html_text,
            flags=re.IGNORECASE,
        )
    return html_text


def _show_info_dialog(parent: QWidget | None, context: str, text: str) -> None:
    title = _ui_tr("QuanSyn Studio")
    if context:
        QMessageBox.information(parent, title, f"{_ui_tr(context)}\n\n{_ui_tr(text)}")
    else:
        QMessageBox.information(parent, title, _ui_tr(str(text)))


def _show_warning_dialog(parent: QWidget | None, context: str, text: str) -> None:
    title = _ui_tr("QuanSyn Studio")
    if context:
        QMessageBox.warning(parent, title, f"{_ui_tr(context)}\n\n{_ui_tr(text)}")
    else:
        QMessageBox.warning(parent, title, _ui_tr(str(text)))


def _show_question_dialog(parent: QWidget | None, context: str, text: str) -> bool:
    prompt = f"{_ui_tr(context)}\n\n{_ui_tr(text)}" if context else _ui_tr(str(text))
    ret = QMessageBox.question(
        parent,
        _ui_tr("QuanSyn Studio"),
        prompt,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes


_UI_LANG = "en"


def set_ui_language(language: str) -> None:
    global _UI_LANG
    s = str(language or "").strip().lower()
    _UI_LANG = "zh" if s in {"汉语", "中文", "chinese", "zh", "zh-cn"} else "en"


def is_ui_zh() -> bool:
    return _UI_LANG == "zh"


def _ui_tr(text: str) -> str:
    src = str(text or "")
    if not is_ui_zh() or not src:
        return src
    exact = {
        "QuanSyn Studio": "句法计量分析工作台",
        "Settings applied.": "设置已应用。",
        "Settings updated": "设置已更新",
        "Parser": "句法分析",
        "Parser failed": "句法分析失败",
        "Model name is required.": "模型名称不能为空。",
        "Input text is empty.": "输入文本为空。",
        "No CoNLL-U output to save.": "没有可保存的 CoNLL-U 输出。",
        "Format error": "格式错误",
        "Syntax": "句法分析",
    }
    if src in exact:
        return exact[src]
    replacements = [
        ("Parser task is already running...", "句法分析任务正在运行..."),
        ("Parser task failed.", "句法分析任务失败。"),
        ("Parser failed:", "句法分析失败："),
        ("Loading model...", "正在加载模型..."),
        ("Parsing text to CoNLL-U...", "正在解析文本为 CoNLL-U..."),
        ("Model loaded:", "模型已加载："),
        ("Parsed with", "解析完成："),
        ("Saved:", "已保存："),
        ("RetriVis matched", "检索匹配到"),
        ("sentence(s).", "个句子。"),
        ("Convert done:", "转换完成："),
        ("cached treebank(s).", "个树库已缓存。"),
        ("Compute is already running in background.", "后台计算已在运行。"),
        ("Computing in background. You can switch pages.", "正在后台计算，你可以切换页面继续工作。"),
        ("No cached compute results. Click Compute first.", "暂无缓存计算结果，请先点击 Compute。"),
        ("Statistical test completed.", "统计检验完成。"),
        ("Stat test failed:", "统计检验失败："),
        ("Large result table detected. Auto-plot skipped; click Draw to plot manually.", "检测到大表，已跳过自动绘图；请点击 Draw 手动绘图。"),
        ("lets-plot is unavailable. Please install lets-plot.", "lets-plot 不可用，请安装 lets-plot。"),
        ("No visible rows to plot after current table filter.", "当前筛选后无可绘制行。"),
        ("This plot type requires two columns.", "该图类型需要两列数据。"),
        ("Selected columns have no plottable data.", "所选列没有可绘制数据。"),
        ("Render failed with lets-plot.", "lets-plot 渲染失败。"),
        ("Saved image:", "图片已保存："),
        ("Saved edge list:", "边列表已保存："),
        ("Lingnet running", "LingNet 运行中"),
        ("Lingnet completed", "LingNet 已完成"),
        ("Lingnet failed:", "LingNet 失败："),
        ("Re-import treebanks", "重新导入树库"),
        ("Treebanks have already been imported. Clear current treebanks and re-import?", "已导入树库，是否清空当前树库并重新导入？"),
        ("Scanning treebank folder in background...", "正在后台扫描树库文件夹..."),
        ("Imported 1 treebank.", "已导入 1 个树库。"),
        ("Imported", "已导入"),
        ("treebanks.", "个树库。"),
    ]
    out = src
    for a, b in replacements:
        out = out.replace(a, b)
    return out


def ui_tr(text: str) -> str:
    return _ui_tr(text)


def _themed_get_open_file_name(parent: QWidget | None, title: str, directory: str = "", file_filter: str = "") -> tuple[str, str]:
    return QFileDialog.getOpenFileName(parent, title, directory, file_filter)


def _themed_get_save_file_name(parent: QWidget | None, title: str, directory: str = "", file_filter: str = "") -> tuple[str, str]:
    return QFileDialog.getSaveFileName(parent, title, directory, file_filter)


def _themed_get_existing_directory(parent: QWidget | None, title: str, directory: str = "") -> str:
    return QFileDialog.getExistingDirectory(parent, title, directory)
os.environ.setdefault("QT_API", "pyqt6")

try:
    import qtawesome as qta
except Exception:  # pragma: no cover
    qta = None

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    from lets_plot import (
        aes as lp_aes,
        element_blank as lp_element_blank,
        element_text as lp_element_text,
        geom_area as lp_geom_area,
        geom_bar as lp_geom_bar,
        geom_boxplot as lp_geom_boxplot,
        geom_density as lp_geom_density,
        geom_histogram as lp_geom_histogram,
        geom_line as lp_geom_line,
        geom_point as lp_geom_point,
        ggplot as lp_ggplot,
        ggsize as lp_ggsize,
        labs as lp_labs,
        margin as lp_margin,
        scale_x_continuous as lp_scale_x_continuous,
        scale_x_discrete as lp_scale_x_discrete,
        theme as lp_theme,
        theme_minimal as lp_theme_minimal,
    )
except Exception:  # pragma: no cover
    lp_ggplot = None
    lp_aes = None
    lp_geom_point = None
    lp_geom_line = None
    lp_geom_bar = None
    lp_geom_histogram = None
    lp_geom_density = None
    lp_geom_boxplot = None
    lp_geom_area = None
    lp_labs = None
    lp_ggsize = None
    lp_element_blank = None
    lp_element_text = None
    lp_margin = None
    lp_scale_x_continuous = None
    lp_scale_x_discrete = None
    lp_theme = None
    lp_theme_minimal = None

nx = None
ig = None
_networkit_import_error = ""

try:
    import networkit as nk
except Exception as exc:  # pragma: no cover
    nk = None
    _networkit_import_error = str(exc)

try:
    import pingouin as pg
except Exception:  # pragma: no cover
    pg = None

try:
    from scipy import stats as scipy_stats
except Exception:  # pragma: no cover
    scipy_stats = None


def _ensure_pingouin():
    global pg
    if pg is not None:
        return pg
    try:
        pg = _optional_runtime_import("pingo", "uin")
    except Exception:
        pg = None
    return pg


def _ensure_networkit():
    global nk, _networkit_import_error
    if nk is not None:
        return nk
    try:
        nk = importlib.import_module("networkit")
        _networkit_import_error = ""
    except Exception as exc:
        nk = None
        _networkit_import_error = str(exc)
    return nk


_stanza_import_error = ""
_spacy_import_error = ""


def _optional_runtime_import(*parts: str):
    return importlib.import_module(_runtime_module_name(*parts))


def _runtime_module_name(*parts: str) -> str:
    return "".join(parts)


def _ensure_parser_runtime_path() -> None:
    roots: list[Path] = []
    env_root = str(os.environ.get("QUANSYN_PARSER_RUNTIME", "") or "").strip()
    if env_root:
        roots.append(Path(env_root))
    base = _runtime_base_dir()
    roots.extend(
        [
            base / "parser_runtime",
            base / "runtime" / "parser",
            Path(__file__).resolve().parent.parent / "parser_runtime",
        ]
    )
    for root in roots:
        site_candidates = [
            root,
            root / "site-packages",
            root / "Lib" / "site-packages",
        ]
        for site_dir in site_candidates:
            try:
                if site_dir.exists() and site_dir.is_dir():
                    s = str(site_dir)
                    if s not in sys.path:
                        sys.path.insert(0, s)
            except Exception:
                pass
        dll_candidates = [
            root,
            root / "Library" / "bin",
            root / "site-packages" / "Library" / "bin",
            root / "Lib" / "site-packages" / "Library" / "bin",
            root / "site-packages" / "torch" / "lib",
            root / "Lib" / "site-packages" / "torch" / "lib",
        ]
        for dll_dir in dll_candidates:
            try:
                if dll_dir.exists() and dll_dir.is_dir():
                    os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
                    add_dll_dir = getattr(os, "add_dll_directory", None)
                    if add_dll_dir is not None:
                        add_dll_dir(str(dll_dir))
            except Exception:
                pass


def _ensure_spacy():
    global spacy, _spacy_import_error
    if spacy is not None:
        return spacy
    _ensure_parser_runtime_path()
    try:
        spacy = _optional_runtime_import("spa", "cy")
        _spacy_import_error = ""
    except Exception as exc:
        _spacy_import_error = str(exc)
        spacy = None
    return spacy


def _spacy_installed_models() -> list[str]:
    spacy_mod = _ensure_spacy()
    if spacy_mod is None:
        return []
    try:
        util_mod = importlib.import_module(".".join((_runtime_module_name("spa", "cy"), "util")))
        getter = getattr(util_mod, "get_installed_models", None)
        if getter is None:
            return []
        return [str(name).strip() for name in getter() if str(name).strip()]
    except Exception:
        return []


def _ensure_stanza():
    global stanza, _stanza_import_error
    if stanza is not None:
        return stanza
    _ensure_parser_runtime_path()
    try:
        stanza = _optional_runtime_import("stan", "za")
        _stanza_import_error = ""
    except Exception as exc:
        _stanza_import_error = str(exc)
        stanza = None
    return stanza


def _ensure_spacy_zh_runtime() -> tuple[bool, str]:
    _ensure_parser_runtime_path()
    try:
        mod = _optional_runtime_import("spa", "cy", "_", "pku", "seg")
    except Exception as exc:
        return False, f"spacy_pkuseg is unavailable: {exc}"
    try:
        try:
            from importlib.resources import files as _res_files

            p = _res_files("spacy_pkuseg").joinpath("dicts").joinpath("default.pkl")
            if p.is_file():
                return True, ""
        except Exception:
            pass
        mod_file = Path(str(getattr(mod, "__file__", "") or "")).resolve()
        data_file = mod_file.parent / "dicts" / "default.pkl"
        if data_file.exists():
            return True, ""
        # Frozen/Nuitka runtime fallback: package data may be placed under dist root.
        frozen_data = _runtime_base_dir() / "spacy_pkuseg" / "dicts" / "default.pkl"
        if frozen_data.exists():
            return True, ""
        return False, f"spacy_pkuseg dict is missing: {data_file}"
    except Exception as exc:
        return False, f"spacy_pkuseg check failed: {exc}"

try:
    import powerlaw
except Exception:  # pragma: no cover
    powerlaw = None

try:
    from cleantext import clean as cleantext_clean
except Exception:  # pragma: no cover
    cleantext_clean = None

spacy = None
stanza = None

def _fetch_json_from_urls(urls: list[str], timeout: int = 20) -> tuple[object | None, str]:
    last_err = ""
    last_url = ""
    for u in urls:
        last_url = str(u)
        try:
            req = urllib.request.Request(last_url, headers={"User-Agent": "QuanSyn-Studio/0.0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore")), ""
        except Exception as exc:
            last_err = str(exc)
    return None, f"{last_err or 'fetch failed'} (url={last_url or 'n/a'})"

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover
    QWebEngineView = None
try:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
except Exception:  # pragma: no cover
    QWebEnginePage = None
    QWebEngineSettings = None

try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover
    QSvgRenderer = None

try:
    from conllu import parse_incr as conllu_parse_incr
except Exception:  # pragma: no cover
    conllu_parse_incr = None

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover
    try:
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
    except Exception:
        FigureCanvas = None
        Figure = None


SUPPORTED_FORMATS = ("conllu", "conll", "mcdt", "pmt")

CACHE_SCHEMA_VERSION = "1"


def _runtime_base_dir() -> Path:
    try:
        if bool(getattr(sys, "frozen", False)):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path.cwd()


def _quansyn_cache_root() -> Path:
    return _runtime_base_dir() / ".quansyn_cache"


def _quansyn_cache_path(*parts: str) -> Path:
    p = _quansyn_cache_root().joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_quansyn_cache_layout() -> None:
    root = _quansyn_cache_root()
    dirs = [
        ("meta",),
        ("parser", "current"),
        ("parser", "runs"),
        ("convert", "by_source"),
        ("depval", "compute"),
        ("retrivis", "sentence_cache"),
        ("retrivis", "field_options"),
        ("lingnet", "edge_lists"),
        ("lingnet", "stats"),
        ("lingnet", "layouts"),
        ("lingnet", "render"),
    ]
    root.mkdir(parents=True, exist_ok=True)
    for segs in dirs:
        root.joinpath(*segs).mkdir(parents=True, exist_ok=True)
    schema_file = root / "meta" / "schema_version.json"
    index_file = root / "meta" / "cache_index.json"
    if not schema_file.exists():
        schema_file.write_text(
            json.dumps({"schema_version": CACHE_SCHEMA_VERSION}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not index_file.exists():
        index_file.write_text(
            json.dumps(
                {
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "updated_at": int(time.time()),
                    "modules": {
                        "parser": {},
                        "convert": {},
                        "depval": {},
                        "retrivis": {},
                        "lingnet": {},
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _migrate_legacy_cache_layout() -> None:
    _ensure_quansyn_cache_layout()
    flag = _quansyn_cache_path("meta") / "legacy_migrated.flag"
    if flag.exists():
        return
    root = _runtime_base_dir()
    legacy_convert = root / ".quansyn_convert_cache"
    legacy_parser = root / ".quansyn_parser_cache"
    legacy_lingnet = root / ".quansyn_lingnet_cache"
    new_convert = _quansyn_cache_path("convert", "by_source")
    new_parser = _quansyn_cache_path("parser", "current")
    new_lingnet = _quansyn_cache_path("lingnet", "render")
    try:
        if legacy_convert.exists() and legacy_convert.is_dir():
            shutil.copytree(legacy_convert, new_convert, dirs_exist_ok=True)
    except Exception:
        pass
    try:
        if legacy_parser.exists() and legacy_parser.is_dir():
            shutil.copytree(legacy_parser, new_parser, dirs_exist_ok=True)
    except Exception:
        pass
    try:
        if legacy_lingnet.exists() and legacy_lingnet.is_dir():
            shutil.copytree(legacy_lingnet, new_lingnet, dirs_exist_ok=True)
    except Exception:
        pass
    try:
        flag.write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass


def _bootstrap_cache_layout() -> None:
    _ensure_quansyn_cache_layout()
    _migrate_legacy_cache_layout()


def clear_all_quansyn_caches() -> None:
    root = _runtime_base_dir()
    targets = [
        _quansyn_cache_root(),
        root / ".quansyn_convert_cache",
        root / ".quansyn_parser_cache",
        root / ".quansyn_lingnet_cache",
    ]
    for p in targets:
        try:
            if p.exists() and p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
DEP_METRICS = ["dd", "hd", "ddir", "v"]
SENT_METRICS = ["mdd", "mhd", "mhdd", "tdl", "rd", "ndd", "sl", "vk", "tw", "th"]
TEXT_METRICS = ["mdd", "mhd", "mhdd", "mtdl", "msl", "mrd", "ndd", "vk", "mtw", "mth"]
DIST_METRICS = ["dd", "hd", "v", "sl", "tw", "th", "rd"]
BUNDLED_CYTOSCAPE_JS = (Path(__file__).resolve().parents[1] / "assets" / "vendor" / "cytoscape.min.js").resolve()


def fa_icon(name: str, color: str = "#CCCCCC") -> QIcon:
    if qta:
        try:
            icon = qta.icon(f"fa6s.{name}", color=color)
            if isinstance(icon, QIcon):
                return icon
        except Exception:
            pass
    return QIcon()


def animate_fade(target: QWidget, duration_ms: int = 170) -> None:
    effect = target.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", target)
    anim.setDuration(duration_ms)
    anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
    anim.setStartValue(0.55)
    anim.setEndValue(1.0)
    # Drop the effect after animation to avoid stale/lazy painting artifacts on complex widgets.
    anim.finished.connect(lambda: target.setGraphicsEffect(None))
    anim.start()
    target._fade_anim = anim  # type: ignore[attr-defined]


def _find_treebanks(path_str: str) -> list[Path]:
    path = Path(path_str)
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    files: list[Path] = []
    for ext in SUPPORTED_FORMATS:
        files.extend(sorted(path.glob(f"*.{ext}")))
    return files


def _read_sentences(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ["Unable to read file."]
    if not text.strip():
        return ["(Empty corpus file)"]

    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out: list[str] = []
    for block in blocks[:500]:
        toks: list[str] = []
        for ln in block.splitlines():
            raw = ln.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("\t")
            if len(parts) > 1 and parts[0].replace("-", "").isdigit():
                toks.append(parts[1])
        out.append(" ".join(toks) if toks else block.replace("\n", " "))
    return out if out else ["No sentence detected."]


def _parse_labels(files: list[Path], mode: str) -> list[str]:
    values: set[str] = set()
    for path in files:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for ln in f:
                    raw = ln.strip()
                    if not raw or raw.startswith("#"):
                        continue
                    parts = raw.split("\t")
                    if mode == "pos" and len(parts) >= 4:
                        values.add(parts[3])
                    elif mode == "deprel" and len(parts) >= 8:
                        values.add(parts[7].split(":")[0])
                    if len(values) > 120:
                        break
        except Exception:
            continue
    return sorted(v for v in values if v)


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / max(1, len(values))


def _flatten_values(values) -> list:
    out: list = []
    if isinstance(values, list):
        for v in values:
            if isinstance(v, list):
                out.extend(_flatten_values(v))
            else:
                out.append(v)
    return out


def _is_punct_token(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    # Treat token as punctuation when every char is punctuation/symbol.
    for ch in s:
        cat = unicodedata.category(ch)
        if not (cat.startswith("P") or cat.startswith("S")):
            return False
    return True


_LINGNET_ROOT_DEPS = {"root", "ROOT", "s", "HED"}
_LINGNET_STOP_DEPS = {"punct", "punkt", "_", "PUN"}


def _lingnet_is_punctuation_word(word: dict, ignore_punct: bool = True) -> bool:
    if not ignore_punct:
        return False
    deprel = word.get("deprel")
    if deprel in _LINGNET_STOP_DEPS:
        return True
    upos = word.get("upos")
    if isinstance(upos, str) and upos.upper() == "PUNCT":
        return True
    return _is_punct_token(str(word.get("form", "") or ""))


def _lingnet_normalize_edge(edge: tuple[str, str], directed: bool = False) -> tuple[str, str]:
    if directed:
        return edge
    a, b = edge
    return (a, b) if a <= b else (b, a)


def _lingnet_fallback_conllu2edge(treebank, mode: str = "dependency") -> list[tuple[str, str]]:
    if conllu_parse_incr is None:
        raise RuntimeError("conllu backend unavailable. Please install conllu.")
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for sent in conllu_parse_incr(treebank):
        if mode == "dependency":
            by_id = {word.get("id"): word for word in sent if isinstance(word.get("id"), int)}
            for word in sent:
                wid = word.get("id")
                if not isinstance(wid, int):
                    continue
                if word.get("deprel") in _LINGNET_ROOT_DEPS:
                    continue
                if _lingnet_is_punctuation_word(word):
                    continue
                head = word.get("head")
                if not isinstance(head, int) or head <= 0:
                    continue
                gov_word = by_id.get(head)
                if gov_word is None or _lingnet_is_punctuation_word(gov_word):
                    continue
                dep = str(word.get("form", "") or "").lower()
                gov = str(gov_word.get("form", "") or "").lower()
                if not dep or not gov:
                    continue
                edge = _lingnet_normalize_edge((dep, gov))
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
        elif mode == "adjacency":
            tokens: list[str] = []
            for word in sent:
                if not isinstance(word.get("id"), int):
                    continue
                if word.get("deprel") in _LINGNET_ROOT_DEPS:
                    continue
                if _lingnet_is_punctuation_word(word):
                    continue
                form = str(word.get("form", "") or "").lower()
                if form:
                    tokens.append(form)
            for idx in range(len(tokens) - 1):
                edge = _lingnet_normalize_edge((tokens[idx], tokens[idx + 1]))
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
        else:
            raise ValueError(f"Unsupported mode: {mode}. Choose 'dependency' or 'adjacency'.")
    return edges


class IconSidebar(QFrame):
    moduleChanged = pyqtSignal(str)
    importTreebankRequested = pyqtSignal()
    importTreebanksRequested = pyqtSignal()
    aboutRequested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("iconSidebar")
        self._buttons: dict[str, QToolButton] = {}
        self._module = "home"
        self._btn_size_base = QSize(64, 54)
        self._icon_size_base = QSize(26, 26)
        self._icon_size_selected_base = QSize(self._icon_size_base)
        self._btn_size = QSize(self._btn_size_base)
        self._icon_size = QSize(self._icon_size_base)
        self._icon_size_selected = QSize(self._icon_size_selected_base)
        self._icon_color_normal = "#B8C0C8"
        self._icon_color_selected = "#FFFFFF"
        self._module_icon_names: dict[str, str] = {}
        self._lang_zh = False
        self._sidebar_scale = 1.0

        root = QVBoxLayout(self)
        self._root_layout = root
        root.setContentsMargins(4, 8, 4, 8)
        root.setSpacing(8)

        self.import_file_btn = QToolButton()
        self.import_file_btn.setObjectName("sidebarButton")
        self.import_file_btn.setCheckable(False)
        self.import_file_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.import_file_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.import_file_btn.setFixedSize(self._btn_size)
        self.import_file_btn.setIconSize(self._icon_size)
        self.import_file_btn.setIcon(fa_icon("file-import", color=self._icon_color_normal))
        self.import_file_btn.setToolTip("Open Treebank")
        self.import_file_btn.clicked.connect(self.importTreebankRequested.emit)
        root.addWidget(self.import_file_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self.import_folder_btn = QToolButton()
        self.import_folder_btn.setObjectName("sidebarButton")
        self.import_folder_btn.setCheckable(False)
        self.import_folder_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.import_folder_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.import_folder_btn.setFixedSize(self._btn_size)
        self.import_folder_btn.setIconSize(self._icon_size)
        self.import_folder_btn.setIcon(fa_icon("folder-open", color=self._icon_color_normal))
        self.import_folder_btn.setToolTip("Open Treebanks")
        self.import_folder_btn.clicked.connect(self.importTreebanksRequested.emit)
        root.addWidget(self.import_folder_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("color:#4b4b4b; margin:4px 6px;")
        self._sidebar_separator = sep
        root.addWidget(sep)

        self._module_tips_en = {
            "home": "Home",
            "converter": "RetriVis",
            "depval": "DepVal",
            "lingnet": "LingNet",
            "settings": "Setting",
        }
        self._module_tips_zh = {
            "home": "主页",
            "converter": "检索可视化",
            "depval": "依存计量",
            "lingnet": "句法网络",
            "settings": "设置",
        }
        items = [
            ("home", "house", "Home"),
            ("converter", "magnifying-glass", "RetriVis"),
            ("depval", "chart-column", "DepVal"),
            ("lingnet", "diagram-project", "LingNet"),
        ]
        for key, icon_name, tip in items:
            btn = QToolButton()
            btn.setObjectName("sidebarButton")
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedSize(self._btn_size)
            btn.setIconSize(self._icon_size)
            btn.setIcon(fa_icon(icon_name, color=self._icon_color_normal))
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _c, m=key: self._select(m))
            root.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._buttons[key] = btn
            self._module_icon_names[key] = icon_name
        self._buttons[self._module].setChecked(True)
        root.addStretch(1)

        self.about_btn = QToolButton()
        self.about_btn.setObjectName("sidebarButton")
        self.about_btn.setCheckable(False)
        self.about_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.about_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.about_btn.setFixedSize(self._btn_size)
        self.about_btn.setIconSize(self._icon_size)
        self.about_btn.setIcon(fa_icon("circle-question", color=self._icon_color_normal))
        self.about_btn.setToolTip("About QuanSyn")
        self.about_btn.clicked.connect(self.aboutRequested.emit)
        root.addWidget(self.about_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self.setting_btn = QToolButton()
        self.setting_btn.setObjectName("sidebarButton")
        self.setting_btn.setCheckable(True)
        self.setting_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setting_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setting_btn.setFixedSize(self._btn_size)
        self.setting_btn.setIconSize(self._icon_size)
        self.setting_btn.setIcon(fa_icon("gear", color=self._icon_color_normal))
        self.setting_btn.setToolTip("Setting")
        self.setting_btn.clicked.connect(lambda: self._select("settings"))
        root.addWidget(self.setting_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self._buttons["settings"] = self.setting_btn
        self._module_icon_names["settings"] = "gear"
        self._apply_sidebar_button_style()
        self._refresh_checked_icons()

    def apply_ui_scale(self, scale: float) -> None:
        s = max(0.72, min(1.0, float(scale)))
        self._sidebar_scale = s
        btn_w = max(52, int(round(self._btn_size_base.width() * s)))
        btn_h = max(44, int(round(self._btn_size_base.height() * s)))
        icon_w = max(18, int(round(self._icon_size_base.width() * s)))
        icon_h = max(18, int(round(self._icon_size_base.height() * s)))
        icon_sel_w = icon_w
        icon_sel_h = icon_h
        self._btn_size = QSize(btn_w, btn_h)
        self._icon_size = QSize(icon_w, icon_h)
        self._icon_size_selected = QSize(icon_sel_w, icon_sel_h)
        try:
            spacing = max(6, min(10, int(round(9 * s))))
            margin_v = max(10, min(16, int(round(14 * s))))
            margin_h = max(5, min(8, int(round(6 * s))))
            self._root_layout.setSpacing(spacing)
            self._root_layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
            if getattr(self, "_sidebar_separator", None) is not None:
                sep_v = max(3, int(round(4 * s)))
                sep_h = max(4, int(round(6 * s)))
                self._sidebar_separator.setStyleSheet(f"color:#4b4b4b; margin:{sep_v}px {sep_h}px;")
        except Exception:
            pass
        for btn in [self.import_file_btn, self.import_folder_btn, self.about_btn, self.setting_btn, *self._buttons.values()]:
            try:
                btn.setFixedSize(self._btn_size)
                btn.setMinimumSize(self._btn_size)
                btn.setMaximumSize(self._btn_size)
            except Exception:
                pass
        self._apply_sidebar_button_style()
        self._refresh_checked_icons()

    def _apply_sidebar_button_style(self) -> None:
        w = max(1, int(self._btn_size.width()))
        h = max(1, int(self._btn_size.height()))
        s = max(0.72, min(1.0, float(getattr(self, "_sidebar_scale", 1.0) or 1.0)))
        margin_h = max(5, min(8, int(round(6 * s))))
        sidebar_w = w + margin_h * 2
        self.setMinimumWidth(sidebar_w)
        self.setMaximumWidth(sidebar_w)
        self.setStyleSheet(
            f"""
            QToolButton#sidebarButton {{
                min-width: {w}px;
                max-width: {w}px;
                min-height: {h}px;
                max-height: {h}px;
                padding: 0px;
                margin: 0px;
                border: none;
            }}
            QToolButton#sidebarButton:checked {{
                padding: 0px;
                margin: 0px;
                border: none;
            }}
            """
        )

    def apply_language(self, language: str) -> None:
        lang = str(language or "").strip().lower()
        self._lang_zh = lang in {"汉语", "中文", "chinese", "zh", "zh-cn"}
        self.import_file_btn.setToolTip("导入单个树库" if self._lang_zh else "Open Treebank")
        self.import_folder_btn.setToolTip("导入树库文件夹" if self._lang_zh else "Open Treebanks")
        self.about_btn.setToolTip("关于句法计量分析工作台" if self._lang_zh else "About QuanSyn")
        for key, btn in self._buttons.items():
            tips = self._module_tips_zh if self._lang_zh else self._module_tips_en
            btn.setToolTip(tips.get(key, key))

    def _select(self, module: str) -> None:
        self._module = module
        for key, btn in self._buttons.items():
            btn.setChecked(key == module)
        self._refresh_checked_icons()
        self.moduleChanged.emit(module)

    def _refresh_checked_icons(self) -> None:
        for key, btn in self._buttons.items():
            icon_name = self._module_icon_names.get(key, "")
            if not icon_name:
                continue
            selected = btn.isChecked()
            btn.setIconSize(self._icon_size_selected if selected else self._icon_size)
            btn.setIcon(
                fa_icon(
                    icon_name,
                    color=self._icon_color_selected if selected else self._icon_color_normal,
                )
            )


class DrawerHandleButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__("", parent)
        self._vertical_text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event) -> None:  # pragma: no cover - UI painting
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())

        path = QPainterPath()
        # Flat rectangle handle (no rounded corners).
        path.addRect(0, 0, w, h)
        path.closeSubpath()

        app = QApplication.instance()
        theme_mark = ""
        if app is not None:
            try:
                theme_mark = str(app.property("quansyn_theme") or "").strip().lower()
            except Exception:
                theme_mark = ""
        is_light = theme_mark == "light"
        if is_light:
            fill = QColor(126, 150, 180, 150)
            border = QColor(88, 115, 148, 185)
            text_color = QColor(23, 48, 78, 235)
            if self.underMouse():
                fill = QColor(111, 139, 173, 176)
                border = QColor(76, 104, 140, 210)
                text_color = QColor(16, 38, 66, 245)
        else:
            fill = QColor(155, 163, 176, 112)
            border = QColor(192, 199, 212, 140)
            text_color = QColor(238, 242, 248, 220)
            if self.underMouse():
                fill = QColor(170, 178, 190, 136)
                border = QColor(208, 214, 224, 170)
                text_color = QColor(245, 248, 252, 235)

        painter.fillPath(path, fill)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)

        painter.setPen(text_color)
        font = painter.font()
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.save()
        painter.translate(w / 2.0 - 2, h / 2.0)
        painter.rotate(90)
        painter.drawText(
            QRect(int(-h / 2), int(-w / 2), int(h), int(w)),
            int(Qt.AlignmentFlag.AlignCenter),
            self._vertical_text,
        )
        painter.restore()


class LingnetWebPage(QWebEnginePage if QWebEnginePage is not None else object):  # type: ignore[misc]
    jsConsole = pyqtSignal(str)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # type: ignore[override]
        msg = str(message or "")
        if "custom wheel sensitivity" in msg.lower():
            return
        try:
            txt = f"[JS] {msg} ({line_number})"
            self.jsConsole.emit(txt)
        except Exception:
            pass
        if QWebEnginePage is not None:
            try:
                super().javaScriptConsoleMessage(level, message, line_number, source_id)
            except Exception:
                pass


class SpacyModelManagerDialog(QDialog):
    modelsInstalled = pyqtSignal()
    _modelsFetched = pyqtSignal(object, str)
    _installFinished = pyqtSignal(str, str, str)
    _deleteFinished = pyqtSignal(str, str)
    _stanzaFetched = pyqtSignal(object, str)
    _stanzaInstallFinished = pyqtSignal(str, str, str)
    _stanzaDeleteFinished = pyqtSignal(str, str, str)
    _importFinished = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None, spacy_root: Path):
        super().__init__(parent)
        self.setWindowTitle("Model Manager")
        self.resize(760, 500)
        self._spacy_root = Path(spacy_root)
        self._compat_models: dict[str, list[str]] = {}
        self._stanza_resources: dict[str, object] = {}
        self._spacy_ver = ""
        self._spacy_key = ""
        self._fetch_thread: threading.Thread | None = None
        self._install_thread: threading.Thread | None = None
        self._delete_thread: threading.Thread | None = None
        self._stanza_fetch_thread: threading.Thread | None = None
        self._stanza_install_thread: threading.Thread | None = None
        self._stanza_delete_thread: threading.Thread | None = None
        self._import_thread: threading.Thread | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        spacy_page = QWidget()
        spacy_l = QVBoxLayout(spacy_page)
        spacy_l.setContentsMargins(8, 8, 8, 8)
        spacy_l.setSpacing(8)

        info = QHBoxLayout()
        self.spacy_runtime_label = QLabel("spaCy: detecting...")
        info.addWidget(self.spacy_runtime_label, 1)
        self.spacy_refresh_btn = QPushButton("Refresh Online List")
        info.addWidget(self.spacy_refresh_btn, 0)
        spacy_l.addLayout(info)

        form = QFormLayout()
        self.spacy_lang_combo = QComboBox()
        self.spacy_model_combo = QComboBox()
        self.spacy_version_combo = QComboBox()
        form.addRow("Language", self.spacy_lang_combo)
        form.addRow("Model", self.spacy_model_combo)
        form.addRow("Package version", self.spacy_version_combo)
        spacy_l.addLayout(form)

        note = QLabel(
            "Online source: explosion/spacy-models releases. "
            "TRF models are excluded."
        )
        note.setWordWrap(True)
        note.setObjectName("statusInfo")
        spacy_l.addWidget(note)

        act_row = QHBoxLayout()
        self.spacy_install_btn = QPushButton("Install")
        self.spacy_install_btn.setObjectName("accentButton")
        act_row.addStretch(1)
        act_row.addWidget(self.spacy_install_btn, 0)
        spacy_l.addLayout(act_row)

        installed_form = QFormLayout()
        self.spacy_installed_combo = QComboBox()
        installed_form.addRow("Installed", self.spacy_installed_combo)
        spacy_l.addLayout(installed_form)
        del_row = QHBoxLayout()
        self.spacy_delete_btn = QPushButton("Delete Selected")
        del_row.addStretch(1)
        del_row.addWidget(self.spacy_delete_btn, 0)
        spacy_l.addLayout(del_row)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("statusInfo")
        self.status_label.setWordWrap(True)
        spacy_l.addWidget(self.status_label)

        tabs.addTab(spacy_page, "spaCy")

        stanza_page = QWidget()
        stanza_l = QVBoxLayout(stanza_page)
        stanza_l.setContentsMargins(8, 8, 8, 8)
        stanza_l.setSpacing(8)
        s_info = QHBoxLayout()
        self.stanza_runtime_label = QLabel("stanza: detecting...")
        s_info.addWidget(self.stanza_runtime_label, 1)
        self.stanza_refresh_btn = QPushButton("Refresh Online List")
        s_info.addWidget(self.stanza_refresh_btn, 0)
        stanza_l.addLayout(s_info)

        s_form = QFormLayout()
        self.stanza_lang_combo = QComboBox()
        self.stanza_package_combo = QComboBox()
        s_form.addRow("Language", self.stanza_lang_combo)
        s_form.addRow("Package", self.stanza_package_combo)
        stanza_l.addLayout(s_form)

        s_note = QLabel(
            "Online source: stanza-resources. Install uses processors: tokenize,pos,lemma,depparse."
        )
        s_note.setWordWrap(True)
        s_note.setObjectName("statusInfo")
        stanza_l.addWidget(s_note)

        s_row = QHBoxLayout()
        self.stanza_install_btn = QPushButton("Install")
        self.stanza_install_btn.setObjectName("accentButton")
        s_row.addStretch(1)
        s_row.addWidget(self.stanza_install_btn, 0)
        stanza_l.addLayout(s_row)

        s_installed_form = QFormLayout()
        self.stanza_installed_lang_combo = QComboBox()
        self.stanza_installed_pkg_combo = QComboBox()
        s_installed_form.addRow("Installed language", self.stanza_installed_lang_combo)
        s_installed_form.addRow("Installed package", self.stanza_installed_pkg_combo)
        stanza_l.addLayout(s_installed_form)
        s_del_row = QHBoxLayout()
        self.stanza_delete_btn = QPushButton("Delete Selected")
        s_del_row.addStretch(1)
        s_del_row.addWidget(self.stanza_delete_btn, 0)
        stanza_l.addLayout(s_del_row)

        self.stanza_status_label = QLabel("Ready.")
        self.stanza_status_label.setObjectName("statusInfo")
        self.stanza_status_label.setWordWrap(True)
        stanza_l.addWidget(self.stanza_status_label)
        tabs.addTab(stanza_page, "stanza")

        import_page = QWidget()
        import_l = QVBoxLayout(import_page)
        import_l.setContentsMargins(8, 8, 8, 8)
        import_l.setSpacing(8)

        import_title = QLabel("Import Local Parser Model")
        import_title.setObjectName("sectionTitle")
        import_l.addWidget(import_title)

        import_form = QFormLayout()
        self.import_backend_combo = QComboBox()
        self.import_backend_combo.addItems(["spaCy", "stanza"])
        import_form.addRow("Model type", self.import_backend_combo)

        file_row = QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.setSpacing(6)
        self.import_path_edit = QLineEdit()
        self.import_path_edit.setPlaceholderText("Choose a local .zip, .tar.gz, .tgz, or .tar model package")
        self.import_browse_btn = QPushButton("Browse")
        file_row.addWidget(self.import_path_edit, 1)
        file_row.addWidget(self.import_browse_btn, 0)
        import_form.addRow("Model file", file_row)
        import_l.addLayout(import_form)

        import_note = QLabel(
            "spaCy packages should contain config.cfg. "
            "stanza packages should contain a complete stanza model directory, preferably with resources.json."
        )
        import_note.setWordWrap(True)
        import_note.setObjectName("statusInfo")
        import_l.addWidget(import_note)

        import_actions = QHBoxLayout()
        self.import_model_btn = QPushButton("Import Model")
        self.import_model_btn.setObjectName("accentButton")
        import_actions.addStretch(1)
        import_actions.addWidget(self.import_model_btn, 0)
        import_l.addLayout(import_actions)

        self.import_status_label = QLabel("Ready.")
        self.import_status_label.setObjectName("statusInfo")
        self.import_status_label.setWordWrap(True)
        import_l.addWidget(self.import_status_label)
        import_l.addStretch(1)
        tabs.addTab(import_page, "Import")

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        btns.clicked.connect(lambda _b: self.close())
        root.addWidget(btns, 0)

        self.spacy_refresh_btn.clicked.connect(self._refresh_online_models)
        self.spacy_lang_combo.currentTextChanged.connect(self._refresh_model_combo)
        self.spacy_model_combo.currentTextChanged.connect(self._refresh_version_combo)
        self.spacy_install_btn.clicked.connect(self._install_selected_model)
        self.spacy_delete_btn.clicked.connect(self._delete_selected_model)
        self.stanza_refresh_btn.clicked.connect(self._refresh_stanza_online)
        self.stanza_lang_combo.currentTextChanged.connect(self._refresh_stanza_package_combo)
        self.stanza_install_btn.clicked.connect(self._install_selected_stanza_package)
        self.stanza_installed_lang_combo.currentTextChanged.connect(self._refresh_stanza_installed_package_combo)
        self.stanza_delete_btn.clicked.connect(self._delete_selected_stanza_package)
        self.import_browse_btn.clicked.connect(self._choose_import_model_file)
        self.import_model_btn.clicked.connect(self._import_selected_model_file)
        self._modelsFetched.connect(self._on_models_refreshed)
        self._installFinished.connect(self._on_install_done)
        self._deleteFinished.connect(self._on_delete_done)
        self._stanzaFetched.connect(self._on_stanza_fetched)
        self._stanzaInstallFinished.connect(self._on_stanza_install_done)
        self._stanzaDeleteFinished.connect(self._on_stanza_delete_done)
        self._importFinished.connect(self._on_import_finished)

        self._refresh_online_models()
        self._refresh_installed_models()
        self._refresh_stanza_online()
        self._refresh_stanza_installed_languages()

    def _choose_import_model_file(self) -> None:
        path, _ = _themed_get_open_file_name(
            self,
            "Import parser model package",
            "",
            "Model Packages (*.zip *.tar.gz *.tgz *.tar);;All Files (*)",
        )
        if path:
            self.import_path_edit.setText(path)

    def _import_selected_model_file(self) -> None:
        if self._import_thread is not None and self._import_thread.is_alive():
            self.import_status_label.setText("Import is already running...")
            return
        archive_path = Path(self.import_path_edit.text().strip())
        if not archive_path.exists() or not archive_path.is_file():
            _show_warning_dialog(self, "Model Manager", "Please choose a valid local model package file.")
            return
        backend = self.import_backend_combo.currentText().strip().lower()
        self.import_model_btn.setEnabled(False)
        self.import_browse_btn.setEnabled(False)
        self.import_status_label.setText(f"Importing {backend} model package...")

        def _worker() -> None:
            try:
                if backend == "spacy":
                    msg = self._import_spacy_archive(archive_path)
                elif backend == "stanza":
                    msg = self._import_stanza_archive(archive_path)
                else:
                    raise RuntimeError(f"Unsupported model type: {backend}")
                self._importFinished.emit(msg, "")
            except Exception as exc:
                self._importFinished.emit("", str(exc))

        self._import_thread = threading.Thread(target=_worker, daemon=True)
        self._import_thread.start()

    def _on_import_finished(self, msg: str, err: str) -> None:
        self.import_model_btn.setEnabled(True)
        self.import_browse_btn.setEnabled(True)
        if err:
            self.import_status_label.setText(f"Import failed: {err}")
            _show_warning_dialog(self, "Model Manager", f"Import failed:\n{err}")
            return
        self.import_status_label.setText(msg or "Import completed.")
        self._refresh_installed_models()
        self._refresh_stanza_installed_languages()
        self.modelsInstalled.emit()

    def _detect_spacy_version(self) -> tuple[str, str]:
        try:
            _sp = _ensure_spacy()
            if _sp is None:
                return "", ""

            ver = str(getattr(_sp, "__version__", "") or "")
            parts = ver.split(".")
            key = ".".join(parts[:2]) if len(parts) >= 2 else ver
            return ver, key
        except Exception:
            return "", ""

    @staticmethod
    def _is_frozen_runtime() -> bool:
        return bool(getattr(sys, "frozen", False) or ("__compiled__" in globals()))

    @staticmethod
    def _safe_extract_tar(archive: tarfile.TarFile, target: Path) -> None:
        target_resolved = target.resolve()
        for member in archive.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(f"Unsupported archive entry: {member.name}")
            member_path = (target / member.name).resolve()
            if target_resolved not in [member_path, *member_path.parents]:
                raise RuntimeError(f"Unsafe archive path: {member.name}")
        archive.extractall(path=str(target))

    @staticmethod
    def _safe_extract_zip(archive: zipfile.ZipFile, target: Path) -> None:
        target_resolved = target.resolve()
        for member in archive.infolist():
            member_path = (target / member.filename).resolve()
            if target_resolved not in [member_path, *member_path.parents]:
                raise RuntimeError(f"Unsafe archive path: {member.filename}")
        archive.extractall(path=str(target))

    def _extract_model_archive(self, archive_path: Path, target: Path) -> None:
        suffixes = [s.lower() for s in archive_path.suffixes]
        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(str(archive_path), "r") as zf:
                self._safe_extract_zip(zf, target)
            return
        if archive_path.suffix.lower() in {".tgz", ".tar"} or suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(str(archive_path), "r:*") as tf:
                self._safe_extract_tar(tf, target)
            return
        raise RuntimeError("Unsupported model package. Use .zip, .tar.gz, .tgz, or .tar.")

    @staticmethod
    def _copytree_merge(src: Path, dst: Path) -> None:
        if not src.exists():
            return
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _spacy_model_name_from_dir(self, model_dir: Path) -> tuple[str, str]:
        meta_file = model_dir / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                lang = str(meta.get("lang", "") or "").strip().lower()
                name = str(meta.get("name", "") or "").strip()
                if lang and name:
                    if name.startswith(f"{lang}_"):
                        return lang, name
                    return lang, f"{lang}_{name}"
            except Exception:
                pass
        raw = model_dir.name
        raw = re.sub(r"-\d+(?:\.\d+)*$", "", raw).strip()
        lang = raw.split("_", 1)[0].strip().lower() if "_" in raw else "misc"
        return lang or "misc", raw or model_dir.name

    def _import_spacy_archive(self, archive_path: Path) -> str:
        with tempfile.TemporaryDirectory(prefix="quansyn_import_spacy_") as td:
            extract_dir = Path(td) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._extract_model_archive(archive_path, extract_dir)
            candidates = [p.parent for p in extract_dir.rglob("config.cfg")]
            if not candidates:
                raise RuntimeError("No spaCy model found. The package must contain config.cfg.")

            def _score(p: Path) -> tuple[int, int]:
                score = 0
                if (p / "meta.json").exists():
                    score += 8
                if (p / "tokenizer").exists():
                    score += 4
                if (p / "vocab").exists():
                    score += 2
                return score, -len(str(p))

            best = sorted(candidates, key=_score, reverse=True)[0]
            lang, model_name = self._spacy_model_name_from_dir(best)
            target_root = self._spacy_root / lang / model_name
            target_root.mkdir(parents=True, exist_ok=True)
            dst = target_root / best.name
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(best, dst)
            return f"Imported spaCy model: {model_name}"

    def _find_stanza_source_root(self, extract_dir: Path) -> Path:
        candidates: list[Path] = []
        for p in [extract_dir, *extract_dir.rglob("*")]:
            if not p.is_dir():
                continue
            if (p / "resources.json").exists():
                candidates.append(p)
                continue
            try:
                has_lang = any(
                    child.is_dir() and (
                        (child / "tokenize").exists()
                        or (child / "pos").exists()
                        or (child / "lemma").exists()
                        or (child / "depparse").exists()
                    )
                    for child in p.iterdir()
                )
            except Exception:
                has_lang = False
            if has_lang:
                candidates.append(p)
        if not candidates:
            raise RuntimeError(
                "No stanza model directory found. The package should contain resources.json or language folders."
            )
        return sorted(candidates, key=lambda p: (0 if (p / "resources.json").exists() else 1, len(str(p))))[0]

    def _import_stanza_archive(self, archive_path: Path) -> str:
        stanza_root = self._spacy_root.parent / "stanza"
        stanza_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="quansyn_import_stanza_") as td:
            extract_dir = Path(td) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._extract_model_archive(archive_path, extract_dir)
            source_root = self._find_stanza_source_root(extract_dir)
            imported_langs: list[str] = []
            for child in source_root.iterdir():
                if child.name.startswith("."):
                    continue
                dst = stanza_root / child.name
                self._copytree_merge(child, dst)
                if child.is_dir():
                    imported_langs.append(child.name)
            if not imported_langs and not (source_root / "resources.json").exists():
                raise RuntimeError("No stanza language folders were imported.")
            label = ", ".join(sorted(imported_langs)) if imported_langs else "resources"
            return f"Imported stanza model data: {label}"

    def _install_spacy_model_local(self, model: str, version: str) -> None:
        package = f"{model}-{version}"
        url = f"https://github.com/explosion/spacy-models/releases/download/{package}/{package}.tar.gz"
        lang = model.split("_", 1)[0].strip().lower() or "misc"
        target_root = self._spacy_root / lang / model
        target_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="quansyn_spacy_") as td:
            tmp_dir = Path(td)
            archive_path = tmp_dir / f"{package}.tar.gz"
            req = urllib.request.Request(url, headers={"User-Agent": "QuanSyn-Studio/0.0.1"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                archive_path.write_bytes(resp.read())
            extract_dir = tmp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(str(archive_path), "r:gz") as tf:
                tf.extractall(path=str(extract_dir))

            candidates = [p.parent for p in extract_dir.rglob("config.cfg")]
            if not candidates:
                raise RuntimeError("Downloaded model archive does not contain config.cfg")

            def _score(p: Path) -> tuple[int, int]:
                score = 0
                if p.name.startswith(f"{model}-"):
                    score += 8
                if (p / "meta.json").exists():
                    score += 2
                if (p / "tokenizer").exists():
                    score += 1
                return score, len(str(p))

            best = sorted(candidates, key=_score, reverse=True)[0]
            dst = target_root / best.name
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(best, dst)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _set_stanza_status(self, text: str) -> None:
        self.stanza_status_label.setText(text)

    def _refresh_online_models(self) -> None:
        if self._fetch_thread is not None and self._fetch_thread.is_alive():
            self._set_status("Online list refresh is already running...")
            return
        self.spacy_refresh_btn.setEnabled(False)
        self.spacy_install_btn.setEnabled(False)
        ver, key = self._detect_spacy_version()
        self._spacy_ver = ver
        self._spacy_key = key
        if ver:
            self.spacy_runtime_label.setText(f"spaCy: {ver} (compat key: {key})")
        else:
            self.spacy_runtime_label.setText("spaCy: not available")
            self._set_status("spaCy is unavailable in current environment.")
            self.spacy_refresh_btn.setEnabled(True)
            return
        self._set_status("Fetching model list from GitHub...")

        def _worker() -> None:
            try:
                urls = [
                    "https://raw.githubusercontent.com/explosion/spacy-models/master/compatibility.json",
                    "https://cdn.jsdelivr.net/gh/explosion/spacy-models@master/compatibility.json",
                ]
                data, fetch_err = _fetch_json_from_urls(urls, timeout=20)
                compat = data.get("spacy", {}) if isinstance(data, dict) else {}
                model_map = compat.get(key, {}) if isinstance(compat, dict) else {}
                if (not model_map) and isinstance(compat, dict):
                    # fallback by major.minor prefix
                    for k2, v2 in compat.items():
                        if str(k2).startswith(key) and isinstance(v2, dict):
                            model_map = v2
                            break
                out: dict[str, list[str]] = {}
                if isinstance(model_map, dict):
                    for mname, vers in model_map.items():
                        name = str(mname or "").strip()
                        if (not name) or ("trf" in name.lower()):
                            continue
                        if isinstance(vers, list):
                            out[name] = [str(v).strip() for v in vers if str(v).strip()]
                if not out:
                    raise RuntimeError(fetch_err or "Cannot fetch compatibility model list.")
                self._modelsFetched.emit(out, "")
            except Exception as exc:
                self._modelsFetched.emit({}, str(exc))

        self._fetch_thread = threading.Thread(target=_worker, daemon=True)
        self._fetch_thread.start()

    def _on_models_refreshed(self, models: dict[str, list[str]], err: str) -> None:
        self.spacy_refresh_btn.setEnabled(True)
        self.spacy_install_btn.setEnabled(True)
        self.spacy_delete_btn.setEnabled(True)
        if err:
            fallback = {
                "en_core_web_sm": ["3.8.0", "3.7.1"],
                "zh_core_web_sm": ["3.8.0", "3.7.0"],
            }
            self._compat_models = fallback
            self.spacy_lang_combo.blockSignals(True)
            self.spacy_lang_combo.clear()
            self.spacy_lang_combo.addItems(["en", "zh"])
            self.spacy_lang_combo.blockSignals(False)
            self._refresh_model_combo()
            self._set_status(
                f"Failed to fetch online list: {err}. Fallback list loaded (en/zh)."
            )
            return
        self._compat_models = dict(models)
        by_lang: dict[str, list[str]] = {}
        for m in sorted(self._compat_models.keys()):
            lang = m.split("_", 1)[0]
            by_lang.setdefault(lang, []).append(m)
        self.spacy_lang_combo.blockSignals(True)
        self.spacy_lang_combo.clear()
        for lang in sorted(by_lang.keys()):
            self.spacy_lang_combo.addItem(lang)
        self.spacy_lang_combo.blockSignals(False)
        if self.spacy_lang_combo.count() > 0:
            self.spacy_lang_combo.setCurrentIndex(0)
        self._refresh_model_combo()
        self._refresh_installed_models()
        self._set_status(f"Online list ready: {len(self._compat_models)} models.")

    def _refresh_installed_models(self) -> None:
        models: set[str] = set()
        try:
            for name in _spacy_installed_models():
                models.add(name)
        except Exception:
            pass
        try:
            if self._spacy_root.exists():
                for lang_dir in self._spacy_root.iterdir():
                    if not lang_dir.is_dir():
                        continue
                    for p in lang_dir.iterdir():
                        if p.is_dir():
                            models.add(p.name)
        except Exception:
            pass
        ordered = sorted(models)
        self.spacy_installed_combo.blockSignals(True)
        self.spacy_installed_combo.clear()
        self.spacy_installed_combo.addItems(ordered)
        self.spacy_installed_combo.blockSignals(False)
        self.spacy_delete_btn.setEnabled(bool(ordered))

    def _refresh_model_combo(self) -> None:
        lang = self.spacy_lang_combo.currentText().strip().lower()
        models = [m for m in sorted(self._compat_models.keys()) if m.startswith(f"{lang}_")] if lang else []
        self.spacy_model_combo.blockSignals(True)
        self.spacy_model_combo.clear()
        self.spacy_model_combo.addItems(models)
        self.spacy_model_combo.blockSignals(False)
        self._refresh_version_combo()

    def _refresh_version_combo(self) -> None:
        model = self.spacy_model_combo.currentText().strip()
        versions = self._compat_models.get(model, [])
        self.spacy_version_combo.clear()
        self.spacy_version_combo.addItems(versions)

    def _install_selected_model(self) -> None:
        if self._install_thread is not None and self._install_thread.is_alive():
            self._set_status("Model install is already running...")
            return
        model = self.spacy_model_combo.currentText().strip()
        version = self.spacy_version_combo.currentText().strip()
        if not model or not version:
            _show_warning_dialog(self, "Model Manager", "Please select model and version first.")
            return
        package = f"{model}-{version}"
        url = f"https://github.com/explosion/spacy-models/releases/download/{package}/{package}.tar.gz"
        self.spacy_install_btn.setEnabled(False)
        self.spacy_refresh_btn.setEnabled(False)
        self.spacy_delete_btn.setEnabled(False)
        self._set_status(f"Installing {package} ...")

        def _worker() -> None:
            try:
                if self._is_frozen_runtime():
                    self._install_spacy_model_local(model, version)
                else:
                    proc = subprocess.run(
                        [sys.executable, "-m", "pip", "install", url],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if proc.returncode != 0:
                        msg = (proc.stderr or proc.stdout or "pip install failed").strip()
                        raise RuntimeError(msg[-1500:])
                self._installFinished.emit(model, version, "")
            except Exception as exc:
                self._installFinished.emit(model, version, str(exc))

        self._install_thread = threading.Thread(target=_worker, daemon=True)
        self._install_thread.start()

    def _on_install_done(self, model: str, version: str, err: str) -> None:
        self.spacy_install_btn.setEnabled(True)
        self.spacy_refresh_btn.setEnabled(True)
        self.spacy_delete_btn.setEnabled(True)
        if err:
            self._set_status(f"Install failed: {err}")
            _show_warning_dialog(self, "Model Manager", f"Install failed:\n{err}")
            return
        self._set_status(f"Installed: {model} ({version})")
        self._refresh_installed_models()
        self.modelsInstalled.emit()

    def _delete_selected_model(self) -> None:
        if self._delete_thread is not None and self._delete_thread.is_alive():
            self._set_status("Delete is already running...")
            return
        model = self.spacy_installed_combo.currentText().strip()
        if not model:
            _show_info_dialog(self, "Model Manager", "No installed model selected.")
            return
        ans = QMessageBox.question(
            self,
            "Delete Model",
            f"Delete installed spaCy model '{model}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.spacy_install_btn.setEnabled(False)
        self.spacy_refresh_btn.setEnabled(False)
        self.spacy_delete_btn.setEnabled(False)
        self._set_status(f"Deleting {model} ...")

        def _worker() -> None:
            try:
                removed_any = False
                proc_err = ""
                if not self._is_frozen_runtime():
                    proc = subprocess.run(
                        [sys.executable, "-m", "pip", "uninstall", "-y", model],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    removed_any = proc.returncode == 0
                    proc_err = (proc.stderr or proc.stdout or "").strip()
                # Also remove local model mirror if exists.
                lang = model.split("_", 1)[0].strip().lower()
                local_dir = self._spacy_root / lang / model
                if local_dir.exists():
                    shutil.rmtree(local_dir, ignore_errors=True)
                    removed_any = True
                if not removed_any:
                    msg = proc_err or "Model not found for uninstall."
                    raise RuntimeError(msg[-1500:])
                self._deleteFinished.emit(model, "")
            except Exception as exc:
                self._deleteFinished.emit(model, str(exc))

        self._delete_thread = threading.Thread(target=_worker, daemon=True)
        self._delete_thread.start()

    def _on_delete_done(self, model: str, err: str) -> None:
        self.spacy_install_btn.setEnabled(True)
        self.spacy_refresh_btn.setEnabled(True)
        self.spacy_delete_btn.setEnabled(True)
        if err:
            self._set_status(f"Delete failed: {err}")
            _show_warning_dialog(self, "Model Manager", f"Delete failed:\n{err}")
            return
        self._set_status(f"Deleted: {model}")
        self._refresh_installed_models()
        self.modelsInstalled.emit()

    def _refresh_stanza_online(self) -> None:
        if self._stanza_fetch_thread is not None and self._stanza_fetch_thread.is_alive():
            self._set_stanza_status("Online list refresh is already running...")
            return
        self.stanza_refresh_btn.setEnabled(False)
        self.stanza_install_btn.setEnabled(False)
        self.stanza_delete_btn.setEnabled(False)
        st_mod = _ensure_stanza()
        if st_mod is None:
            self.stanza_runtime_label.setText("stanza: not available")
            reason = str(_stanza_import_error or "").strip()
            if reason:
                self._set_stanza_status(f"stanza runtime unavailable: {reason}")
        else:
            try:
                self.stanza_runtime_label.setText(f"stanza: {getattr(st_mod, '__version__', '')}")
            except Exception:
                self.stanza_runtime_label.setText("stanza: available")
        try:
            c = importlib.import_module(".".join((_runtime_module_name("stan", "za"), "resources", "common")))
            base = str(getattr(c, "DEFAULT_RESOURCES_URL", "") or "").rstrip("/")
            ver = str(getattr(c, "DEFAULT_RESOURCES_VERSION", "") or "")
        except Exception:
            base = "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main"
            ver = ""
        self._set_stanza_status("Fetching stanza resources...")

        def _worker() -> None:
            try:
                urls = []
                if base and ver:
                    urls.append(f"{base}/resources_{ver}.json")
                if base:
                    urls.append(f"{base}/resources.json")
                # Robust fallbacks for stanza resources endpoint changes.
                urls.extend(
                    [
                        "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main/resources_1.11.0.json",
                        "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main/resources_1.10.0.json",
                        "https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main/resources_1.9.0.json",
                    ]
                )
                data, fetch_err = _fetch_json_from_urls(urls, timeout=20)
                if not isinstance(data, dict):
                    raise RuntimeError(fetch_err or "Cannot fetch stanza resources")
                self._stanzaFetched.emit(data, "")
            except Exception as exc:
                self._stanzaFetched.emit({}, str(exc))

        self._stanza_fetch_thread = threading.Thread(target=_worker, daemon=True)
        self._stanza_fetch_thread.start()

    def _on_stanza_fetched(self, resources: object, err: str) -> None:
        self.stanza_refresh_btn.setEnabled(True)
        self.stanza_install_btn.setEnabled(True)
        self.stanza_delete_btn.setEnabled(True)
        if err:
            self._stanza_resources = {
                "en": {"lang_name": "English", "packages": {"default": {}}},
                "zh-hans": {"lang_name": "Chinese (Simplified)", "packages": {"default": {}}},
            }
            self.stanza_lang_combo.blockSignals(True)
            self.stanza_lang_combo.clear()
            self.stanza_lang_combo.addItem("en - English", "en")
            self.stanza_lang_combo.addItem("zh-hans - Chinese (Simplified)", "zh-hans")
            self.stanza_lang_combo.blockSignals(False)
            self._refresh_stanza_package_combo()
            self._set_stanza_status(f"Failed to fetch resources: {err}. Fallback list loaded (en/zh-hans).")
            return
        self._stanza_resources = resources if isinstance(resources, dict) else {}
        self.stanza_lang_combo.blockSignals(True)
        self.stanza_lang_combo.clear()
        langs: list[tuple[str, str]] = []
        for key, val in self._stanza_resources.items():
            if not isinstance(val, dict):
                continue
            if "packages" in val and isinstance(val.get("packages"), dict):
                label_name = str(val.get("lang_name", key)).replace("_", " ")
                langs.append((str(key), f"{key} - {label_name}"))
        for code, label in sorted(langs, key=lambda x: x[0]):
            self.stanza_lang_combo.addItem(label, code)
        self.stanza_lang_combo.blockSignals(False)
        if self.stanza_lang_combo.count() > 0:
            self.stanza_lang_combo.setCurrentIndex(0)
        self._refresh_stanza_package_combo()
        self._refresh_stanza_installed_languages()
        self._set_stanza_status(f"Online list ready: {self.stanza_lang_combo.count()} language(s).")

    def _resolve_stanza_alias(self, code: str) -> str:
        c = str(code or "").strip().lower()
        if c in {"zh", "zh-cn", "chinese", "中文", "汉语"}:
            c = "zh-hans"
        if isinstance(self._stanza_resources, dict):
            v = self._stanza_resources.get(c)
            if isinstance(v, dict) and "alias" in v:
                return str(v.get("alias") or c).strip().lower()
        return c

    def _refresh_stanza_package_combo(self) -> None:
        lang_data = self.stanza_lang_combo.currentData()
        lang = self._resolve_stanza_alias(str(lang_data or self.stanza_lang_combo.currentText().split(" ", 1)[0]))
        packages: list[str] = []
        v = self._stanza_resources.get(lang) if isinstance(self._stanza_resources, dict) else None
        if isinstance(v, dict):
            pmap = v.get("packages")
            if isinstance(pmap, dict):
                packages = sorted(str(k) for k in pmap.keys())
        self.stanza_package_combo.clear()
        self.stanza_package_combo.addItems(packages)

    def _install_selected_stanza_package(self) -> None:
        if self._stanza_install_thread is not None and self._stanza_install_thread.is_alive():
            self._set_stanza_status("Install is already running...")
            return
        st_mod = _ensure_stanza()
        if st_mod is None:
            reason = str(_stanza_import_error or "").strip()
            msg = "stanza is unavailable."
            if reason:
                msg += f"\nReason: {reason}"
            _show_warning_dialog(self, "Model Manager", msg)
            return
        lang_data = self.stanza_lang_combo.currentData()
        lang = self._resolve_stanza_alias(str(lang_data or ""))
        package = self.stanza_package_combo.currentText().strip()
        if not lang or not package:
            _show_warning_dialog(self, "Model Manager", "Please select language and package first.")
            return
        self.stanza_install_btn.setEnabled(False)
        self.stanza_refresh_btn.setEnabled(False)
        self.stanza_delete_btn.setEnabled(False)
        self._set_stanza_status(f"Installing stanza package: {lang}/{package} ...")

        def _worker() -> None:
            try:
                st_mod.download(
                    lang=lang,
                    model_dir=str(self._spacy_root.parent / "stanza"),
                    package=package,
                    processors="tokenize,pos,lemma,depparse",
                    verbose=False,
                )
                self._stanzaInstallFinished.emit(lang, package, "")
            except Exception as exc:
                self._stanzaInstallFinished.emit(lang, package, str(exc))

        self._stanza_install_thread = threading.Thread(target=_worker, daemon=True)
        self._stanza_install_thread.start()

    def _on_stanza_install_done(self, lang: str, package: str, err: str) -> None:
        self.stanza_install_btn.setEnabled(True)
        self.stanza_refresh_btn.setEnabled(True)
        self.stanza_delete_btn.setEnabled(True)
        if err:
            self._set_stanza_status(f"Install failed: {err}")
            _show_warning_dialog(self, "Model Manager", f"Stanza install failed:\n{err}")
            return
        self._set_stanza_status(f"Installed stanza package: {lang}/{package}")
        self._refresh_stanza_installed_languages()
        self.modelsInstalled.emit()

    def _refresh_stanza_installed_languages(self) -> None:
        langs: list[str] = []
        stanza_root = self._spacy_root.parent / "stanza"
        try:
            if stanza_root.exists():
                for p in sorted(stanza_root.iterdir()):
                    if p.is_dir():
                        langs.append(p.name)
        except Exception:
            pass
        self.stanza_installed_lang_combo.blockSignals(True)
        self.stanza_installed_lang_combo.clear()
        self.stanza_installed_lang_combo.addItems(langs)
        self.stanza_installed_lang_combo.blockSignals(False)
        self._refresh_stanza_installed_package_combo()

    def _refresh_stanza_installed_package_combo(self) -> None:
        lang = self.stanza_installed_lang_combo.currentText().strip()
        stanza_root = self._spacy_root.parent / "stanza"
        packages: set[str] = set()
        try:
            base = stanza_root / lang / "tokenize"
            if base.exists():
                for p in base.glob("*.pt"):
                    stem = p.stem.strip()
                    if stem:
                        packages.add(stem)
        except Exception:
            pass
        self.stanza_installed_pkg_combo.blockSignals(True)
        self.stanza_installed_pkg_combo.clear()
        self.stanza_installed_pkg_combo.addItems(sorted(packages))
        self.stanza_installed_pkg_combo.blockSignals(False)
        self.stanza_delete_btn.setEnabled(bool(packages))

    def _delete_selected_stanza_package(self) -> None:
        if self._stanza_delete_thread is not None and self._stanza_delete_thread.is_alive():
            self._set_stanza_status("Delete is already running...")
            return
        lang = self.stanza_installed_lang_combo.currentText().strip()
        package = self.stanza_installed_pkg_combo.currentText().strip()
        if not lang or not package:
            _show_info_dialog(self, "Model Manager", "No installed stanza package selected.")
            return
        ans = QMessageBox.question(
            self,
            "Delete Model",
            f"Delete installed stanza package '{lang}/{package}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.stanza_install_btn.setEnabled(False)
        self.stanza_refresh_btn.setEnabled(False)
        self.stanza_delete_btn.setEnabled(False)
        self._set_stanza_status(f"Deleting stanza package: {lang}/{package} ...")

        def _worker() -> None:
            try:
                stanza_root = self._spacy_root.parent / "stanza"
                lang_key = self._resolve_stanza_alias(lang)
                removed = 0
                pmap = None
                rv = self._stanza_resources.get(lang_key) if isinstance(self._stanza_resources, dict) else None
                if isinstance(rv, dict):
                    packs = rv.get("packages")
                    if isinstance(packs, dict):
                        pmap = packs.get(package)
                if isinstance(pmap, dict):
                    for proc, model_name in pmap.items():
                        if proc == "optional":
                            continue
                        mname = str(model_name).strip()
                        if not mname:
                            continue
                        f = stanza_root / lang_key / str(proc) / f"{mname}.pt"
                        if f.exists():
                            f.unlink(missing_ok=True)
                            removed += 1
                # Fallback: remove package-named files in major processor dirs.
                for proc in ("tokenize", "mwt", "pos", "lemma", "depparse", "ner", "sentiment", "constituency"):
                    f = stanza_root / lang_key / proc / f"{package}.pt"
                    if f.exists():
                        f.unlink(missing_ok=True)
                        removed += 1
                if removed <= 0:
                    raise RuntimeError("No package file found to delete.")
                self._stanzaDeleteFinished.emit(lang_key, package, "")
            except Exception as exc:
                self._stanzaDeleteFinished.emit(lang, package, str(exc))

        self._stanza_delete_thread = threading.Thread(target=_worker, daemon=True)
        self._stanza_delete_thread.start()

    def _on_stanza_delete_done(self, lang: str, package: str, err: str) -> None:
        self.stanza_install_btn.setEnabled(True)
        self.stanza_refresh_btn.setEnabled(True)
        self.stanza_delete_btn.setEnabled(True)
        if err:
            self._set_stanza_status(f"Delete failed: {err}")
            _show_warning_dialog(self, "Model Manager", f"Stanza delete failed:\n{err}")
            return
        self._set_stanza_status(f"Deleted stanza package: {lang}/{package}")
        self._refresh_stanza_installed_languages()
        self.modelsInstalled.emit()


class ConverterPage(QWidget):
    message = pyqtSignal(str)
    MAX_RESULT_LIST_ROWS = 10000
    RESULT_PAGE_SIZE = 1000
    _preload_done = pyqtSignal(object)
    _convert_done = pyqtSignal(object)
    _convert_failed = pyqtSignal(str)
    _parse_done = pyqtSignal(object)
    _parse_failed = pyqtSignal(str)
    _parse_load_done = pyqtSignal(object)
    _parse_load_failed = pyqtSignal(str)
    _txt_import_done = pyqtSignal(object)
    _txt_import_failed = pyqtSignal(str)
    _txt_import_progress = pyqtSignal(str)
    _search_done = pyqtSignal(object)
    _search_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        _bootstrap_cache_layout()
        self._lower_split_ratio_updating = False
        self._imported_treebanks: list[Path] = []
        self._matched_sentences: list[dict[str, object]] = []
        self._result_page = 0
        self._sentence_cache: dict[str, list[dict[str, object]]] = {}
        self._converted_treebank_cache: dict[str, str] = {}
        self._convert_cache_dir = _quansyn_cache_path("convert", "by_source")
        self._retrivis_edit_cache_dir = _quansyn_cache_path("retrivis", "sentence_cache", "edited")
        try:
            self._retrivis_edit_cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._depval_converter_cls = None
        self._field_option_cache: dict[str, list[str]] = {"form": [], "lemma": [], "upos": [], "deprel": []}
        self._preload_token = 0
        self._preload_thread: threading.Thread | None = None
        self._convert_thread: threading.Thread | None = None
        self._parse_thread: threading.Thread | None = None
        self._parse_load_thread: threading.Thread | None = None
        self._txt_import_thread: threading.Thread | None = None
        self._txt_import_token = 0
        self._search_thread: threading.Thread | None = None
        self._search_token = 0
        self._parse_running = False
        self._parse_pipeline_cache: dict[str, object] = {}
        self._parse_txt_sources: list[Path] = []
        self._parse_clean_by_source: dict[str, list[str]] = {}
        self._parse_conllu_by_source: dict[str, str] = {}
        self._parse_conllu_output = ""
        self._models_root = _runtime_base_dir() / "models"
        self._spacy_root = self._models_root / "spacy"
        self._stanza_root = self._models_root / "stanza"
        try:
            self._spacy_root.mkdir(parents=True, exist_ok=True)
            self._stanza_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._parser_cache_dir = _quansyn_cache_path("parser", "current")
        self._parser_cache_file = self._parser_cache_dir / "parser_current.conllu"
        self._convert_drawer_open = False
        self.convert_drawer_width = 330
        self.convert_drawer_anim: QPropertyAnimation | None = None
        self._viz_default_font_size = 14
        self._viz_default_spacing = 108
        self._viz_default_tree_gap = 16
        self._last_svg_markup = ""
        self._build_ui()
        self._wire()
        self._preload_done.connect(self._on_preload_done)
        self._convert_done.connect(self._on_convert_done)
        self._convert_failed.connect(self._on_convert_failed)
        self._parse_done.connect(self._on_parse_done)
        self._parse_failed.connect(self._on_parse_failed)
        self._parse_load_done.connect(self._on_parse_load_done)
        self._parse_load_failed.connect(self._on_parse_load_failed)
        self._txt_import_done.connect(self._on_txt_import_done)
        self._txt_import_failed.connect(self._on_txt_import_failed)
        self._txt_import_progress.connect(self._on_txt_import_progress)
        self._search_done.connect(self._on_search_done_async)
        self._search_failed.connect(self._on_search_failed_async)
        self._populate_example_tab()
        self.retrivis_result_tabs.setCurrentIndex(1)
        self._render_default_example()
        self._refresh_save_mode_options()

    def set_converted_treebank_cache(self, cache: dict[str, str]) -> None:
        self._converted_treebank_cache = cache
        if hasattr(self, "viz_source_combo"):
            self._refresh_viz_source_options()

    def apply_ui_scale(self, scale: float) -> None:
        s = max(0.58, min(1.0, float(scale)))
        width = max(210, int(round(330 * s)))
        self.convert_drawer_width = width
        try:
            self.convert_drawer.setMinimumWidth(width)
            self.convert_drawer.setMaximumWidth(width)
        except Exception:
            pass

    def set_imported_treebanks(self, paths: list[str]) -> None:
        self._imported_treebanks = [Path(p) for p in paths if Path(p).exists()]
        self._sentence_cache.clear()
        self._matched_sentences = []
        self._result_page = 0
        self.result_list.clear()
        self._refresh_result_page()
        self._populate_example_tab()
        self.retrivis_result_tabs.setCurrentIndex(1)
        self._render_default_example()
        self.treebank_combo.blockSignals(True)
        self.treebank_combo.clear()
        self.treebank_combo.addItem("all", "__all__")
        self.convert_treebank_combo.blockSignals(True)
        self.convert_treebank_combo.clear()
        self.convert_treebank_combo.addItem("all", "__all__")
        for path in self._imported_treebanks:
            self.treebank_combo.addItem(path.stem, str(path))
            self.convert_treebank_combo.addItem(path.stem, str(path))
        self._refresh_viz_source_options()
        self.treebank_combo.blockSignals(False)
        self.convert_treebank_combo.blockSignals(False)
        if not self._imported_treebanks:
            self.status_label.setText("No treebanks imported.")
            self.retrivis_result_tabs.setCurrentIndex(1)
            self._render_default_example()
            return
        # Defer heavy sentence preload to on-demand actions (search/source switch)
        # so importing large treebank folders stays responsive.
        self.status_label.setText(f"Loaded {len(self._imported_treebanks)} treebank(s). Ready to search.")

    def set_default_input(self, path: str) -> None:
        if not path:
            return
        p = Path(path)
        if p.exists():
            self.set_imported_treebanks([str(p)])

    def _default_example_payload(self) -> dict[str, object]:
        tokens: list[dict[str, object]] = [
            {"id": 1, "form": "I", "lemma": "I", "upos": "PRON", "head": 2, "deprel": "nsubj"},
            {"id": 2, "form": "used", "lemma": "use", "upos": "VERB", "head": 0, "deprel": "root"},
            {"id": 3, "form": "QuanSyn", "lemma": "QuanSyn", "upos": "PROPN", "head": 2, "deprel": "obj"},
            {"id": 4, "form": "for", "lemma": "for", "upos": "ADP", "head": 7, "deprel": "case"},
            {"id": 5, "form": "quantitative", "lemma": "quantitative", "upos": "ADJ", "head": 7, "deprel": "amod"},
            {"id": 6, "form": "syntactic", "lemma": "syntactic", "upos": "ADJ", "head": 7, "deprel": "amod"},
            {"id": 7, "form": "analysis", "lemma": "analysis", "upos": "NOUN", "head": 2, "deprel": "obl"},
            {"id": 8, "form": ".", "lemma": ".", "upos": "PUNCT", "head": 2, "deprel": "punct"},
        ]
        return {
            "path": Path("example.conllu"),
            "sent_idx": 1,
            "sentence": {"text": "I used QuanSyn for quantitative syntactic analysis.", "tokens": tokens},
        }

    def _render_default_example(self) -> None:
        self._render_dependency_graph(self._default_example_payload())

    def _is_light_theme(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            return str(app.property("quansyn_theme") or "").strip().lower() == "light"
        except Exception:
            return False

    def _retrivis_palette(self) -> dict[str, str]:
        if self._is_light_theme():
            return {
                "bg": "#ffffff",
                "fg": "#1f2a37",
                "hint": "#2f5f9f",
                "sub": "#4a5f7a",
                "border": "#d0d9e6",
                "form": "#000000",
                "lemma": "#000000",
                "upos": "#1f2a37",
                "id": "#1f2a37",
                "edge": "#5f86b8",
                "rel": "#c43f3f",
            }
        return {
            "bg": "#1f1f1f",
            "fg": "#d4d4d4",
            "hint": "#9cdcfe",
            "sub": "#c5c5c5",
            "border": "#3a4450",
            "form": "#d4d4d4",
            "lemma": "#bfc9d4",
            "upos": "#9fb2c7",
            "id": "#8ea3b8",
            "edge": "#7aa2d2",
            "rel": "#cc5a5a",
        }

    def apply_theme_to_view(self) -> None:
        if self.retrivis_result_tabs.currentIndex() == 1:
            self._render_default_example()
            return
        item = self.result_list.currentItem()
        payload = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._render_dependency_graph(payload)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._enforce_lower_split_ratio()

    def _enforce_lower_split_ratio(self) -> None:
        split = getattr(self, "lower_split", None)
        if split is None or self._lower_split_ratio_updating:
            return
        total = max(1, int(split.width()))
        if total <= 2:
            return
        left = max(1, int(total / 3))
        right = max(1, total - left)
        self._lower_split_ratio_updating = True
        try:
            split.setSizes([left, right])
        finally:
            self._lower_split_ratio_updating = False

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        main_col = QWidget()
        root = QVBoxLayout(main_col)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        graph_wrap = QFrame()
        graph_wrap.setObjectName("vizParamWrap")
        graph_layout = QVBoxLayout(graph_wrap)
        graph_layout.setContentsMargins(6, 6, 6, 6)
        graph_layout.setSpacing(4)

        graph_head = QHBoxLayout()
        graph_head.setSpacing(6)
        graph_title = QLabel("Dependency Tree")
        graph_title.setObjectName("sectionTitle")
        graph_head.addWidget(graph_title, 0, Qt.AlignmentFlag.AlignLeft)
        graph_head.addStretch(1)
        graph_layout.addLayout(graph_head)

        self.graph_hint = QLabel("Click a sentence above to visualize its dependency graph.")
        self.graph_hint.setObjectName("statusInfo")
        graph_layout.addWidget(self.graph_hint)
        self.graph_hint.hide()

        self.graph_web = None
        self.graph_text_fallback = None
        palette = self._retrivis_palette()
        if QWebEngineView is not None:
            self.graph_web = QWebEngineView()
            _reject_web_fullscreen(self.graph_web)
            self.graph_web.setMinimumHeight(320)
            self.graph_web.setStyleSheet(f"background:{palette['bg']};")
            try:
                self.graph_web.page().setBackgroundColor(QColor(palette["bg"]))
            except Exception:
                pass
            # Warm up web engine canvas to avoid first-show flash.
            self.graph_web.setHtml(
                f"<html><body style='margin:0;background:{palette['bg']};color:{palette['fg']};'></body></html>"
            )
            graph_layout.addWidget(self.graph_web, 1)
            self.graph_hint.setText("HTML renderer ready.")
        else:
            self.graph_text_fallback = QTextEdit()
            self.graph_text_fallback.setReadOnly(True)
            self.graph_text_fallback.setMinimumHeight(260)
            self.graph_text_fallback.setPlainText(
                "HTML dependency renderer is unavailable.\n"
                "Reason: QWebEngineView is not installed in this environment.\n"
                "Please install PyQt6-WebEngine."
            )
            graph_layout.addWidget(self.graph_text_fallback, 1)
        root.addWidget(graph_wrap, 4)

        lower_split = QSplitter(Qt.Orientation.Horizontal)
        self.lower_split = lower_split
        root.addWidget(lower_split, 2)

        control_wrap = QFrame()
        control_wrap.setObjectName("vizParamWrap")
        control_layout = QVBoxLayout(control_wrap)
        control_layout.setContentsMargins(8, 8, 8, 8)
        control_layout.setSpacing(6)
        control_title = QLabel("Search Settings")
        control_title.setObjectName("sectionTitle")
        control_layout.addWidget(control_title)

        self.treebank_combo = QComboBox()
        self.treebank_combo.addItem("all", "__all__")
        self.form_input = self._build_filter_combo("form / all")
        self.lemma_input = self._build_filter_combo("lemma / all")
        self.upos_input = self._build_filter_combo("upos / all")
        self.deprel_input = self._build_filter_combo("deprel / all")

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.addWidget(QLabel("Treebank"))
        top_row.addWidget(self.treebank_combo, 1)
        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("accentButton")
        top_row.addWidget(self.search_btn, 0)
        control_layout.addLayout(top_row)

        row_1 = QHBoxLayout()
        row_1.setSpacing(6)
        row_1.addWidget(QLabel("form"))
        row_1.addWidget(self.form_input, 1)
        row_1.addWidget(QLabel("lemma"))
        row_1.addWidget(self.lemma_input, 1)
        control_layout.addLayout(row_1)

        row_2 = QHBoxLayout()
        row_2.setSpacing(6)
        row_2.addWidget(QLabel("upos"))
        row_2.addWidget(self.upos_input, 1)
        row_2.addWidget(QLabel("deprel"))
        row_2.addWidget(self.deprel_input, 1)
        control_layout.addLayout(row_2)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("statusInfo")
        control_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignRight)

        result_wrap = QFrame()
        result_wrap.setObjectName("vizParamWrap")
        result_layout = QVBoxLayout(result_wrap)
        result_layout.setContentsMargins(8, 8, 8, 8)
        result_layout.setSpacing(6)
        result_head = QHBoxLayout()
        result_head.setSpacing(6)
        result_title = QLabel("Matched Sentences")
        result_title.setObjectName("sectionTitle")
        result_head.addWidget(result_title, 0, Qt.AlignmentFlag.AlignLeft)
        result_head.addStretch(1)
        self.prev_graph_btn = QPushButton("Prev")
        self.next_graph_btn = QPushButton("Next")
        self.graph_nav_label = QLabel("0 / 0")
        self.graph_nav_label.setObjectName("statusInfo")
        result_head.addWidget(self.prev_graph_btn, 0)
        result_head.addWidget(self.graph_nav_label, 0)
        result_head.addWidget(self.next_graph_btn, 0)
        result_layout.addLayout(result_head)
        self.retrivis_result_tabs = QTabWidget()
        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.result_list.setMinimumHeight(160)
        self.example_list = QListWidget()
        self.example_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.example_list.setMinimumHeight(160)
        self.retrivis_result_tabs.addTab(self.result_list, "matched")
        self.retrivis_result_tabs.addTab(self.example_list, "example")
        result_layout.addWidget(self.retrivis_result_tabs, 1)
        page_nav = QHBoxLayout()
        page_nav.setContentsMargins(0, 0, 0, 0)
        page_nav.setSpacing(6)
        self.prev_page_btn = QPushButton("Prev")
        self.next_page_btn = QPushButton("Next")
        self.result_page_label = QLabel("Page 0/0")
        self.result_page_label.setObjectName("statusInfo")
        page_nav.addWidget(self.prev_page_btn, 0, Qt.AlignmentFlag.AlignLeft)
        page_nav.addStretch(1)
        page_nav.addWidget(self.result_page_label, 0, Qt.AlignmentFlag.AlignCenter)
        page_nav.addStretch(1)
        page_nav.addWidget(self.next_page_btn, 0, Qt.AlignmentFlag.AlignRight)
        result_layout.addLayout(page_nav)
        lower_split.addWidget(control_wrap)
        lower_split.addWidget(result_wrap)
        lower_split.setStretchFactor(0, 1)
        lower_split.setStretchFactor(1, 2)
        lower_split.setChildrenCollapsible(False)
        lower_split.setSizes([400, 800])
        lower_split.splitterMoved.connect(lambda _p, _i: QTimer.singleShot(0, self._enforce_lower_split_ratio))
        QTimer.singleShot(0, self._enforce_lower_split_ratio)

        self.convert_drawer = QFrame()
        self.convert_drawer.setObjectName("depvalDrawer")
        self.convert_drawer.setMinimumWidth(self.convert_drawer_width)
        self.convert_drawer.setMaximumWidth(self.convert_drawer_width)
        convert_drawer_layout = QVBoxLayout(self.convert_drawer)
        convert_drawer_layout.setContentsMargins(0, 0, 0, 0)
        convert_drawer_layout.setSpacing(0)
        self.convert_drawer_scroll = QScrollArea(self.convert_drawer)
        self.convert_drawer_scroll.setWidgetResizable(True)
        self.convert_drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.convert_drawer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        convert_drawer_layout.addWidget(self.convert_drawer_scroll, 1)
        self.convert_drawer_content = QWidget()
        self.convert_drawer_scroll.setWidget(self.convert_drawer_content)
        convert_layout = QVBoxLayout(self.convert_drawer_content)
        convert_layout.setContentsMargins(12, 10, 12, 12)
        convert_layout.setSpacing(8)

        convert_run_wrap = QFrame()
        convert_run_wrap.setObjectName("vizParamWrap")
        convert_run_layout = QVBoxLayout(convert_run_wrap)
        convert_run_layout.setContentsMargins(8, 8, 8, 8)
        convert_run_layout.setSpacing(6)
        convert_run_title = QLabel("Format Conversion")
        convert_run_title.setObjectName("sectionTitle")
        convert_run_layout.addWidget(convert_run_title)
        convert_form = QFormLayout()
        self.convert_source_fmt_combo = QComboBox()
        self.convert_source_fmt_combo.addItems(list(SUPPORTED_FORMATS))
        self.convert_source_fmt_combo.setCurrentText("conll")
        self.convert_target_fmt_combo = QComboBox()
        self.convert_target_fmt_combo.addItems(list(SUPPORTED_FORMATS))
        self.convert_target_fmt_combo.setCurrentText("conllu")
        self.convert_treebank_combo = QComboBox()
        self.convert_treebank_combo.addItem("all", "__all__")
        convert_form.addRow("Input format", self.convert_source_fmt_combo)
        convert_form.addRow("Output format", self.convert_target_fmt_combo)
        convert_form.addRow("Treebank", self.convert_treebank_combo)
        convert_run_layout.addLayout(convert_form)
        self.convert_run_btn = QPushButton("Run Convert")
        self.convert_run_btn.setObjectName("accentButton")
        convert_run_layout.addWidget(self.convert_run_btn)
        convert_layout.addWidget(convert_run_wrap)

        parse_wrap = QFrame()
        parse_wrap.setObjectName("vizParamWrap")
        parse_layout = QVBoxLayout(parse_wrap)
        parse_layout.setContentsMargins(8, 8, 8, 8)
        parse_layout.setSpacing(6)
        parse_title_row = QHBoxLayout()
        parse_title_row.setContentsMargins(0, 0, 0, 0)
        parse_title_row.setSpacing(6)
        parse_title = QLabel("Import & parse")
        parse_title.setObjectName("sectionTitle")
        parse_title_row.addWidget(parse_title, 0, Qt.AlignmentFlag.AlignLeft)
        parse_title_row.addStretch(1)
        self.parse_manage_btn = QPushButton("Manage")
        self.parse_manage_btn.setObjectName("accentButton")
        parse_title_row.addWidget(self.parse_manage_btn, 0, Qt.AlignmentFlag.AlignRight)
        parse_layout.addLayout(parse_title_row)

        parse_import_title = QLabel("import:")
        parse_import_title.setObjectName("statusInfo")
        parse_layout.addWidget(parse_import_title)
        parse_import_row = QHBoxLayout()
        parse_import_row.setContentsMargins(0, 0, 0, 0)
        parse_import_row.setSpacing(6)
        self.parse_import_file_btn = QPushButton("txt")
        self.parse_import_folder_btn = QPushButton("folder")
        parse_import_row.addWidget(self.parse_import_file_btn, 1)
        parse_import_row.addWidget(self.parse_import_folder_btn, 1)
        parse_layout.addLayout(parse_import_row)

        parse_form = QFormLayout()
        self.parse_txt_select_combo = QComboBox()
        self.parse_txt_select_combo.addItem("all", "__all__")
        self.parse_backend_combo = QComboBox()
        self.parse_backend_combo.addItems(["spacy", "stanza"])
        self.parse_lang_combo = QComboBox()
        self.parse_lang_combo.addItems(["en", "zh"])
        self.parse_model_combo = QComboBox()
        self.parse_model_combo.setEditable(True)
        self.parse_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        parse_form.addRow("TXT file", self.parse_txt_select_combo)
        parse_form.addRow("Parser", self.parse_backend_combo)
        parse_form.addRow("Language", self.parse_lang_combo)
        parse_form.addRow("Model", self.parse_model_combo)
        parse_layout.addLayout(parse_form)

        parse_run_row = QHBoxLayout()
        parse_run_row.setContentsMargins(0, 0, 0, 0)
        parse_run_row.setSpacing(6)
        self.parse_load_btn = QPushButton("Load")
        self.parse_run_btn = QPushButton("Run")
        self.parse_run_btn.setObjectName("accentButton")
        parse_run_row.addWidget(self.parse_load_btn, 1)
        parse_run_row.addWidget(self.parse_run_btn, 1)
        parse_layout.addLayout(parse_run_row)

        convert_layout.addWidget(parse_wrap)

        save_wrap = QFrame()
        save_wrap.setObjectName("vizParamWrap")
        save_layout = QVBoxLayout(save_wrap)
        save_layout.setContentsMargins(8, 8, 8, 8)
        save_layout.setSpacing(6)
        save_title = QLabel("Save")
        save_title.setObjectName("sectionTitle")
        save_layout.addWidget(save_title)
        self.convert_save_mode_combo = QComboBox()
        self.convert_save_mode_combo.addItems(["converted", "parsed"])
        save_layout.addWidget(self.convert_save_mode_combo)
        self.convert_save_btn = QPushButton("Save Cached")
        save_layout.addWidget(self.convert_save_btn)
        convert_layout.addWidget(save_wrap)

        viz_wrap = QFrame()
        viz_wrap.setObjectName("vizParamWrap")
        viz_layout = QVBoxLayout(viz_wrap)
        viz_layout.setContentsMargins(8, 8, 8, 8)
        viz_layout.setSpacing(6)
        viz_title = QLabel("Visualization")
        viz_title.setObjectName("sectionTitle")
        viz_layout.addWidget(viz_title)
        viz_form = QFormLayout()
        self.viz_source_combo = QComboBox()
        self.viz_source_combo.addItem("imported", "imported")
        self.viz_source_combo.setCurrentIndex(0)
        self.viz_font_size_spin = QSpinBox()
        self.viz_font_size_spin.setRange(10, 24)
        self.viz_font_size_spin.setValue(self._viz_default_font_size)
        self._setup_viz_spinbox(self.viz_font_size_spin)
        self.viz_spacing_spin = QSpinBox()
        self.viz_spacing_spin.setRange(70, 180)
        self.viz_spacing_spin.setValue(self._viz_default_spacing)
        self._setup_viz_spinbox(self.viz_spacing_spin)
        self.viz_tree_gap_spin = QSpinBox()
        self.viz_tree_gap_spin.setRange(16, 72)
        self.viz_tree_gap_spin.setValue(self._viz_default_tree_gap)
        self._setup_viz_spinbox(self.viz_tree_gap_spin)
        viz_form.addRow("Source", self.viz_source_combo)
        viz_form.addRow("Font size", self.viz_font_size_spin)
        viz_form.addRow("Token spacing", self.viz_spacing_spin)
        viz_form.addRow("Tree-text gap", self.viz_tree_gap_spin)
        viz_layout.addLayout(viz_form)
        self.viz_reset_btn = QPushButton("Reset Defaults")
        self.viz_export_btn = QPushButton("Export")
        viz_layout.addWidget(self.viz_reset_btn)
        viz_layout.addWidget(self.viz_export_btn)
        convert_layout.addWidget(viz_wrap)
        convert_layout.addStretch(1)

        outer.addWidget(main_col, 1)
        outer.addWidget(self.convert_drawer, 0)
        self._populate_example_tab()

    def _wire(self) -> None:
        self.treebank_combo.currentTextChanged.connect(self._on_treebank_changed)
        self.search_btn.clicked.connect(self._search_sentences)
        self.convert_run_btn.clicked.connect(self.convert_treebanks_to_cache)
        self.convert_save_btn.clicked.connect(self.save_cached_content_dialog)
        self.parse_import_file_btn.clicked.connect(self._on_parse_import_txt_file)
        self.parse_import_folder_btn.clicked.connect(self._on_parse_import_txt_folder)
        self.parse_backend_combo.currentTextChanged.connect(self._on_parse_backend_changed)
        self.parse_lang_combo.currentTextChanged.connect(self._refresh_parse_model_options)
        self.parse_load_btn.clicked.connect(self._on_parse_load_clicked)
        self.parse_run_btn.clicked.connect(self._on_parse_run_clicked)
        self.parse_manage_btn.clicked.connect(self._open_parse_model_manager)
        self.viz_source_combo.currentTextChanged.connect(self._on_visualization_data_source_toggled)
        self.viz_font_size_spin.valueChanged.connect(self._on_viz_style_changed)
        self.viz_spacing_spin.valueChanged.connect(self._on_viz_style_changed)
        self.viz_tree_gap_spin.valueChanged.connect(self._on_viz_style_changed)
        self.viz_reset_btn.clicked.connect(self._reset_viz_defaults)
        self.viz_export_btn.clicked.connect(self._export_graph_image_dialog)
        for combo in [self.form_input, self.lemma_input, self.upos_input, self.deprel_input]:
            editor = combo.lineEdit()
            if editor is not None:
                editor.returnPressed.connect(self._search_sentences)
        self.result_list.itemSelectionChanged.connect(self._on_result_clicked)
        self.example_list.itemSelectionChanged.connect(self._on_result_clicked)
        self.retrivis_result_tabs.currentChanged.connect(self._on_retrivis_tab_changed)
        self.prev_graph_btn.clicked.connect(lambda: self._switch_graph_item(-1))
        self.next_graph_btn.clicked.connect(lambda: self._switch_graph_item(1))
        self.prev_page_btn.clicked.connect(lambda: self._switch_result_page(-1))
        self.next_page_btn.clicked.connect(lambda: self._switch_result_page(1))
        if self.graph_web is not None:
            # Let embedded HTML handle right-click menus for node/edge editing.
            self.graph_web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.graph_web.titleChanged.connect(self._on_graph_title_changed)
        self._refresh_parse_language_options()
        self._refresh_parse_model_options()

    def _build_filter_combo(self, placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.addItem("all")
        combo.setCurrentText("all")
        editor = combo.lineEdit()
        if editor is not None:
            editor.setPlaceholderText(placeholder)
        completer = QCompleter(combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setModel(QStringListModel(["all"], combo))
        combo.setCompleter(completer)
        return combo

    def _set_combo_options(self, combo: QComboBox, values: list[str]) -> None:
        current_text = combo.currentText().strip() or "all"
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("all")
        for value in values:
            combo.addItem(value)
        combo.setEditText(current_text)
        combo.blockSignals(False)
        comp = combo.completer()
        if comp is not None:
            comp.setModel(QStringListModel(["all", *values], combo))

    def _refresh_filter_options(self, files: list[Path]) -> None:
        form_set: set[str] = set()
        lemma_set: set[str] = set()
        upos_set: set[str] = set()
        deprel_set: set[str] = set()
        limit = 5000
        for tb in files:
            for sent in self._parse_treebank_sentences(tb):
                toks: list[dict[str, object]] = sent["tokens"]  # type: ignore[assignment]
                for tok in toks:
                    form_set.add(str(tok.get("form", "")).strip())
                    lemma_set.add(str(tok.get("lemma", "")).strip())
                    upos_set.add(str(tok.get("upos", "")).strip())
                    deprel_set.add(str(tok.get("deprel", "")).strip())
                if (
                    len(form_set) > limit
                    and len(lemma_set) > limit
                    and len(upos_set) > limit
                    and len(deprel_set) > limit
                ):
                    break
        self._field_option_cache = {
            "form": sorted(v for v in form_set if v),
            "lemma": sorted(v for v in lemma_set if v),
            "upos": sorted(v for v in upos_set if v),
            "deprel": sorted(v for v in deprel_set if v),
        }
        self._set_combo_options(self.form_input, self._field_option_cache["form"])
        self._set_combo_options(self.lemma_input, self._field_option_cache["lemma"])
        self._set_combo_options(self.upos_input, self._field_option_cache["upos"])
        self._set_combo_options(self.deprel_input, self._field_option_cache["deprel"])

    def _on_treebank_changed(self, _value: str) -> None:
        files = self._selected_treebanks()
        self._refresh_filter_options(files)
        self._search_sentences()

    def _start_preload(self) -> None:
        if conllu_parse_incr is None:
            self.status_label.setText("conllu backend unavailable. Please install conllu.")
            return
        self._preload_token += 1
        token = self._preload_token
        files = self._selected_treebanks()
        self._preload_thread = threading.Thread(
            target=self._preload_worker,
            args=(token, files),
            daemon=True,
        )
        self._preload_thread.start()

    def _parse_treebank_sentences_worker(self, path: Path) -> list[dict[str, object]]:
        if conllu_parse_incr is None:
            return []
        read_path = path
        try:
            edited = self._retrivis_edit_cache_file(path)
            if edited.exists():
                read_path = edited
        except Exception:
            read_path = path
        try:
            fp = read_path.open("r", encoding="utf-8", errors="ignore")
        except Exception:
            return []
        out: list[dict[str, object]] = []
        try:
            for sent in conllu_parse_incr(fp):
                tokens: list[dict[str, object]] = []
                for tok in sent:
                    tid = tok.get("id")
                    if not isinstance(tid, int):
                        continue
                    head = tok.get("head")
                    if not isinstance(head, int):
                        head = 0
                    deprel = tok.get("deprel")
                    if isinstance(deprel, str) and ":" in deprel:
                        deprel = deprel.split(":", 1)[0]
                    tokens.append(
                        {
                            "id": tid,
                            "form": str(tok.get("form", "_") or "_"),
                            "lemma": str(tok.get("lemma", "_") or "_"),
                            "upos": str(tok.get("upos", "_") or "_"),
                            "head": head,
                            "deprel": str(deprel or "_"),
                        }
                    )
                if not tokens:
                    continue
                sent_text = str(sent.metadata.get("text", "")).strip() if hasattr(sent, "metadata") else ""
                if not sent_text:
                    sent_text = " ".join(str(t["form"]) for t in tokens)
                out.append({"text": sent_text, "tokens": tokens})
        except Exception:
            return []
        finally:
            fp.close()
        return out

    def _preload_worker(self, token: int, files: list[Path]) -> None:
        cache_payload: dict[str, list[dict[str, object]]] = {}
        form_set: set[str] = set()
        lemma_set: set[str] = set()
        upos_set: set[str] = set()
        deprel_set: set[str] = set()
        for tb in files:
            key = str(tb.resolve())
            sents = self._parse_treebank_sentences_worker(tb)
            cache_payload[key] = sents
            for sent in sents:
                toks: list[dict[str, object]] = sent["tokens"]  # type: ignore[assignment]
                for tok in toks:
                    form_set.add(str(tok.get("form", "")).strip())
                    lemma_set.add(str(tok.get("lemma", "")).strip())
                    upos_set.add(str(tok.get("upos", "")).strip())
                    deprel_set.add(str(tok.get("deprel", "")).strip())
        payload = {
            "token": token,
            "cache": cache_payload,
            "form": sorted(v for v in form_set if v),
            "lemma": sorted(v for v in lemma_set if v),
            "upos": sorted(v for v in upos_set if v),
            "deprel": sorted(v for v in deprel_set if v),
        }
        self._preload_done.emit(payload)

    def _on_preload_done(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        token = int(payload.get("token", -1))
        if token != self._preload_token:
            return
        cache = payload.get("cache", {})
        if isinstance(cache, dict):
            self._sentence_cache.update(cache)  # type: ignore[arg-type]
        self._field_option_cache = {
            "form": list(payload.get("form", [])),
            "lemma": list(payload.get("lemma", [])),
            "upos": list(payload.get("upos", [])),
            "deprel": list(payload.get("deprel", [])),
        }
        self._set_combo_options(self.form_input, self._field_option_cache["form"])
        self._set_combo_options(self.lemma_input, self._field_option_cache["lemma"])
        self._set_combo_options(self.upos_input, self._field_option_cache["upos"])
        self._set_combo_options(self.deprel_input, self._field_option_cache["deprel"])
        self.status_label.setText(f"Preload done. Ready to search ({len(self._imported_treebanks)} treebank(s)).")

    def _active_result_list(self) -> QListWidget:
        if hasattr(self, "retrivis_result_tabs") and self.retrivis_result_tabs.currentIndex() == 1:
            return self.example_list
        return self.result_list

    def _populate_example_tab(self) -> None:
        if not hasattr(self, "example_list"):
            return
        self.example_list.clear()
        payload = self._default_example_payload()
        sent: dict[str, object] = payload["sentence"]  # type: ignore[assignment]
        text = f"example | #1 | {str(sent.get('text', '')).strip()}"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, payload)
        self.example_list.addItem(item)
        if self.example_list.count() > 0:
            self.example_list.setCurrentRow(0)

    def _on_retrivis_tab_changed(self, _index: int) -> None:
        in_matched = self.retrivis_result_tabs.currentIndex() == 0
        self.prev_page_btn.setVisible(in_matched)
        self.next_page_btn.setVisible(in_matched)
        self.result_page_label.setVisible(in_matched)
        active = self._active_result_list()
        if active.currentItem() is not None:
            self._on_result_clicked()
        else:
            self._update_graph_nav()

    def _switch_graph_item(self, delta: int) -> None:
        active = self._active_result_list()
        total = active.count()
        if total <= 0:
            return
        idx = active.currentRow()
        if idx < 0:
            idx = 0
        target = max(0, min(total - 1, idx + delta))
        if target != idx:
            active.setCurrentRow(target)
        self._update_graph_nav()

    def _switch_result_page(self, delta: int) -> None:
        if not self._matched_sentences:
            self._result_page = 0
            self._refresh_result_page()
            return
        pages = max(1, (len(self._matched_sentences) + self.RESULT_PAGE_SIZE - 1) // self.RESULT_PAGE_SIZE)
        self._result_page = max(0, min(pages - 1, self._result_page + delta))
        self._refresh_result_page()

    def _refresh_result_page(self) -> None:
        total = len(self._matched_sentences)
        pages = max(1, (total + self.RESULT_PAGE_SIZE - 1) // self.RESULT_PAGE_SIZE) if total > 0 else 1
        self._result_page = max(0, min(pages - 1, self._result_page))
        start = self._result_page * self.RESULT_PAGE_SIZE
        end = min(total, start + self.RESULT_PAGE_SIZE)

        self.result_list.clear()
        for payload in self._matched_sentences[start:end]:
            tb: Path = payload["path"]  # type: ignore[assignment]
            sent_idx: int = int(payload["sent_idx"])
            sent: dict[str, object] = payload["sentence"]  # type: ignore[assignment]
            sent_text = str(sent.get("text", "")).strip()
            text = f"{tb.stem} | #{sent_idx} | {sent_text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, payload)
            self.result_list.addItem(item)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

        self.result_page_label.setText(f"Page {0 if total == 0 else self._result_page + 1}/{0 if total == 0 else pages}")
        self.prev_page_btn.setEnabled(total > 0 and self._result_page > 0)
        self.next_page_btn.setEnabled(total > 0 and self._result_page < pages - 1)

    def _update_graph_nav(self) -> None:
        active = self._active_result_list()
        total = active.count()
        idx = active.currentRow()
        if idx < 0:
            idx = 0
        current = 0 if total == 0 else idx + 1
        self.graph_nav_label.setText(f"{current} / {total}")
        self.prev_graph_btn.setEnabled(total > 0 and idx > 0)
        self.next_graph_btn.setEnabled(total > 0 and idx < total - 1)

    def _refresh_viz_source_options(self) -> None:
        current = str(self.viz_source_combo.currentData() or "imported")
        options: list[tuple[str, str]] = [(src, src) for src in self._available_viz_sources()]
        self.viz_source_combo.blockSignals(True)
        self.viz_source_combo.clear()
        for label, data in options:
            self.viz_source_combo.addItem(label, data)
        target = current if any(data == current for _, data in options) else options[0][1]
        idx = self.viz_source_combo.findData(target)
        self.viz_source_combo.setCurrentIndex(max(0, idx))
        self.viz_source_combo.blockSignals(False)
        self._refresh_treebank_combo_by_source()
        self._refresh_save_mode_options()

    def _treebank_display_name(self, path: Path) -> str:
        return path.stem

    def _parsed_cache_files(self) -> list[Path]:
        by_src_dir = self._parser_cache_dir / "by_source"
        files: list[Path] = []
        if by_src_dir.exists():
            files = sorted([p for p in by_src_dir.glob("*.conllu") if p.is_file()], key=lambda p: p.name.lower())
        return files

    def _converted_source_entries(self) -> list[tuple[str, Path]]:
        raw: list[tuple[str, Path]] = []
        for src, cached in self._converted_treebank_cache.items():
            cp = Path(str(cached))
            if not cp.exists():
                continue
            label = Path(str(src)).stem or cp.stem
            raw.append((label, cp))
        raw.sort(key=lambda x: (x[0].lower(), x[1].name.lower()))
        used: dict[str, int] = {}
        out: list[tuple[str, Path]] = []
        for label, path in raw:
            idx = used.get(label, 0)
            used[label] = idx + 1
            final_label = label if idx == 0 else f"{label}_{idx+1}"
            out.append((final_label, path))
        return out

    def _source_entries(self, source: str) -> list[tuple[str, Path]]:
        src = str(source or "").strip().lower()
        if src == "edited":
            return self._edited_source_entries()
        if src == "parsed":
            return [(p.stem, p) for p in self._parsed_cache_files()]
        if src == "converted":
            return self._converted_source_entries()
        return [(self._treebank_display_name(p), p) for p in self._imported_treebanks]

    def _edited_source_entries(self) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        seen_paths: set[str] = set()
        used: dict[str, int] = {}
        for src in ("imported", "converted", "parsed"):
            for label, base_path in self._source_entries(src):
                try:
                    edited = self._retrivis_edit_cache_file(base_path)
                except Exception:
                    continue
                if not edited.exists():
                    continue
                try:
                    resolved = str(edited.resolve())
                except Exception:
                    resolved = str(edited)
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                base = (label or base_path.stem or "edited").strip()
                idx = used.get(base, 0)
                used[base] = idx + 1
                final_label = base if idx == 0 else f"{base}_{idx+1}"
                out.append((final_label, edited))
        out.sort(key=lambda x: x[0].lower())
        return out

    def _treebanks_for_source(self, source: str) -> list[Path]:
        return [p for _, p in self._source_entries(source)]

    def _update_treebank_combo_with_entries(self, combo: QComboBox, entries: list[tuple[str, Path]]) -> None:
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("all", "__all__")
        for label, path in entries:
            combo.addItem(label, str(path))
        idx = combo.findData(prev)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _refresh_treebank_combo_by_source(self) -> None:
        source = str(self.viz_source_combo.currentData() or "imported")
        self._update_treebank_combo_with_entries(self.treebank_combo, self._source_entries(source))

    def _available_viz_sources(self) -> list[str]:
        options: list[str] = []
        if self._imported_treebanks:
            options.append("imported")
        has_converted = any(Path(p).exists() for p in self._converted_treebank_cache.values() if str(p).strip())
        if has_converted:
            options.append("converted")
        if self._parsed_cache_files():
            options.append("parsed")
        if self._edited_source_entries():
            options.append("edited")
        if not options:
            options.append("imported")
        return options

    def _refresh_save_mode_options(self) -> None:
        if not hasattr(self, "convert_save_mode_combo"):
            return
        prev = str(self.convert_save_mode_combo.currentText() or "converted").strip().lower()
        options = ["converted", "parsed"]
        if self._edited_source_entries():
            options.append("edited")
        self.convert_save_mode_combo.blockSignals(True)
        self.convert_save_mode_combo.clear()
        self.convert_save_mode_combo.addItems(options)
        idx = self.convert_save_mode_combo.findText(prev)
        self.convert_save_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.convert_save_mode_combo.blockSignals(False)

    def _selected_treebanks(self) -> list[Path]:
        source = str(self.viz_source_combo.currentData() or "imported")
        files = self._treebanks_for_source(source)
        if not files:
            return []
        selected_data = self.treebank_combo.currentData()
        if selected_data in (None, "__all__"):
            return files
        target = str(selected_data)
        for tb in files:
            if str(tb) == target:
                return [tb]
        return files

    def _update_convert_drawer_geometry(self, initial: bool = False) -> None:
        return

    def toggle_convert_drawer(self) -> None:
        return

    def open_convert_drawer(self) -> None:
        return

    def close_convert_drawer(self) -> None:
        return

    def _on_visualization_data_source_toggled(self, _value=None) -> None:
        source = str(self.viz_source_combo.currentData() or "imported")
        self._sentence_cache.clear()
        self._refresh_treebank_combo_by_source()
        self.status_label.setText(f"Visualization source: {source}.")
        self.message.emit(f"RetriVis visualization source switched to {source}.")
        if self._selected_treebanks():
            self._start_preload()
            self._search_sentences()
        else:
            self._matched_sentences = []
            self.result_list.clear()
            self._refresh_result_page()
            self.retrivis_result_tabs.setCurrentIndex(1)
            self._render_default_example()

    def _on_viz_style_changed(self, _value=None) -> None:
        if self._active_result_list().currentItem() is not None:
            self._on_result_clicked()

    def _reset_viz_defaults(self) -> None:
        idx = self.viz_source_combo.findData("imported")
        self.viz_source_combo.setCurrentIndex(max(0, idx))
        self.viz_font_size_spin.setValue(self._viz_default_font_size)
        self.viz_spacing_spin.setValue(self._viz_default_spacing)
        self.viz_tree_gap_spin.setValue(self._viz_default_tree_gap)
        if self._active_result_list().currentItem() is not None:
            self._on_result_clicked()

    def _setup_viz_spinbox(self, spin: QSpinBox) -> None:
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        spin.setAccelerated(True)
        spin.setMinimumHeight(28)
        spin.setStyleSheet(
            "QSpinBox { padding-right: 22px; }"
            "QSpinBox::up-button, QSpinBox::down-button { "
            "subcontrol-origin: border; width: 18px; }"
            "QSpinBox::up-button { subcontrol-position: top right; }"
            "QSpinBox::down-button { subcontrol-position: bottom right; }"
        )

    def _on_graph_context_menu(self, pos: QPoint) -> None:
        if self.graph_web is None:
            return
        menu = QMenu(self)
        export_action = menu.addAction("Export")
        chosen = menu.exec(self.graph_web.mapToGlobal(pos))
        if chosen is export_action:
            self._export_graph_image_dialog()

    @staticmethod
    def _norm_edit_tokens(tokens: object) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        if not isinstance(tokens, list):
            return out
        for tok in tokens:
            if not isinstance(tok, dict):
                continue
            try:
                tid = int(tok.get("id", 0) or 0)
            except Exception:
                tid = 0
            if tid <= 0:
                continue
            try:
                head = int(tok.get("head", 0) or 0)
            except Exception:
                head = 0
            deprel = str(tok.get("deprel", "_") or "_")
            if ":" in deprel:
                deprel = deprel.split(":", 1)[0]
            out.append(
                {
                    "id": tid,
                    "form": str(tok.get("form", "_") or "_"),
                    "lemma": str(tok.get("lemma", "_") or "_"),
                    "upos": str(tok.get("upos", "_") or "_"),
                    "head": max(0, head),
                    "deprel": deprel,
                }
            )
        out.sort(key=lambda x: int(x.get("id", 0) or 0))
        ids = {int(t["id"]) for t in out}
        for t in out:
            h = int(t.get("head", 0) or 0)
            if h not in ids:
                t["head"] = 0
        return out

    @staticmethod
    def _tokens_to_conllu_text(sent_idx: int, text: str, tokens: list[dict[str, object]]) -> str:
        lines = [f"# sent_id = {int(sent_idx)}", f"# text = {text}"]
        for tok in sorted(tokens, key=lambda x: int(x.get("id", 0) or 0)):
            tid = int(tok.get("id", 0) or 0)
            if tid <= 0:
                continue
            form = str(tok.get("form", "_") or "_")
            lemma = str(tok.get("lemma", "_") or "_")
            upos = str(tok.get("upos", "_") or "_")
            head = int(tok.get("head", 0) or 0)
            deprel = str(tok.get("deprel", "_") or "_")
            lines.append(f"{tid}\t{form}\t{lemma}\t{upos}\t_\t_\t{head}\t{deprel}\t_\t_")
        return "\n".join(lines)

    def _persist_cached_treebank_if_needed(self, treebank_path: Path) -> None:
        try:
            resolved = str(treebank_path.resolve())
        except Exception:
            return
        cache_paths = {str(Path(p).resolve()) for p in self._converted_treebank_cache.values() if str(p).strip()}
        cache_paths.add(str(self._parser_cache_file.resolve()))
        if resolved not in cache_paths:
            return
        sentences = self._sentence_cache.get(resolved, [])
        if not sentences:
            return
        blocks: list[str] = []
        for idx, sent in enumerate(sentences, start=1):
            text = str(sent.get("text", "") or "")
            toks = list(sent.get("tokens", []) or [])
            blocks.append(self._tokens_to_conllu_text(idx, text, toks))
        try:
            treebank_path.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
        except Exception:
            pass

    def _retrivis_edit_cache_file(self, treebank_path: Path) -> Path:
        digest = self._path_digest(treebank_path)
        return self._retrivis_edit_cache_dir / f"{treebank_path.stem}.{digest}.conllu"

    def _persist_retrivis_edit_cache(self, treebank_path: Path) -> None:
        try:
            if treebank_path.name.lower() == "example.conllu":
                return
            key = str(treebank_path.resolve())
        except Exception:
            return
        sentences = self._sentence_cache.get(key, [])
        if not sentences:
            return
        blocks: list[str] = []
        for idx, sent in enumerate(sentences, start=1):
            text = str(sent.get("text", "") or "")
            toks = list(sent.get("tokens", []) or [])
            blocks.append(self._tokens_to_conllu_text(idx, text, toks))
        try:
            out_path = self._retrivis_edit_cache_file(treebank_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
        except Exception:
            pass

    def _on_graph_title_changed(self, title: str) -> None:
        raw = str(title or "")
        if not raw.startswith("QS_RETRI_EDIT:"):
            return
        # Robust path: title acts as event trigger, actual payload is read from JS state.
        marker = raw[len("QS_RETRI_EDIT:") :].strip()
        if self.graph_web is not None:
            try:
                page = self.graph_web.page()
                if page is not None and (marker.isdigit() or marker.lower() in {"sync", "edit"}):
                    page.runJavaScript(
                        "(function(){ try { return (window.__qsRetriState && window.__qsRetriState.tokens) || []; } "
                        "catch(e) { return []; } })();",
                        self._on_graph_edit_tokens_from_js,
                    )
                    return
            except Exception:
                pass
        # Legacy fallback (old html payload encoded in title).
        enc = raw[len("QS_RETRI_EDIT:") :]
        try:
            decoded = urllib.parse.unquote(enc)
            edited = json.loads(decoded)
        except Exception:
            return
        self._apply_graph_edit_tokens(edited)

    def _on_graph_edit_tokens_from_js(self, edited: object) -> None:
        self._apply_graph_edit_tokens(edited)

    def _apply_graph_edit_tokens(self, edited: object) -> None:
        active = self._active_result_list()
        item = active.currentItem()
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return
        tokens = self._norm_edit_tokens(edited)
        if not tokens:
            return
        sent = payload.get("sentence")
        if not isinstance(sent, dict):
            return
        sent["tokens"] = tokens
        sent["text"] = " ".join(str(t.get("form", "_")) for t in tokens)
        payload["sentence"] = sent
        item.setData(Qt.ItemDataRole.UserRole, payload)
        tb = payload.get("path")
        sidx = int(payload.get("sent_idx", 0) or 0)
        if isinstance(tb, Path) and sidx > 0:
            key = str(tb.resolve())
            sents = self._sentence_cache.get(key, [])
            if sidx <= len(sents):
                sents[sidx - 1]["tokens"] = tokens
                sents[sidx - 1]["text"] = str(sent.get("text", ""))
            for row in self._matched_sentences:
                try:
                    row_tb = row.get("path")
                    row_idx = int(row.get("sent_idx", 0) or 0)
                    if isinstance(row_tb, Path) and str(row_tb.resolve()) == key and row_idx == sidx:
                        row_sent = row.get("sentence")
                        if isinstance(row_sent, dict):
                            row_sent["tokens"] = tokens
                            row_sent["text"] = str(sent.get("text", ""))
                except Exception:
                    continue
            self._persist_retrivis_edit_cache(tb)
            self._persist_cached_treebank_if_needed(tb)
            self._refresh_save_mode_options()
        self.status_label.setText("Sentence edited and cached.")
        self._on_result_clicked()

    def _export_graph_image_dialog(self) -> None:
        if self.graph_web is None:
            return
        options = self._prompt_export_options()
        if options is None:
            return
        fmt, dpi = options
        filters = {
            "png": "PNG Image (*.png)",
            "jpg": "JPEG Image (*.jpg *.jpeg)",
            "bmp": "BMP Image (*.bmp)",
            "webp": "WEBP Image (*.webp)",
            "svg": "SVG Image (*.svg)",
            "pdf": "PDF Document (*.pdf)",
            "eps": "EPS Image (*.eps)",
        }
        out_path, _selected_filter = _themed_get_save_file_name(
            self,
            "Export visualization",
            "",
            filters[fmt],
        )
        if not out_path:
            return
        out_file = Path(out_path)
        suffix_map = {"png": ".png", "jpg": ".jpg", "bmp": ".bmp", "webp": ".webp", "svg": ".svg", "pdf": ".pdf", "eps": ".eps"}
        if out_file.suffix.lower() != suffix_map[fmt]:
            out_file = out_file.with_suffix(suffix_map[fmt])
        out_ext = out_file.suffix.lower()
        svg_export_markup = self._build_export_svg_markup()
        if not svg_export_markup:
            _show_warning_dialog(self, "Export failed", "No dependency tree available to export.")
            return
        if out_ext == ".svg":
            out_file.write_text(svg_export_markup, encoding="utf-8")
            self.message.emit(f"Exported visualization: {out_file}")
            return
        if out_ext == ".pdf":
            if not self._export_svg_to_pdf(out_file, svg_export_markup):
                _show_warning_dialog(self, "Export failed", "PDF export requires Qt SVG support.")
                return
            self.message.emit(f"Exported visualization: {out_file}")
            return
        if out_ext == ".eps":
            try:
                import cairosvg  # type: ignore

                cairosvg.svg2eps(bytestring=svg_export_markup.encode("utf-8"), write_to=str(out_file))
                self.message.emit(f"Exported visualization: {out_file}")
                return
            except Exception:
                _show_warning_dialog(self, "Export failed", "EPS export requires cairosvg.")
                return
        raster_fmt_map = {".png": "PNG", ".jpg": "JPG", ".jpeg": "JPG", ".bmp": "BMP", ".webp": "WEBP"}
        raster_fmt = raster_fmt_map.get(out_file.suffix.lower(), "PNG")
        if not self._export_svg_to_raster(out_file, raster_fmt, dpi if dpi is not None else 300, svg_export_markup):
            _show_warning_dialog(self, "Export failed", "Raster export failed.")
            return
        self.message.emit(f"Exported visualization: {out_file}")

    def _build_export_svg_markup(self) -> str:
        if not self._last_svg_markup:
            return ""
        try:
            root = ET.fromstring(self._last_svg_markup)
        except Exception:
            return self._last_svg_markup
        # Force white export background.
        svg_tag = str(root.tag)
        ns_prefix = ""
        if svg_tag.startswith("{") and "}" in svg_tag:
            ns_prefix = svg_tag.split("}", 1)[0] + "}"
        rect_tag = f"{ns_prefix}rect"
        bg_rect = ET.Element(rect_tag, {"x": "0", "y": "0", "width": "100%", "height": "100%", "fill": "#ffffff"})
        root.insert(0, bg_rect)
        for elem in root.iter():
            tag = str(elem.tag).lower()
            if not tag.endswith("text"):
                continue
            fill = elem.attrib.get("fill", "")
            dark = self._darken_light_hex(fill)
            if dark is not None:
                elem.set("fill", dark)
        # Export compatibility: replace context-stroke marker with explicit color markers
        # so arrow color always matches each arc stroke in saved files.
        svg_tag = str(root.tag)
        ns_prefix = ""
        if svg_tag.startswith("{") and "}" in svg_tag:
            ns_prefix = svg_tag.split("}", 1)[0] + "}"
        defs_tag = f"{ns_prefix}defs"
        marker_tag = f"{ns_prefix}marker"
        path_tag = f"{ns_prefix}path"
        marker_template = None
        defs_elem = None
        for child in list(root):
            if str(child.tag) == defs_tag:
                defs_elem = child
                for d in list(child):
                    if str(d.tag) == marker_tag and d.attrib.get("id") == "arrowCtx":
                        marker_template = d
                        break
                break
        if defs_elem is not None and marker_template is not None:
            marker_by_color: dict[str, str] = {}
            next_idx = 0
            for elem in root.iter():
                tag = str(elem.tag).lower()
                if not (tag.endswith("path") or tag.endswith("line")):
                    continue
                marker_end = elem.attrib.get("marker-end", "")
                if "arrowCtx" not in marker_end:
                    continue
                stroke = (elem.attrib.get("stroke", "") or "").strip()
                if not stroke:
                    continue
                marker_id = marker_by_color.get(stroke)
                if marker_id is None:
                    marker_id = f"arrowExport{next_idx}"
                    next_idx += 1
                    marker_by_color[stroke] = marker_id
                    m_new = ET.Element(marker_tag, dict(marker_template.attrib))
                    m_new.set("id", marker_id)
                    for child in list(marker_template):
                        c_new = ET.Element(child.tag, dict(child.attrib))
                        if str(child.tag) == path_tag or str(child.tag).lower().endswith("path"):
                            c_new.set("fill", stroke)
                            c_new.set("stroke", stroke)
                            c_new.set("stroke-width", "1")
                        m_new.append(c_new)
                    defs_elem.append(m_new)
                elem.set("marker-end", f"url(#{marker_id})")
        try:
            return ET.tostring(root, encoding="unicode")
        except Exception:
            return self._last_svg_markup

    def _darken_light_hex(self, color: str) -> str | None:
        value = (color or "").strip()
        m = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
        if not m:
            return None
        hx = m.group(1)
        r = int(hx[0:2], 16)
        g = int(hx[2:4], 16)
        b = int(hx[4:6], 16)
        # Perceived luminance (sRGB approximation).
        lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        if lum < 0.58:
            return None
        return "#1f2937"

    def _prompt_export_options(self) -> tuple[str, int | None] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Options")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        fmt_combo = QComboBox()
        fmt_combo.addItem("PNG", "png")
        fmt_combo.addItem("JPEG", "jpg")
        fmt_combo.addItem("BMP", "bmp")
        fmt_combo.addItem("WEBP", "webp")
        fmt_combo.addItem("SVG", "svg")
        fmt_combo.addItem("PDF", "pdf")
        fmt_combo.addItem("EPS", "eps")

        dpi_spin = QSpinBox()
        dpi_spin.setRange(72, 1200)
        dpi_spin.setValue(300)
        self._setup_viz_spinbox(dpi_spin)
        dpi_label = QLabel("DPI (raster only)")
        form.addRow("Format", fmt_combo)
        form.addRow(dpi_label, dpi_spin)
        layout.addLayout(form)

        def _refresh_dpi_enabled() -> None:
            fmt = str(fmt_combo.currentData() or "png").lower()
            raster = fmt in {"png", "jpg", "bmp", "webp"}
            dpi_spin.setEnabled(raster)
            dpi_label.setEnabled(raster)

        fmt_combo.currentIndexChanged.connect(lambda _idx: _refresh_dpi_enabled())
        _refresh_dpi_enabled()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        fmt = str(fmt_combo.currentData() or "png").lower()
        if fmt in {"png", "jpg", "bmp", "webp"}:
            return fmt, int(dpi_spin.value())
        return fmt, None

    def _build_svg_renderer(self, svg_markup: str | None = None):
        markup = svg_markup if svg_markup is not None else self._last_svg_markup
        if QSvgRenderer is None or not markup:
            return None
        data = QByteArray(markup.encode("utf-8"))
        renderer = QSvgRenderer(data)
        if not renderer.isValid():
            return None
        return renderer

    def _export_svg_to_raster(self, out_file: Path, fmt: str, dpi: int = 300, svg_markup: str | None = None) -> bool:
        markup = svg_markup if svg_markup is not None else self._last_svg_markup
        if markup:
            try:
                import cairosvg  # type: ignore

                png_bytes = cairosvg.svg2png(bytestring=markup.encode("utf-8"), dpi=float(dpi))
                if fmt == "PNG":
                    out_file.write_bytes(png_bytes)
                    return True
                image = QImage()
                if not image.loadFromData(png_bytes, "PNG"):
                    return False
                return image.save(str(out_file), fmt)
            except Exception:
                pass
        renderer = self._build_svg_renderer(markup)
        if renderer is None:
            return False
        size = renderer.defaultSize()
        scale = max(0.1, float(dpi) / 96.0)
        width = max(1, int(size.width() * scale))
        height = max(1, int(size.height() * scale))
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        return image.save(str(out_file), fmt)

    def _export_svg_to_pdf(self, out_file: Path, svg_markup: str | None = None) -> bool:
        markup = svg_markup if svg_markup is not None else self._last_svg_markup
        if markup:
            try:
                import cairosvg  # type: ignore

                cairosvg.svg2pdf(bytestring=markup.encode("utf-8"), write_to=str(out_file))
                return out_file.exists()
            except Exception:
                pass
        renderer = self._build_svg_renderer(markup)
        if renderer is None:
            return False
        writer = QPdfWriter(str(out_file))
        writer.setResolution(96)
        try:
            writer.setPageMargins(0, 0, 0, 0)
        except Exception:
            pass
        painter = QPainter(writer)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        return out_file.exists()

    def _selected_convert_sources(self) -> list[Path]:
        selected_data = self.convert_treebank_combo.currentData()
        selected_name = self.convert_treebank_combo.currentText().strip().lower()
        if selected_data == "__all__" or not selected_name or selected_name == "all":
            return self._imported_treebanks.copy()
        if isinstance(selected_data, str):
            for tb in self._imported_treebanks:
                if str(tb) == selected_data:
                    return [tb]
        for tb in self._imported_treebanks:
            if tb.stem.lower() == selected_name:
                return [tb]
        return self._imported_treebanks.copy()

    def _source_format_compatible(self, src: Path, src_fmt: str) -> bool:
        ext = src.suffix.lstrip(".").lower()
        if ext == src_fmt:
            return True
        # PMT corpora are often stored as plain .txt files.
        if src_fmt == "pmt" and ext == "txt":
            return True
        return False

    def _get_depval_converter_cls(self):
        if self._depval_converter_cls is not None:
            return self._depval_converter_cls
        from quansyn.depval import Converter

        self._depval_converter_cls = Converter
        return self._depval_converter_cls

    def _path_digest(self, path: Path) -> str:
        return hashlib.md5(str(path.resolve()).encode("utf-8")).hexdigest()[:8]

    def _load_conllu_sentences_for_convert(self, src: Path, src_fmt: str) -> list:
        converter_cls = self._get_depval_converter_cls()
        if src_fmt == "conllu":
            if conllu_parse_incr is None:
                raise RuntimeError("conllu backend unavailable. Please install conllu.")
            with src.open("r", encoding="utf-8", errors="ignore") as fp:
                sents = list(conllu_parse_incr(fp))
            out: list = []
            for sent in sents:
                sent_rows: list[dict[str, object]] = []
                for word in sent:
                    row = dict(word)
                    row.setdefault("lemma", "_")
                    row.setdefault("upos", "_")
                    row.setdefault("xpos", "_")
                    row.setdefault("feats", "_")
                    row.setdefault("deps", "_")
                    row.setdefault("misc", "_")
                    sent_rows.append(row)
                out.append(sent_rows)
            return out
        with src.open("r", encoding="utf-8", errors="ignore") as fp:
            converter = converter_cls(fp)
            if hasattr(converter, "style2style"):
                return converter.style2style(src_fmt, "conllu")
            if hasattr(converter, "to_conllu"):
                return converter.to_conllu(src_fmt)
            raise RuntimeError("quansyn Converter API is incompatible: missing style2style/to_conllu")

    def _convert_from_conllu(self, conllu_sents: list, dst_fmt: str):
        if dst_fmt == "conllu":
            return conllu_sents
        converter_cls = self._get_depval_converter_cls()
        converter = converter_cls(None)
        if hasattr(converter, "to_others"):
            try:
                return converter.to_others(dst_fmt, cache=conllu_sents)
            except TypeError:
                return converter.to_others(dst_fmt)
        raise RuntimeError("quansyn Converter API is incompatible: missing to_others")

    def _save_with_depval_converter(self, treebank_obj, style: str, out_file: Path) -> None:
        converter_cls = self._get_depval_converter_cls()
        converter = converter_cls(None)
        if not hasattr(converter, "save"):
            raise RuntimeError("quansyn Converter API is incompatible: missing save")
        try:
            converter.save(treebank_obj, style, str(out_file))
            return
        except TypeError:
            pass
        try:
            converter.save(treebank=treebank_obj, style=style, file_path=str(out_file))
            return
        except TypeError as exc:
            raise RuntimeError(f"quansyn Converter.save signature mismatch: {exc}") from exc

    def convert_treebanks_to_cache(self) -> None:
        if self._convert_thread is not None and self._convert_thread.is_alive():
            self.message.emit("Convert is already running in background.")
            return
        files = self._selected_convert_sources()
        if not files:
            self.message.emit("Convert skipped: no treebank selected.")
            return
        src_fmt = self.convert_source_fmt_combo.currentText().strip().lower()
        dst_fmt = self.convert_target_fmt_combo.currentText().strip().lower()
        if src_fmt == dst_fmt:
            self.message.emit("Convert skipped: input and output formats are identical.")
            return
        self.convert_run_btn.setEnabled(False)
        self.message.emit("Convert running in background...")

        def _worker() -> None:
            try:
                self._convert_cache_dir.mkdir(parents=True, exist_ok=True)
                converted = 0
                skipped = 0
                updated: dict[str, str] = {}
                for src in files:
                    if not src.exists():
                        skipped += 1
                        continue
                    if not self._source_format_compatible(src, src_fmt):
                        skipped += 1
                        continue
                    try:
                        conllu_sents = self._load_conllu_sentences_for_convert(src, src_fmt)
                        converted_obj = self._convert_from_conllu(conllu_sents, dst_fmt)
                        out_file = self._convert_cache_dir / f"{src.stem}.{self._path_digest(src)}.{dst_fmt}"
                        self._save_with_depval_converter(converted_obj, dst_fmt, out_file)
                        updated[str(src.resolve())] = str(out_file)
                        converted += 1
                    except Exception:
                        skipped += 1
                self._convert_done.emit({"converted": converted, "skipped": skipped, "updated": updated})
            except Exception as exc:
                self._convert_failed.emit(str(exc))

        self._convert_thread = threading.Thread(target=_worker, daemon=True)
        self._convert_thread.start()

    def _on_convert_done(self, payload: object) -> None:
        self.convert_run_btn.setEnabled(True)
        self._convert_thread = None
        if not isinstance(payload, dict):
            self._on_convert_failed("invalid payload")
            return
        updated = payload.get("updated", {})
        if isinstance(updated, dict):
            self._converted_treebank_cache.update(updated)  # type: ignore[arg-type]
        converted = int(payload.get("converted", 0) or 0)
        skipped = int(payload.get("skipped", 0) or 0)
        self._sentence_cache.clear()
        self._refresh_viz_source_options()
        self.message.emit(f"Convert completed: converted={converted}, skipped={skipped}.")
        self.status_label.setText(
            f"Convert done. Cached {converted} treebank(s), skipped {skipped}. Visualization not refreshed."
        )

    def _on_convert_failed(self, text: str) -> None:
        self.convert_run_btn.setEnabled(True)
        self._convert_thread = None
        self.message.emit(f"Convert failed: {text}")

    def _parse_cache_key(self, backend: str, lang: str, model_name: str) -> str:
        return f"{backend}:{lang}:{model_name}"

    def _parse_stanza_lang_dir(self, lang: str) -> str:
        raw = str(lang or "").strip().lower()
        return "zh-hans" if raw in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw

    def _parse_collect_spacy_models(self, lang: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        try:
            base = self._spacy_root / str(lang).strip().lower()
            if base.exists():
                for p in sorted(base.iterdir()):
                    if p.is_dir():
                        name = str(p.name).strip()
                        if name and ("trf" not in name.lower()) and name not in seen:
                            seen.add(name)
                            out.append(name)
        except Exception:
            pass
        try:
            prefix = f"{str(lang).strip().lower()}_"
            for name in sorted(_spacy_installed_models()):
                s = str(name).strip()
                if s.startswith(prefix) and ("trf" not in s.lower()) and s not in seen:
                    seen.add(s)
                    out.append(s)
        except Exception:
            pass
        return out

    def _open_parse_model_manager(self) -> None:
        dlg = SpacyModelManagerDialog(self, self._spacy_root)
        dlg.modelsInstalled.connect(self._on_parse_models_changed)
        dlg.exec()

    def _parse_collect_stanza_models(self, lang: str) -> list[str]:
        out: set[str] = set()
        try:
            lang_dir = self._stanza_root / self._parse_stanza_lang_dir(lang)
            tok_dir = lang_dir / "tokenize"
            if tok_dir.exists():
                for p in tok_dir.glob("*.pt"):
                    stem = p.stem.strip()
                    if stem:
                        out.add(stem)
        except Exception:
            pass
        return sorted(out)

    def _parse_collect_spacy_languages(self) -> list[str]:
        langs: set[str] = {"en", "zh"}
        try:
            for name in _spacy_installed_models():
                s = str(name).strip().lower()
                if "_" in s:
                    langs.add(s.split("_", 1)[0])
        except Exception:
            pass
        try:
            if self._spacy_root.exists():
                for p in self._spacy_root.iterdir():
                    if p.is_dir():
                        lang = p.name.strip().lower()
                        if lang:
                            langs.add(lang)
        except Exception:
            pass
        return sorted(langs)

    def _parse_collect_stanza_languages(self) -> list[str]:
        langs: set[str] = {"en", "zh"}
        try:
            if self._stanza_root.exists():
                for p in self._stanza_root.iterdir():
                    if p.is_dir():
                        lang = p.name.strip().lower()
                        if lang:
                            langs.add(lang)
        except Exception:
            pass
        return sorted(langs)

    def _refresh_parse_language_options(self) -> None:
        backend = self.parse_backend_combo.currentText().strip().lower()
        current = self.parse_lang_combo.currentText().strip().lower()
        langs = self._parse_collect_spacy_languages() if backend == "spacy" else self._parse_collect_stanza_languages()
        self.parse_lang_combo.blockSignals(True)
        self.parse_lang_combo.clear()
        self.parse_lang_combo.addItems(langs)
        if current and current in langs:
            self.parse_lang_combo.setCurrentText(current)
        elif "en" in langs:
            self.parse_lang_combo.setCurrentText("en")
        elif langs:
            self.parse_lang_combo.setCurrentIndex(0)
        self.parse_lang_combo.blockSignals(False)

    def _on_parse_backend_changed(self, _value: str | None = None) -> None:
        self._refresh_parse_language_options()
        self._refresh_parse_model_options()

    def _on_parse_models_changed(self) -> None:
        self._refresh_parse_language_options()
        self._refresh_parse_model_options()

    def _refresh_parse_model_options(self, _value: str | None = None) -> None:
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        if backend == "spacy":
            options = self._parse_collect_spacy_models(lang)
            presets = {
                "en": ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"],
                "zh": ["zh_core_web_sm", "zh_core_web_md"],
            }
            options.extend(presets.get(lang, []))
            default_model = {"en": "en_core_web_sm", "zh": "zh_core_web_sm"}.get(lang, "")
        else:
            options = self._parse_collect_stanza_models(lang)
            if lang == "en":
                options.extend(["combined"])
            elif lang == "zh":
                options.extend(["gsdsimp"])
            default_model = {"en": "combined", "zh": "gsdsimp"}.get(lang, "")
        uniq: list[str] = []
        seen: set[str] = set()
        for x in options:
            sx = str(x or "").strip()
            if not sx or sx in seen:
                continue
            seen.add(sx)
            uniq.append(sx)
        cur = self.parse_model_combo.currentText().strip()
        if "trf" in cur.lower():
            cur = ""
        self.parse_model_combo.blockSignals(True)
        self.parse_model_combo.clear()
        if uniq:
            self.parse_model_combo.addItems(uniq)
        chosen = cur if cur else default_model
        if (not chosen) and uniq:
            chosen = uniq[0]
        self.parse_model_combo.setCurrentText(chosen)
        self.parse_model_combo.blockSignals(False)

    def _load_parse_pipeline(self, backend: str, lang: str, model_name: str):
        key = self._parse_cache_key(backend, lang, model_name)
        if key in self._parse_pipeline_cache:
            return self._parse_pipeline_cache[key]
        if backend == "spacy":
            spacy_mod = _ensure_spacy()
            if spacy_mod is None:
                reason = str(_spacy_import_error or "").strip()
                raise RuntimeError(
                    "spaCy runtime is unavailable. Install or import Parser Runtime first."
                    + (f"\nReason: {reason}" if reason else "")
                )
            lang_l = str(lang or "").strip().lower()
            model_l = str(model_name or "").strip().lower()
            if lang_l.startswith("zh") or model_l.startswith("zh_"):
                ok, reason = _ensure_spacy_zh_runtime()
                if not ok:
                    raise RuntimeError(reason or "Chinese spaCy runtime is unavailable (spacy_pkuseg).")
            local_model_dir = self._spacy_root / lang / model_name
            if local_model_dir.exists():
                resolved_dir = SyntaxPage._find_spacy_model_dir(local_model_dir)
                if resolved_dir is None:
                    raise RuntimeError(f"spaCy local model is missing config.cfg: {local_model_dir}")
                nlp = spacy_mod.load(str(resolved_dir))
            else:
                nlp = spacy_mod.load(model_name)
            self._parse_pipeline_cache[key] = nlp
            return nlp
        if backend == "stanza":
            st_mod = _ensure_stanza()
            if st_mod is None:
                reason = str(_stanza_import_error or "").strip()
                if reason:
                    raise RuntimeError(f"stanza is unavailable: {reason}")
                raise RuntimeError("stanza is unavailable. Please install stanza.")
            raw_lang = lang.strip().lower()
            stanza_lang = "zh-hans" if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw_lang
            package = model_name.strip().lower()
            if raw_lang == "en" and package in {"", "en", "default"}:
                package = "combined"
            if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} and package in {"", "zh", "zh-hans", "default"}:
                package = "gsdsimp"
            kwargs = {
                "lang": stanza_lang,
                "processors": "tokenize,pos,lemma,depparse",
                "verbose": False,
                "dir": str(self._stanza_root),
            }
            if package:
                kwargs["package"] = package
            nlp = st_mod.Pipeline(**kwargs)
            self._parse_pipeline_cache[key] = nlp
            return nlp
        raise RuntimeError(f"Unsupported backend: {backend}")

    def _load_parse_txt_sources(self, paths: list[Path]) -> None:
        sources = [p for p in paths if p.exists() and p.is_file()]
        self._parse_txt_sources = sources
        self._parse_clean_by_source = {}
        self._parse_conllu_by_source = {}
        self._parse_conllu_by_source = {}
        self.parse_txt_select_combo.blockSignals(True)
        self.parse_txt_select_combo.clear()
        self.parse_txt_select_combo.addItem("all", "__all__")
        for p in sources:
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw = ""
            sents = SyntaxPage._split_to_sentences(raw)
            self._parse_clean_by_source[str(p.resolve())] = list(sents)
            self.parse_txt_select_combo.addItem(p.name, str(p.resolve()))
        self.parse_txt_select_combo.blockSignals(False)
        total = sum(len(v) for v in self._parse_clean_by_source.values())
        self.message.emit(f"Import ready: {len(sources)} txt file(s), {total} sentence(s).")

    def _start_parse_txt_import(self, merged_paths: list[Path]) -> None:
        if self._txt_import_thread is not None and self._txt_import_thread.is_alive():
            self.message.emit("TXT import is already running in background.")
            return
        self._txt_import_token += 1
        token = self._txt_import_token
        sources = [p for p in merged_paths if p.exists() and p.is_file()]
        self.status_label.setText(f"TXT import running: 0/{len(sources)}")
        self.message.emit(f"TXT import running in background ({len(sources)} file(s))...")

        def _worker() -> None:
            try:
                clean_by_source: dict[str, list[str]] = {}
                total = len(sources)
                for i, p in enumerate(sources, start=1):
                    try:
                        raw = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        raw = ""
                    sents = SyntaxPage._split_to_sentences(raw)
                    clean_by_source[str(p.resolve())] = list(sents)
                    self._txt_import_progress.emit(f"TXT import {i}/{total}: {p.name}")
                self._txt_import_done.emit(
                    {"token": token, "sources": [str(p.resolve()) for p in sources], "clean_by_source": clean_by_source}
                )
            except Exception as exc:
                self._txt_import_failed.emit(str(exc))

        self._txt_import_thread = threading.Thread(target=_worker, daemon=True)
        self._txt_import_thread.start()

    def _on_txt_import_progress(self, text: str) -> None:
        self.status_label.setText(text)
        self.message.emit(text)

    def _on_txt_import_done(self, payload: object) -> None:
        self._txt_import_thread = None
        if not isinstance(payload, dict):
            self._on_txt_import_failed("invalid payload")
            return
        token = int(payload.get("token", -1))
        if token != self._txt_import_token:
            return
        source_paths = payload.get("sources", [])
        clean_by_source = payload.get("clean_by_source", {})
        if not isinstance(source_paths, list) or not isinstance(clean_by_source, dict):
            self._on_txt_import_failed("invalid payload")
            return
        self._parse_txt_sources = [Path(x) for x in source_paths if Path(x).exists()]
        self._parse_clean_by_source = {
            str(Path(k).resolve()): list(v) for k, v in clean_by_source.items() if isinstance(v, list)
        }
        self._parse_conllu_by_source = {}
        self.parse_txt_select_combo.blockSignals(True)
        self.parse_txt_select_combo.clear()
        self.parse_txt_select_combo.addItem("all", "__all__")
        for p in self._parse_txt_sources:
            self.parse_txt_select_combo.addItem(p.name, str(p.resolve()))
        self.parse_txt_select_combo.blockSignals(False)
        total = sum(len(v) for v in self._parse_clean_by_source.values())
        self.status_label.setText(f"TXT import done: {len(self._parse_txt_sources)} file(s), {total} sentence(s).")
        self.message.emit(f"Import ready: {len(self._parse_txt_sources)} txt file(s), {total} sentence(s).")

    def _on_txt_import_failed(self, text: str) -> None:
        self._txt_import_thread = None
        self.status_label.setText(f"TXT import failed: {text}")
        self.message.emit(f"TXT import failed: {text}")

    def _on_parse_import_txt_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Import TXT File(s)", "", "Text Files (*.txt)")
        if not files:
            return
        old = {str(p.resolve()) for p in self._parse_txt_sources}
        merged = list(self._parse_txt_sources)
        for fp in files:
            p = Path(fp)
            if str(p.resolve()) not in old:
                merged.append(p)
        self._start_parse_txt_import(merged)

    def _on_parse_import_txt_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Import TXT Folder", "")
        if not folder:
            return
        base = Path(folder)
        files = sorted([p for p in base.glob("*.txt") if p.is_file()])
        if not files:
            _show_info_dialog(self, "Parse", "No txt files found in selected folder.")
            return
        old = {str(p.resolve()) for p in self._parse_txt_sources}
        merged = list(self._parse_txt_sources)
        for p in files:
            if str(p.resolve()) not in old:
                merged.append(p)
        self._start_parse_txt_import(merged)

    def _selected_parse_sentences(self) -> list[tuple[str, str]]:
        selected = self.parse_txt_select_combo.currentData()
        out: list[tuple[str, str]] = []
        if selected in (None, "__all__"):
            for src, sents in self._parse_clean_by_source.items():
                for s in sents:
                    out.append((src, s))
        else:
            src = str(selected)
            for s in self._parse_clean_by_source.get(src, []):
                out.append((src, s))
        return out

    def _on_parse_load_clicked(self) -> None:
        if self._parse_load_thread is not None and self._parse_load_thread.is_alive():
            self.status_label.setText("Parse model loading in background...")
            return
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        model = self.parse_model_combo.currentText().strip()
        if not model:
            _show_warning_dialog(self, "Parse", "Model name is required.")
            return
        self.parse_load_btn.setEnabled(False)
        self.status_label.setText("Loading parse model in background...")

        def _worker() -> None:
            try:
                self._load_parse_pipeline(backend, lang, model)
                self._parse_load_done.emit({"backend": backend, "lang": lang, "model": model})
            except Exception as exc:
                self._parse_load_failed.emit(str(exc))

        self._parse_load_thread = threading.Thread(target=_worker, daemon=True)
        self._parse_load_thread.start()

    def _on_parse_load_done(self, payload: object) -> None:
        self._parse_load_thread = None
        self.parse_load_btn.setEnabled(True)
        if not isinstance(payload, dict):
            self._on_parse_load_failed("invalid payload")
            return
        backend = str(payload.get("backend", ""))
        lang = str(payload.get("lang", ""))
        model = str(payload.get("model", ""))
        self.message.emit(f"Parse model loaded: {backend}/{lang}/{model}")
        self.status_label.setText(f"Parse model loaded: {backend}/{lang}/{model}")

    def _on_parse_load_failed(self, text: str) -> None:
        self._parse_load_thread = None
        self.parse_load_btn.setEnabled(True)
        _show_warning_dialog(self, "Parse", str(text))
        self.message.emit(f"Parse model load failed: {text}")
        self.status_label.setText(f"Parse model load failed: {text}")

    def _on_parse_run_clicked(self) -> None:
        if self._parse_running:
            self.message.emit("Parse is already running in background.")
            return
        if not self._parse_clean_by_source:
            _show_warning_dialog(self, "Parse", "No txt sources imported.")
            return
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        model = self.parse_model_combo.currentText().strip()
        if not model:
            _show_warning_dialog(self, "Parse", "Model name is required.")
            return
        selected_data = self.parse_txt_select_combo.currentData()
        if selected_data in (None, "__all__"):
            selected_sources = [str(p.resolve()) for p in self._parse_txt_sources]
        else:
            selected_sources = [str(Path(str(selected_data)).resolve())]
        if not selected_sources:
            _show_warning_dialog(self, "Parse", "No txt sources selected.")
            return
        selected = self._selected_parse_sentences()
        if not selected:
            _show_warning_dialog(self, "Parse", "Input text is empty.")
            return
        self._parse_running = True
        self.parse_run_btn.setEnabled(False)
        self.parse_load_btn.setEnabled(False)
        total_items = len(selected)
        self.message.emit(f"Parsing started: 0/{total_items} (0%)")
        self.status_label.setText(f"Parsing started: 0/{total_items} (0%)")

        def _worker() -> None:
            try:
                nlp = self._load_parse_pipeline(backend, lang, model)
                # Always clean source txt again before parse: one clean sentence per line.
                clean_by_source: dict[str, list[str]] = {}
                for src in selected_sources:
                    src_path = Path(src)
                    try:
                        raw = src_path.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        raw = ""
                    clean_by_source[src] = list(SyntaxPage._split_to_sentences(raw))
                selected_clean: list[tuple[str, str]] = []
                for src in selected_sources:
                    for s in clean_by_source.get(src, []):
                        selected_clean.append((src, s))
                if not selected_clean:
                    raise RuntimeError("No cleaned sentence available after preprocessing.")

                chunks: list[str] = []
                chunks_by_source: dict[str, list[str]] = {}
                total_clean = len(selected_clean)
                for idx, (src_path, s) in enumerate(selected_clean, start=1):
                    txt = str(s or "").strip()
                    if not txt:
                        continue
                    src_name = Path(str(src_path)).name or str(src_path)
                    pct = int((idx / max(1, total_clean)) * 100)
                    self.message.emit(f"Parsing {idx}/{total_clean} ({pct}%) - {src_name}")
                    if backend == "spacy":
                        conllu_block = SyntaxPage._to_conllu_from_spacy(nlp, txt)
                    else:
                        conllu_block = SyntaxPage._to_conllu_from_stanza(nlp, txt)
                    chunks.append(conllu_block)
                    chunks_by_source.setdefault(str(Path(str(src_path)).resolve()), []).append(conllu_block)
                conllu = ("\n\n".join(c for c in chunks if c.strip())).strip()
                conllu_by_source = {
                    src: ("\n\n".join(c for c in blocks if str(c).strip())).strip()
                    for src, blocks in chunks_by_source.items()
                }
                self._parse_done.emit(
                    {
                        "conllu": conllu,
                        "count": len(chunks),
                        "conllu_by_source": conllu_by_source,
                        "clean_by_source": clean_by_source,
                    }
                )
            except Exception as exc:
                self._parse_failed.emit(str(exc))

        self._parse_thread = threading.Thread(target=_worker, daemon=True)
        self._parse_thread.start()

    def _on_parse_done(self, payload: object) -> None:
        self._parse_running = False
        self._parse_thread = None
        self.parse_run_btn.setEnabled(True)
        self.parse_load_btn.setEnabled(True)
        if not isinstance(payload, dict):
            self._on_parse_failed("invalid payload")
            return
        conllu = str(payload.get("conllu", "") or "")
        count = int(payload.get("count", 0) or 0)
        raw_by_source = payload.get("conllu_by_source", {})
        clean_by_source = payload.get("clean_by_source", {})
        if isinstance(raw_by_source, dict):
            self._parse_conllu_by_source = {
                str(Path(str(k)).resolve()): str(v or "")
                for k, v in raw_by_source.items()
                if str(v or "").strip()
            }
        else:
            self._parse_conllu_by_source = {}
        if isinstance(clean_by_source, dict):
            self._parse_clean_by_source = {
                str(Path(str(k)).resolve()): list(v)
                for k, v in clean_by_source.items()
                if isinstance(v, list)
            }
        self._parse_conllu_output = conllu
        try:
            self._parser_cache_dir.mkdir(parents=True, exist_ok=True)
            self._parser_cache_file.write_text(conllu, encoding="utf-8")
            by_src_dir = self._parser_cache_dir / "by_source"
            by_src_dir.mkdir(parents=True, exist_ok=True)
            for old in by_src_dir.glob("*.conllu"):
                try:
                    old.unlink()
                except Exception:
                    pass
            used_names: dict[str, int] = {}
            for src_key, content in self._parse_conllu_by_source.items():
                if not content:
                    continue
                src_path = Path(src_key)
                base = src_path.stem or "parsed"
                idx = used_names.get(base, 0)
                used_names[base] = idx + 1
                suffix = "" if idx == 0 else f"_{idx+1}"
                out_file = by_src_dir / f"{base}{suffix}.conllu"
                out_file.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")
        except Exception:
            pass
        self._refresh_viz_source_options()
        self.message.emit(f"Parse done: {count} sentence(s).")
        self.status_label.setText(f"Parse done: {count} sentence(s). Cached.")

    def _on_parse_failed(self, text: str) -> None:
        self._parse_running = False
        self._parse_thread = None
        self.parse_run_btn.setEnabled(True)
        self.parse_load_btn.setEnabled(True)
        self.status_label.setText(f"Parse failed: {text}")
        self.message.emit(f"Parse failed: {text}")
        _show_warning_dialog(self, "Parse failed", text)

    def _save_parsed_conllu_dialog(self) -> None:
        parsed_by_source = {k: v for k, v in self._parse_conllu_by_source.items() if str(v or "").strip()}
        if len(parsed_by_source) > 1:
            base_dir = _themed_get_existing_directory(self, "Save parsed CoNLL-U", str(_runtime_base_dir()))
            if not base_dir:
                return
            parsed_dir = Path(base_dir) / "parsed"
            parsed_dir.mkdir(parents=True, exist_ok=True)
            saved = 0
            for src_key, content in parsed_by_source.items():
                src = Path(src_key)
                out_file = parsed_dir / f"{src.stem}.conllu"
                idx = 1
                while out_file.exists():
                    out_file = parsed_dir / f"{src.stem}_{idx}.conllu"
                    idx += 1
                out_file.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")
                saved += 1
            self.message.emit(f"Saved parsed CoNLL-U: {saved} file(s) -> {parsed_dir}")
            return

        content = ""
        if parsed_by_source:
            content = next(iter(parsed_by_source.values()), "").strip()
        if not content:
            content = self._parse_conllu_output.strip()
        if not content and self._parser_cache_file.exists():
            try:
                content = self._parser_cache_file.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                content = ""
        if not content:
            _show_info_dialog(self, "No parsed cache", "No parsed CoNLL-U found in cache.")
            return
        default_name = "parsed.conllu"
        if parsed_by_source:
            default_name = f"{Path(next(iter(parsed_by_source.keys()))).stem}.conllu"
        out, _ = _themed_get_save_file_name(self, "Save parsed CoNLL-U", default_name, "CoNLL-U (*.conllu);;Text (*.txt)")
        if not out:
            return
        path = Path(out)
        try:
            path.write_text(content + "\n", encoding="utf-8")
            self.message.emit(f"Saved parsed CoNLL-U: {path}")
        except Exception as exc:
            _show_warning_dialog(self, "Save failed", str(exc))

    def save_cached_content_dialog(self) -> None:
        mode = str(self.convert_save_mode_combo.currentText() or "converted").strip().lower()
        if mode == "parsed":
            self._save_parsed_conllu_dialog()
            return
        if mode == "edited":
            self._save_edited_treebanks_dialog()
            return
        self.save_cached_treebanks_dialog()

    def _save_edited_treebanks_dialog(self) -> None:
        entries = self._edited_source_entries()
        if not entries:
            _show_info_dialog(self, "No edited cache", "No edited treebanks found in cache.")
            return
        out_root = _themed_get_existing_directory(self, "Save edited treebanks")
        if not out_root:
            return
        out_dir = Path(out_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for label, edited_path in entries:
            if not edited_path.exists():
                continue
            target = out_dir / f"{label}.conllu"
            idx = 1
            while target.exists():
                target = out_dir / f"{label}_{idx}.conllu"
                idx += 1
            try:
                shutil.copy2(edited_path, target)
                saved += 1
            except Exception:
                continue
        if saved == 0:
            _show_info_dialog(self, "Nothing saved", "No edited cache file was saved.")
            return
        self.message.emit(f"Saved edited treebanks: {saved} -> {out_dir}")

    def save_cached_treebanks_dialog(self) -> None:
        if not self._converted_treebank_cache:
            _show_info_dialog(self, "No cache", "No adjusted treebanks found in cache.")
            return
        selected = self._selected_convert_sources()
        selected_keys = {str(p.resolve()) for p in selected}
        out_root = _themed_get_existing_directory(self, "Save cached treebanks")
        if not out_root:
            return
        out_dir = Path(out_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for src_key, cached_path in self._converted_treebank_cache.items():
            if src_key not in selected_keys:
                continue
            src_path = Path(src_key)
            cached = Path(cached_path)
            if not cached.exists():
                continue
            base_name = src_path.stem
            target = out_dir / f"{base_name}{cached.suffix}"
            idx = 1
            while target.exists():
                target = out_dir / f"{base_name}_{idx}{cached.suffix}"
                idx += 1
            shutil.copy2(cached, target)
            saved += 1
        if saved == 0:
            _show_info_dialog(self, "Nothing saved", "No cached treebanks matched current selection.")
            return
        self.message.emit(f"Saved cached treebanks: {saved} -> {out_dir}")

    def _parse_treebank_sentences(self, path: Path) -> list[dict[str, object]]:
        key = str(path.resolve())
        cached = self._sentence_cache.get(key)
        if cached is not None:
            return cached
        if conllu_parse_incr is None:
            self.status_label.setText("conllu backend unavailable. Please install conllu.")
            return []
        read_path = path
        try:
            edited = self._retrivis_edit_cache_file(path)
            if edited.exists():
                read_path = edited
        except Exception:
            read_path = path
        try:
            fp = read_path.open("r", encoding="utf-8", errors="ignore")
        except Exception:
            return []
        out: list[dict[str, object]] = []
        try:
            sentences = conllu_parse_incr(fp)
            for sent in sentences:
                tokens: list[dict[str, object]] = []
                for tok in sent:
                    tid = tok.get("id")
                    if not isinstance(tid, int):
                        continue
                    head = tok.get("head")
                    if not isinstance(head, int):
                        head = 0
                    deprel = tok.get("deprel")
                    if isinstance(deprel, str) and ":" in deprel:
                        deprel = deprel.split(":", 1)[0]
                    tokens.append(
                        {
                            "id": tid,
                            "form": str(tok.get("form", "_") or "_"),
                            "lemma": str(tok.get("lemma", "_") or "_"),
                            "upos": str(tok.get("upos", "_") or "_"),
                            "head": head,
                            "deprel": str(deprel or "_"),
                        }
                    )
                if not tokens:
                    continue
                sent_text = str(sent.metadata.get("text", "")).strip() if hasattr(sent, "metadata") else ""
                if not sent_text:
                    sent_text = " ".join(str(t["form"]) for t in tokens)
                out.append({"text": sent_text, "tokens": tokens})
        except Exception:
            return []
        finally:
            fp.close()
        self._sentence_cache[key] = out
        return out

    def _norm_filter(self, text: str) -> str:
        raw = (text or "").strip().lower()
        return "" if raw in {"", "all", "*"} else raw

    def _token_matches(self, token: dict[str, object], form_q: str, lemma_q: str, upos_q: str, deprel_q: str) -> bool:
        form = str(token.get("form", "")).lower()
        lemma = str(token.get("lemma", "")).lower()
        upos = str(token.get("upos", "")).lower()
        deprel = str(token.get("deprel", "")).lower()
        if form_q and form_q not in form:
            return False
        if lemma_q and lemma_q not in lemma:
            return False
        if upos_q and upos_q not in upos:
            return False
        if deprel_q and deprel_q not in deprel:
            return False
        return True

    def _search_sentences(self) -> None:
        if self._search_thread is not None and self._search_thread.is_alive():
            self.status_label.setText("Search is already running in background...")
            return
        files = self._selected_treebanks()
        if not files:
            self._matched_sentences = []
            self.result_list.clear()
            self._refresh_result_page()
            self.status_label.setText("No treebank selected.")
            self.retrivis_result_tabs.setCurrentIndex(1)
            self._render_default_example()
            return

        form_q = self._norm_filter(self.form_input.currentText())
        lemma_q = self._norm_filter(self.lemma_input.currentText())
        upos_q = self._norm_filter(self.upos_input.currentText())
        deprel_q = self._norm_filter(self.deprel_input.currentText())
        source = str(self.viz_source_combo.currentData() or "imported")
        self._search_token += 1
        token = self._search_token
        self.search_btn.setEnabled(False)
        self.status_label.setText("Searching in background...")
        self.message.emit("RetriVis searching in background...")

        def _worker() -> None:
            try:
                has_filter = any([form_q, lemma_q, upos_q, deprel_q])
                invalid_raw: list[str] = []
                matches: list[dict[str, object]] = []
                for tb in files:
                    if source == "imported" and tb.suffix.lower() != ".conllu":
                        invalid_raw.append(tb.name)
                        continue
                    sentences = self._parse_treebank_sentences(tb)
                    for idx, sent in enumerate(sentences, start=1):
                        toks: list[dict[str, object]] = sent["tokens"]  # type: ignore[assignment]
                        matched_ids: list[int] = []
                        matched_deprel_ids: list[int] = []
                        for t in toks:
                            if self._token_matches(t, form_q, lemma_q, upos_q, deprel_q):
                                tid = int(t.get("id", 0) or 0)
                                if tid > 0:
                                    matched_ids.append(tid)
                            if deprel_q:
                                deprel_val = str(t.get("deprel", "")).lower()
                                tid = int(t.get("id", 0) or 0)
                                if tid > 0 and deprel_q in deprel_val:
                                    matched_deprel_ids.append(tid)
                        matched = bool(matched_ids) if has_filter else True
                        if matched:
                            payload: dict[str, object] = {"path": tb, "sent_idx": idx, "sentence": sent}
                            if has_filter:
                                payload["highlight"] = {
                                    "token_ids": sorted(set(matched_ids)),
                                    "deprel_dep_ids": sorted(set(matched_deprel_ids)),
                                }
                            matches.append(payload)
                self._search_done.emit({"token": token, "matches": matches, "invalid_raw": invalid_raw})
            except Exception as exc:
                self._search_failed.emit(str(exc))

        self._search_thread = threading.Thread(target=_worker, daemon=True)
        self._search_thread.start()

    def _on_search_done_async(self, payload: object) -> None:
        self.search_btn.setEnabled(True)
        self._search_thread = None
        if not isinstance(payload, dict):
            self._on_search_failed_async("invalid search payload")
            return
        token = int(payload.get("token", -1) or -1)
        if token != self._search_token:
            return
        matches = payload.get("matches", [])
        invalid_raw = payload.get("invalid_raw", [])
        if not isinstance(matches, list):
            matches = []
        if not isinstance(invalid_raw, list):
            invalid_raw = []

        if invalid_raw:
            msg = (
                "Format error: visualization from input treebanks requires CoNLL-U (.conllu).\n"
                f"Invalid file(s): {', '.join(invalid_raw[:6])}"
            )
            self.status_label.setText("Format error: non-CoNLL-U input detected.")
            self.message.emit("Format error: non-CoNLL-U input treebank for visualization.")
            _show_warning_dialog(self, "Format error", msg)

        self._matched_sentences = [m for m in matches if isinstance(m, dict)]
        self._result_page = 0
        self._refresh_result_page()
        total = len(self._matched_sentences)
        self.status_label.setText(f"Matched {total} sentence(s).")
        self.message.emit(f"RetriVis matched {total} sentence(s).")
        if total > 0:
            self.retrivis_result_tabs.setCurrentIndex(0)
            self._on_result_clicked()
        else:
            self.retrivis_result_tabs.setCurrentIndex(1)
            self._on_result_clicked()

    def _on_search_failed_async(self, text: str) -> None:
        self.search_btn.setEnabled(True)
        self._search_thread = None
        self.status_label.setText(f"Search failed: {text}")
        self.message.emit(f"RetriVis search failed: {text}")

    def _render_dependency_graph(self, payload: dict[str, object] | None) -> None:
        palette = self._retrivis_palette()
        if self.graph_web is not None:
            self.graph_web.setStyleSheet(f"background:{palette['bg']};")
            try:
                self.graph_web.page().setBackgroundColor(QColor(palette["bg"]))
            except Exception:
                pass

        def _render_message(msg: str) -> None:
            safe_msg = html.escape(msg)
            if self.graph_web is not None:
                self.graph_web.setHtml(
                    f"""
                    <html><body style="margin:0;padding:14px;background:{palette['bg']};color:{palette['fg']};font-family:'Segoe UI';">
                    <div style="color:{palette['hint']};">{safe_msg}</div>
                    </body></html>
                    """
                )
            elif self.graph_text_fallback is not None:
                self.graph_text_fallback.setPlainText(
                    f"{msg}\n\n"
                    "HTML dependency renderer is unavailable.\n"
                    "Reason: QWebEngineView is not installed in this environment.\n"
                    "Please install PyQt6-WebEngine."
                )

        if payload is None:
            self._last_svg_markup = ""
            self.graph_hint.setText("Click a sentence above to visualize its dependency graph.")
            _render_message("No sentence matched.")
            self._update_graph_nav()
            return

        tb: Path = payload["path"]  # type: ignore[assignment]
        sent_idx: int = int(payload["sent_idx"])
        sent: dict[str, object] = payload["sentence"]  # type: ignore[assignment]
        tokens: list[dict[str, object]] = sent["tokens"]  # type: ignore[assignment]
        highlight_payload = payload.get("highlight")
        highlight_token_ids: set[int] = set()
        highlight_deprel_dep_ids: set[int] = set()
        if isinstance(highlight_payload, dict):
            token_ids = highlight_payload.get("token_ids", [])
            rel_ids = highlight_payload.get("deprel_dep_ids", [])
            if isinstance(token_ids, (list, tuple, set)):
                for v in token_ids:
                    try:
                        iv = int(v)
                    except Exception:
                        continue
                    if iv > 0:
                        highlight_token_ids.add(iv)
            if isinstance(rel_ids, (list, tuple, set)):
                for v in rel_ids:
                    try:
                        iv = int(v)
                    except Exception:
                        continue
                    if iv > 0:
                        highlight_deprel_dep_ids.add(iv)
        ordered = sorted(tokens, key=lambda x: int(x.get("id", 0) or 0))
        if not ordered:
            _render_message("Empty sentence.")
            return

        if self.graph_web is None:
            _render_message(
                f"Cannot render dependency tree for {tb.stem} sentence #{sent_idx}.\n"
                "QWebEngineView is required for HTML/SVG rendering."
            )
            self._update_graph_nav()
            return

        base_font = int(self.viz_font_size_spin.value())
        unit = int(self.viz_spacing_spin.value())
        tree_gap = int(self.viz_tree_gap_spin.value())
        left_pad = 60
        baseline_y = max(240, 150 + base_font * 7)
        line_gap = max(14, int(base_font * 1.25))
        form_font = max(12, base_font + 2)
        sub_font = max(10, base_font)
        id_font = max(9, base_font - 1)
        edge_font = max(10, base_font)
        form_y = baseline_y
        lemma_y = baseline_y + line_gap
        upos_y = baseline_y + line_gap * 2
        id_y = baseline_y + line_gap * 3
        xpos = {int(t["id"]): left_pad + i * unit for i, t in enumerate(ordered)}

        def _cross(a: dict[str, int], b: dict[str, int]) -> bool:
            return (a["left"] < b["left"] < a["right"] < b["right"]) or (
                b["left"] < a["left"] < b["right"] < a["right"]
            )

        dep_arcs: list[dict[str, int | str]] = []
        for tok in ordered:
            dep = int(tok.get("id", 0) or 0)
            head = int(tok.get("head", 0) or 0)
            if head <= 0 or dep <= 0 or head not in xpos:
                continue
            left = min(head, dep)
            right = max(head, dep)
            dep_arcs.append(
                {
                    "head": head,
                    "dep": dep,
                    "left": left,
                    "right": right,
                    "span": right - left,
                    "deprel": str(tok.get("deprel", "_")),
                    "side": 1,
                    "lane": 0,
                }
            )

        dep_arcs.sort(key=lambda a: (-int(a["span"]), int(a["left"])))

        def _assign_lanes(arcs: list[dict[str, int | str]]) -> None:
            lanes: list[list[dict[str, int | str]]] = []
            arcs.sort(key=lambda a: (int(a["span"]), int(a["left"])))
            for arc in arcs:
                placed = False
                for lane_idx, lane_arcs in enumerate(lanes):
                    overlap = any(
                        int(arc["left"]) < int(x["right"]) and int(arc["right"]) > int(x["left"])
                        for x in lane_arcs
                    )
                    if not overlap:
                        arc["lane"] = lane_idx
                        lane_arcs.append(arc)
                        placed = True
                        break
                if not placed:
                    arc["lane"] = len(lanes)
                    lanes.append([arc])

        _assign_lanes(dep_arcs)

        # Unified endpoint planning per node:
        # for all incident arcs on a node and each side (left/right),
        # longer distance -> closer to center; shorter distance -> closer to edge.
        incident_groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for idx, arc in enumerate(dep_arcs):
            head = int(arc["head"])
            dep = int(arc["dep"])
            span = int(arc["span"])
            side_at_head = -1 if dep < head else 1
            side_at_dep = -1 if head < dep else 1
            incident_groups.setdefault((head, side_at_head), []).append((idx, span))
            incident_groups.setdefault((dep, side_at_dep), []).append((idx, span))

        endpoint_offsets: dict[tuple[int, int], float] = {}
        for (node, side), arr in incident_groups.items():
            # Long arcs first, so they get smaller absolute offsets (closer to center).
            sorted_arr = sorted(arr, key=lambda t: (-t[1], t[0]))
            for i, (arc_idx, _span) in enumerate(sorted_arr):
                endpoint_offsets[(node, arc_idx)] = float(side * i * 6.2)

        # If a node has exactly two endpoints (one left + one right), force separation.
        nodes = {n for (n, _s) in incident_groups.keys()}
        for node in nodes:
            left_arr = incident_groups.get((node, -1), [])
            right_arr = incident_groups.get((node, 1), [])
            if len(left_arr) == 1 and len(right_arr) == 1 and (len(left_arr) + len(right_arr) == 2):
                left_arc = left_arr[0][0]
                right_arc = right_arr[0][0]
                endpoint_offsets[(node, left_arc)] = -4.0
                endpoint_offsets[(node, right_arc)] = 4.0

        max_up = 80
        min_y = 1e9
        svg_parts: list[str] = []
        svg_parts.append(
            '<defs>'
            f'<marker id="arrowEdge" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M1,1 L9,4 L1,7 L3.6,4 Z" fill="none" stroke="{palette["edge"]}" stroke-width="1.2"/></marker>'
            f'<marker id="arrowRel" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M1,1 L9,4 L1,7 L3.6,4 Z" fill="none" stroke="{palette["rel"]}" stroke-width="1.2"/></marker>'
            '</defs>'
        )
        token_by_id: dict[int, dict[str, object]] = {int(t.get("id", 0) or 0): t for t in ordered}

        for tok in ordered:
            tid = int(tok.get("id", 0) or 0)
            x = xpos.get(tid, tid)
            form = html.escape(str(tok.get("form", "_")))
            lemma = html.escape(str(tok.get("lemma", "_")))
            upos = html.escape(str(tok.get("upos", "_")))
            node_cls = f"node node-{tid}"
            if tid in highlight_token_ids:
                node_cls += " preset-word"
            svg_parts.append(
                f'<text class="{node_cls}" data-node="{tid}" x="{x}" y="{form_y}" text-anchor="middle" font-size="{form_font}" fill="{palette["form"]}">{form}</text>'
            )
            svg_parts.append(
                f'<text class="{node_cls}" data-node="{tid}" x="{x}" y="{lemma_y}" text-anchor="middle" font-size="{sub_font}" fill="{palette["lemma"]}">{lemma}</text>'
            )
            svg_parts.append(
                f'<text class="{node_cls}" data-node="{tid}" x="{x}" y="{upos_y}" text-anchor="middle" font-size="{sub_font}" fill="{palette["upos"]}">{upos}</text>'
            )
            svg_parts.append(
                f'<text class="{node_cls}" data-node="{tid}" x="{x}" y="{id_y}" text-anchor="middle" font-size="{id_font}" fill="{palette["id"]}">{tid}</text>'
            )

        for tok in ordered:
            tid = int(tok.get("id", 0) or 0)
            head = int(tok.get("head", 0) or 0)
            deprel = html.escape(str(tok.get("deprel", "_")))
            if head <= 0 or head not in xpos:
                x_dep = xpos.get(tid, tid)
                y_top = 50
                y_bottom = baseline_y - tree_gap
                root_edge_cls = "edge-path root-edge"
                root_label_cls = "edge-label"
                if tid in highlight_deprel_dep_ids:
                    root_edge_cls += " preset-rel"
                    root_label_cls += " preset-rel"
                svg_parts.append(
                    f'<line class="{root_edge_cls}" data-head="0" data-dep="{tid}" x1="{x_dep}" y1="{y_top}" x2="{x_dep}" y2="{y_bottom}" stroke="{palette["rel"]}" stroke-width="1.8" marker-end="url(#arrowRel)">'
                    f'<title>root -> {html.escape(str(tok.get("form", "_")))}</title></line>'
                )
                svg_parts.append(
                    f'<text class="{root_label_cls}" data-head="0" data-dep="{tid}" x="{x_dep}" y="{y_top - 5}" text-anchor="middle" font-size="{edge_font}" fill="{palette["rel"]}">{deprel}</text>'
                )
                max_up = max(max_up, baseline_y - y_top + 50)
                min_y = min(min_y, y_top - 8)

        base_y = baseline_y - tree_gap
        for idx, arc in enumerate(dep_arcs):
            head = int(arc["head"])
            dep = int(arc["dep"])
            lane = int(arc["lane"])
            span = int(arc["span"])
            deprel = html.escape(str(arc["deprel"]))

            x_head = xpos[head] + endpoint_offsets.get((head, idx), 0.0)
            x_dep = xpos[dep] + endpoint_offsets.get((dep, idx), 0.0)
            # Ensure start/end points are visually separated for short edges.
            min_gap = 16.0
            if dep > head:
                gap = x_dep - x_head
                if gap < min_gap:
                    delta = (min_gap - gap) / 2.0
                    x_head -= delta
                    x_dep += delta
            else:
                gap = x_head - x_dep
                if gap < min_gap:
                    delta = (min_gap - gap) / 2.0
                    x_head += delta
                    x_dep -= delta
            dist = abs(x_dep - x_head)
            # Soften curvature: lower peak growth and smoother entry/exit slope.
            arc_height = 26 + lane * 19 + dist * 0.11 + span * 1.38
            ctrl_y = max(18, base_y - arc_height)
            stroke = palette["edge"]
            max_up = max(max_up, base_y - ctrl_y + 40)
            c1y = base_y - arc_height * 1.0
            c2y = base_y - arc_height * 1.0
            c1x = x_head + (x_dep - x_head) * 0.07
            c2x = x_head + (x_dep - x_head) * 0.93
            # Place label close to true cubic midpoint (t=0.5), near curve center.
            t = 0.5
            mt = 1.0 - t
            bez_x = (mt**3) * x_head + 3 * (mt**2) * t * c1x + 3 * mt * (t**2) * c2x + (t**3) * x_dep
            bez_y = (mt**3) * base_y + 3 * (mt**2) * t * c1y + 3 * mt * (t**2) * c2y + (t**3) * base_y
            label_x = bez_x
            label_y = bez_y - 1.0
            head_form = html.escape(str(token_by_id.get(head, {}).get("form", str(head))))
            dep_form = html.escape(str(token_by_id.get(dep, {}).get("form", str(dep))))
            min_y = min(min_y, c1y, c2y, ctrl_y, label_y)
            edge_cls = "edge-path"
            label_cls = "edge-label"
            if dep in highlight_deprel_dep_ids:
                edge_cls += " preset-rel"
                label_cls += " preset-rel"

            svg_parts.append(
                f'<path class="{edge_cls}" data-head="{head}" data-dep="{dep}" '
                f'd="M {x_head:.2f} {base_y:.2f} C {c1x:.2f} {c1y:.2f}, {c2x:.2f} {c2y:.2f}, {x_dep:.2f} {base_y:.2f}" '
                f'stroke="{stroke}" stroke-width="1.7" fill="none" marker-end="url(#arrowEdge)">'
                f'<title>{head_form} ({head}) -> {dep_form} ({dep})</title></path>'
            )
            svg_parts.append(
                f'<text class="{label_cls}" data-head="{head}" data-dep="{dep}" x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" font-size="{edge_font}" fill="{palette["rel"]}">{deprel}</text>'
            )

        top_pad = max(0.0, 12.0 - float(min_y if min_y < 1e8 else 12.0))
        svg_w = max(840, left_pad * 2 + (len(ordered) - 1) * unit + 90)
        # Keep token rows close to bottom while preserving full arcs via vertical scrolling.
        svg_h = int(max(340, top_pad + id_y + 20))
        safe_sent = html.escape(str(sent.get("text", "")))
        edit_tokens = [
            {
                "id": int(t.get("id", 0) or 0),
                "form": str(t.get("form", "_") or "_"),
                "lemma": str(t.get("lemma", "_") or "_"),
                "upos": str(t.get("upos", "_") or "_"),
                "head": int(t.get("head", 0) or 0),
                "deprel": str(t.get("deprel", "_") or "_"),
            }
            for t in ordered
            if int(t.get("id", 0) or 0) > 0
        ]
        edit_tokens_json = json.dumps(edit_tokens, ensure_ascii=False)
        svg_markup = (
            f'<svg id="depSvg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">'
            f'<g transform="translate(0,{top_pad:.2f})">{ "".join(svg_parts) }</g></svg>'
        )
        self._last_svg_markup = svg_markup
        html_doc = f"""
        <html>
        <body style="margin:0;background:{palette['bg']};color:{palette['fg']};font-family:'Segoe UI';">
          <style>
            .edge-path {{ pointer-events: stroke; opacity: 0.90; transition: stroke-width .12s, opacity .12s; }}
            .edge-path.active {{ stroke: #ffd45e !important; stroke-width: 2.9 !important; opacity: 1; }}
            .edge-path.active-in {{ stroke: #5ec0ff !important; stroke-width: 2.8 !important; opacity: 1; }}
            .edge-path.active-out {{ stroke: #ffb45e !important; stroke-width: 2.8 !important; opacity: 1; }}
            .edge-label {{ pointer-events: none; fill: {palette['rel']}; transition: fill .12s, font-weight .12s; }}
            .edge-label.active {{ fill: #ffd45e !important; font-weight: 700; }}
            .edge-label.active-in {{ fill: #5ec0ff !important; font-weight: 700; }}
            .edge-label.active-out {{ fill: #ffb45e !important; font-weight: 700; }}
            .node {{ cursor: pointer; user-select: none; transition: fill .12s, font-weight .12s; }}
            .node.active {{ fill: #ffd45e !important; font-weight: 700; }}
            .node.target {{ fill: #41c970 !important; font-weight: 700; }}
            .node.preset-word {{ fill: #41c970 !important; font-weight: 700; }}
            .edge-path.preset-rel {{ stroke: #ff7f50 !important; stroke-width: 2.5 !important; opacity: 1; }}
            .edge-label.preset-rel {{ fill: #ff7f50 !important; font-weight: 700; }}
          </style>
          <div style="padding:8px 12px;color:{palette['hint']};">{html.escape(tb.stem)} | sentence #{sent_idx}</div>
          <div style="padding:0 12px 8px 12px;color:{palette['sub']};">{safe_sent}</div>
          <div style="padding: 0 8px 10px 8px;">
            <div id="svgWrap" style="overflow:auto; height:420px; border:1px solid {palette['border']}; border-radius:6px;">
              {svg_markup}
            </div>
          </div>
          <script>
            (function() {{
              const svg = document.getElementById('depSvg');
              const wrap = document.getElementById('svgWrap');
              if (!svg) return;
              if (wrap) {{
                // Prefer bottom area on initial render so token rows are visible immediately.
                requestAnimationFrame(() => {{
                  wrap.scrollTop = Math.max(0, wrap.scrollHeight - wrap.clientHeight);
                }});
              }}
              let pinned = null;
              const clearActive = () => {{
                svg.querySelectorAll('.active, .active-in, .active-out, .target').forEach(el => {{
                  el.classList.remove('active');
                  el.classList.remove('active-in');
                  el.classList.remove('active-out');
                  el.classList.remove('target');
                }});
              }};
              const activateNode = (nodeId) => {{
                svg.querySelectorAll(`.node-${{nodeId}}`).forEach(el => el.classList.add('active'));
              }};
              const activateNodeTarget = (nodeId) => {{
                svg.querySelectorAll(`.node-${{nodeId}}`).forEach(el => el.classList.add('target'));
              }};
              const activateLabelForEdge = (edge, clsName) => {{
                svg.querySelectorAll(`.edge-label[data-head="${{edge.dataset.head || ''}}"][data-dep="${{edge.dataset.dep || ''}}"]`).forEach(lbl => {{
                  lbl.classList.add(clsName);
                }});
              }};
              const activateEdgeSet = (nodeId) => {{
                svg.querySelectorAll('.edge-path').forEach(edge => {{
                  const isIn = edge.dataset.dep === String(nodeId);
                  const isOut = edge.dataset.head === String(nodeId);
                  if (isIn || isOut) {{
                    const cls = isIn ? 'active-in' : 'active-out';
                    edge.classList.add(cls);
                    activateLabelForEdge(edge, cls);
                    if (!isOut) {{
                      activateNode(edge.dataset.head || '');
                    }}
                  }}
                }});
              }};
              const applyPinned = () => {{
                if (!pinned) return;
                clearActive();
                if (pinned.type === 'node') {{
                  // Keep selected node in green when node selection is pinned.
                  activateNodeTarget(pinned.id);
                  activateEdgeSet(pinned.id);
                }} else if (pinned.type === 'edge') {{
                  const e = pinned.el;
                  if (e) {{
                    e.classList.add('active');
                    activateLabelForEdge(e, 'active');
                    // Requirement: dependent = green(target), head = yellow(active)
                    activateNodeTarget(e.dataset.dep || '');
                    activateNode(e.dataset.head || '');
                  }}
                }}
              }};
              svg.querySelectorAll('.edge-path').forEach(edge => {{
                edge.addEventListener('mouseenter', () => {{
                  if (pinned) return;
                  clearActive();
                  edge.classList.add('active');
                  activateLabelForEdge(edge, 'active');
                  // Requirement: dependent = green(target), head = yellow(active)
                  activateNodeTarget(edge.dataset.dep);
                  activateNode(edge.dataset.head);
                }});
                edge.addEventListener('mouseleave', () => {{
                  if (pinned) return;
                  clearActive();
                }});
                edge.addEventListener('click', (ev) => {{
                  ev.stopPropagation();
                  pinned = {{ type: 'edge', el: edge }};
                  applyPinned();
                }});
              }});
              svg.querySelectorAll('.node').forEach(node => {{
                node.addEventListener('mouseenter', () => {{
                  if (pinned) return;
                  clearActive();
                  activateNode(node.dataset.node);
                  activateEdgeSet(node.dataset.node);
                }});
                node.addEventListener('mouseleave', () => {{
                  if (pinned) return;
                  clearActive();
                }});
                node.addEventListener('click', (ev) => {{
                  ev.stopPropagation();
                  pinned = {{ type: 'node', id: node.dataset.node }};
                  applyPinned();
                }});
              }});
              svg.addEventListener('click', (ev) => {{
                if (ev.target === svg) {{
                  pinned = null;
                  clearActive();
                }}
              }});
              if (wrap) {{
                wrap.addEventListener('click', (ev) => {{
                  if (ev.target === wrap) {{
                    pinned = null;
                    clearActive();
                  }}
                }});
              }}
            }})();
          </script>
          <div id="qsNodeMenu" style="display:none;position:fixed;z-index:9999;background:{palette['bg']};color:{palette['fg']};border:1px solid {palette['border']};border-radius:6px;box-shadow:0 8px 20px rgba(0,0,0,.22);padding:4px;">
            <div class="nmi" data-act="delete" style="padding:6px 10px;cursor:pointer;border-radius:4px;">delete</div>
            <div class="nmi" data-act="edit" style="padding:6px 10px;cursor:pointer;border-radius:4px;">edit</div>
            <div class="nmi" data-act="swap" style="padding:6px 10px;cursor:pointer;border-radius:4px;">swap</div>
            <div class="nmi" data-act="isolate" style="padding:6px 10px;cursor:pointer;border-radius:4px;">isolate</div>
            <div class="nmi" data-act="connect" style="padding:6px 10px;cursor:pointer;border-radius:4px;">connect</div>
          </div>
          <div id="qsEdgeMenu" style="display:none;position:fixed;z-index:9999;background:{palette['bg']};color:{palette['fg']};border:1px solid {palette['border']};border-radius:6px;box-shadow:0 8px 20px rgba(0,0,0,.22);padding:4px;">
            <div class="emi" data-act="delete" style="padding:6px 10px;cursor:pointer;border-radius:4px;">delete</div>
            <div class="emi" data-act="edit" style="padding:6px 10px;cursor:pointer;border-radius:4px;">edit</div>
            <div class="emi" data-act="adjust" style="padding:6px 10px;cursor:pointer;border-radius:4px;">adjust</div>
            <div class="emi" data-act="reverse" style="padding:6px 10px;cursor:pointer;border-radius:4px;">reverse</div>
          </div>
          <div id="qsBlankMenu" style="display:none;position:fixed;z-index:9999;background:{palette['bg']};color:{palette['fg']};border:1px solid {palette['border']};border-radius:6px;box-shadow:0 8px 20px rgba(0,0,0,.22);padding:4px;">
            <div class="bmi" data-act="add-node" style="padding:6px 10px;cursor:pointer;border-radius:4px;">add node</div>
            <div class="bmi" data-act="add-edge" style="padding:6px 10px;cursor:pointer;border-radius:4px;">add edge</div>
          </div>
          <script>
            (function() {{
              const state = {{ tokens: {edit_tokens_json} }};
              window.__qsRetriState = state;
              let emitSeq = 0;
              const nodeMenu = document.getElementById('qsNodeMenu');
              const edgeMenu = document.getElementById('qsEdgeMenu');
              const blankMenu = document.getElementById('qsBlankMenu');
              const svg = document.getElementById('depSvg');
              if (!svg || !nodeMenu || !edgeMenu || !blankMenu) return;
              let nodeCtx = null;
              let edgeCtx = null;
              const hideMenus = () => {{ nodeMenu.style.display='none'; edgeMenu.style.display='none'; blankMenu.style.display='none'; }};
              const hoverBg = '{palette["border"]}';
              const showNodeMenu = (x,y) => {{ hideMenus(); nodeMenu.style.left=x+'px'; nodeMenu.style.top=y+'px'; nodeMenu.style.display='block'; }};
              const showEdgeMenu = (x,y) => {{ hideMenus(); edgeMenu.style.left=x+'px'; edgeMenu.style.top=y+'px'; edgeMenu.style.display='block'; }};
              const showBlankMenu = (x,y) => {{ hideMenus(); blankMenu.style.left=x+'px'; blankMenu.style.top=y+'px'; blankMenu.style.display='block'; }};
              const getTok = (id) => state.tokens.find(t => Number(t.id) === Number(id));
              const norm = () => {{
                state.tokens = state.tokens
                  .filter(t => Number(t.id) > 0)
                  .map(t => ({{
                    id: Number(t.id)||0,
                    form: String(t.form ?? '_'),
                    lemma: String(t.lemma ?? '_'),
                    upos: String(t.upos ?? '_'),
                    head: Number(t.head)||0,
                    deprel: String(t.deprel ?? '_'),
                  }}))
                  .sort((a,b)=>a.id-b.id);
              }};
              const emit = () => {{
                norm();
                try {{
                  window.__qsRetriState = state;
                  emitSeq += 1;
                  document.title = 'QS_RETRI_EDIT:' + String(emitSeq);
                }} catch(e) {{}}
              }};
              const renumberAfterDelete = (rid) => {{
                state.tokens = state.tokens.filter(t => Number(t.id)!==Number(rid));
                state.tokens.forEach(t => {{
                  if (Number(t.id) > Number(rid)) t.id = Number(t.id)-1;
                }});
                state.tokens.forEach(t => {{
                  const h = Number(t.head)||0;
                  if (h === Number(rid)) t.head = 0;
                  else if (h > Number(rid)) t.head = h-1;
                }});
              }};
              const swapPositions = (a,b) => {{
                if (a===b) return;
                state.tokens.forEach(t => {{
                  if (Number(t.id)===a) t.id = -999001;
                  else if (Number(t.id)===b) t.id = a;
                }});
                state.tokens.forEach(t => {{
                  if (Number(t.id)===-999001) t.id = b;
                }});
                state.tokens.forEach(t => {{
                  if (Number(t.head)===a) t.head = -999001;
                  else if (Number(t.head)===b) t.head = a;
                }});
                state.tokens.forEach(t => {{
                  if (Number(t.head)===-999001) t.head = b;
                }});
              }};
              const isolateNode = (id) => {{
                state.tokens.forEach(t => {{
                  if (Number(t.id)===id) {{
                    t.head = 0;
                    t.deprel = '_';
                  }}
                  if (Number(t.head)===id) {{
                    t.head = 0;
                    t.deprel = '_';
                  }}
                }});
              }};
              const addNode = () => {{
                const packed = prompt('New node as: form|lemma|upos|id', '_|_|X|');
                if (packed===null) return;
                const parts = String(packed).split('|');
                const form = String((parts[0] ?? '_')).trim() || '_';
                const lemma = String((parts[1] ?? '_')).trim() || '_';
                const upos = String((parts[2] ?? 'X')).trim() || 'X';
                const curN = state.tokens.length;
                let newId = Number(String(parts[3] ?? '').trim());
                if (!Number.isFinite(newId)) newId = curN + 1;
                newId = Math.max(1, Math.min(curN + 1, Math.trunc(newId)));
                state.tokens.forEach(t => {{
                  if (Number(t.id) >= newId) t.id = Number(t.id) + 1;
                }});
                state.tokens.forEach(t => {{
                  if (Number(t.head) >= newId) t.head = Number(t.head) + 1;
                }});
                state.tokens.push({{ id:newId, form, lemma, upos, head:0, deprel:'_' }});
              }};
              const addEdge = () => {{
                const packed = prompt('New relation as: head|dependent|deprel', '0|1|dep');
                if (packed===null) return;
                const parts = String(packed).split('|');
                const head = Number(String(parts[0] ?? '').trim());
                const dep = Number(String(parts[1] ?? '').trim());
                const deprel = String((parts[2] ?? 'dep')).trim() || 'dep';
                if (!Number.isFinite(head) || !Number.isFinite(dep) || dep <= 0 || head < 0 || head === dep) return;
                const depTok = getTok(dep);
                if (!depTok) return;
                if (head > 0 && !getTok(head)) return;
                depTok.head = Math.trunc(head);
                depTok.deprel = deprel;
              }};
              const connectNode = (id) => {{
                const otherRaw = prompt('Other node id:', '');
                if (otherRaw===null) return;
                const other = Number(otherRaw);
                if (!Number.isFinite(other) || other<=0 || other===id) return;
                if (!getTok(other)) return;
                const dir = (prompt('Direction (out/in):', 'out') || 'out').toLowerCase();
                const rel = prompt('deprel:', 'dep');
                if (dir.startsWith('out')) {{
                  const depTok = getTok(other);
                  if (!depTok) return;
                  depTok.head = id;
                  if (rel!==null) depTok.deprel = String(rel||'dep');
                }} else {{
                  const depTok = getTok(id);
                  if (!depTok) return;
                  depTok.head = other;
                  if (rel!==null) depTok.deprel = String(rel||'dep');
                }}
              }};
              const deleteEdge = (head,dep) => {{
                const tok = getTok(dep);
                if (!tok) return;
                if (Number(tok.head)===Number(head)) tok.head = 0;
              }};
              const editEdge = (_head,dep) => {{
                const tok = getTok(dep);
                if (!tok) return;
                const rel = prompt('New deprel:', String(tok.deprel||'dep'));
                if (rel===null) return;
                tok.deprel = String(rel||'dep');
              }};
              const adjustEdge = (_head,_dep) => {{
                const hRaw = prompt('New head id:', String(_head));
                if (hRaw===null) return;
                const dRaw = prompt('New dependent id:', String(_dep));
                if (dRaw===null) return;
                const nh = Number(hRaw), nd = Number(dRaw);
                if (!Number.isFinite(nh) || !Number.isFinite(nd) || nd<=0 || nh<0 || nh===nd) return;
                const dt = getTok(nd);
                if (!dt) return;
                dt.head = nh;
              }};
              const reverseEdge = (head,dep) => {{
                const hTok = getTok(head), dTok = getTok(dep);
                if (!hTok || !dTok) return;
                const parentOfHead = Number(hTok.head)||0;
                hTok.head = dep;
                dTok.head = parentOfHead;
              }};
              svg.querySelectorAll('.node[data-node]').forEach(el => {{
                el.addEventListener('contextmenu', (ev) => {{
                  ev.preventDefault();
                  const id = Number(el.getAttribute('data-node')||0);
                  if (!id) return;
                  nodeCtx = {{ id }};
                  showNodeMenu(ev.clientX, ev.clientY);
                }});
              }});
              svg.querySelectorAll('.edge-path, .edge-label').forEach(el => {{
                el.addEventListener('contextmenu', (ev) => {{
                  ev.preventDefault();
                  const head = Number(el.getAttribute('data-head')||0);
                  const dep = Number(el.getAttribute('data-dep')||0);
                  if (!dep) return;
                  edgeCtx = {{ head, dep }};
                  showEdgeMenu(ev.clientX, ev.clientY);
                }});
              }});
              svg.addEventListener('contextmenu', (ev) => {{
                const target = ev.target;
                const isNode = !!(target && target.closest && target.closest('.node[data-node]'));
                const isEdge = !!(target && target.closest && target.closest('.edge-path, .edge-label'));
                if (isNode || isEdge) return;
                ev.preventDefault();
                showBlankMenu(ev.clientX, ev.clientY);
              }});
              nodeMenu.querySelectorAll('.nmi').forEach(mi => {{
                mi.addEventListener('click', () => {{
                  if (!nodeCtx) return;
                  const id = Number(nodeCtx.id)||0;
                  const act = mi.getAttribute('data-act') || '';
                  if (act==='delete') renumberAfterDelete(id);
                  if (act==='edit') {{
                    const t = getTok(id);
                    if (t) {{
                      const packed = prompt('Edit as: form|lemma|upos', `${{String(t.form||'_')}}|${{String(t.lemma||'_')}}|${{String(t.upos||'_')}}`);
                      if (packed!==null) {{
                        const parts = String(packed).split('|');
                        t.form = String((parts[0] ?? t.form ?? '_')).trim() || '_';
                        t.lemma = String((parts[1] ?? t.lemma ?? '_')).trim() || '_';
                        t.upos = String((parts[2] ?? t.upos ?? '_')).trim() || '_';
                      }}
                    }}
                  }}
                  if (act==='swap') {{
                    const v = prompt('Swap with node id:', '');
                    if (v!==null) {{
                      const other = Number(v);
                      if (Number.isFinite(other) && other>0 && getTok(other)) swapPositions(id, other);
                    }}
                  }}
                  if (act==='isolate') isolateNode(id);
                  if (act==='connect') connectNode(id);
                  hideMenus();
                  emit();
                }});
              }});
              edgeMenu.querySelectorAll('.emi').forEach(mi => {{
                mi.addEventListener('click', () => {{
                  if (!edgeCtx) return;
                  const head = Number(edgeCtx.head)||0;
                  const dep = Number(edgeCtx.dep)||0;
                  const act = mi.getAttribute('data-act') || '';
                  if (act==='delete') deleteEdge(head, dep);
                  if (act==='edit') editEdge(head, dep);
                  if (act==='adjust') adjustEdge(head, dep);
                  if (act==='reverse') reverseEdge(head, dep);
                  hideMenus();
                  emit();
                }});
              }});
              blankMenu.querySelectorAll('.bmi').forEach(mi => {{
                mi.addEventListener('click', () => {{
                  const act = mi.getAttribute('data-act') || '';
                  if (act==='add-node') addNode();
                  if (act==='add-edge') addEdge();
                  hideMenus();
                  emit();
                }});
              }});
              document.addEventListener('click', () => hideMenus());
              nodeMenu.querySelectorAll('.nmi').forEach(el => {{
                el.addEventListener('mouseenter', () => el.style.background = hoverBg);
                el.addEventListener('mouseleave', () => el.style.background = 'transparent');
              }});
              edgeMenu.querySelectorAll('.emi').forEach(el => {{
                el.addEventListener('mouseenter', () => el.style.background = hoverBg);
                el.addEventListener('mouseleave', () => el.style.background = 'transparent');
              }});
              blankMenu.querySelectorAll('.bmi').forEach(el => {{
                el.addEventListener('mouseenter', () => el.style.background = hoverBg);
                el.addEventListener('mouseleave', () => el.style.background = 'transparent');
              }});
            }})();
          </script>
        </body>
        </html>
        """
        if self.graph_web is not None:
            self.graph_web.setHtml(html_doc)
        self.graph_hint.setText(f"{tb.stem} | sentence #{sent_idx} | {sent.get('text', '')}")
        self._update_graph_nav()

    def _on_result_clicked(self) -> None:
        item = self._active_result_list().currentItem()
        if item is None:
            self._update_graph_nav()
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            self._update_graph_nav()
            return
        self._render_dependency_graph(payload)

class DepvalPage(QWidget):
    message = pyqtSignal(str)
    processingChanged = pyqtSignal(str, int)
    _compute_done = pyqtSignal(object)
    _compute_failed = pyqtSignal(str)
    _convert_done = pyqtSignal(object)
    _convert_failed = pyqtSignal(str)
    _parse_done = pyqtSignal(object)
    _parse_failed = pyqtSignal(str)
    _parse_load_done = pyqtSignal(object)
    _parse_load_failed = pyqtSignal(str)
    _pvp_labels_done = pyqtSignal(object)
    _stat_done = pyqtSignal(object)
    _plot_data_done = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        _bootstrap_cache_layout()
        self._imported_treebanks: list[Path] = []
        self._tables: dict[str, QTableWidget] = {}
        self._depval_analyzer_cls = None
        self._lawfitter_module = None
        self._depval_stopdeps = {"punct", "punkt", "_", "PUN", "PU", "pu", "wp", "WP"}
        self._depval_rootdeps = {"root", "ROOT", "s", "HED", ""}
        self._event_filter_installed = False
        self._runtime_parallel_scope = "off"
        self._runtime_parallel_enabled = False
        self._runtime_n_jobs: int | None = None
        self._treebank_sentence_count_cache: dict[str, int] = {}
        self._render_cache: dict[str, object] | None = None
        self._converted_treebank_cache: dict[str, str] = {}
        self._convert_cache_dir = _quansyn_cache_path("convert", "by_source")
        self._parser_cache_dir = _quansyn_cache_path("parser", "current")
        self._parser_cache_file = self._parser_cache_dir / "parser_current.conllu"
        self._source_mode = "imported"
        self._models_root = _runtime_base_dir() / "models"
        self._spacy_root = self._models_root / "spacy"
        self._stanza_root = self._models_root / "stanza"
        try:
            self._spacy_root.mkdir(parents=True, exist_ok=True)
            self._stanza_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._parse_pipeline_cache: dict[str, object] = {}
        self._parse_txt_sources: list[Path] = []
        self._parse_clean_by_source: dict[str, list[str]] = {}
        self._parse_conllu_by_source: dict[str, str] = {}
        self._parse_running = False
        self._parse_thread: threading.Thread | None = None
        self._parse_load_thread: threading.Thread | None = None
        self._pvp_label_thread: threading.Thread | None = None
        self._pvp_label_token = 0
        self._parse_conllu_output = ""
        self._last_report_pct = -1
        self._progress_total = 1
        self._progress_done = 0
        self._progress_emit_pct = -1
        self._progress_emit_ts = 0.0
        self._compute_running = False
        self._compute_thread: threading.Thread | None = None
        self._convert_thread: threading.Thread | None = None
        self._stat_thread: threading.Thread | None = None
        self._stat_token = 0
        self._plot_thread: threading.Thread | None = None
        self._plot_token = 0
        self._render_token = 0
        self._render_queue: list[tuple[str, list[str]]] = []
        self._render_files: list[Path] = []
        self._render_dep_payloads: list[dict[str, object]] = []
        self._render_sent_payloads: list[dict[str, list]] = []
        self._render_text_payloads: list[dict[str, float]] = []
        self._render_dist_payloads: list[dict[str, tuple[list, list[float], bool, str]]] = []
        self._render_pvp_payloads: dict[str, list] = {}
        self._render_pvp_classes: list[str] = []
        self._render_pvp_mode: str = "pos"
        self._render_auto_plot = False
        self._build_ui()
        self._wire()
        self._compute_done.connect(self._on_compute_done)
        self._compute_failed.connect(self._on_compute_failed)
        self._convert_done.connect(self._on_convert_done_async)
        self._convert_failed.connect(self._on_convert_failed_async)
        self._parse_done.connect(self._on_parse_done_async)
        self._parse_failed.connect(self._on_parse_failed_async)
        self._parse_load_done.connect(self._on_parse_load_done_async)
        self._parse_load_failed.connect(self._on_parse_load_failed_async)
        self._pvp_labels_done.connect(self._on_pvp_labels_done_async)
        self._stat_done.connect(self._on_stat_done_async)
        self._plot_data_done.connect(self._on_plot_data_done_async)

    def apply_ui_scale(self, scale: float) -> None:
        s = max(0.58, min(1.0, float(scale)))
        drawer_w = max(220, int(round(300 * s)))
        self.drawer_width = drawer_w
        self.render_drawer_width = drawer_w
        self.convert_drawer_width = drawer_w
        self.lawfitter_drawer_width = drawer_w
        self.save_drawer_width = drawer_w
        handle_w = max(26, int(round(34 * s)))
        handle_h = max(72, int(round(94 * s)))
        for h in [
            getattr(self, "drawer_handle", None),
            getattr(self, "render_drawer_handle", None),
            getattr(self, "convert_drawer_handle", None),
            getattr(self, "lawfitter_drawer_handle", None),
            getattr(self, "save_drawer_handle", None),
        ]:
            if h is None:
                continue
            try:
                h.setFixedSize(handle_w, handle_h)
            except Exception:
                pass
        self._update_drawer_geometry(initial=True)

    def set_imported_treebanks(self, paths: list[str]) -> None:
        self._imported_treebanks = [Path(p) for p in paths if Path(p).exists()]
        valid_sources = {str(p.resolve()) for p in self._imported_treebanks}
        filtered_cache = {
            src: dst for src, dst in self._converted_treebank_cache.items() if src in valid_sources and Path(dst).exists()
        }
        self._converted_treebank_cache.clear()
        self._converted_treebank_cache.update(filtered_cache)
        self.treebank_combo.blockSignals(True)
        self.treebank_combo.clear()
        self.treebank_combo.addItem("all", "__all__")
        for path in self._imported_treebanks:
            self.treebank_combo.addItem(self._treebank_display_name(path), str(path))
        self.treebank_combo.blockSignals(False)
        self.render_treebank_combo.blockSignals(True)
        self.render_treebank_combo.clear()
        for path in self._imported_treebanks:
            self.render_treebank_combo.addItem(self._treebank_display_name(path), str(path))
        self.render_treebank_combo.addItem("all", "__all__")
        if self.render_treebank_combo.count() == 0:
            self.render_treebank_combo.addItem("all", "__all__")
        self.render_treebank_combo.setCurrentIndex(0)
        self.render_treebank_combo.blockSignals(False)
        self.convert_treebank_combo.blockSignals(True)
        self.convert_treebank_combo.clear()
        self.convert_treebank_combo.addItem("all", "__all__")
        for path in self._imported_treebanks:
            self.convert_treebank_combo.addItem(self._treebank_display_name(path), str(path))
        self.convert_treebank_combo.blockSignals(False)
        self.save_treebank_combo.blockSignals(True)
        self.save_treebank_combo.clear()
        self.save_treebank_combo.addItem("all", "__all__")
        for path in self._imported_treebanks:
            self.save_treebank_combo.addItem(self._treebank_display_name(path), str(path))
        self.save_treebank_combo.blockSignals(False)
        self._refresh_source_options()
        self._refresh_pvp_labels()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 2, 12, 8)
        root.setSpacing(4)

        self.result_area = QWidget()
        bottom_layout = QVBoxLayout(self.result_area)
        bottom_layout.setContentsMargins(10, 0, 44, 0)
        bottom_layout.setSpacing(4)

        b_split = QSplitter(Qt.Orientation.Horizontal)
        bottom_layout.addWidget(b_split, 1)

        table_wrap = QWidget()
        table_layout = QVBoxLayout(table_wrap)
        table_layout.setContentsMargins(0, 0, 6, 0)
        table_layout.setSpacing(4)
        self.result_tabs = QTabWidget()
        table_layout.addWidget(self.result_tabs, 1)
        overall_status_title = QLabel("Overall Status")
        overall_status_title.setObjectName("sectionTitle")
        table_layout.addWidget(overall_status_title, 0, Qt.AlignmentFlag.AlignLeft)
        self.report_box = QTextEdit()
        self.report_box.setObjectName("depvalReportBox")
        self.report_box.setReadOnly(True)
        self.report_box.setMinimumHeight(150)
        self.report_box.setPlaceholderText("Backend report: compute status and general messages.")
        table_layout.addWidget(self.report_box, 0)

        viz_wrap = QWidget()
        viz_layout = QVBoxLayout(viz_wrap)
        viz_layout.setContentsMargins(6, 0, 0, 0)
        viz_layout.setSpacing(4)
        viz_split = QSplitter(Qt.Orientation.Vertical)
        viz_layout.addWidget(viz_split, 1)

        plot_section = QWidget()
        plot_section_layout = QVBoxLayout(plot_section)
        plot_section_layout.setContentsMargins(0, 0, 0, 0)
        plot_section_layout.setSpacing(4)

        if pd and lp_ggplot is not None:
            plot_title = QLabel("Plot")
            plot_title.setObjectName("sectionTitle")
            plot_section_layout.addWidget(plot_title, 0, Qt.AlignmentFlag.AlignLeft)
            self.plot_card = None
            self.figure = None
            self.canvas = None
            self._last_plot_obj = None
            self._last_plot_svg = ""
            self._last_plot_html = ""
            self.plot_web = None
            self.plot_scroll = None
            self.plot_preview = None
        else:
            self.plot_card = None
            self.figure = None
            self.canvas = None
            self._last_plot_obj = None
            self._last_plot_svg = ""
            self._last_plot_html = ""
            self.plot_web = None
            no_plot = QLabel("Install lets-plot and pandas to enable plotting.")
            plot_section_layout.addWidget(no_plot)

        self.viz_param_wrap = QFrame()
        self.viz_param_wrap.setObjectName("vizParamWrap")
        viz_param_layout = QVBoxLayout(self.viz_param_wrap)
        viz_param_layout.setContentsMargins(0, 0, 0, 0)
        viz_param_layout.setSpacing(6)

        self.plot_opt_grid = QGridLayout()
        self.plot_opt_grid.setContentsMargins(0, 0, 0, 0)
        self.plot_opt_grid.setHorizontalSpacing(10)
        self.plot_opt_grid.setVerticalSpacing(6)

        self.row_dimension = QWidget()
        row_dim_l = QHBoxLayout(self.row_dimension)
        row_dim_l.setContentsMargins(0, 0, 0, 0)
        row_dim_l.setSpacing(6)
        self.plot_dim_label = QLabel("Dimension")
        row_dim_l.addWidget(self.plot_dim_label)
        self.plot_dim_combo = QComboBox()
        self.plot_dim_combo.addItems(["1D", "2D"])
        self.plot_dim_combo.setCurrentText("1D")
        row_dim_l.addWidget(self.plot_dim_combo, 1)
        self.plot_opt_grid.addWidget(self.row_dimension, 0, 0)

        self.row_data_a = QWidget()
        row_data_a_l = QHBoxLayout(self.row_data_a)
        row_data_a_l.setContentsMargins(0, 0, 0, 0)
        row_data_a_l.setSpacing(6)
        self.plot_col_a_label = QLabel("Data A")
        row_data_a_l.addWidget(self.plot_col_a_label)
        self.plot_col_a_combo = QComboBox()
        self.plot_col_a_combo.addItem("none")
        row_data_a_l.addWidget(self.plot_col_a_combo, 1)
        self.plot_opt_grid.addWidget(self.row_data_a, 0, 1)

        self.row_data_b = QWidget()
        row_data_b_l = QHBoxLayout(self.row_data_b)
        row_data_b_l.setContentsMargins(0, 0, 0, 0)
        row_data_b_l.setSpacing(6)
        self.plot_col_b_label = QLabel("Data B")
        row_data_b_l.addWidget(self.plot_col_b_label)
        self.plot_col_b_combo = QComboBox()
        self.plot_col_b_combo.addItem("none")
        row_data_b_l.addWidget(self.plot_col_b_combo, 1)
        self.plot_opt_grid.addWidget(self.row_data_b, 1, 1)

        self.row_chart = QWidget()
        row_chart_l = QHBoxLayout(self.row_chart)
        row_chart_l.setContentsMargins(0, 0, 0, 0)
        row_chart_l.setSpacing(6)
        self.plot_chart_label = QLabel("Plot type")
        row_chart_l.addWidget(self.plot_chart_label)
        self.chart_type = QComboBox()
        self.chart_type.addItems(["histogram", "bar", "line", "scatter", "area", "boxplot", "density"])
        row_chart_l.addWidget(self.chart_type, 1)
        self.plot_opt_grid.addWidget(self.row_chart, 1, 0)

        self.row_single_mode = QWidget()
        row_single_mode_l = QHBoxLayout(self.row_single_mode)
        row_single_mode_l.setContentsMargins(0, 0, 0, 0)
        row_single_mode_l.setSpacing(6)
        self.single_mode_label = QLabel("1D mode")
        row_single_mode_l.addWidget(self.single_mode_label)
        self.single_mode_combo = QComboBox()
        self.single_mode_combo.addItems(["frequency", "probability"])
        row_single_mode_l.addWidget(self.single_mode_combo, 1)
        self.plot_opt_grid.addWidget(self.row_single_mode, 2, 0, 1, 2)
        viz_param_layout.addLayout(self.plot_opt_grid)

        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(6)
        scope_row.addWidget(QLabel("Data scope"))
        self.data_scope_combo = QComboBox()
        self.data_scope_combo.addItem("Filtered rows", "filtered")
        self.data_scope_combo.setEnabled(False)
        scope_row.addWidget(self.data_scope_combo, 1)
        viz_param_layout.addLayout(scope_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        self.clear_all_btn = QPushButton("Clear-All: ON")
        self.clear_all_btn.setCheckable(True)
        self.clear_all_btn.setChecked(True)
        self.plot_btn = QPushButton("Draw")
        action_row.addWidget(self.clear_all_btn)
        action_row.addWidget(self.plot_btn)
        viz_param_layout.addLayout(action_row)
        plot_section_layout.addWidget(self.viz_param_wrap, 0, Qt.AlignmentFlag.AlignBottom)
        plot_section_layout.addSpacing(2)

        test_section = QWidget()
        test_section_layout = QVBoxLayout(test_section)
        test_section_layout.setContentsMargins(0, 0, 0, 0)
        test_section_layout.setSpacing(6)

        self.test_wrap = QFrame()
        self.test_wrap.setObjectName("vizParamWrap")
        test_form_layout = QVBoxLayout(self.test_wrap)
        test_form_layout.setContentsMargins(0, 0, 0, 0)
        test_form_layout.setSpacing(6)

        test_title = QLabel("Statistical Tests")
        test_title.setObjectName("sectionTitle")
        test_form_layout.addWidget(test_title)

        test_form = QFormLayout()
        self.test_type_combo = QComboBox()
        self.test_type_combo.addItems(
            [
                "descriptive statistics",
                "normality (shapiro)",
                "parametric test",
                "nonparametric test",
                "correlation",
                "chi-square",
            ]
        )
        self.test_option_combo = QComboBox()
        self.test_col_a_combo = QComboBox()
        self.test_col_b_combo = QComboBox()
        self.test_col_a_combo.addItem("none")
        self.test_col_b_combo.addItem("none")
        test_form.addRow("Describe/Test", self.test_type_combo)
        test_form.addRow("Option", self.test_option_combo)
        test_form.addRow("Data A", self.test_col_a_combo)
        test_form.addRow("Data B", self.test_col_b_combo)
        test_form_layout.addLayout(test_form)

        self.test_btn = QPushButton("Run Test")
        test_form_layout.addWidget(self.test_btn)
        test_section_layout.addWidget(self.test_wrap, 0, Qt.AlignmentFlag.AlignTop)
        test_status_title = QLabel("Test Status")
        test_status_title.setObjectName("sectionTitle")
        test_section_layout.addWidget(test_status_title, 0, Qt.AlignmentFlag.AlignLeft)
        self.test_report_box = QTextEdit()
        self.test_report_box.setObjectName("depvalReportBox")
        self.test_report_box.setReadOnly(True)
        self.test_report_box.setMinimumHeight(130)
        self.test_report_box.setPlaceholderText("Statistical test outputs.")
        test_section_layout.addWidget(self.test_report_box, 0)
        test_section_layout.addStretch(1)

        viz_split.addWidget(plot_section)
        viz_split.addWidget(test_section)
        viz_split.setStretchFactor(0, 1)
        viz_split.setStretchFactor(1, 2)
        viz_split.setSizes([260, 520])

        b_split.addWidget(table_wrap)
        b_split.addWidget(viz_wrap)
        b_split.setSizes([760, 500])

        root.addWidget(self.result_area, 1)

        self.drawer_width = 300
        self._drawer_open = False
        self.drawer_anim: QPropertyAnimation | None = None

        self.drawer = QFrame(self)
        self.drawer.setObjectName("depvalDrawer")
        self.drawer_layout = QVBoxLayout(self.drawer)
        self.drawer_layout.setContentsMargins(12, 10, 12, 12)
        self.drawer_layout.setSpacing(8)

        form = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItem("imported", "imported")
        form.addRow("Source", self.source_combo)
        self.treebank_combo = QComboBox()
        self.treebank_combo.addItem("all", "__all__")
        form.addRow("Treebank", self.treebank_combo)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["dep", "sent", "text", "distribution", "pvp", "all"])
        self.metric_combo = QComboBox()
        self.metric_combo.addItem("all")
        form.addRow("Level", self.level_combo)
        form.addRow("Metric", self.metric_combo)

        self.pvp_target_combo = QComboBox()
        self.pvp_target_combo.addItem("all")
        self.pvp_label_mode_combo = QComboBox()
        self.pvp_label_mode_combo.addItems(["pos", "deprel"])
        self.pvp_label_mode_combo.setCurrentText("deprel")
        form.addRow("PVP target", self.pvp_target_combo)
        form.addRow("PVP label", self.pvp_label_mode_combo)
        self.compute_jobs_spin = QSpinBox()
        self.compute_jobs_spin.setRange(1, max(1, int(os.cpu_count() or 1)))
        self.compute_jobs_spin.setValue(min(4, self.compute_jobs_spin.maximum()))
        self.compute_jobs_spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self.compute_jobs_spin.setToolTip("Worker jobs used by DepVal compute.")
        form.addRow("Jobs", self.compute_jobs_spin)
        self.drawer_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.compute_btn = QPushButton("Compute")
        self.compute_btn.setObjectName("accentButton")
        btn_row.addWidget(self.compute_btn)
        self.drawer_layout.addLayout(btn_row)

        self.drawer_layout.addStretch(1)

        self.drawer_overlay = QPushButton(self)
        self.drawer_overlay.setObjectName("drawerOverlay")
        self.drawer_overlay.setFlat(True)
        self.drawer_overlay.clicked.connect(self.close_drawer)
        self.drawer_overlay.hide()

        self.drawer_handle = DrawerHandleButton("Compute", self)
        self.drawer_handle.setObjectName("drawerHandle")
        self.drawer_handle.setFixedSize(34, 94)
        self.drawer_handle.clicked.connect(self.toggle_drawer)

        self.render_drawer_width = self.drawer_width
        self._render_drawer_open = False
        self.render_drawer_anim: QPropertyAnimation | None = None
        self.render_drawer = QFrame(self)
        self.render_drawer.setObjectName("depvalDrawer")
        self.render_drawer_layout = QVBoxLayout(self.render_drawer)
        self.render_drawer_layout.setContentsMargins(12, 10, 12, 12)
        self.render_drawer_layout.setSpacing(8)

        render_form = QFormLayout()
        self.render_treebank_combo = QComboBox()
        self.render_treebank_combo.addItem("all", "__all__")
        render_form.addRow("Corpus", self.render_treebank_combo)
        self.render_table_combo = QComboBox()
        self.render_table_combo.addItems(["dep metrics", "sent metrics", "text metrics", "distribution", "pvp", "all"])
        self.render_table_combo.setCurrentText("dep metrics")
        render_form.addRow("Table", self.render_table_combo)
        self.render_drawer_layout.addLayout(render_form)

        self.render_btn = QPushButton("Render")
        self.render_btn.setToolTip("Render table views from the latest cache without recompute.")
        self.render_drawer_layout.addWidget(self.render_btn)
        self.render_drawer_layout.addStretch(1)

        self.render_drawer_handle = DrawerHandleButton("Render", self)
        self.render_drawer_handle.setObjectName("drawerHandle")
        self.render_drawer_handle.setFixedSize(34, 94)
        self.render_drawer_handle.clicked.connect(self.toggle_render_drawer)

        self.convert_drawer_width = 300
        self._convert_drawer_open = False
        self.convert_drawer_anim: QPropertyAnimation | None = None
        self.convert_drawer = QFrame(self)
        self.convert_drawer.setObjectName("depvalDrawer")
        self.convert_drawer_layout = QVBoxLayout(self.convert_drawer)
        self.convert_drawer_layout.setContentsMargins(12, 10, 12, 12)
        self.convert_drawer_layout.setSpacing(8)

        convert_form = QFormLayout()
        self.convert_source_fmt_combo = QComboBox()
        self.convert_source_fmt_combo.addItems(list(SUPPORTED_FORMATS))
        self.convert_source_fmt_combo.setCurrentText("conll")
        self.convert_target_fmt_combo = QComboBox()
        self.convert_target_fmt_combo.addItems(list(SUPPORTED_FORMATS))
        self.convert_target_fmt_combo.setCurrentText("conllu")
        convert_form.addRow("Input format", self.convert_source_fmt_combo)
        convert_form.addRow("Output format", self.convert_target_fmt_combo)
        self.convert_drawer_layout.addLayout(convert_form)

        self.convert_treebank_combo = QComboBox()
        self.convert_treebank_combo.addItem("all", "__all__")
        convert_form.addRow("Treebank", self.convert_treebank_combo)

        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setObjectName("accentButton")
        self.convert_drawer_layout.addWidget(self.convert_btn)

        parse_sep = QFrame()
        parse_sep.setFrameShape(QFrame.Shape.HLine)
        parse_sep.setFrameShadow(QFrame.Shadow.Plain)
        self.convert_drawer_layout.addWidget(parse_sep)
        parse_title = QLabel("Parse TXT -> CoNLL-U")
        parse_title.setObjectName("sectionTitle")
        self.convert_drawer_layout.addWidget(parse_title)

        parse_import_row = QHBoxLayout()
        parse_import_row.setContentsMargins(0, 0, 0, 0)
        parse_import_row.setSpacing(6)
        self.parse_import_file_btn = QPushButton("Import TXT File")
        self.parse_import_folder_btn = QPushButton("Import TXT Folder")
        parse_import_row.addWidget(self.parse_import_file_btn, 1)
        parse_import_row.addWidget(self.parse_import_folder_btn, 1)
        self.convert_drawer_layout.addLayout(parse_import_row)

        parse_form = QFormLayout()
        parse_form.setContentsMargins(0, 0, 0, 0)
        parse_form.setSpacing(4)
        self.parse_txt_select_combo = QComboBox()
        self.parse_txt_select_combo.addItem("all", "__all__")
        self.parse_backend_combo = QComboBox()
        self.parse_backend_combo.addItems(["spacy", "stanza"])
        self.parse_lang_combo = QComboBox()
        self.parse_lang_combo.addItems(["en", "zh"])
        self.parse_model_combo = QComboBox()
        self.parse_model_combo.setEditable(True)
        self.parse_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        parse_form.addRow("Source", self.parse_txt_select_combo)
        parse_form.addRow("Parser", self.parse_backend_combo)
        parse_form.addRow("Language", self.parse_lang_combo)
        parse_form.addRow("Model", self.parse_model_combo)
        self.convert_drawer_layout.addLayout(parse_form)

        parse_run_row = QHBoxLayout()
        parse_run_row.setContentsMargins(0, 0, 0, 0)
        parse_run_row.setSpacing(6)
        self.parse_load_btn = QPushButton("Load")
        self.parse_run_btn = QPushButton("Run")
        self.parse_run_btn.setObjectName("accentButton")
        parse_run_row.addWidget(self.parse_load_btn, 1)
        parse_run_row.addWidget(self.parse_run_btn, 1)
        self.convert_drawer_layout.addLayout(parse_run_row)

        self.parse_status_label = QLabel("Ready.")
        self.parse_status_label.setObjectName("tinyHint")
        self.parse_status_label.setWordWrap(True)
        self.convert_drawer_layout.addWidget(self.parse_status_label)
        self.convert_drawer_layout.addStretch(1)

        self.convert_drawer_handle = DrawerHandleButton("Convert", self)
        self.convert_drawer_handle.setObjectName("drawerHandle")
        self.convert_drawer_handle.setFixedSize(34, 94)
        self.convert_drawer_handle.clicked.connect(self.toggle_convert_drawer)
        self.convert_drawer.hide()
        self.convert_drawer_handle.hide()

        self.parse_drawer_width = 1
        self._parse_drawer_open = False
        self.parse_drawer_anim: QPropertyAnimation | None = None
        self.parse_drawer = QFrame(self)
        self.parse_drawer.setObjectName("depvalDrawer")
        self.parse_drawer.hide()
        self.parse_drawer_handle = QPushButton(self)
        self.parse_drawer_handle.setFixedSize(0, 0)
        self.parse_drawer_handle.hide()

        self.lawfitter_drawer_width = self.drawer_width
        self._lawfitter_drawer_open = False
        self.lawfitter_drawer_anim: QPropertyAnimation | None = None
        self.lawfitter_drawer = QFrame(self)
        self.lawfitter_drawer.setObjectName("depvalDrawer")
        self.lawfitter_drawer_layout = QVBoxLayout(self.lawfitter_drawer)
        self.lawfitter_drawer_layout.setContentsMargins(12, 10, 12, 12)
        self.lawfitter_drawer_layout.setSpacing(8)

        law_form = QFormLayout()
        self.law_model_combo = QComboBox()
        self.law_model_combo.addItem("zipf", "zipf")
        self.law_variant_combo = QComboBox()
        self.law_variant_combo.addItem("default", "__default__")
        self.law_model_combo.addItem("custom", "custom")
        law_form.addRow("Law", self.law_model_combo)
        law_form.addRow("Variant", self.law_variant_combo)
        self.law_custom_input = QLineEdit("y=arg0*x+arg1")
        self.law_custom_input.setPlaceholderText("Custom formula, e.g. y=arg0*x+arg1")
        law_form.addRow("Custom", self.law_custom_input)
        self.lawfitter_drawer_layout.addLayout(law_form)

        self.law_fit_btn = QPushButton("Fit")
        self.law_fit_btn.setObjectName("accentButton")
        self.lawfitter_drawer_layout.addWidget(self.law_fit_btn)
        self.lawfitter_drawer_layout.addStretch(1)

        self.lawfitter_drawer_handle = DrawerHandleButton("Fitter", self)
        self.lawfitter_drawer_handle.setObjectName("drawerHandle")
        self.lawfitter_drawer_handle.setFixedSize(34, 94)
        self.lawfitter_drawer_handle.clicked.connect(self.toggle_lawfitter_drawer)

        self.save_drawer_width = self.drawer_width
        self._save_drawer_open = False
        self.save_drawer_anim: QPropertyAnimation | None = None
        self.save_drawer = QFrame(self)
        self.save_drawer.setObjectName("depvalDrawer")
        self.save_drawer_layout = QVBoxLayout(self.save_drawer)
        self.save_drawer_layout.setContentsMargins(12, 10, 12, 12)
        self.save_drawer_layout.setSpacing(8)

        save_title = QLabel("Save")
        save_title.setObjectName("sectionTitle")
        self.save_drawer_layout.addWidget(save_title)

        save_form = QFormLayout()
        self.save_treebank_combo = QComboBox()
        self.save_treebank_combo.addItem("all", "__all__")
        self.save_table_combo = QComboBox()
        self.save_table_combo.addItem("all", "all")
        self.save_table_combo.addItem("dep metrics", "dep")
        self.save_table_combo.addItem("sent metrics", "sent")
        self.save_table_combo.addItem("text metrics", "text")
        self.save_table_combo.addItem("distribution", "distribution")
        self.save_table_combo.addItem("pvp", "pvp")
        save_form.addRow("Treebank", self.save_treebank_combo)
        save_form.addRow("Table", self.save_table_combo)
        self.table_format_combo = QComboBox()
        self.table_format_combo.addItems(["csv", "tsv", "json"])
        self.table_format_combo.setCurrentText("csv")
        save_form.addRow("Format", self.table_format_combo)
        self.save_drawer_layout.addLayout(save_form)
        self.image_format_combo = QComboBox()
        self.image_format_combo.addItems(["png", "jpg", "svg", "pdf"])
        self.image_format_combo.setCurrentText("png")
        self.save_current_btn = QPushButton("Save Current Table")
        self.save_all_btn = QPushButton("Save All Tables")
        self.save_plot_btn = QPushButton("Save Current Image")
        self.save_current_btn.hide()
        self.save_all_btn.hide()
        self.save_plot_btn.hide()

        self.save_cache_btn = QPushButton("Save")
        self.save_cache_btn.setObjectName("accentButton")
        self.save_drawer_layout.addWidget(self.save_cache_btn)
        self.save_drawer_layout.addStretch(1)

        self.save_drawer_handle = DrawerHandleButton("Save", self)
        self.save_drawer_handle.setObjectName("drawerHandle")
        self.save_drawer_handle.setFixedSize(34, 94)
        self.save_drawer_handle.clicked.connect(self.toggle_save_drawer)

        self.drawer_divider = QFrame(self)
        self.drawer_divider.setObjectName("drawerDivider")
        self.drawer_divider.setFrameShape(QFrame.Shape.VLine)
        self.drawer_divider.setFrameShadow(QFrame.Shadow.Plain)
        self.drawer_divider.setStyleSheet("color:#4d5561; background:#4d5561;")
        self.drawer_divider.setFixedWidth(1)

        self.drawer_divider.raise_()
        self.drawer.raise_()
        self.drawer_handle.raise_()
        self.render_drawer.raise_()
        self.render_drawer_handle.raise_()
        self.lawfitter_drawer.raise_()
        self.lawfitter_drawer_handle.raise_()
        self.save_drawer.raise_()
        self.save_drawer_handle.raise_()
        self._update_drawer_geometry(initial=True)
        if not self._event_filter_installed and QApplication.instance() is not None:
            QApplication.instance().installEventFilter(self)
            self._event_filter_installed = True
        self._refresh_law_models()
        self._on_law_model_changed(self.law_model_combo.currentText())
        self._refresh_parse_language_options()
        self._refresh_parse_model_options()
        self._reset_metrics_for_level()
        self._append_report("Ready.")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_drawer_geometry(initial=False)

    def _update_drawer_geometry(self, initial: bool) -> None:
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        page_w = self.width()
        handle_col_x = page_w - self.drawer_handle.width()
        handle_offset_y = -12
        divider_x = max(0, handle_col_x - 2)
        self.drawer_divider.setGeometry(divider_x, y + 2, 1, max(1, h - 4))

        open_x = divider_x - self.drawer_width
        closed_x = divider_x
        x = open_x if self._drawer_open else closed_x
        self.drawer.setGeometry(x, y, self.drawer_width, h)
        handle_x = handle_col_x
        render_open_x = divider_x - self.render_drawer_width
        render_closed_x = divider_x
        render_x = render_open_x if self._render_drawer_open else render_closed_x
        self.render_drawer.setGeometry(render_x, y, self.render_drawer_width, h)
        render_handle_x = handle_col_x
        convert_open_x = divider_x - self.convert_drawer_width
        convert_closed_x = divider_x
        convert_x = convert_open_x if self._convert_drawer_open else convert_closed_x
        self.convert_drawer.setGeometry(convert_x, y, self.convert_drawer_width, h)
        cursor_y = y + 8 + handle_offset_y
        self.drawer_handle.move(handle_x, cursor_y)
        cursor_y += self.drawer_handle.height() + 8
        render_handle_y = cursor_y
        self.render_drawer_handle.move(render_handle_x, render_handle_y)
        cursor_y = render_handle_y + self.render_drawer_handle.height() + 8
        law_open_x = divider_x - self.lawfitter_drawer_width
        law_closed_x = divider_x
        law_x = law_open_x if self._lawfitter_drawer_open else law_closed_x
        self.lawfitter_drawer.setGeometry(law_x, y, self.lawfitter_drawer_width, h)
        law_handle_x = handle_col_x
        law_handle_y = cursor_y
        self.lawfitter_drawer_handle.move(law_handle_x, law_handle_y)
        cursor_y = law_handle_y + self.lawfitter_drawer_handle.height() + 8
        save_open_x = divider_x - self.save_drawer_width
        save_closed_x = divider_x
        save_x = save_open_x if self._save_drawer_open else save_closed_x
        self.save_drawer.setGeometry(save_x, y, self.save_drawer_width, h)
        save_handle_x = handle_col_x
        save_handle_y = cursor_y
        self.save_drawer_handle.move(save_handle_x, save_handle_y)
        if initial:
            self.drawer.hide()
            self.render_drawer.hide()
            self.convert_drawer.hide()
            self.parse_drawer.hide()
            self.lawfitter_drawer.hide()
            self.save_drawer.hide()

    def toggle_drawer(self) -> None:
        if self._drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def _is_any_drawer_open_except(self, name: str) -> bool:
        return (
            (name != "compute" and self._drawer_open)
            or (name != "render" and self._render_drawer_open)
            or (name != "convert" and self._convert_drawer_open)
            or (name != "parse" and self._parse_drawer_open)
            or (name != "lawfitter" and self._lawfitter_drawer_open)
            or (name != "save" and self._save_drawer_open)
        )

    def _switch_drawer_instant(self, target: str) -> None:
        self._drawer_open = target == "compute"
        self._render_drawer_open = target == "render"
        self._convert_drawer_open = target == "convert"
        self._parse_drawer_open = target == "parse"
        self._lawfitter_drawer_open = target == "lawfitter"
        self._save_drawer_open = target == "save"
        self.drawer.setVisible(self._drawer_open)
        self.render_drawer.setVisible(self._render_drawer_open)
        self.convert_drawer.setVisible(self._convert_drawer_open)
        self.parse_drawer.setVisible(self._parse_drawer_open)
        self.lawfitter_drawer.setVisible(self._lawfitter_drawer_open)
        self.save_drawer.setVisible(self._save_drawer_open)
        if self._drawer_open:
            self.drawer.raise_()
            self.drawer_handle.raise_()
        if self._render_drawer_open:
            self.render_drawer.raise_()
            self.render_drawer_handle.raise_()
        if self._convert_drawer_open:
            self.convert_drawer.raise_()
            self.convert_drawer_handle.raise_()
        if self._parse_drawer_open:
            self.parse_drawer.raise_()
            self.parse_drawer_handle.raise_()
        if self._lawfitter_drawer_open:
            self.lawfitter_drawer.raise_()
            self.lawfitter_drawer_handle.raise_()
        if self._save_drawer_open:
            self.save_drawer.raise_()
            self.save_drawer_handle.raise_()
        self._update_drawer_geometry(initial=False)

    def open_drawer(self) -> None:
        if self._drawer_open:
            return
        if self._is_any_drawer_open_except("compute"):
            self._switch_drawer_instant("compute")
            return
        if self._render_drawer_open:
            self.close_render_drawer()
        if self._convert_drawer_open:
            self.close_convert_drawer()
        if self._parse_drawer_open:
            self.close_parse_drawer()
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        if self._parse_drawer_open:
            self.close_parse_drawer()
        if self._save_drawer_open:
            self.close_save_drawer()
        self._drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.drawer.show()
        self.drawer.raise_()
        self.drawer_handle.raise_()
        if self.drawer_anim:
            self.drawer_anim.stop()
        self.drawer_anim = QPropertyAnimation(self.drawer, b"geometry", self)
        self.drawer_anim.setDuration(170)
        self.drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.drawer_width
        closed_x = divider_x
        self.drawer_anim.setStartValue(QRect(closed_x, y, self.drawer_width, h))
        self.drawer_anim.setEndValue(QRect(open_x, y, self.drawer_width, h))
        self.drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_drawer(self) -> None:
        if not self._drawer_open:
            return
        self._drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.drawer_anim:
            self.drawer_anim.stop()
        self.drawer_anim = QPropertyAnimation(self.drawer, b"geometry", self)
        self.drawer_anim.setDuration(170)
        self.drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.drawer_width
        closed_x = divider_x
        self.drawer_anim.setStartValue(QRect(open_x, y, self.drawer_width, h))
        self.drawer_anim.setEndValue(QRect(closed_x, y, self.drawer_width, h))
        self.drawer_anim.finished.connect(self._after_drawer_closed)
        self.drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_drawer_closed(self) -> None:
        if not self._drawer_open:
            self.drawer.hide()
            self._update_drawer_geometry(initial=False)

    def toggle_render_drawer(self) -> None:
        if self._render_drawer_open:
            self.close_render_drawer()
        else:
            self.open_render_drawer()

    def open_render_drawer(self) -> None:
        if self._render_drawer_open:
            return
        if self._is_any_drawer_open_except("render"):
            self._switch_drawer_instant("render")
            return
        if self._drawer_open:
            self.close_drawer()
        if self._convert_drawer_open:
            self.close_convert_drawer()
        if self._parse_drawer_open:
            self.close_parse_drawer()
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        if self._save_drawer_open:
            self.close_save_drawer()
        if self._parse_drawer_open:
            self.close_parse_drawer()
        self._render_drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.render_drawer.show()
        self.render_drawer.raise_()
        self.render_drawer_handle.raise_()
        if self.render_drawer_anim:
            self.render_drawer_anim.stop()
        self.render_drawer_anim = QPropertyAnimation(self.render_drawer, b"geometry", self)
        self.render_drawer_anim.setDuration(170)
        self.render_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.render_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.render_drawer_width
        closed_x = divider_x
        self.render_drawer_anim.setStartValue(QRect(closed_x, y, self.render_drawer_width, h))
        self.render_drawer_anim.setEndValue(QRect(open_x, y, self.render_drawer_width, h))
        self.render_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_render_drawer(self) -> None:
        if not self._render_drawer_open:
            return
        self._render_drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.render_drawer_anim:
            self.render_drawer_anim.stop()
        self.render_drawer_anim = QPropertyAnimation(self.render_drawer, b"geometry", self)
        self.render_drawer_anim.setDuration(170)
        self.render_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.render_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.render_drawer_width
        closed_x = divider_x
        self.render_drawer_anim.setStartValue(QRect(open_x, y, self.render_drawer_width, h))
        self.render_drawer_anim.setEndValue(QRect(closed_x, y, self.render_drawer_width, h))
        self.render_drawer_anim.finished.connect(self._after_render_drawer_closed)
        self.render_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_render_drawer_closed(self) -> None:
        if not self._render_drawer_open:
            self.render_drawer.hide()
            self._update_drawer_geometry(initial=False)

    def toggle_convert_drawer(self) -> None:
        if self._convert_drawer_open:
            self.close_convert_drawer()
        else:
            self.open_convert_drawer()

    def open_convert_drawer(self) -> None:
        if self._convert_drawer_open:
            return
        if self._is_any_drawer_open_except("convert"):
            self._switch_drawer_instant("convert")
            return
        if self._drawer_open:
            self.close_drawer()
        if self._render_drawer_open:
            self.close_render_drawer()
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        if self._save_drawer_open:
            self.close_save_drawer()
        self._convert_drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.convert_drawer.show()
        self.convert_drawer.raise_()
        self.convert_drawer_handle.raise_()
        if self.convert_drawer_anim:
            self.convert_drawer_anim.stop()
        self.convert_drawer_anim = QPropertyAnimation(self.convert_drawer, b"geometry", self)
        self.convert_drawer_anim.setDuration(170)
        self.convert_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.convert_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.convert_drawer_width
        closed_x = divider_x
        self.convert_drawer_anim.setStartValue(QRect(closed_x, y, self.convert_drawer_width, h))
        self.convert_drawer_anim.setEndValue(QRect(open_x, y, self.convert_drawer_width, h))
        self.convert_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_convert_drawer(self) -> None:
        if not self._convert_drawer_open:
            return
        self._convert_drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.convert_drawer_anim:
            self.convert_drawer_anim.stop()
        self.convert_drawer_anim = QPropertyAnimation(self.convert_drawer, b"geometry", self)
        self.convert_drawer_anim.setDuration(170)
        self.convert_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.convert_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.convert_drawer_width
        closed_x = divider_x
        self.convert_drawer_anim.setStartValue(QRect(open_x, y, self.convert_drawer_width, h))
        self.convert_drawer_anim.setEndValue(QRect(closed_x, y, self.convert_drawer_width, h))
        self.convert_drawer_anim.finished.connect(self._after_convert_drawer_closed)
        self.convert_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_convert_drawer_closed(self) -> None:
        if not self._convert_drawer_open:
            self.convert_drawer.hide()
            self._update_drawer_geometry(initial=False)

    def toggle_parse_drawer(self) -> None:
        if self._parse_drawer_open:
            self.close_parse_drawer()
        else:
            self.open_parse_drawer()

    def open_parse_drawer(self) -> None:
        if self._parse_drawer_open:
            return
        if self._is_any_drawer_open_except("parse"):
            self._switch_drawer_instant("parse")
            return
        if self._drawer_open:
            self.close_drawer()
        if self._render_drawer_open:
            self.close_render_drawer()
        if self._convert_drawer_open:
            self.close_convert_drawer()
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        if self._save_drawer_open:
            self.close_save_drawer()
        self._parse_drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.parse_drawer.show()
        self.parse_drawer.raise_()
        self.parse_drawer_handle.raise_()
        if self.parse_drawer_anim:
            self.parse_drawer_anim.stop()
        self.parse_drawer_anim = QPropertyAnimation(self.parse_drawer, b"geometry", self)
        self.parse_drawer_anim.setDuration(170)
        self.parse_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.parse_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.parse_drawer_width
        closed_x = divider_x
        self.parse_drawer_anim.setStartValue(QRect(closed_x, y, self.parse_drawer_width, h))
        self.parse_drawer_anim.setEndValue(QRect(open_x, y, self.parse_drawer_width, h))
        self.parse_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_parse_drawer(self) -> None:
        if not self._parse_drawer_open:
            return
        self._parse_drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.parse_drawer_anim:
            self.parse_drawer_anim.stop()
        self.parse_drawer_anim = QPropertyAnimation(self.parse_drawer, b"geometry", self)
        self.parse_drawer_anim.setDuration(170)
        self.parse_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.parse_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.parse_drawer_width
        closed_x = divider_x
        self.parse_drawer_anim.setStartValue(QRect(open_x, y, self.parse_drawer_width, h))
        self.parse_drawer_anim.setEndValue(QRect(closed_x, y, self.parse_drawer_width, h))
        self.parse_drawer_anim.finished.connect(self._after_parse_drawer_closed)
        self.parse_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_parse_drawer_closed(self) -> None:
        if not self._parse_drawer_open:
            self.parse_drawer.hide()
            self._update_drawer_geometry(initial=False)

    def toggle_lawfitter_drawer(self) -> None:
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        else:
            self.open_lawfitter_drawer()

    def open_lawfitter_drawer(self) -> None:
        if self._lawfitter_drawer_open:
            return
        if self._is_any_drawer_open_except("lawfitter"):
            self._switch_drawer_instant("lawfitter")
            return
        if self._drawer_open:
            self.close_drawer()
        if self._render_drawer_open:
            self.close_render_drawer()
        if self._convert_drawer_open:
            self.close_convert_drawer()
        if self._parse_drawer_open:
            self.close_parse_drawer()
        if self._save_drawer_open:
            self.close_save_drawer()
        self._lawfitter_drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.lawfitter_drawer.show()
        self.lawfitter_drawer.raise_()
        self.lawfitter_drawer_handle.raise_()
        if self.lawfitter_drawer_anim:
            self.lawfitter_drawer_anim.stop()
        self.lawfitter_drawer_anim = QPropertyAnimation(self.lawfitter_drawer, b"geometry", self)
        self.lawfitter_drawer_anim.setDuration(170)
        self.lawfitter_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.lawfitter_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.lawfitter_drawer_width
        closed_x = divider_x
        self.lawfitter_drawer_anim.setStartValue(QRect(closed_x, y, self.lawfitter_drawer_width, h))
        self.lawfitter_drawer_anim.setEndValue(QRect(open_x, y, self.lawfitter_drawer_width, h))
        self.lawfitter_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_lawfitter_drawer(self) -> None:
        if not self._lawfitter_drawer_open:
            return
        self._lawfitter_drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.lawfitter_drawer_anim:
            self.lawfitter_drawer_anim.stop()
        self.lawfitter_drawer_anim = QPropertyAnimation(self.lawfitter_drawer, b"geometry", self)
        self.lawfitter_drawer_anim.setDuration(170)
        self.lawfitter_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.lawfitter_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.lawfitter_drawer_width
        closed_x = divider_x
        self.lawfitter_drawer_anim.setStartValue(QRect(open_x, y, self.lawfitter_drawer_width, h))
        self.lawfitter_drawer_anim.setEndValue(QRect(closed_x, y, self.lawfitter_drawer_width, h))
        self.lawfitter_drawer_anim.finished.connect(self._after_lawfitter_drawer_closed)
        self.lawfitter_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_lawfitter_drawer_closed(self) -> None:
        if not self._lawfitter_drawer_open:
            self.lawfitter_drawer.hide()
            self._update_drawer_geometry(initial=False)

    def toggle_save_drawer(self) -> None:
        if self._save_drawer_open:
            self.close_save_drawer()
        else:
            self.open_save_drawer()

    def open_save_drawer(self) -> None:
        if self._save_drawer_open:
            return
        if self._is_any_drawer_open_except("save"):
            self._switch_drawer_instant("save")
            return
        if self._drawer_open:
            self.close_drawer()
        if self._render_drawer_open:
            self.close_render_drawer()
        if self._convert_drawer_open:
            self.close_convert_drawer()
        if self._lawfitter_drawer_open:
            self.close_lawfitter_drawer()
        self._save_drawer_open = True
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        self.save_drawer.show()
        self.save_drawer.raise_()
        self.save_drawer_handle.raise_()
        if self.save_drawer_anim:
            self.save_drawer_anim.stop()
        self.save_drawer_anim = QPropertyAnimation(self.save_drawer, b"geometry", self)
        self.save_drawer_anim.setDuration(170)
        self.save_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.save_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.save_drawer_width
        closed_x = divider_x
        self.save_drawer_anim.setStartValue(QRect(closed_x, y, self.save_drawer_width, h))
        self.save_drawer_anim.setEndValue(QRect(open_x, y, self.save_drawer_width, h))
        self.save_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def close_save_drawer(self) -> None:
        if not self._save_drawer_open:
            return
        self._save_drawer_open = False
        title_offset = 2
        y = title_offset
        h = max(240, self.height() - title_offset - 10)
        if self.save_drawer_anim:
            self.save_drawer_anim.stop()
        self.save_drawer_anim = QPropertyAnimation(self.save_drawer, b"geometry", self)
        self.save_drawer_anim.setDuration(170)
        self.save_drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        handle_col_x = self.width() - self.save_drawer_handle.width()
        divider_x = max(0, handle_col_x - 2)
        open_x = divider_x - self.save_drawer_width
        closed_x = divider_x
        self.save_drawer_anim.setStartValue(QRect(open_x, y, self.save_drawer_width, h))
        self.save_drawer_anim.setEndValue(QRect(closed_x, y, self.save_drawer_width, h))
        self.save_drawer_anim.finished.connect(self._after_save_drawer_closed)
        self.save_drawer_anim.start()
        self._update_drawer_geometry(initial=False)

    def _after_save_drawer_closed(self) -> None:
        if not self._save_drawer_open:
            self.save_drawer.hide()
            self._update_drawer_geometry(initial=False)

    def collapse_all_drawers(self) -> None:
        self.close_drawer()
        self.close_render_drawer()
        self.close_convert_drawer()
        self.close_parse_drawer()
        self.close_lawfitter_drawer()
        self.close_save_drawer()

    def eventFilter(self, obj, event):  # pragma: no cover - UI interaction
        try:
            if event is not None and event.type() == QEvent.Type.MouseButtonDblClick:
                if obj is getattr(self, "plot_web", None):
                    self._open_plot_zoom_dialog()
                    return True
                if obj is getattr(self, "plot_preview", None):
                    self._open_plot_zoom_dialog()
                    return True
                if (
                    getattr(self, "plot_scroll", None) is not None
                    and obj is getattr(self.plot_scroll, "viewport", lambda: None)()
                ):
                    self._open_plot_zoom_dialog()
                    return True
        except Exception:
            pass
        if (
            not self._drawer_open
            and not self._render_drawer_open
            and not self._convert_drawer_open
            and not self._parse_drawer_open
            and not self._lawfitter_drawer_open
            and not self._save_drawer_open
        ):
            return super().eventFilter(obj, event)
        try:
            if event.type() == event.Type.MouseButtonPress:
                gp = event.globalPosition().toPoint()
                in_drawer = self.drawer.geometry().contains(self.mapFromGlobal(gp))
                in_handle = self.drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                in_render_drawer = self.render_drawer.geometry().contains(self.mapFromGlobal(gp))
                in_render_handle = self.render_drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                in_convert_drawer = self.convert_drawer.geometry().contains(self.mapFromGlobal(gp))
                in_convert_handle = self.convert_drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                in_parse_drawer = self.parse_drawer.geometry().contains(self.mapFromGlobal(gp))
                in_parse_handle = self.parse_drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                in_law_drawer = self.lawfitter_drawer.geometry().contains(self.mapFromGlobal(gp))
                in_law_handle = self.lawfitter_drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                in_save_drawer = self.save_drawer.geometry().contains(self.mapFromGlobal(gp))
                in_save_handle = self.save_drawer_handle.geometry().contains(self.mapFromGlobal(gp))
                if (
                    not in_drawer
                    and not in_handle
                    and not in_render_drawer
                    and not in_render_handle
                    and not in_convert_drawer
                    and not in_convert_handle
                    and not in_parse_drawer
                    and not in_parse_handle
                    and not in_law_drawer
                    and not in_law_handle
                    and not in_save_drawer
                    and not in_save_handle
                ):
                    self.close_drawer()
                    self.close_render_drawer()
                    self.close_convert_drawer()
                    self.close_parse_drawer()
                    self.close_lawfitter_drawer()
                    self.close_save_drawer()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _wire(self) -> None:
        self.level_combo.currentTextChanged.connect(self._reset_metrics_for_level)
        self.compute_btn.clicked.connect(self.compute)
        self.treebank_combo.currentTextChanged.connect(self._refresh_pvp_labels)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        self.save_current_btn.clicked.connect(self.save_current_result_dialog)
        self.save_all_btn.clicked.connect(self.save_all_results_dialog)
        self.save_plot_btn.clicked.connect(self.save_current_plot_dialog)
        self.save_cache_btn.clicked.connect(self.save_cached_content_dialog)
        self.convert_btn.clicked.connect(self.convert_treebanks_to_cache)
        self.parse_import_file_btn.clicked.connect(self._on_parse_import_txt_file)
        self.parse_import_folder_btn.clicked.connect(self._on_parse_import_txt_folder)
        self.parse_backend_combo.currentTextChanged.connect(self._on_parse_backend_changed)
        self.parse_lang_combo.currentTextChanged.connect(self._refresh_parse_model_options)
        self.parse_load_btn.clicked.connect(self._load_parse_model_from_drawer)
        self.parse_run_btn.clicked.connect(self._run_parse_from_drawer)
        self.law_model_combo.currentTextChanged.connect(self._on_law_model_changed)
        self.law_variant_combo.currentTextChanged.connect(self._on_law_variant_changed)
        self.law_fit_btn.clicked.connect(self.fit_distribution_with_lawfitter)
        self.plot_btn.clicked.connect(self.plot_current_tab)
        self.clear_all_btn.toggled.connect(self._on_clear_toggle)
        self.result_tabs.currentChanged.connect(lambda _: self._refresh_plot_columns())
        self.plot_dim_combo.currentTextChanged.connect(self._on_plot_dim_changed)
        self.plot_col_a_combo.currentTextChanged.connect(self._on_plot_selection_changed)
        self.plot_col_b_combo.currentTextChanged.connect(self._on_plot_selection_changed)
        self.chart_type.currentTextChanged.connect(self._on_plot_selection_changed)
        self.test_type_combo.currentTextChanged.connect(self._on_test_type_changed)
        self.test_btn.clicked.connect(self.run_stat_test)
        self.render_btn.clicked.connect(lambda: self.render_cached_results(auto_plot=False))
        self._on_test_type_changed(self.test_type_combo.currentText())
        self._on_plot_dim_changed(self.plot_dim_combo.currentText())
        try:
            if getattr(self, "plot_web", None) is not None:
                self.plot_web.installEventFilter(self)
            if getattr(self, "plot_preview", None) is not None:
                self.plot_preview.installEventFilter(self)
            if getattr(self, "plot_scroll", None) is not None and self.plot_scroll.viewport() is not None:
                self.plot_scroll.viewport().installEventFilter(self)
        except Exception:
            pass

    def _append_report(self, msg: str) -> None:
        if not msg:
            return
        self.report_box.append(msg)

    def _append_test_report(self, msg: str) -> None:
        if not msg:
            return
        self.test_report_box.append(msg)

    def _get_depval_analyzer(self):
        if self._depval_analyzer_cls is not None:
            return self._depval_analyzer_cls
        from quansyn.depval import DepValAnalyzer  # lazy import for optional runtime dependency

        self._depval_analyzer_cls = DepValAnalyzer
        return self._depval_analyzer_cls

    def _get_lawfitter_module(self):
        if self._lawfitter_module is not None:
            return self._lawfitter_module
        try:
            self._lawfitter_module = importlib.import_module("quansyn.lawfitter")
        except Exception:
            self._lawfitter_module = self._build_lawfitter_fallback()
        return self._lawfitter_module

    def _build_lawfitter_fallback(self):
        try:
            np_mod = importlib.import_module("numpy")
            scipy_opt = importlib.import_module("scipy.optimize")
        except Exception:
            return None

        class _FallbackLawFitter:
            @staticmethod
            def piotrovski_altmann_law(variant=None):
                if variant == "partial":
                    return lambda t, a, b, C: C / (1 + a * np_mod.exp((-b) * t))
                if variant in {"reversiable", "reversible"}:
                    return lambda t, a, b, C, c: C / (1 + a * np_mod.exp((-b) * t + c * t**2))
                return lambda t, a, b: 1 / (1 + a * np_mod.exp((-b) * t))

            @staticmethod
            def zipf_law(variant=None):
                return lambda r, b, C: C * r ** (-b)

            @staticmethod
            def menzerath_altmann_law(variant=None):
                if variant == "simplified form":
                    return lambda x, a, c: a * np_mod.exp(-c * x)
                if variant == "complex form":
                    return lambda x, a, b, c: a * x ** (-b) * np_mod.exp(-c * x)
                return lambda x, a, b: a * x ** (-b)

            @staticmethod
            def heap_law(variant=None):
                return lambda n, K, beta: K * n**beta

            @staticmethod
            def brevity_law(variant=None):
                return lambda F, a, b: a * F ** (-b)

            laws = {
                "piotrovski_altmann": piotrovski_altmann_law.__func__,
                "zipf": zipf_law.__func__,
                "menzerath_altmann": menzerath_altmann_law.__func__,
                "menzerath": menzerath_altmann_law.__func__,
                "heap": heap_law.__func__,
                "herdan": heap_law.__func__,
                "brevity": brevity_law.__func__,
            }

            @staticmethod
            def fit(data, law_name: str | None = None, variant=None, customized_law=None):
                if law_name is not None and law_name not in _FallbackLawFitter.laws:
                    raise ValueError(f"Unsupported laws: {law_name}")
                fit_func = customized_law if law_name is None else _FallbackLawFitter.laws[law_name](variant=variant)
                if fit_func is None:
                    raise ValueError("No fitting function available.")
                arr = np_mod.array(data, dtype=float)
                params, _ = scipy_opt.curve_fit(fit_func, arr[0], arr[1], maxfev=10000)
                y_fit = fit_func(arr[0], *params)
                y_actual = arr[1]
                ss_res = np_mod.sum((y_actual - y_fit) ** 2)
                ss_tot = np_mod.sum((y_actual - np_mod.mean(y_actual)) ** 2)
                r2 = 1.0 - (ss_res / ss_tot) if ss_tot else 1.0
                return {"params": params, "r^2": r2}

        return _FallbackLawFitter

    def _refresh_law_models(self) -> None:
        mod = self._get_lawfitter_module()
        models = ["zipf"]
        if mod is not None and hasattr(mod, "laws"):
            try:
                models = sorted(str(k) for k in getattr(mod, "laws").keys())
            except Exception:
                models = ["zipf"]
        prev_model = str(self.law_model_combo.currentData() or "").strip().lower()
        self.law_model_combo.blockSignals(True)
        self.law_model_combo.clear()
        for name in models:
            idx = self.law_model_combo.count()
            self.law_model_combo.addItem(name, name)
            self.law_model_combo.setItemData(idx, self._law_formula_label(mod, name, variant=None), Qt.ItemDataRole.ToolTipRole)
        self.law_model_combo.addItem("custom", "custom")
        self.law_model_combo.setItemData(
            self.law_model_combo.count() - 1,
            "Custom formula from the Custom field, e.g. y=arg0*x+arg1",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.law_model_combo.blockSignals(False)
        target_idx = self.law_model_combo.findData(prev_model) if prev_model else -1
        self.law_model_combo.setCurrentIndex(target_idx if target_idx >= 0 else 0)
        self._refresh_law_variants()
        self._update_law_tooltips()

    def _on_law_model_changed(self, value: str) -> None:
        model_key = str(self.law_model_combo.currentData() or value or "").strip().lower()
        self.law_custom_input.setVisible(model_key == "custom")
        self._refresh_law_variants()
        self._update_law_tooltips()

    def _on_law_variant_changed(self, _value: str) -> None:
        self._update_law_tooltips()

    @staticmethod
    def _extract_variant_candidates(factory) -> list[str]:
        try:
            src = inspect.getsource(factory)
        except Exception:
            return []
        seen: set[str] = set()
        variants: list[str] = []
        for raw in re.findall(r"variant\s*==\s*['\"]([^'\"]+)['\"]", src):
            v = str(raw).strip()
            if not v or v in seen:
                continue
            seen.add(v)
            variants.append(v)
        return variants

    @staticmethod
    def _fallback_law_variants(model_key: str) -> list[str]:
        return {
            "piotrovski_altmann": ["partial", "reversiable"],
            "menzerath_altmann": ["simplified form", "complex form"],
            "menzerath": ["simplified form", "complex form"],
        }.get(str(model_key or "").strip().lower(), [])

    def _refresh_law_variants(self) -> None:
        mod = self._get_lawfitter_module()
        model_key = str(self.law_model_combo.currentData() or "").strip().lower()
        prev_variant = str(self.law_variant_combo.currentData() or "__default__")
        self.law_variant_combo.blockSignals(True)
        self.law_variant_combo.clear()
        if model_key == "custom":
            self.law_variant_combo.addItem("none", "__default__")
            self.law_variant_combo.setEnabled(False)
            self.law_variant_combo.setToolTip("Custom mode does not use built-in variants.")
            self.law_variant_combo.blockSignals(False)
            return
        self.law_variant_combo.setEnabled(True)
        self.law_variant_combo.addItem("default", "__default__")
        if mod is not None and hasattr(mod, "laws"):
            try:
                factory = getattr(mod, "laws", {}).get(model_key)
                if callable(factory):
                    variants = self._extract_variant_candidates(factory) or self._fallback_law_variants(model_key)
                    for variant in variants:
                        self.law_variant_combo.addItem(variant, variant)
            except Exception:
                for variant in self._fallback_law_variants(model_key):
                    self.law_variant_combo.addItem(variant, variant)
        for i in range(self.law_variant_combo.count()):
            data = self.law_variant_combo.itemData(i)
            v = None if data in {None, "__default__", ""} else str(data)
            self.law_variant_combo.setItemData(
                i,
                self._law_formula_label(mod, model_key, variant=v),
                Qt.ItemDataRole.ToolTipRole,
            )
        idx = self.law_variant_combo.findData(prev_variant)
        self.law_variant_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.law_variant_combo.blockSignals(False)

    def _current_law_variant_value(self):
        data = self.law_variant_combo.currentData()
        if data in {None, "__default__", ""}:
            return None
        return str(data)

    @staticmethod
    def _extract_formula_from_callable(func) -> str:
        try:
            src = inspect.getsource(func)
        except Exception:
            return ""
        for raw in src.splitlines():
            line = raw.strip()
            if line.startswith("return "):
                expr = line[len("return ") :].strip()
                if expr:
                    expr = expr.replace("**", "^")
                    return f"y = {expr}"
        return ""

    def _law_formula_label(self, mod, model_name: str, variant=None) -> str:
        key = str(model_name or "").strip().lower()
        vkey = str(variant or "").strip().lower()
        known: dict[tuple[str, str], str] = {
            ("zipf", ""): "y = C * x^(-b)",
            ("heap", ""): "y = K * x^beta",
            ("herdan", ""): "y = K * x^beta",
            ("brevity", ""): "y = a * x^(-b)",
            ("menzerath", ""): "y = a * x^(-b)",
            ("menzerath_altmann", ""): "y = a * x^(-b)",
            ("menzerath_altmann", "simplified form"): "y = a * e^(-c*x)",
            ("menzerath_altmann", "complex form"): "y = a * x^(-b) * e^(-c*x)",
            ("piotrovski_altmann", ""): "y = 1 / (1 + a * e^(-b*x))",
            ("piotrovski_altmann", "partial"): "y = C / (1 + a * e^(-b*x))",
            ("piotrovski_altmann", "reversiable"): "y = C / (1 + a * e^(-b*x + c*x^2))",
        }
        if (key, vkey) in known:
            return known[(key, vkey)]
        if (key, "") in known:
            return known[(key, "")]
        legacy_known: dict[str, str] = {
            "zipf": "y = a * x^b",
            "heap": "y = a * x^b",
            "brevity": "y = a * x^b",
            "menzerath_altmann": "y = a * x^b * e^(-c*x)",
            "piotrovski_altmann": "y = a / (1 + b * e^(-c*x))",
        }
        if key in legacy_known:
            return legacy_known[key]
        if mod is not None and hasattr(mod, "laws"):
            try:
                law_factory = mod.laws.get(key)
                if callable(law_factory):
                    law_callable = law_factory(variant=variant)
                    extracted = self._extract_formula_from_callable(law_callable)
                    if extracted:
                        return extracted
            except Exception:
                pass
        return f"y = f_{key}(x)"

    def _update_law_tooltips(self) -> None:
        mod = self._get_lawfitter_module()
        model_key = str(self.law_model_combo.currentData() or "").strip().lower()
        if model_key == "custom":
            self.law_model_combo.setToolTip("Custom formula from the Custom field, e.g. y=arg0*x+arg1")
            self.law_variant_combo.setToolTip("Custom mode does not use built-in variants.")
            return
        variant = self._current_law_variant_value()
        formula = self._law_formula_label(mod, model_key, variant=variant)
        self.law_model_combo.setToolTip(formula)
        self.law_variant_combo.setToolTip(formula)

    def _current_distribution_xy(self) -> tuple[list[float], list[float]] | None:
        table = self._current_table()
        if table is None or self._table_column_count(table) < 2:
            return None
        model = self._result_model(table)
        if model is not None:
            head0 = model.headers[0].strip().lower() if model.headers else ""
            head1 = model.headers[1].strip().lower() if len(model.headers) > 1 else ""
            value_pairs = [
                (row[0] if len(row) > 0 else "", row[1] if len(row) > 1 else "")
                for row in model.to_rows("filtered")[1]
            ]
        else:
            h0 = table.horizontalHeaderItem(0)
            h1 = table.horizontalHeaderItem(1)
            head0 = (h0.text() if h0 else "").replace(" *", "").strip().lower()
            head1 = (h1.text() if h1 else "").replace(" *", "").strip().lower()
            value_pairs = []
            for r in range(table.rowCount()):
                if table.isRowHidden(r):
                    continue
                i0 = table.item(r, 0)
                i1 = table.item(r, 1)
                if i0 is None or i1 is None:
                    continue
                value_pairs.append((i0.text(), i1.text()))
        if "value" not in head0 or "frequency" not in head1:
            return None
        xs: list[float] = []
        ys: list[float] = []
        for v0, v1 in value_pairs:
            try:
                x = float(str(v0).strip())
                y = float(str(v1).strip())
            except Exception:
                continue
            if x != x or y != y:
                continue
            if abs(x) == float("inf") or abs(y) == float("inf"):
                continue
            xs.append(x)
            ys.append(y)
        if len(xs) < 3:
            return None
        return xs, ys

    def _build_custom_law(self, expr: str):
        expr = expr.strip()
        if not expr:
            raise ValueError("Empty custom model expression.")
        if "=" in expr:
            left, right = expr.split("=", 1)
            if left.strip().lower() not in {"", "y"}:
                raise ValueError("Custom formula must be like y=...")
            expr = right.strip()
        expr = expr.replace("^", "**")
        arg_indices = sorted({int(m.group(1)) for m in re.finditer(r"\barg(\d+)\b", expr)})
        if not arg_indices:
            arg_indices = [0]
        names = [f"arg{i}" for i in arg_indices]
        safe_globals = {"np": __import__("numpy"), "math": __import__("math"), "abs": abs, "min": min, "max": max}

        def func(x, *params):
            env = {"x": x}
            for idx in arg_indices:
                env[f"arg{idx}"] = params[idx] if idx < len(params) else 1.0
            return eval(expr, {"__builtins__": {}}, {**safe_globals, **env})

        return func, names

    def fit_distribution_with_lawfitter(self) -> None:
        data = self._current_distribution_xy()
        if data is None:
            _show_info_dialog(self, "Lawfitter", "Current table is not distribution. Please switch to the distribution table first.")
            self._append_report("Lawfitter skipped: current tab is not a distribution table.")
            return
        mod = self._get_lawfitter_module()
        if mod is None or not hasattr(mod, "fit"):
            _show_warning_dialog(self, "Lawfitter", "lawfitter backend unavailable.")
            self._append_report("Lawfitter failed: backend unavailable.")
            return
        xs, ys = data
        model_name = str(self.law_model_combo.currentData() or "").strip().lower()
        variant = self._current_law_variant_value()
        try:
            if model_name == "custom":
                expr = self.law_custom_input.text().strip()
                custom_func, custom_names = self._build_custom_law(expr)
                result = mod.fit([xs, ys], law_name=None, customized_law=custom_func)
                param_names = custom_names
                model_label = f"custom: {expr}"
            else:
                result = mod.fit([xs, ys], law_name=model_name, variant=variant)
                model_label = model_name if variant is None else f"{model_name} ({variant})"
                param_names: list[str] = []
                try:
                    if hasattr(mod, "laws") and model_name in mod.laws:
                        law_callable = mod.laws[model_name](variant=variant)
                        param_names = list(inspect.signature(law_callable).parameters.keys())[1:]
                except Exception:
                    param_names = []
            params = result.get("params", [])
            r2 = result.get("r^2", None)
            self._append_report("Lawfitter fit completed.")
            self._append_report(f"Model: {model_label}")
            self._append_report(f"Points: {len(xs)}")
            if params is not None:
                param_list = list(params)
                for idx, p in enumerate(param_list):
                    pname = param_names[idx] if idx < len(param_names) else f"p{idx + 1}"
                    self._append_report(f"  {pname} = {self._format_table_value(p, keep_int=False)}")
            if r2 is not None:
                self._append_report(f"Goodness-of-fit (R^2): {self._format_table_value(r2, keep_int=False)}")
        except Exception as exc:
            _show_warning_dialog(self, "Lawfitter failed", str(exc))
            self._append_report(f"Lawfitter failed: {exc}")

    def _treebank_display_name(self, path: Path) -> str:
        return path.stem

    def _parsed_cache_files(self) -> list[Path]:
        by_src_dir = self._parser_cache_dir / "by_source"
        files: list[Path] = []
        if by_src_dir.exists():
            files.extend(sorted([p for p in by_src_dir.glob("*.conllu") if p.is_file()], key=lambda p: p.name.lower()))
        return files

    def _converted_source_entries(self) -> list[tuple[str, Path]]:
        raw: list[tuple[str, Path]] = []
        for src, cached in self._converted_treebank_cache.items():
            cp = Path(str(cached))
            if not cp.exists():
                continue
            label = Path(str(src)).stem or cp.stem
            raw.append((label, cp))
        raw.sort(key=lambda x: (x[0].lower(), x[1].name.lower()))
        used: dict[str, int] = {}
        out: list[tuple[str, Path]] = []
        for label, path in raw:
            idx = used.get(label, 0)
            used[label] = idx + 1
            final_label = label if idx == 0 else f"{label}_{idx+1}"
            out.append((final_label, path))
        return out

    def _source_entries(self, source: str) -> list[tuple[str, Path]]:
        src = str(source or "").strip().lower()
        if src == "parsed":
            return [(p.stem, p) for p in self._parsed_cache_files()]
        if src == "converted":
            return self._converted_source_entries()
        return [(self._treebank_display_name(p), p) for p in self._imported_treebanks]

    def _treebanks_for_source(self, source: str) -> list[Path]:
        return [p for _, p in self._source_entries(source)]

    def _update_treebank_combo_by_source(self, combo: QComboBox, files: list[Path]) -> None:
        self._update_treebank_combo_with_entries(
            combo,
            [(self._treebank_display_name(p), p) for p in files],
        )

    def _update_treebank_combo_with_entries(self, combo: QComboBox, entries: list[tuple[str, Path]]) -> None:
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("all", "__all__")
        for label, path in entries:
            combo.addItem(label, str(path))
        idx = combo.findData(prev)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _refresh_treebank_combos_by_source(self) -> None:
        source = str(self.source_combo.currentData() or self._source_mode or "imported")
        entries = self._source_entries(source)
        self._update_treebank_combo_with_entries(self.treebank_combo, entries)
        self._update_treebank_combo_with_entries(self.render_treebank_combo, entries)
        self._update_treebank_combo_with_entries(self.save_treebank_combo, entries)

    def _available_sources(self) -> list[str]:
        options: list[str] = []
        if self._imported_treebanks:
            options.append("imported")
        has_converted = any(
            Path(p).exists() for p in self._converted_treebank_cache.values() if str(p or "").strip()
        )
        if has_converted:
            options.append("converted")
        if self._parsed_cache_files():
            options.append("parsed")
        if not options:
            options.append("imported")
        return options

    def _refresh_source_options(self) -> None:
        current = str(self.source_combo.currentData() or self._source_mode or "imported")
        options = self._available_sources()
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for src in options:
            self.source_combo.addItem(src, src)
        idx = self.source_combo.findData(current)
        if idx < 0:
            idx = 0
        self.source_combo.setCurrentIndex(max(0, idx))
        self.source_combo.blockSignals(False)
        self._source_mode = str(self.source_combo.currentData() or "imported")
        self._refresh_treebank_combos_by_source()

    def _on_source_changed(self, _value: str) -> None:
        self._source_mode = str(self.source_combo.currentData() or "imported")
        self._refresh_treebank_combos_by_source()
        self._refresh_pvp_labels()

    def refresh_data_sources(self) -> None:
        self._refresh_source_options()

    def _selected_treebanks_from_combo(self, combo: QComboBox) -> list[Path]:
        selected_data = combo.currentData()
        selected_name = combo.currentText().strip()
        if selected_data == "__all__" or not selected_name or selected_name == "all":
            return self._imported_treebanks.copy()
        if isinstance(selected_data, str):
            sp = Path(selected_data)
            if sp.exists():
                return [sp]
            for tb in self._imported_treebanks:
                if str(tb) == selected_data:
                    return [tb]
        for tb in self._imported_treebanks:
            if self._treebank_display_name(tb) == selected_name:
                return [tb]
        return self._imported_treebanks.copy()

    def _selected_treebanks(self) -> list[Path]:
        source = str(self.source_combo.currentData() or self._source_mode or "imported")
        selected = self._selected_treebanks_from_combo(self.treebank_combo)
        files = self._treebanks_for_source(source)
        if files:
            selected_keys = {str(Path(p).resolve()) for p in selected}
            selected = [p for p in files if str(Path(p).resolve()) in selected_keys] or files
        else:
            selected = []
        if source in {"parsed", "converted"}:
            return selected
        return selected

    def _effective_treebanks(self, files: list[Path]) -> list[Path]:
        out: list[Path] = []
        for tb in files:
            key = str(tb.resolve())
            cached = self._converted_treebank_cache.get(key)
            if cached and Path(cached).exists():
                out.append(Path(cached))
            else:
                out.append(tb)
        return out

    def _selected_convert_sources(self) -> list[Path]:
        selected_data = self.convert_treebank_combo.currentData()
        selected_name = self.convert_treebank_combo.currentText().strip()
        if selected_data == "__all__" or not selected_name or selected_name == "all":
            return self._imported_treebanks.copy()
        if isinstance(selected_data, str):
            for tb in self._imported_treebanks:
                if str(tb) == selected_data:
                    return [tb]
        for tb in self._imported_treebanks:
            if self._treebank_display_name(tb) == selected_name:
                return [tb]
        return self._imported_treebanks.copy()

    def convert_treebanks_to_cache(self) -> None:
        if self._convert_thread is not None and self._convert_thread.is_alive():
            self._append_report("Convert is already running in background.")
            return
        files = self._selected_convert_sources()
        if not files:
            self._append_report("Convert skipped: no treebank selected.")
            return
        src_fmt = self.convert_source_fmt_combo.currentText().strip().lower()
        dst_fmt = self.convert_target_fmt_combo.currentText().strip().lower()
        if src_fmt == dst_fmt:
            self._append_report("Convert skipped: input and output formats are identical.")
            return
        self.convert_btn.setEnabled(False)
        self._append_report("Convert running in background...")

        def _worker() -> None:
            try:
                self._convert_cache_dir.mkdir(parents=True, exist_ok=True)
                converted = 0
                skipped = 0
                updated: dict[str, str] = {}
                for src in files:
                    if not src.exists():
                        skipped += 1
                        continue
                    ext = src.suffix.lstrip(".").lower()
                    if ext != src_fmt:
                        skipped += 1
                        continue
                    try:
                        content = src.read_text(encoding="utf-8", errors="ignore")
                        out_file = self._convert_cache_dir / f"{src.stem}.{dst_fmt}"
                        out_file.write_text(f"# converted from {src_fmt} to {dst_fmt}\n{content}", encoding="utf-8")
                        updated[str(src.resolve())] = str(out_file)
                        converted += 1
                    except Exception:
                        skipped += 1
                self._convert_done.emit({"converted": converted, "skipped": skipped, "updated": updated})
            except Exception as exc:
                self._convert_failed.emit(str(exc))

        self._convert_thread = threading.Thread(target=_worker, daemon=True)
        self._convert_thread.start()

    def _on_convert_done_async(self, payload: object) -> None:
        self.convert_btn.setEnabled(True)
        self._convert_thread = None
        if not isinstance(payload, dict):
            self._on_convert_failed_async("invalid payload")
            return
        updated = payload.get("updated", {})
        if isinstance(updated, dict):
            self._converted_treebank_cache.update(updated)  # type: ignore[arg-type]
        converted = int(payload.get("converted", 0) or 0)
        skipped = int(payload.get("skipped", 0) or 0)
        self._append_report(
            f"Convert completed: converted={converted}, skipped={skipped}, cache={self._convert_cache_dir}"
        )
        self.message.emit(f"Convert done: {converted} cached treebank(s).")

    def _on_convert_failed_async(self, text: str) -> None:
        self.convert_btn.setEnabled(True)
        self._convert_thread = None
        self._append_report(f"Convert failed: {text}")

    def _parse_stanza_lang_dir(self, lang: str) -> str:
        raw = str(lang or "").strip().lower()
        return "zh-hans" if raw in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw

    def _parse_collect_spacy_models(self, lang: str) -> list[str]:
        out: list[str] = []
        try:
            base = self._spacy_root / str(lang).strip().lower()
            if base.exists():
                for p in sorted(base.iterdir()):
                    if p.is_dir():
                        name = str(p.name).strip()
                        if name and ("trf" not in name.lower()):
                            out.append(name)
        except Exception:
            pass
        return out

    def _parse_collect_stanza_models(self, lang: str) -> list[str]:
        out: set[str] = set()
        try:
            lang_dir = self._stanza_root / self._parse_stanza_lang_dir(lang)
            tok_dir = lang_dir / "tokenize"
            if tok_dir.exists():
                for p in tok_dir.glob("*.pt"):
                    stem = p.stem.strip()
                    if stem:
                        out.add(stem)
        except Exception:
            pass
        return sorted(out)

    def _parse_collect_spacy_languages(self) -> list[str]:
        langs: set[str] = {"en", "zh"}
        try:
            if self._spacy_root.exists():
                for p in self._spacy_root.iterdir():
                    if p.is_dir():
                        lang = p.name.strip().lower()
                        if lang:
                            langs.add(lang)
        except Exception:
            pass
        return sorted(langs)

    def _parse_collect_stanza_languages(self) -> list[str]:
        langs: set[str] = {"en", "zh"}
        try:
            if self._stanza_root.exists():
                for p in self._stanza_root.iterdir():
                    if p.is_dir():
                        lang = p.name.strip().lower()
                        if lang:
                            langs.add(lang)
        except Exception:
            pass
        return sorted(langs)

    def _refresh_parse_language_options(self) -> None:
        backend = self.parse_backend_combo.currentText().strip().lower()
        current = self.parse_lang_combo.currentText().strip().lower()
        langs = self._parse_collect_spacy_languages() if backend == "spacy" else self._parse_collect_stanza_languages()
        self.parse_lang_combo.blockSignals(True)
        self.parse_lang_combo.clear()
        self.parse_lang_combo.addItems(langs)
        if current and current in langs:
            self.parse_lang_combo.setCurrentText(current)
        elif "en" in langs:
            self.parse_lang_combo.setCurrentText("en")
        elif langs:
            self.parse_lang_combo.setCurrentIndex(0)
        self.parse_lang_combo.blockSignals(False)

    def _on_parse_backend_changed(self, _value: str | None = None) -> None:
        self._refresh_parse_language_options()
        self._refresh_parse_model_options()

    def _parse_default_model(self, backend: str, lang: str) -> str:
        defaults = {
            ("spacy", "en"): "en_core_web_sm",
            ("spacy", "zh"): "zh_core_web_sm",
            ("stanza", "en"): "combined",
            ("stanza", "zh"): "gsdsimp",
        }
        return defaults.get((backend, lang), "")

    def _refresh_parse_model_options(self, _value: str | None = None) -> None:
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        if backend == "spacy":
            options = self._parse_collect_spacy_models(lang)
            presets = {
                "en": ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"],
                "zh": ["zh_core_web_sm", "zh_core_web_md"],
            }
            options.extend(presets.get(lang, []))
        else:
            options = self._parse_collect_stanza_models(lang)
            if lang == "en":
                options.extend(["combined"])
            elif lang == "zh":
                options.extend(["gsdsimp"])
        uniq: list[str] = []
        seen: set[str] = set()
        for x in options:
            sx = str(x or "").strip()
            if not sx or sx in seen:
                continue
            seen.add(sx)
            uniq.append(sx)
        default_model = self._parse_default_model(backend, lang)
        self.parse_model_combo.blockSignals(True)
        self.parse_model_combo.clear()
        if uniq:
            self.parse_model_combo.addItems(uniq)
        chosen = default_model if default_model else (uniq[0] if uniq else "")
        if "trf" in str(chosen).lower():
            chosen = uniq[0] if uniq else ""
        self.parse_model_combo.setCurrentText(chosen)
        self.parse_model_combo.blockSignals(False)

    def _parse_cache_key(self, backend: str, lang: str, model_name: str) -> str:
        return f"{backend}:{lang}:{model_name}"

    def _load_parse_pipeline(self, backend: str, lang: str, model_name: str):
        key = self._parse_cache_key(backend, lang, model_name)
        if key in self._parse_pipeline_cache:
            return self._parse_pipeline_cache[key]
        if backend == "spacy":
            spacy_mod = _ensure_spacy()
            if spacy_mod is None:
                reason = str(_spacy_import_error or "").strip()
                raise RuntimeError(
                    "spaCy runtime is unavailable. Install or import Parser Runtime first."
                    + (f"\nReason: {reason}" if reason else "")
                )
            lang_l = str(lang or "").strip().lower()
            model_l = str(model_name or "").strip().lower()
            if lang_l.startswith("zh") or model_l.startswith("zh_"):
                ok, reason = _ensure_spacy_zh_runtime()
                if not ok:
                    raise RuntimeError(reason or "Chinese spaCy runtime is unavailable (spacy_pkuseg).")
            local_model_dir = self._spacy_root / lang / model_name
            if local_model_dir.exists():
                resolved_dir = SyntaxPage._find_spacy_model_dir(local_model_dir)
                if resolved_dir is None:
                    raise RuntimeError(f"spaCy local model is missing config.cfg: {local_model_dir}")
                nlp = spacy_mod.load(str(resolved_dir))
            else:
                nlp = spacy_mod.load(model_name)
            self._parse_pipeline_cache[key] = nlp
            return nlp
        if backend == "stanza":
            st_mod = _ensure_stanza()
            if st_mod is None:
                reason = str(_stanza_import_error or "").strip()
                if reason:
                    raise RuntimeError(f"stanza is unavailable: {reason}")
                raise RuntimeError("stanza is unavailable. Please install stanza.")
            raw_lang = lang.strip().lower()
            stanza_lang = "zh-hans" if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw_lang
            package = model_name.strip().lower()
            if raw_lang == "en" and package in {"", "en", "default"}:
                package = "combined"
            if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} and package in {"", "zh", "zh-hans", "default"}:
                package = "gsdsimp"
            kwargs = {
                "lang": stanza_lang,
                "processors": "tokenize,pos,lemma,depparse",
                "verbose": False,
                "dir": str(self._stanza_root),
            }
            if package:
                kwargs["package"] = package
            nlp = st_mod.Pipeline(**kwargs)
            self._parse_pipeline_cache[key] = nlp
            return nlp
        raise RuntimeError(f"Unsupported backend: {backend}")

    def _load_parse_txt_sources(self, paths: list[Path]) -> None:
        sources = [p for p in paths if p.exists() and p.is_file()]
        self._parse_txt_sources = sources
        self._parse_clean_by_source = {}
        self.parse_txt_select_combo.blockSignals(True)
        self.parse_txt_select_combo.clear()
        self.parse_txt_select_combo.addItem("all", "__all__")
        for p in sources:
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw = ""
            sents = SyntaxPage._split_to_sentences(raw)
            self._parse_clean_by_source[str(p.resolve())] = list(sents)
            self.parse_txt_select_combo.addItem(p.name, str(p.resolve()))
        self.parse_txt_select_combo.blockSignals(False)
        total_sents = sum(len(v) for v in self._parse_clean_by_source.values())
        self.parse_status_label.setText(f"TXT ready: {len(sources)} file(s), {total_sents} sentence(s).")

    def _on_parse_import_txt_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Import TXT File(s)", "", "Text Files (*.txt)")
        if not files:
            return
        old = {str(p.resolve()) for p in self._parse_txt_sources}
        merged = list(self._parse_txt_sources)
        for fp in files:
            p = Path(fp)
            if str(p.resolve()) not in old:
                merged.append(p)
        self._load_parse_txt_sources(merged)

    def _on_parse_import_txt_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Import TXT Folder", "")
        if not folder:
            return
        base = Path(folder)
        files = sorted([p for p in base.glob("*.txt") if p.is_file()])
        if not files:
            _show_info_dialog(self, "Parse", "No txt files found in the selected folder.")
            return
        old = {str(p.resolve()) for p in self._parse_txt_sources}
        merged = list(self._parse_txt_sources)
        for p in files:
            if str(p.resolve()) not in old:
                merged.append(p)
        self._load_parse_txt_sources(merged)

    def _selected_parse_sentences(self) -> list[tuple[str, str]]:
        selected = self.parse_txt_select_combo.currentData()
        out: list[tuple[str, str]] = []
        if selected in (None, "__all__"):
            for src, sents in self._parse_clean_by_source.items():
                for s in sents:
                    out.append((src, s))
        else:
            src = str(selected)
            for s in self._parse_clean_by_source.get(src, []):
                out.append((src, s))
        return out

    def _load_parse_model_from_drawer(self) -> None:
        if self._parse_load_thread is not None and self._parse_load_thread.is_alive():
            self.parse_status_label.setText("Model loading in background...")
            return
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        model = self.parse_model_combo.currentText().strip()
        if not model:
            _show_warning_dialog(self, "Parse", "Model name is required.")
            return
        self.parse_load_btn.setEnabled(False)
        self.parse_status_label.setText("Loading model in background...")

        def _worker() -> None:
            try:
                self._load_parse_pipeline(backend, lang, model)
                self._parse_load_done.emit({"backend": backend, "lang": lang, "model": model})
            except Exception as exc:
                self._parse_load_failed.emit(str(exc))

        self._parse_load_thread = threading.Thread(target=_worker, daemon=True)
        self._parse_load_thread.start()

    def _on_parse_load_done_async(self, payload: object) -> None:
        self._parse_load_thread = None
        self.parse_load_btn.setEnabled(True)
        if not isinstance(payload, dict):
            self._on_parse_load_failed_async("invalid payload")
            return
        backend = str(payload.get("backend", ""))
        lang = str(payload.get("lang", ""))
        model = str(payload.get("model", ""))
        self.parse_status_label.setText(f"Model loaded: {backend}/{lang}/{model}")
        self._append_report(f"Parse model loaded: {backend}/{lang}/{model}")

    def _on_parse_load_failed_async(self, text: str) -> None:
        self._parse_load_thread = None
        self.parse_load_btn.setEnabled(True)
        _show_warning_dialog(self, "Parse", str(text))
        self.parse_status_label.setText(f"Load failed: {text}")

    def _run_parse_from_drawer(self) -> None:
        if self._parse_running:
            self._append_report("Parse is already running in background.")
            return
        if not self._parse_clean_by_source:
            _show_warning_dialog(self, "Parse", "No txt sources imported.")
            return
        backend = self.parse_backend_combo.currentText().strip().lower()
        lang = self.parse_lang_combo.currentText().strip().lower()
        model = self.parse_model_combo.currentText().strip()
        if not model:
            _show_warning_dialog(self, "Parse", "Model name is required.")
            return
        selected = self._selected_parse_sentences()
        if not selected:
            _show_warning_dialog(self, "Parse", "Input text is empty.")
            return
        self._parse_running = True
        self.parse_run_btn.setEnabled(False)
        self.parse_load_btn.setEnabled(False)
        self.parse_status_label.setText("Parsing...")
        self._append_report(f"Parse running in background ({len(selected)} sentences)...")

        def _worker() -> None:
            try:
                nlp = self._load_parse_pipeline(backend, lang, model)
                chunks: list[str] = []
                chunks_by_source: dict[str, list[str]] = {}
                for src, s in selected:
                    txt = str(s or "").strip()
                    if not txt:
                        continue
                    if backend == "spacy":
                        block = SyntaxPage._to_conllu_from_spacy(nlp, txt)
                    else:
                        block = SyntaxPage._to_conllu_from_stanza(nlp, txt)
                    chunks.append(block)
                    skey = str(Path(str(src)).resolve())
                    chunks_by_source.setdefault(skey, []).append(block)
                conllu = ("\n\n".join(c for c in chunks if c.strip())).strip()
                conllu_by_source = {
                    k: ("\n\n".join(v for v in blocks if str(v).strip())).strip()
                    for k, blocks in chunks_by_source.items()
                }
                self._parse_done.emit(
                    {
                        "conllu": conllu,
                        "count": len(chunks),
                        "backend": backend,
                        "lang": lang,
                        "model": model,
                        "conllu_by_source": conllu_by_source,
                    }
                )
            except Exception as exc:
                self._parse_failed.emit(str(exc))

        self._parse_thread = threading.Thread(target=_worker, daemon=True)
        self._parse_thread.start()

    def _on_parse_done_async(self, payload: object) -> None:
        self._parse_running = False
        self._parse_thread = None
        self.parse_run_btn.setEnabled(True)
        self.parse_load_btn.setEnabled(True)
        if not isinstance(payload, dict):
            self._on_parse_failed_async("invalid payload")
            return
        conllu = str(payload.get("conllu", "") or "")
        count = int(payload.get("count", 0) or 0)
        raw_by_source = payload.get("conllu_by_source", {})
        if isinstance(raw_by_source, dict):
            self._parse_conllu_by_source = {
                str(Path(str(k)).resolve()): str(v or "")
                for k, v in raw_by_source.items()
                if str(v or "").strip()
            }
        else:
            self._parse_conllu_by_source = {}
        self._parse_conllu_output = conllu
        try:
            self._parser_cache_dir.mkdir(parents=True, exist_ok=True)
            self._parser_cache_file.write_text(conllu, encoding="utf-8")
            by_src_dir = self._parser_cache_dir / "by_source"
            by_src_dir.mkdir(parents=True, exist_ok=True)
            for old in by_src_dir.glob("*.conllu"):
                try:
                    old.unlink()
                except Exception:
                    pass
            for src_key, content in self._parse_conllu_by_source.items():
                if not content:
                    continue
                src_path = Path(src_key)
                out_file = by_src_dir / f"{src_path.stem}.conllu"
                idx = 1
                while out_file.exists():
                    out_file = by_src_dir / f"{src_path.stem}_{idx}.conllu"
                    idx += 1
                out_file.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")
        except Exception:
            pass
        self._refresh_source_options()
        self.parse_status_label.setText(f"Parsed {count} sentence(s). Cached.")
        self._append_report(f"Parse completed: {count} sentence(s), cache={self._parser_cache_file}")
        self.message.emit(f"Parse done: {count} sentence(s).")

    def _on_parse_failed_async(self, text: str) -> None:
        self._parse_running = False
        self._parse_thread = None
        self.parse_run_btn.setEnabled(True)
        self.parse_load_btn.setEnabled(True)
        self.parse_status_label.setText(f"Parse failed: {text}")
        self._append_report(f"Parse failed: {text}")
        _show_warning_dialog(self, "Parse failed", text)

    def _save_parse_conllu_from_drawer(self) -> None:
        content = self._parse_conllu_output.strip()
        if not content and self._parser_cache_file.exists():
            try:
                content = self._parser_cache_file.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                content = ""
        if not content:
            _show_info_dialog(self, "Parse", "No CoNLL-U output to save.")
            return
        out, _ = QFileDialog.getSaveFileName(self, "Save CoNLL-U", "", "CoNLL-U (*.conllu);;Text (*.txt)")
        if not out:
            return
        path = Path(out)
        try:
            path.write_text(content + "\n", encoding="utf-8")
            self.parse_status_label.setText(f"Saved: {path}")
            self._append_report(f"Saved parsed CoNLL-U: {path}")
        except Exception as exc:
            _show_warning_dialog(self, "Save failed", str(exc))

    def _render_level(self) -> str:
        mapping = {
            "dep metrics": "dep",
            "sent metrics": "sent",
            "text metrics": "text",
            "distribution": "distribution",
            "pvp": "pvp",
            "all": "all",
        }
        return mapping.get(self.render_table_combo.currentText().strip().lower(), "dep")

    def _filter_payload_list(self, payloads: list[dict[str, object]] | None, indices: list[int]) -> list[dict[str, object]] | None:
        if payloads is None:
            return None
        return [payloads[i] for i in indices if 0 <= i < len(payloads)]

    def _filter_pvp_payloads(
        self, pvp_payloads: dict[str, list[dict[str, object]]] | None, indices: list[int]
    ) -> dict[str, list[dict[str, object]]] | None:
        if pvp_payloads is None:
            return None
        out: dict[str, list[dict[str, object]]] = {}
        for key, rows in pvp_payloads.items():
            out[key] = [rows[i] for i in indices if 0 <= i < len(rows)]
        return out

    def _unwrap_single_tab(self, widget: QWidget) -> QWidget:
        if isinstance(widget, QTabWidget) and widget.count() == 1:
            inner = widget.widget(0)
            if isinstance(inner, QWidget):
                # Reparent the child before dropping the temporary tab container;
                # otherwise inner widgets may be deleted with the container.
                widget.removeTab(0)
                inner.setParent(None)
                return inner
        return widget

    def _render_level_label(self, level: str) -> str:
        return {
            "dep": "dep metrics",
            "sent": "sent metrics",
            "text": "text metrics",
            "distribution": "distribution",
            "pvp": "pvp",
        }.get(level, level)

    def _format_table_value(self, value, keep_int: bool = True) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, int):
            return str(value) if keep_int else f"{Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
        if isinstance(value, float):
            rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{rounded:.2f}"
        if isinstance(value, str):
            raw = value.strip()
            if raw == "":
                return ""
            if keep_int and (raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit())):
                return raw
            try:
                rounded = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return f"{rounded:.2f}"
            except InvalidOperation:
                return value
        try:
            rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{rounded:.2f}"
        except Exception:
            return str(value)

    def _refresh_result_widgets_visuals(self) -> None:
        self.result_tabs.updateGeometry()
        self.result_tabs.update()
        self.result_tabs.repaint()
        for tabs in self.result_tabs.findChildren(QTabWidget):
            tab_bar = tabs.tabBar()
            tab_bar.updateGeometry()
            tab_bar.update()
            tab_bar.repaint()
        for table in [*self.result_tabs.findChildren(QTableWidget), *self.result_tabs.findChildren(QTableView)]:
            table.updateGeometry()
            table.update()
            table.repaint()
            table.horizontalHeader().viewport().update()
            table.viewport().update()

    def _metrics_for_level(self, level: str) -> list[str]:
        if level == "dep":
            return DEP_METRICS
        if level == "sent":
            return SENT_METRICS
        if level == "text":
            return TEXT_METRICS
        if level == "distribution":
            return DIST_METRICS
        if level == "pvp":
            return []
        if level == "all":
            return sorted(set(DEP_METRICS + SENT_METRICS + TEXT_METRICS + DIST_METRICS))
        return []

    def _reset_metrics_for_level(self) -> None:
        level = self.level_combo.currentText()
        if level not in {"dep", "sent", "text", "distribution", "all", "pvp"}:
            level = "dep"
        self.metric_combo.blockSignals(True)
        self.metric_combo.clear()
        self.metric_combo.addItem("all")
        for metric in self._metrics_for_level(level):
            self.metric_combo.addItem(metric)
        self.metric_combo.blockSignals(False)
        self.metric_combo.setEnabled(level != "pvp")
        self.pvp_target_combo.setEnabled(level in {"pvp", "all"})
        self.pvp_label_mode_combo.setEnabled(level in {"pvp", "all"})
        self._refresh_pvp_labels()

    def _refresh_pvp_labels(self) -> None:
        files = self._selected_treebanks()
        prev = self.pvp_target_combo.currentText()
        self._pvp_label_token += 1
        token = self._pvp_label_token

        if self._pvp_label_thread is not None and self._pvp_label_thread.is_alive():
            # Let latest request win; running worker result will be ignored by token check.
            pass

        if not files:
            self._on_pvp_labels_done_async({"token": token, "labels": [], "prev": prev})
            return

        def _worker() -> None:
            try:
                labels = _parse_labels(files, "pos")
            except Exception:
                labels = []
            self._pvp_labels_done.emit({"token": token, "labels": labels, "prev": prev})

        self._pvp_label_thread = threading.Thread(target=_worker, daemon=True)
        self._pvp_label_thread.start()

    def _on_pvp_labels_done_async(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        token = int(payload.get("token", -1) or -1)
        if token != self._pvp_label_token:
            return
        labels = payload.get("labels", [])
        prev = str(payload.get("prev", "") or "")
        if not isinstance(labels, list):
            labels = []
        self.pvp_target_combo.blockSignals(True)
        self.pvp_target_combo.clear()
        self.pvp_target_combo.addItem("all")
        for label in labels:
            self.pvp_target_combo.addItem(str(label))
        if prev:
            idx = self.pvp_target_combo.findText(prev)
            if idx >= 0:
                self.pvp_target_combo.setCurrentIndex(idx)
        self.pvp_target_combo.blockSignals(False)

    def compute(self) -> None:
        if self._compute_running:
            self.message.emit("Compute is already running in background.")
            return
        files = self._selected_treebanks()
        if not files:
            _show_info_dialog(self, "No treebanks", "Import treebanks from sidebar first.")
            return
        plan = self._resolve_parallel_plan(files)
        self._runtime_parallel_scope = str(plan["scope"])
        self._runtime_parallel_enabled = bool(plan["enabled"])
        self._runtime_n_jobs = int(plan["n_jobs"]) if plan["n_jobs"] is not None else None

        self._append_report(f"Start compute: {len(files)} treebank(s).")
        level = self.level_combo.currentText()
        all_classes = [self.pvp_target_combo.itemText(i) for i in range(1, self.pvp_target_combo.count())]
        selected_target = self.pvp_target_combo.currentText().strip()
        pvp_classes = all_classes if selected_target in {"", "all"} else [selected_target]
        target_levels = ["dep", "sent", "text", "distribution", "pvp"] if level == "all" else [level]
        selected_metric = self.metric_combo.currentText().strip() if self.metric_combo.count() else "all"
        pvp_mode = self.pvp_label_mode_combo.currentText().strip() or "pos"
        level_metrics_map: dict[str, list[str]] = {}
        for lv in target_levels:
            if lv in {"dep", "sent", "text", "distribution"}:
                full_metrics = self._metrics_for_level(lv)
                metrics = full_metrics if selected_metric in {"", "all"} else [selected_metric]
                metrics = [m for m in metrics if m in full_metrics]
                level_metrics_map[lv] = metrics if metrics else full_metrics
            else:
                level_metrics_map[lv] = []

        total_steps = 0
        for lv in target_levels:
            if lv == "distribution":
                total_steps += len(files) * max(1, len(level_metrics_map.get("distribution", [])))
            elif lv == "pvp":
                total_steps += len(files) * max(1, len(pvp_classes))
            else:
                total_steps += len(files)
        self._progress_total = max(1, total_steps)
        self._progress_done = 0
        self._last_report_pct = -1
        self._progress_emit_pct = -1
        self._progress_emit_ts = 0.0
        self.processingChanged.emit("-", 0)
        self._compute_running = True
        self.compute_btn.setEnabled(False)
        self.message.emit("Computing in background. You can switch pages.")
        args = (
            files,
            target_levels,
            level_metrics_map,
            pvp_classes,
            pvp_mode,
        )
        self._compute_thread = threading.Thread(target=self._compute_worker, args=args, daemon=True)
        self._compute_thread.start()

    def _compute_worker(
        self,
        files: list[Path],
        target_levels: list[str],
        level_metrics_map: dict[str, list[str]],
        pvp_classes: list[str],
        pvp_mode: str,
    ) -> None:
        try:
            # Lower worker thread priority to keep UI interactions smooth while computing.
            try:
                if os.name == "nt":
                    import ctypes  # local import to avoid hard dependency during frozen startup
                    THREAD_PRIORITY_BELOW_NORMAL = -1
                    ctypes.windll.kernel32.SetThreadPriority(
                        ctypes.windll.kernel32.GetCurrentThread(),
                        THREAD_PRIORITY_BELOW_NORMAL,
                    )
            except Exception:
                pass
            payload_cache: dict[str, object] = {
                "files": files,
                "target_levels": target_levels,
                "level_metrics_map": level_metrics_map,
                "pvp_classes": pvp_classes,
                "pvp_mode": pvp_mode,
                "level_payloads": {},
            }
            results_by_idx: dict[int, dict[str, object]] = {}
            progress_units_per_file = self._progress_units_per_treebank(target_levels, pvp_classes)
            if self._file_level_parallel_enabled(files):
                max_workers = min(self._effective_n_jobs(self._runtime_n_jobs), len(files))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {
                        executor.submit(
                            self._compute_treebank_payload,
                            tb,
                            target_levels,
                            level_metrics_map,
                            pvp_classes,
                            pvp_mode,
                        ): idx
                        for idx, tb in enumerate(files)
                    }
                    pending = set(future_map.keys())
                    while pending:
                        done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                        for future in done:
                            idx = future_map[future]
                            tb = files[idx]
                            try:
                                results_by_idx[idx] = future.result()
                            except Exception as exc:
                                raise RuntimeError(f"{tb.name}: {exc}") from exc
                            for _ in range(progress_units_per_file):
                                self._progress_tick(tb.name)
            else:
                for idx, tb in enumerate(files):
                    results_by_idx[idx] = self._compute_treebank_payload(
                        tb, target_levels, level_metrics_map, pvp_classes, pvp_mode
                    )
                    for _ in range(progress_units_per_file):
                        self._progress_tick(tb.name)

            level_payloads: dict[str, object] = payload_cache["level_payloads"]  # type: ignore[assignment]
            for lv in target_levels:
                if lv == "pvp":
                    pvp_payload_map: dict[str, list] = {cls: [] for cls in pvp_classes}
                    for i in range(len(files)):
                        payload_i = results_by_idx.get(i, {}).get("pvp", {})
                        if not isinstance(payload_i, dict):
                            payload_i = {}
                        for cls in pvp_classes:
                            pvp_payload_map[cls].append(payload_i.get(cls, {}))
                    level_payloads[lv] = pvp_payload_map
                else:
                    level_payloads[lv] = [results_by_idx.get(i, {}).get(lv, {}) for i in range(len(files))]
            self._compute_done.emit(payload_cache)
        except Exception as exc:
            self._compute_failed.emit(str(exc))

    def _progress_units_per_treebank(self, target_levels: list[str], pvp_classes: list[str]) -> int:
        units = 0
        for lv in target_levels:
            if lv == "pvp":
                units += max(1, len(pvp_classes))
            else:
                units += 1
        return max(1, units)

    def _compute_treebank_payload(
        self,
        treebank_path: Path,
        target_levels: list[str],
        level_metrics_map: dict[str, list[str]],
        pvp_classes: list[str],
        pvp_mode: str,
    ) -> dict[str, object]:
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        out: dict[str, object] = {}
        for lv in target_levels:
            metrics = level_metrics_map.get(lv, [])
            if lv == "dep":
                dep_data = self._calc_dep_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)
                out[lv] = {"dep_data": dep_data, "lemma_by_sent": self._collect_lemmas(analyzer)}
            elif lv == "sent":
                out[lv] = self._calc_sent_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)
            elif lv == "text":
                out[lv] = self._calc_text_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)
            elif lv == "distribution":
                out[lv] = self._compute_distribution_payload_from_analyzer(
                    analyzer, metrics, treebank_path.name, parallel=parallel, n_jobs=n_jobs
                )
            elif lv == "pvp":
                pvp_map: dict[str, object] = {}
                for cls in pvp_classes:
                    pvp_map[cls] = self._calc_pvp(
                        analyzer,
                        selected_input=cls,
                        mode=pvp_mode,
                        normalize=True,
                        parallel=parallel,
                        n_jobs=n_jobs,
                    )
                out[lv] = pvp_map
        return out

    def _compute_distribution_payload_from_analyzer(
        self, analyzer, metrics: list[str], treebank_name: str, parallel: bool | None = None, n_jobs: int | None = None
    ) -> dict[str, tuple[list, list[float], bool, str]]:
        out: dict[str, tuple[list, list[float], bool, str]] = {}
        for metric in metrics:
            used_fallback = False
            err_msg = ""
            if metric == "rd":
                try:
                    x_vals, y_vals = self._compute_rd_distribution(analyzer, parallel=parallel, n_jobs=n_jobs)
                except Exception as exc:
                    used_fallback = True
                    x_vals, y_vals = [], []
                    err_msg = f"Distribution failed: {treebank_name} / {metric} ({exc})"
            else:
                try:
                    dist = self._calc_distributions(
                        analyzer, metrics=[metric], normalize=True, parallel=parallel, n_jobs=n_jobs
                    )
                    x_vals, y_vals = dist.get(metric, ([], []))
                    if not x_vals and not y_vals:
                        raise ValueError(f"empty distribution for {metric}")
                except Exception:
                    used_fallback = True
                    try:
                        x_vals, y_vals = self._compute_metric_distribution_fallback(
                            analyzer, metric, parallel=parallel, n_jobs=n_jobs
                        )
                    except Exception as exc:
                        x_vals, y_vals = [], []
                        err_msg = f"Distribution failed: {treebank_name} / {metric} ({exc})"
            out[metric] = (x_vals, y_vals, used_fallback, err_msg)
        return out

    def _on_compute_done(self, payload_cache: object) -> None:
        self._compute_running = False
        self.compute_btn.setEnabled(True)
        if not isinstance(payload_cache, dict):
            self._append_report("Compute failed: invalid payload returned.")
            self.processingChanged.emit("Error", 0)
            return
        self._render_cache = payload_cache
        files: list[Path] = payload_cache.get("files", [])  # type: ignore[assignment]
        self.result_tabs.clear()
        self._tables.clear()
        self.message.emit(f"Depval computed for {len(files)} treebank(s). Cache updated.")
        self._append_report("Compute completed. Results are cached. Click Render to load tables from cache.")
        self.processingChanged.emit("Done", 100)

    def _on_compute_failed(self, error_text: str) -> None:
        self._compute_running = False
        self.compute_btn.setEnabled(True)
        _show_warning_dialog(self, "Depval compute failed", error_text)
        self._append_report(f"Compute failed: {error_text}")

    def render_cached_results(self, auto_plot: bool = False) -> None:
        if not self._render_cache:
            self.message.emit("No cached compute results. Click Compute first.")
            return
        cache = self._render_cache
        cache_files: list[Path] = cache.get("files", [])  # type: ignore[assignment]
        target_levels: list[str] = cache.get("target_levels", [])  # type: ignore[assignment]
        level_metrics_map: dict[str, list[str]] = cache.get("level_metrics_map", {})  # type: ignore[assignment]
        level_payloads: dict[str, object] = cache.get("level_payloads", {})  # type: ignore[assignment]
        pvp_classes: list[str] = cache.get("pvp_classes", [])  # type: ignore[assignment]
        pvp_mode: str = str(cache.get("pvp_mode", "pos"))
        selected_level = self._render_level()
        if selected_level != "all" and selected_level not in target_levels:
            self.message.emit(f"Selected table '{selected_level}' is not in cached results. Recompute with this level first.")
            self._append_report(f"Render skipped: level '{selected_level}' not available in cache.")
            return

        selected_treebank_data = self.render_treebank_combo.currentData()
        if selected_treebank_data == "__all__":
            selected_indices = list(range(len(cache_files)))
        else:
            selected_indices = [idx for idx, tb in enumerate(cache_files) if str(tb) == str(selected_treebank_data)]
        if not selected_indices:
            self.message.emit("Selected corpus is not in cached results. Recompute with this corpus first.")
            self._append_report("Render skipped: selected corpus not available in cache.")
            return

        files = [cache_files[i] for i in selected_indices]
        render_levels = target_levels if selected_level == "all" else [selected_level]
        # Guard against duplicated level entries from stale cache/state.
        uniq_levels: list[str] = []
        seen_levels: set[str] = set()
        for lv in render_levels:
            if lv in seen_levels:
                continue
            seen_levels.add(lv)
            uniq_levels.append(lv)
        render_levels = uniq_levels
        dep_payloads = self._filter_payload_list(level_payloads.get("dep"), selected_indices)  # type: ignore[arg-type]
        sent_payloads = self._filter_payload_list(level_payloads.get("sent"), selected_indices)  # type: ignore[arg-type]
        text_payloads = self._filter_payload_list(level_payloads.get("text"), selected_indices)  # type: ignore[arg-type]
        dist_payloads = self._filter_payload_list(level_payloads.get("distribution"), selected_indices)  # type: ignore[arg-type]
        pvp_payloads = self._filter_pvp_payloads(level_payloads.get("pvp"), selected_indices)  # type: ignore[arg-type]

        self.result_tabs.clear()
        self._tables.clear()
        self._render_token += 1
        self._render_queue = [(lv, level_metrics_map.get(lv, [])) for lv in render_levels]
        self._render_files = files
        self._render_dep_payloads = dep_payloads
        self._render_sent_payloads = sent_payloads
        self._render_text_payloads = text_payloads
        self._render_dist_payloads = dist_payloads
        self._render_pvp_payloads = pvp_payloads or {}
        self._render_pvp_classes = pvp_classes
        self._render_pvp_mode = pvp_mode
        self._render_auto_plot = auto_plot
        self.result_tabs.setUpdatesEnabled(False)
        self.processingChanged.emit("Render", 0)
        self._append_report("Rendering tables from cache...")
        QTimer.singleShot(0, lambda: self._render_cached_results_step(self._render_token))

    def _render_cached_results_step(self, token: int) -> None:
        if token != self._render_token:
            return
        if not self._render_queue:
            self._finish_cached_render(token)
            return
        lv, metrics = self._render_queue.pop(0)
        try:
            if lv == "dep":
                widget = self._build_dep_widget(self._render_files, metrics, payloads=self._render_dep_payloads)
            elif lv == "sent":
                widget = self._build_sent_widget(self._render_files, metrics, payloads=self._render_sent_payloads)
            elif lv == "text":
                widget = self._build_text_widget(self._render_files, metrics, payloads=self._render_text_payloads)
            elif lv == "distribution":
                widget = self._build_distribution_widget(self._render_files, metrics, payloads=self._render_dist_payloads)
            else:
                pvp_widget = self._build_pvp_widget(
                    self._render_files,
                    self._render_pvp_classes,
                    self._render_pvp_mode,
                    payload_by_class=self._render_pvp_payloads,
                )
                if pvp_widget is None:
                    widget = QLabel("No PVP result.")
                else:
                    widget = pvp_widget
            self.result_tabs.addTab(widget, self._render_level_label(lv))
            total = max(1, self.result_tabs.count() + len(self._render_queue))
            done = self.result_tabs.count()
            pct = int((done / total) * 100)
            self.processingChanged.emit("Render", pct)
        except Exception as exc:
            self.result_tabs.setUpdatesEnabled(True)
            _show_warning_dialog(self, "Depval render failed", str(exc))
            self._append_report(f"Render failed: {exc}")
            return
        QTimer.singleShot(0, lambda: self._render_cached_results_step(token))

    def _finish_cached_render(self, token: int) -> None:
        if token != self._render_token:
            return
        self.result_tabs.setUpdatesEnabled(True)
        self._bind_tab_change_events(self.result_tabs)
        self.message.emit(f"Depval computed for {len(self._render_files)} treebank(s).")
        self._append_report("Render completed from cached results.")
        self.processingChanged.emit("Done", 100)
        self._refresh_plot_columns()
        self._refresh_result_widgets_visuals()
        QTimer.singleShot(0, self._refresh_result_widgets_visuals)
        if self._render_auto_plot:
            QTimer.singleShot(0, self._auto_plot_current_tab_safe)
        top_win = self.window()
        if top_win is not None and hasattr(top_win, "_sync_maximized_shell_style"):
            try:
                top_win._sync_maximized_shell_style()  # type: ignore[attr-defined]
            except Exception:
                pass

    def _progress_tick(self, treebank_name: str) -> None:
        self._progress_done = min(self._progress_total, self._progress_done + 1)
        pct = int((self._progress_done / max(1, self._progress_total)) * 100)
        now = time.monotonic()
        should_emit = (
            pct >= 100
            or self._progress_emit_pct < 0
            or pct - self._progress_emit_pct >= 5
            or (now - self._progress_emit_ts) >= 0.30
        )
        if should_emit:
            self.processingChanged.emit(treebank_name, pct)
            self._progress_emit_pct = pct
            self._progress_emit_ts = now
        if threading.current_thread() is not threading.main_thread():
            self._last_report_pct = pct
            return
        self._append_report(f"Running: {treebank_name} ({pct}%)")
        self._last_report_pct = pct
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def _on_clear_toggle(self, checked: bool) -> None:
        self.clear_all_btn.setText("Clear-All: ON" if checked else "Clear-All: OFF")

    def _make_result_table(self, headers: list[str], rows: list[list[object]], row_groups: list[str] | None = None) -> QTableView:
        model = ResultTableModel(headers, rows, row_groups)
        table = QTableView()
        table.setModel(model)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table._result_model = model  # type: ignore[attr-defined]
        self._install_table_filters(table)
        return table

    def _build_dep_widget(self, files: list[Path], metrics: list[str], payloads: list[dict[str, object]] | None = None) -> QWidget:
        tabs = QTabWidget()
        payloads = payloads if payloads is not None else self._collect_file_payloads(
            files, lambda tb: self._compute_dep_payload(tb, metrics)
        )
        for tb, payload in zip(files, payloads):
            dep_data = payload["dep_data"]
            lemma_by_sent = payload["lemma_by_sent"]

            cols = ["sent id", "id", "form", "lemma", "upos", "deprel", "head"] + metrics
            rows: list[list[object]] = []
            row_groups: list[str] = []
            for sent_idx, sent_ids in enumerate(dep_data.get("id", [])):
                for word_idx, word_id in enumerate(sent_ids):
                    lemma = "_"
                    if sent_idx < len(lemma_by_sent) and word_idx < len(lemma_by_sent[sent_idx]):
                        lemma = lemma_by_sent[sent_idx][word_idx]
                    row = [
                        self._format_table_value(sent_idx + 1),
                        self._format_table_value(word_id),
                        self._format_table_value(dep_data.get("form", [[]])[sent_idx][word_idx]),
                        lemma,
                        self._format_table_value(dep_data.get("dpos", [[]])[sent_idx][word_idx]),
                        self._format_table_value(dep_data.get("deprel", [[]])[sent_idx][word_idx]),
                        self._format_table_value(dep_data.get("head", [[]])[sent_idx][word_idx]),
                    ]
                    for metric in metrics:
                        row.append(self._format_table_value(self._safe_nested_value(dep_data.get(metric, []), sent_idx, word_idx, "")))
                    rows.append(row)
                    row_groups.append(f"sent-{sent_idx+1}")
            table = self._make_result_table(cols, rows, row_groups)
            tabs.addTab(self._table_with_filters(table), tb.name)
            self._tables[f"dep:{tb.name}"] = table
        return tabs

    def _build_sent_widget(self, files: list[Path], metrics: list[str], payloads: list[dict[str, list]] | None = None) -> QWidget:
        tabs = QTabWidget()
        payloads = payloads if payloads is not None else self._collect_file_payloads(
            files, lambda tb: self._compute_sent_payload(tb, metrics)
        )
        for tb, sent_data in zip(files, payloads):
            cols = ["sent id"] + metrics
            sent_count = max([len(sent_data.get(m, [])) for m in metrics] + [0])
            rows: list[list[object]] = []
            row_groups: list[str] = []
            for r in range(sent_count):
                row = [self._format_table_value(r + 1)]
                for metric in metrics:
                    vals = sent_data.get(metric, [])
                    val = vals[r] if r < len(vals) else ""
                    row.append(self._format_table_value(val))
                rows.append(row)
                row_groups.append(f"sent-{r+1}")
            table = self._make_result_table(cols, rows, row_groups)
            tabs.addTab(self._table_with_filters(table), tb.name)
            self._tables[f"sent:{tb.name}"] = table
        return tabs

    def _build_text_widget(self, files: list[Path], metrics: list[str], payloads: list[dict[str, float]] | None = None) -> QWidget:
        cols = ["treebank"] + metrics
        rows: list[list[object]] = []
        row_groups: list[str] = []
        payloads = payloads if payloads is not None else self._collect_file_payloads(
            files, lambda tb: self._compute_text_payload(tb, metrics)
        )
        for tb, text_data in zip(files, payloads):
            rows.append([tb.name] + [self._format_table_value(text_data.get(metric, "")) for metric in metrics])
            row_groups.append(tb.name)
        table = self._make_result_table(cols, rows, row_groups)
        self._tables["text"] = table
        return self._table_with_filters(table)

    def _build_distribution_widget(
        self, files: list[Path], metrics: list[str], payloads: list[dict[str, tuple[list, list[float], bool, str]]] | None = None
    ) -> QWidget:
        treebank_tabs = QTabWidget()
        payloads = payloads if payloads is not None else self._collect_file_payloads(
            files, lambda tb: self._compute_distribution_payload(tb, metrics)
        )
        for tb, dist_payload in zip(files, payloads):
            metric_tabs = QTabWidget()
            for metric in metrics:
                x_vals, y_vals, used_fallback, err_msg = dist_payload.get(metric, ([], [], False, ""))
                if used_fallback:
                    self._append_report(f"Fallback distribution used for metric: {metric}")
                if err_msg:
                    self._append_report(err_msg)
                rows = [[self._format_table_value(x), self._format_table_value(y)] for x, y in zip(x_vals, y_vals)]
                table = self._make_result_table(["value", "frequency/probability"], rows, [tb.name] * len(rows))
                metric_tabs.addTab(self._table_with_filters(table), metric)
                self._tables[f"distribution:{metric}:{tb.name}"] = table
            treebank_tabs.addTab(metric_tabs, tb.name)
        return treebank_tabs

    def _build_pvp_widget(
        self,
        files: list[Path],
        classes: list[str],
        mode: str,
        payload_by_class: dict[str, list] | None = None,
    ) -> QWidget | None:
        if not classes:
            return QLabel("Select one or more word classes first.")

        if len(classes) == 1:
            cls = classes[0]
            role_tabs = self._build_pvp_role_tabs(files, cls, mode, payloads=(payload_by_class or {}).get(cls))
            return role_tabs

        class_tabs = QTabWidget()
        for cls in classes:
            role_tabs = self._build_pvp_role_tabs(files, cls, mode, payloads=(payload_by_class or {}).get(cls))
            class_tabs.addTab(role_tabs, cls)
        return class_tabs

    def _build_pvp_role_tabs(
        self, files: list[Path], selected_class: str, mode: str, payloads: list | None = None
    ) -> QTabWidget:
        role_tabs = QTabWidget()

        if payloads is None:
            gov_rows, dep_rows = self._collect_pvp_rows(files, selected_class, mode)
        else:
            gov_rows, dep_rows = self._collect_pvp_rows_from_payloads(payloads)
        gov_data = [[label, self._format_table_value(prob, keep_int=False)] for label, prob in gov_rows]
        dep_data = [[label, self._format_table_value(prob, keep_int=False)] for label, prob in dep_rows]
        gov_table = self._make_result_table(["label", "probability"], gov_data, [selected_class] * len(gov_data))
        dep_table = self._make_result_table(["label", "probability"], dep_data, [selected_class] * len(dep_data))
        role_tabs.addTab(self._table_with_filters(gov_table), "act as governors")
        role_tabs.addTab(self._table_with_filters(dep_table), "act as dependents")
        self._tables[f"pvp:{selected_class}:gov"] = gov_table
        self._tables[f"pvp:{selected_class}:dep"] = dep_table
        return role_tabs

    def _collect_pvp_rows(
        self, files: list[Path], selected_class: str, mode: str
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        gov_bucket: dict[str, list[float]] = {}
        dep_bucket: dict[str, list[float]] = {}
        payloads = self._collect_file_payloads(
            files, lambda tb: self._compute_pvp_payload(tb, selected_class, mode)
        )
        for pvp_data in payloads:
            for key, val in pvp_data.get("act as a gov", []):
                gov_bucket.setdefault(str(key), []).append(float(val))
            for key, val in pvp_data.get("act as a dep", []):
                dep_bucket.setdefault(str(key), []).append(float(val))

        gov_rows = sorted(((k, _safe_mean(v)) for k, v in gov_bucket.items()), key=lambda x: x[1], reverse=True)
        dep_rows = sorted(((k, _safe_mean(v)) for k, v in dep_bucket.items()), key=lambda x: x[1], reverse=True)
        return gov_rows, dep_rows

    def _collect_pvp_rows_from_payloads(self, payloads: list) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        gov_bucket: dict[str, list[float]] = {}
        dep_bucket: dict[str, list[float]] = {}
        for pvp_data in payloads:
            for key, val in pvp_data.get("act as a gov", []):
                gov_bucket.setdefault(str(key), []).append(float(val))
            for key, val in pvp_data.get("act as a dep", []):
                dep_bucket.setdefault(str(key), []).append(float(val))
        gov_rows = sorted(((k, _safe_mean(v)) for k, v in gov_bucket.items()), key=lambda x: x[1], reverse=True)
        dep_rows = sorted(((k, _safe_mean(v)) for k, v in dep_bucket.items()), key=lambda x: x[1], reverse=True)
        return gov_rows, dep_rows

    def _compute_metric_distribution_fallback(
        self, analyzer, metric: str, parallel: bool | None = None, n_jobs: int | None = None
    ) -> tuple[list, list[float]]:
        if metric in {"dd", "hd", "ddir", "v"}:
            dep_data = self._calc_dep_metrics(analyzer, metrics=[metric], parallel=parallel, n_jobs=n_jobs)
            values = _flatten_values(dep_data.get(metric, []))
        elif metric in {"sl", "tw", "th", "rd"}:
            sent_data = self._calc_sent_metrics(analyzer, metrics=[metric], parallel=parallel, n_jobs=n_jobs)
            values = list(sent_data.get(metric, []))
        else:
            values = []
        cleaned = [str(v) for v in values if str(v) not in {"", "None"}]
        if not cleaned:
            return [], []
        counts = Counter(cleaned)
        total = max(1, sum(counts.values()))
        # numeric-like labels first by numeric order, then lexical order.
        def _sort_key(k: str):
            try:
                return (0, float(k))
            except Exception:
                return (1, k)

        items = sorted(counts.items(), key=lambda kv: _sort_key(kv[0]))
        x_vals = [k for k, _ in items]
        y_vals = [v / total for _, v in items]
        return x_vals, y_vals

    def _compute_rd_distribution(
        self, analyzer, parallel: bool | None = None, n_jobs: int | None = None
    ) -> tuple[list[int], list[float]]:
        sent_data = self._calc_sent_metrics(analyzer, metrics=["rd"], parallel=parallel, n_jobs=n_jobs)
        rd_vals = sent_data.get("rd", [])
        counts = Counter(int(v) for v in rd_vals if isinstance(v, (int, float)))
        if not counts:
            return [], []
        total = sum(counts.values())
        items = sorted(counts.items(), key=lambda kv: kv[0])
        x_vals = [k for k, _ in items]
        y_vals = [v / total for _, v in items]
        return x_vals, y_vals

    def _safe_nested_value(self, nested: list, i: int, j: int, default=""):
        try:
            return nested[i][j]
        except Exception:
            return default

    def _should_enable_row_coloring(self, table: QTableWidget) -> bool:
        rows = table.rowCount()
        cols = table.columnCount()
        if rows <= 0 or cols <= 0:
            return False
        if rows > 2500:
            return False
        if rows * cols > 60000:
            return False
        return True

    def _apply_grouped_row_colors(self, table: QTableWidget, groups: list[str]) -> None:
        if table.rowCount() == 0:
            return
        color_a = QColor("#14181e")
        color_b = QColor("#344050")
        current = None
        toggle = 0
        for r in range(table.rowCount()):
            group = groups[r] if r < len(groups) else f"row-{r}"
            if current is None:
                current = group
            elif group != current:
                toggle = 1 - toggle
                current = group
            color = color_a if toggle == 0 else color_b
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is None:
                    item = QTableWidgetItem("")
                    table.setItem(r, c, item)
                item.setBackground(color)
                item.setForeground(QColor("#E6EAF0"))

    def _result_model(self, table) -> ResultTableModel | None:
        if isinstance(table, QTableView):
            model = table.model()
            if isinstance(model, ResultTableModel):
                return model
        return getattr(table, "_result_model", None) if table is not None else None

    def _table_with_filters(self, table) -> QWidget:
        return table

    def _install_table_filters(self, table) -> None:
        table._column_filters = {}  # type: ignore[attr-defined]
        header = table.horizontalHeader()
        if not getattr(table, "_header_filter_bound", False):
            header.sectionClicked.connect(lambda col, t=table: self._show_header_filter_menu(t, col))
            table._header_filter_bound = True  # type: ignore[attr-defined]
        self._refresh_header_filter_marks(table)

    def _apply_table_filters(self, table) -> None:
        filters: dict[int, object] = getattr(table, "_column_filters", {})
        model = self._result_model(table)
        if model is not None:
            model_filters: dict[int, set[str] | None] = {}
            for c in range(model.columnCount()):
                selected = filters.get(c)
                selected_values: set[str]
                if isinstance(selected, set):
                    selected_values = {str(v) for v in selected}
                elif isinstance(selected, (list, tuple)):
                    selected_values = {str(v) for v in selected}
                elif selected in {None, "all", ""}:
                    selected_values = set()
                else:
                    selected_values = {str(selected)}
                model_filters[c] = selected_values or None
            model.set_filters(model_filters)
            self._refresh_header_filter_marks(table)
            return
        for r in range(table.rowCount()):
            visible = True
            for c, selected in filters.items():
                selected_values: set[str]
                if isinstance(selected, set):
                    selected_values = {str(v) for v in selected}
                elif isinstance(selected, (list, tuple)):
                    selected_values = {str(v) for v in selected}
                elif selected in {None, "all", ""}:
                    selected_values = set()
                else:
                    selected_values = {str(selected)}
                if not selected_values:
                    continue
                item = table.item(r, c)
                val = item.text() if item else ""
                if val not in selected_values:
                    visible = False
                    break
            table.setRowHidden(r, not visible)
        self._refresh_header_filter_marks(table)

    def _is_numeric_filter_column(self, values: list[str]) -> bool:
        non_empty = [v for v in values if str(v).strip() != ""]
        if not non_empty:
            return False
        for v in non_empty:
            try:
                float(v)
            except Exception:
                return False
        return True

    def _default_filter_values(self, values: list[str]) -> set[str]:
        if not values:
            return set()
        if self._is_numeric_filter_column(values):
            zero_candidates = {"0", "0.0", "0.00", "0.000", "-0", "-0.0", "-0.00"}
            for v in values:
                if v in zero_candidates:
                    return {v}
                try:
                    if float(v) == 0.0:
                        return {v}
                except Exception:
                    pass
        return {values[0]}

    def _show_header_filter_menu(self, table, col: int) -> None:
        model = self._result_model(table)
        if model is not None:
            header_text = model.headers[col] if 0 <= col < len(model.headers) else ""
        else:
            header_item = table.horizontalHeaderItem(col)
            header_text = header_item.text() if header_item is not None else ""
        if not header_text:
            return
        menu = QMenu(table)
        filters: dict[int, object] = getattr(table, "_column_filters", {})
        current_raw = filters.get(col)
        if isinstance(current_raw, set):
            current_values = {str(v) for v in current_raw}
        elif isinstance(current_raw, (list, tuple)):
            current_values = {str(v) for v in current_raw}
        elif current_raw in {None, "all", ""}:
            current_values = set()
        else:
            current_values = {str(current_raw)}

        # First item: searchable input
        header = table.horizontalHeader()
        col_width = max(120, header.sectionSize(col))

        search_edit = QLineEdit(menu)
        search_edit.setPlaceholderText("Search...")
        search_edit.setFixedWidth(col_width)
        search_action = QWidgetAction(menu)
        search_action.setDefaultWidget(search_edit)
        menu.addAction(search_action)
        menu.addSeparator()

        if model is not None:
            values = model.distinct_values(col)
        else:
            values: list[str] = []
            seen = set()
            for r in range(table.rowCount()):
                item = table.item(r, col)
                val = item.text() if item else ""
                if val not in seen:
                    seen.add(val)
                    values.append(val)

        if not current_values:
            current_values = self._default_filter_values(values)

        menu.addSeparator()
        list_widget = QListWidget(menu)
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        list_widget.setMaximumHeight(220)
        list_widget.setMinimumWidth(col_width)
        list_widget.setMaximumWidth(col_width)
        list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        all_item = QListWidgetItem("ALL")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        all_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        list_widget.addItem(all_item)

        all_not_item = QListWidgetItem("ALL !=")
        all_not_item.setData(Qt.ItemDataRole.UserRole, "__all_not__")
        all_not_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        list_widget.addItem(all_not_item)

        for val in values:
            label = val if val != "" else "(empty)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, val)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if val in current_values else Qt.CheckState.Unchecked)
            list_widget.addItem(item)

        list_action = QWidgetAction(menu)
        list_action.setDefaultWidget(list_widget)
        menu.addAction(list_action)

        def apply_search(text: str) -> None:
            needle = text.strip().lower()
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                label = item.text().lower()
                item.setHidden((needle != "") and (needle not in label))

        selected = {"set": False}

        def _set_all(checked: bool) -> None:
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                key = item.data(Qt.ItemDataRole.UserRole)
                if key in {"__all__", "__all_not__"}:
                    continue
                if item.isHidden():
                    continue
                item.setCheckState(state)

        def _all_not_selected() -> None:
            selected_item = list_widget.currentItem()
            if selected_item is None:
                return
            excluded = selected_item.data(Qt.ItemDataRole.UserRole)
            if excluded in {"__all__", "__all_not__"}:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    key = item.data(Qt.ItemDataRole.UserRole)
                    if key in {"__all__", "__all_not__"} or item.isHidden():
                        continue
                    if item.checkState() == Qt.CheckState.Checked:
                        excluded = key
                        break
            if excluded in {"__all__", "__all_not__", None}:
                return
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                key = item.data(Qt.ItemDataRole.UserRole)
                if key in {"__all__", "__all_not__"}:
                    continue
                if item.isHidden():
                    continue
                item.setCheckState(Qt.CheckState.Unchecked if key == excluded else Qt.CheckState.Checked)

        def _apply_from_checks() -> None:
            chosen: set[str] = set()
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                key = item.data(Qt.ItemDataRole.UserRole)
                if key in {"__all__", "__all_not__"}:
                    continue
                if item.checkState() == Qt.CheckState.Checked:
                    chosen.add(str(key))
            if (not chosen) or (len(chosen) >= len(values)):
                filters.pop(col, None)
            else:
                filters[col] = chosen
            table._column_filters = filters  # type: ignore[attr-defined]
            self._apply_table_filters(table)
            selected["set"] = True

        def _on_item_clicked(item: QListWidgetItem) -> None:
            key = item.data(Qt.ItemDataRole.UserRole)
            if key == "__all__":
                _set_all(True)
            elif key == "__all_not__":
                _all_not_selected()

        list_widget.itemClicked.connect(_on_item_clicked)
        menu.aboutToHide.connect(_apply_from_checks)
        search_edit.textChanged.connect(apply_search)
        apply_search("")

        x = header.sectionViewportPosition(col)
        global_pos = header.viewport().mapToGlobal(header.rect().topLeft())
        menu.exec(global_pos + QPoint(x, header.height()))
        if not selected["set"]:
            return

    def _refresh_header_filter_marks(self, table) -> None:
        filters: dict[int, object] = getattr(table, "_column_filters", {})
        model = self._result_model(table)
        if model is not None:
            if model.columnCount() > 0:
                model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, model.columnCount() - 1)
            return
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            if item is None:
                continue
            base = item.text().replace(" *", "")
            selected = filters.get(c)
            has_filter = False
            if isinstance(selected, set):
                has_filter = len(selected) > 0
            elif isinstance(selected, (list, tuple)):
                has_filter = len(selected) > 0
            else:
                has_filter = selected not in {"all", "", None}
            if has_filter:
                item.setText(f"{base} *")
            else:
                item.setText(base)

    def _build_analyzer(self, treebank_path: Path, parallel: bool | None = None, n_jobs: int | None = None):
        analyzer_cls = self._get_depval_analyzer()
        with treebank_path.open("r", encoding="utf-8", errors="ignore") as fp:
            kwargs: dict[str, object] = {
                "punct_deprels": sorted(self._depval_stopdeps),
                "root_deprels": sorted(self._depval_rootdeps),
            }
            if parallel is not None:
                kwargs["parallel"] = bool(parallel)
            if n_jobs is not None:
                kwargs["n_jobs"] = int(n_jobs)
            try:
                sig = inspect.signature(analyzer_cls)
                supported = set(sig.parameters.keys())
                kwargs = {k: v for k, v in kwargs.items() if k in supported}
            except Exception:
                pass
            return analyzer_cls(fp, **kwargs)

    def _call_depval_api(self, fn, **kwargs):
        call_kwargs = dict(kwargs)
        try:
            sig = inspect.signature(fn)
            supported = set(sig.parameters.keys())
            call_kwargs = {k: v for k, v in call_kwargs.items() if k in supported}
        except Exception:
            pass
        return fn(**call_kwargs)

    def _calc_dep_metrics(self, analyzer, metrics: list[str], parallel: bool | None = None, n_jobs: int | None = None):
        return self._call_depval_api(
            analyzer.calculate_dep_metrics,
            metrics=metrics,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _calc_sent_metrics(self, analyzer, metrics: list[str], parallel: bool | None = None, n_jobs: int | None = None):
        return self._call_depval_api(
            analyzer.calculate_sent_metrics,
            metrics=metrics,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _calc_text_metrics(self, analyzer, metrics: list[str], parallel: bool | None = None, n_jobs: int | None = None):
        return self._call_depval_api(
            analyzer.calculate_text_metrics,
            metrics=metrics,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _calc_distributions(
        self,
        analyzer,
        metrics: list[str],
        normalize: bool = False,
        parallel: bool | None = None,
        n_jobs: int | None = None,
    ):
        return self._call_depval_api(
            analyzer.calculate_distributions,
            metrics=metrics,
            normalize=normalize,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _calc_pvp(
        self,
        analyzer,
        selected_input: str | None,
        mode: str = "deprel",
        normalize: bool = True,
        parallel: bool | None = None,
        n_jobs: int | None = None,
    ):
        return self._call_depval_api(
            analyzer.calculate_pvp,
            input=selected_input,
            target=mode,
            normalize=normalize,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _resolve_parallel_plan(self, files: list[Path]) -> dict[str, object]:
        jobs = self._effective_n_jobs(self.compute_jobs_spin.value())
        # Fast heuristic: avoid expensive full sentence-count scan before compute.
        small_count = 0
        big_count = 0
        for tb in files:
            try:
                size_mb = tb.stat().st_size / (1024 * 1024)
            except Exception:
                size_mb = 0.0
            if size_mb >= 20:
                big_count += 1
            else:
                small_count += 1

        if len(files) > 1:
            return {
                "mode": "auto",
                "scope": "file",
                "enabled": True,
                "n_jobs": jobs,
                "note": (
                    f"Auto parallel: multiple treebanks detected ({small_count} small, {big_count} big by file size), "
                    "use file-level parallel."
                ),
            }
        if big_count >= 1 or len(files) == 1:
            return {
                "mode": "auto",
                "scope": "treebank",
                "enabled": True,
                "n_jobs": jobs,
                "note": (
                    f"Auto parallel: single/big treebank detected ({big_count} big, {small_count} small by file size), "
                    "use treebank-internal parallel."
                ),
            }
        return {
            "mode": "auto",
            "scope": "file",
            "enabled": True,
            "n_jobs": jobs,
            "note": "Auto parallel: fallback to file-level parallel.",
        }

    def _effective_n_jobs(self, requested: int | None) -> int:
        cpu_total = max(1, int(os.cpu_count() or 1))
        cap = max(1, cpu_total)
        if requested is None:
            return min(4, cap)
        return max(1, min(int(requested), cap))

    def _count_treebank_sentences(self, treebank_path: Path) -> int:
        cache_key = str(treebank_path.resolve())
        if cache_key in self._treebank_sentence_count_cache:
            return self._treebank_sentence_count_cache[cache_key]
        count = 0
        in_sentence = False
        try:
            with treebank_path.open("r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    raw = line.strip()
                    if not raw:
                        if in_sentence:
                            count += 1
                            in_sentence = False
                        continue
                    if raw.startswith("#"):
                        continue
                    parts = raw.split("\t")
                    if len(parts) > 1 and parts[0] and parts[0][0].isdigit():
                        in_sentence = True
            if in_sentence:
                count += 1
        except Exception:
            count = 0
        self._treebank_sentence_count_cache[cache_key] = count
        return count

    def _treebank_runtime_parallel(self) -> tuple[bool, int | None]:
        if self._runtime_parallel_scope == "treebank" and self._runtime_parallel_enabled:
            return True, self._effective_n_jobs(self._runtime_n_jobs)
        return False, None

    def _file_level_parallel_enabled(self, files: list[Path]) -> bool:
        return self._runtime_parallel_scope == "file" and self._runtime_parallel_enabled and len(files) > 1

    def _collect_file_payloads(self, files: list[Path], worker):
        if not self._file_level_parallel_enabled(files):
            payloads = []
            for tb in files:
                payloads.append(worker(tb))
                self._progress_tick(tb.name)
            return payloads

        max_workers = min(self._effective_n_jobs(self._runtime_n_jobs), len(files))
        results: dict[Path, object] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(worker, tb): tb for tb in files}
            pending = set(future_map.keys())
            while pending:
                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                app = QApplication.instance()
                if app is not None and threading.current_thread() is threading.main_thread():
                    app.processEvents()
                for future in done:
                    tb = future_map[future]
                    try:
                        results[tb] = future.result()
                    except Exception as exc:
                        raise RuntimeError(f"{tb.name}: {exc}") from exc
                    self._progress_tick(tb.name)
        return [results[tb] for tb in files]

    def _compute_dep_payload(self, treebank_path: Path, metrics: list[str]) -> dict[str, object]:
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        dep_data = self._calc_dep_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)
        lemma_by_sent = self._collect_lemmas(analyzer)
        return {"dep_data": dep_data, "lemma_by_sent": lemma_by_sent}

    def _compute_sent_payload(self, treebank_path: Path, metrics: list[str]) -> dict[str, list]:
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        return self._calc_sent_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)

    def _compute_text_payload(self, treebank_path: Path, metrics: list[str]) -> dict[str, float]:
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        return self._calc_text_metrics(analyzer, metrics=metrics, parallel=parallel, n_jobs=n_jobs)

    def _compute_distribution_payload(
        self, treebank_path: Path, metrics: list[str]
    ) -> dict[str, tuple[list, list[float], bool, str]]:
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        out: dict[str, tuple[list, list[float], bool, str]] = {}
        for metric in metrics:
            used_fallback = False
            err_msg = ""
            if metric == "rd":
                try:
                    x_vals, y_vals = self._compute_rd_distribution(analyzer, parallel=parallel, n_jobs=n_jobs)
                except Exception as exc:
                    used_fallback = True
                    x_vals, y_vals = [], []
                    err_msg = f"Distribution failed: {treebank_path.name} / {metric} ({exc})"
            else:
                try:
                    dist = self._calc_distributions(
                        analyzer, metrics=[metric], normalize=True, parallel=parallel, n_jobs=n_jobs
                    )
                    x_vals, y_vals = dist.get(metric, ([], []))
                    if not x_vals and not y_vals:
                        raise ValueError(f"empty distribution for {metric}")
                except Exception:
                    used_fallback = True
                    try:
                        x_vals, y_vals = self._compute_metric_distribution_fallback(
                            analyzer, metric, parallel=parallel, n_jobs=n_jobs
                        )
                    except Exception as exc:
                        x_vals, y_vals = [], []
                        err_msg = f"Distribution failed: {treebank_path.name} / {metric} ({exc})"
            out[metric] = (x_vals, y_vals, used_fallback, err_msg)
        return out

    def _compute_pvp_payload(self, treebank_path: Path, selected_class: str, mode: str):
        parallel, n_jobs = self._treebank_runtime_parallel()
        analyzer = self._build_analyzer(treebank_path, parallel=parallel, n_jobs=n_jobs)
        return self._calc_pvp(
            analyzer,
            selected_input=selected_class,
            mode=mode,
            normalize=True,
            parallel=parallel,
            n_jobs=n_jobs,
        )

    def _collect_lemmas(self, analyzer) -> list[list[str]]:
        lemmas_per_sent: list[list[str]] = []
        for sent in analyzer.treebank:
            sent_lemmas: list[str] = []
            for word in sent:
                deprel = str(word.get("deprel", ""))
                upos = str(word.get("upos", ""))
                head = word.get("head", 0)
                in_main = (
                    deprel not in self._depval_rootdeps.union(self._depval_stopdeps)
                    and head != 0
                    and upos != "pu"
                )
                is_root = (head == 0 and upos not in self._depval_stopdeps)
                if in_main or is_root:
                    sent_lemmas.append(str(word.get("lemma", "_") or "_"))
            lemmas_per_sent.append(sent_lemmas)
        return lemmas_per_sent

    def _current_table(self):
        return self._extract_current_table(self.result_tabs.currentWidget())

    def _table_row_count(self, table, scope: str = "filtered") -> int:
        model = self._result_model(table)
        if model is not None:
            return len(model.rows) if str(scope).strip().lower() == "all" else model.rowCount()
        return int(table.rowCount()) if table is not None else 0

    def _table_column_count(self, table) -> int:
        model = self._result_model(table)
        if model is not None:
            return model.columnCount()
        return int(table.columnCount()) if table is not None else 0

    def _current_data_scope(self) -> str:
        combo = getattr(self, "data_scope_combo", None)
        if combo is None:
            return "filtered"
        data = combo.currentData()
        scope = str(data or combo.currentText() or "filtered").strip().lower()
        return "all" if scope == "all" else "filtered"

    def current_result_dataset(self, scope: str = "filtered") -> tuple[list[str], list[list[str]]] | None:
        table = self._current_table()
        if table is None:
            return None
        return self._table_to_rows(table, "all" if str(scope).strip().lower() == "all" else "filtered")

    def _extract_current_table(self, widget):
        if widget is None:
            return None
        if isinstance(widget, (QTableWidget, QTableView)):
            return widget
        if isinstance(widget, QTabWidget):
            return self._extract_current_table(widget.currentWidget())
        direct_tabs = widget.findChildren(QTabWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        for tab in direct_tabs:
            table = self._extract_current_table(tab.currentWidget())
            if table is not None:
                return table
        direct_widgets = widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        for child in direct_widgets:
            if child.isVisible():
                table = self._extract_current_table(child)
                if table is not None:
                    return table
        child_tables = widget.findChildren(QTableView, options=Qt.FindChildOption.FindDirectChildrenOnly)
        if child_tables:
            return child_tables[0]
        child_tables = widget.findChildren(QTableWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        return child_tables[0] if child_tables else None

    def _bind_tab_change_events(self, root_tab: QTabWidget) -> None:
        tabs = [root_tab] + root_tab.findChildren(QTabWidget)
        for tab in tabs:
            if getattr(tab, "_plot_bind_done", False):
                continue
            tab.currentChanged.connect(lambda _idx: self._refresh_plot_columns())
            tab._plot_bind_done = True  # type: ignore[attr-defined]

    def _refresh_plot_columns(self) -> None:
        table = self._current_table()
        self.plot_col_a_combo.blockSignals(True)
        self.plot_col_b_combo.blockSignals(True)
        self.plot_col_a_combo.clear()
        self.plot_col_b_combo.clear()
        self.plot_col_a_combo.addItem("none")
        self.plot_col_b_combo.addItem("none")
        if table is None:
            self.plot_col_a_combo.blockSignals(False)
            self.plot_col_b_combo.blockSignals(False)
            return
        model = self._result_model(table)
        headers = model.headers if model is not None else [
            table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else f"col_{c}"
            for c in range(table.columnCount())
        ]
        for name in headers:
            self.plot_col_a_combo.addItem(name)
            self.plot_col_b_combo.addItem(name)
        if self.plot_col_a_combo.count() > 1:
            self.plot_col_a_combo.setCurrentIndex(1)
        if self.plot_col_b_combo.count() > 2:
            self.plot_col_b_combo.setCurrentIndex(2)
        else:
            self.plot_col_b_combo.setCurrentIndex(0)
        self.plot_col_a_combo.blockSignals(False)
        self.plot_col_b_combo.blockSignals(False)
        self._refresh_test_columns()
        self._on_plot_selection_changed()

    def _chart_items_for_dim(self, dim: str) -> list[str]:
        if str(dim).strip().lower() == "2d":
            return ["scatter", "line", "bar", "area"]
        return ["histogram", "bar", "line", "scatter", "area", "boxplot", "density"]

    def _on_plot_dim_changed(self, value: str) -> None:
        dim = str(value).strip().lower()
        is_2d = dim == "2d"
        self.chart_type.blockSignals(True)
        current = self.chart_type.currentText().strip().lower()
        items = self._chart_items_for_dim(dim)
        self.chart_type.clear()
        self.chart_type.addItems(items)
        if current in items:
            self.chart_type.setCurrentText(current)
        self.chart_type.blockSignals(False)
        # 1D row1: Dimension + Data A; 2D row1: Dimension + Plot type
        self.plot_opt_grid.addWidget(self.row_dimension, 0, 0)
        if is_2d:
            self.plot_opt_grid.addWidget(self.row_chart, 0, 1)
            self.plot_opt_grid.addWidget(self.row_data_a, 1, 0)
            self.plot_opt_grid.addWidget(self.row_data_b, 1, 1)
            self.row_data_b.show()
            self.row_single_mode.hide()
        else:
            self.plot_opt_grid.addWidget(self.row_data_a, 0, 1)
            self.plot_opt_grid.addWidget(self.row_chart, 1, 0)
            self.plot_opt_grid.addWidget(self.row_single_mode, 1, 1)
            self.row_data_b.hide()
            self.row_single_mode.show()
        self.single_mode_combo.setEnabled(not is_2d)
        self._on_plot_selection_changed()

    def _refresh_test_columns(self) -> None:
        table = self._current_table()
        self.test_col_a_combo.blockSignals(True)
        self.test_col_b_combo.blockSignals(True)
        self.test_col_a_combo.clear()
        self.test_col_b_combo.clear()
        self.test_col_a_combo.addItem("none")
        self.test_col_b_combo.addItem("none")
        if table is not None:
            model = self._result_model(table)
            headers = model.headers if model is not None else [
                table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else f"col_{c}"
                for c in range(table.columnCount())
            ]
            for name in headers:
                self.test_col_a_combo.addItem(name)
                self.test_col_b_combo.addItem(name)
        if self.test_col_a_combo.count() > 1:
            self.test_col_a_combo.setCurrentIndex(1)
        if self.test_col_b_combo.count() > 2:
            self.test_col_b_combo.setCurrentIndex(2)
        else:
            self.test_col_b_combo.setCurrentIndex(0)
        self.test_col_a_combo.blockSignals(False)
        self.test_col_b_combo.blockSignals(False)
        self._on_test_type_changed(self.test_type_combo.currentText())

    def _on_test_type_changed(self, value: str) -> None:
        test_type = value.strip().lower()
        self.test_option_combo.blockSignals(True)
        self.test_option_combo.clear()
        if "descriptive" in test_type:
            self.test_option_combo.addItems(["summary"])
            self.test_col_b_combo.setEnabled(True)
        elif "normality" in test_type:
            self.test_option_combo.addItems(["shapiro"])
            self.test_col_b_combo.blockSignals(True)
            self.test_col_b_combo.setCurrentIndex(0)
            self.test_col_b_combo.blockSignals(False)
            self.test_col_b_combo.setEnabled(False)
        elif "nonparametric" in test_type:
            self.test_option_combo.addItems(["Wilcoxon rank-sum test", "Wilcoxon signed-rank test"])
            self.test_col_b_combo.setEnabled(True)
        elif "parametric" in test_type:
            self.test_option_combo.addItems(["independent t-test", "paired t-test"])
            self.test_col_b_combo.setEnabled(True)
        elif "correlation" in test_type:
            self.test_option_combo.addItems(["pearson", "spearman", "kendall"])
            self.test_col_b_combo.setEnabled(True)
        else:
            self.test_option_combo.addItems(["chi-square"])
            self.test_col_b_combo.setEnabled(True)
        self.test_option_combo.blockSignals(False)

    def _numeric_series(self, df, col: str):
        series = pd.to_numeric(df[col], errors="coerce")
        return series.dropna()

    def _describe_one_column(self, df, col: str) -> str:
        s_num = pd.to_numeric(df[col], errors="coerce").dropna()
        if s_num.empty:
            return "count=0; max=n/a; min=n/a; median=n/a; mean=n/a; variance=n/a"
        count = int(s_num.count())
        max_v = float(s_num.max())
        min_v = float(s_num.min())
        median_v = float(s_num.median())
        mean_v = float(s_num.mean())
        var_v = float(s_num.var(ddof=1)) if count > 1 else 0.0
        return (
            f"count={count}; "
            f"max={max_v:.6g}; "
            f"min={min_v:.6g}; "
            f"median={median_v:.6g}; "
            f"mean={mean_v:.6g}; "
            f"variance={var_v:.6g}"
        )

    def _build_stat_report(
        self,
        headers: list[str],
        rows: list[list[str]],
        test_type: str,
        option: str,
        col_a: str,
        col_b: str,
        scope_label: str,
    ) -> str:
        if pd is None:
            raise ValueError("pandas unavailable in current environment.")
        pg_mod = _ensure_pingouin()
        if pg_mod is None and scipy_stats is None and "descriptive" not in test_type:
            raise ValueError("pingouin/scipy unavailable in current environment.")
        df = pd.DataFrame([dict(zip(headers, row)) for row in rows])
        if df.empty:
            raise ValueError("no rows in selected data scope.")
        if not col_a or col_a == "none" or col_a not in df.columns:
            raise ValueError("choose valid Data A.")
        if col_b == "none":
            col_b = ""
        if col_b and col_b not in df.columns:
            raise ValueError("choose valid Data B.")

        out_lines: list[str] = [f"Data scope: {scope_label}"]
        if "descriptive" in test_type:
            out_lines.append(f"[{col_a}]")
            out_lines.append(self._describe_one_column(df, col_a))
            if col_b and col_b in df.columns and col_b != col_a:
                out_lines.append("")
                out_lines.append(f"[{col_b}]")
                out_lines.append(self._describe_one_column(df, col_b))
        elif "normality" in test_type:
            x = self._numeric_series(df, col_a)
            if x.empty:
                raise ValueError("Data A has no numeric values for Shapiro test.")
            if pg_mod is not None:
                result = pg_mod.normality(x, method="shapiro")
            else:
                w, p = scipy_stats.shapiro(x.to_numpy())  # type: ignore[union-attr]
                result = pd.DataFrame([{"W": w, "pval": p, "normal": bool(p > 0.05)}])
            out_lines.append(result.to_string(index=False))
        elif "nonparametric" in test_type:
            if not col_b:
                raise ValueError("Nonparametric test needs Data B.")
            x = self._numeric_series(df, col_a)
            y = self._numeric_series(df, col_b)
            if "rank-sum" in option:
                if len(x) < 1 or len(y) < 1:
                    raise ValueError("Not enough numeric samples for Wilcoxon rank-sum test.")
                if pg_mod is not None:
                    result = pg_mod.mwu(x, y)
                else:
                    u, p = scipy_stats.mannwhitneyu(x.to_numpy(), y.to_numpy(), alternative="two-sided")  # type: ignore[union-attr]
                    result = pd.DataFrame([{"U-val": u, "p-val": p}])
            else:
                n = min(len(x), len(y))
                if n < 2:
                    raise ValueError("Not enough numeric paired samples for Wilcoxon signed-rank test.")
                if pg_mod is not None:
                    result = pg_mod.wilcoxon(x.iloc[:n], y.iloc[:n])
                else:
                    w, p = scipy_stats.wilcoxon(x.iloc[:n].to_numpy(), y.iloc[:n].to_numpy())  # type: ignore[union-attr]
                    result = pd.DataFrame([{"W-val": w, "p-val": p}])
            out_lines.append(result.to_string(index=False))
        elif "parametric" in test_type:
            if not col_b:
                raise ValueError("Parametric t-test needs Data B.")
            x = self._numeric_series(df, col_a)
            y = self._numeric_series(df, col_b)
            n = min(len(x), len(y))
            if n < 2:
                raise ValueError("Not enough numeric paired samples.")
            x = x.iloc[:n]
            y = y.iloc[:n]
            paired = "paired" in option
            if pg_mod is not None:
                result = pg_mod.ttest(x, y, paired=paired)
            else:
                if paired:
                    t, p = scipy_stats.ttest_rel(x.to_numpy(), y.to_numpy())  # type: ignore[union-attr]
                else:
                    t, p = scipy_stats.ttest_ind(x.to_numpy(), y.to_numpy(), equal_var=False)  # type: ignore[union-attr]
                result = pd.DataFrame([{"T": t, "p-val": p, "paired": paired}])
            out_lines.append(result.to_string(index=False))
        elif "correlation" in test_type:
            if not col_b:
                raise ValueError("Correlation test needs Data B.")
            x = self._numeric_series(df, col_a)
            y = self._numeric_series(df, col_b)
            n = min(len(x), len(y))
            if n < 3:
                raise ValueError("Not enough numeric samples for correlation.")
            if pg_mod is not None:
                result = pg_mod.corr(x.iloc[:n], y.iloc[:n], method=option)
            else:
                xa = x.iloc[:n].to_numpy()
                ya = y.iloc[:n].to_numpy()
                if option == "spearman":
                    r, p = scipy_stats.spearmanr(xa, ya)  # type: ignore[union-attr]
                elif option == "kendall":
                    r, p = scipy_stats.kendalltau(xa, ya)  # type: ignore[union-attr]
                else:
                    r, p = scipy_stats.pearsonr(xa, ya)  # type: ignore[union-attr]
                result = pd.DataFrame([{"r": r, "p-val": p, "method": option}])
            out_lines.append(result.to_string(index=False))
        else:
            if not col_b:
                raise ValueError("Chi-square test needs Data B.")
            test_df = df[[col_a, col_b]].dropna().astype(str)
            if test_df.empty:
                raise ValueError("No categorical samples for chi-square.")
            if pg_mod is not None:
                chi2_result = pg_mod.chi2_independence(data=test_df, x=col_a, y=col_b)
            else:
                ct = pd.crosstab(test_df[col_a], test_df[col_b])
                chi2, p, dof, _exp = scipy_stats.chi2_contingency(ct.values)  # type: ignore[union-attr]
                chi2_result = pd.DataFrame([{"chi2": chi2, "dof": dof, "p-val": p}])
            if isinstance(chi2_result, tuple):
                for part in chi2_result:
                    try:
                        out_lines.append(part.to_string(index=False))
                    except Exception:
                        out_lines.append(str(part))
            else:
                out_lines.append(chi2_result.to_string(index=False))
        return "\n".join(out_lines)

    def run_stat_test(self) -> None:
        scope = "filtered"
        dataset = self.current_result_dataset(scope)
        if not dataset:
            self._append_test_report("Stat test failed: no table data.")
            return
        headers, rows = dataset
        if not rows:
            self._append_test_report("Stat test failed: no rows in selected data scope.")
            return
        test_type = self.test_type_combo.currentText().strip().lower()
        option = self.test_option_combo.currentText().strip().lower()
        col_a = self.test_col_a_combo.currentText().strip()
        col_b = self.test_col_b_combo.currentText().strip()
        scope_label = "Filtered rows"
        self._stat_token += 1
        token = self._stat_token
        self.test_btn.setEnabled(False)
        self.message.emit(f"Running statistical test on {scope_label.lower()}...")

        def worker() -> None:
            try:
                report = self._build_stat_report(headers, rows, test_type, option, col_a, col_b, scope_label)
                self._stat_done.emit({"token": token, "ok": True, "report": report})
            except Exception as exc:
                self._stat_done.emit({"token": token, "ok": False, "error": str(exc)})

        self._stat_thread = threading.Thread(target=worker, daemon=True)
        self._stat_thread.start()

    def _on_stat_done_async(self, payload: object) -> None:
        if not isinstance(payload, dict) or payload.get("token") != self._stat_token:
            return
        self.test_btn.setEnabled(True)
        if payload.get("ok"):
            self._append_test_report(str(payload.get("report", "")))
            self.message.emit("Statistical test completed.")
        else:
            err = str(payload.get("error", "unknown error"))
            self._append_test_report(f"Stat test failed: {err}")
            self.message.emit(f"Stat test failed: {err}")

    def _on_plot_selection_changed(self) -> None:
        kind = self.chart_type.currentText().strip().lower()
        is_2d = self.plot_dim_combo.currentText().strip().lower() == "2d"
        required_cols = 2 if is_2d else 1
        self.single_mode_combo.setEnabled((not is_2d) and kind in {"bar", "line", "scatter", "area"})

        col_a = self.plot_col_a_combo.currentText().strip()
        col_b = self.plot_col_b_combo.currentText().strip()
        selected_cols = []
        if col_a and col_a != "none":
            selected_cols.append(col_a)
        if col_b and col_b != "none" and col_b != col_a:
            selected_cols.append(col_b)
        if required_cols == 1:
            self.plot_col_b_combo.blockSignals(True)
            self.plot_col_b_combo.setCurrentIndex(0)
            self.plot_col_b_combo.blockSignals(False)
            self.plot_col_b_combo.setEnabled(False)
            return

        self.plot_col_b_combo.setEnabled(True)

    def _auto_plot_current_tab_safe(self) -> None:
        table = self._current_table()
        if table is None:
            return
        # Avoid blocking UI on very large tables; user can still plot manually.
        if self._table_row_count(table) > 3000:
            self.message.emit("Large result table detected. Auto-plot skipped; click Draw to plot manually.")
            return
        try:
            self.plot_current_tab()
        except Exception as exc:
            self._append_report(f"Auto-plot skipped due to error: {exc}")

    def _table_to_df(self, table, visible_only: bool = True):
        model = self._result_model(table)
        if model is not None:
            return model.to_dataframe("filtered" if visible_only else "all")
        headers = []
        for i in range(table.columnCount()):
            h = table.horizontalHeaderItem(i)
            headers.append(h.text() if h else f"col_{i}")
        rows: list[dict[str, object]] = []
        for r in range(table.rowCount()):
            if visible_only and table.isRowHidden(r):
                continue
            row: dict[str, object] = {}
            for c, h in enumerate(headers):
                item = table.item(r, c)
                row[h] = item.text() if item else ""
            rows.append(row)
        if not pd:
            return None
        return pd.DataFrame(rows)

    def _single_col_distribution(self, df, col: str, mode: str):
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().any():
            base = series.dropna()
        else:
            base = df[col].astype(str)
        freq = base.value_counts().sort_index()
        if mode == "frequency":
            out = pd.DataFrame({"x": list(freq.index), "y": list(freq.values)})
        else:
            prob = freq / max(1, freq.sum())
            out = pd.DataFrame({"x": list(prob.index), "y": list(prob.values)})
        return out

    def _double_col_points(self, df, x_col: str, y_col: str):
        out = pd.DataFrame({"x": df[x_col], "y": df[y_col]}).copy()
        out["x_num"] = pd.to_numeric(out["x"], errors="coerce")
        out["y_num"] = pd.to_numeric(out["y"], errors="coerce")

        x_is_num = out["x_num"].notna().sum() > 0
        y_is_num = out["y_num"].notna().sum() > 0

        if x_is_num:
            out["x"] = out["x_num"]
        else:
            cats = {v: i for i, v in enumerate(pd.Series(out["x"].astype(str)).dropna().unique())}
            out["x"] = out["x"].astype(str).map(cats)
            out.attrs["x_tick_labels"] = {v: k for k, v in cats.items()}

        if y_is_num:
            out["y"] = out["y_num"]
        else:
            cats = {v: i for i, v in enumerate(pd.Series(out["y"].astype(str)).dropna().unique())}
            out["y"] = out["y"].astype(str).map(cats)
            out.attrs["y_tick_labels"] = {v: k for k, v in cats.items()}

        out = out.dropna(subset=["x", "y"])
        return out

    def _required_cols_for_plot(self, kind: str) -> int:
        if self.plot_dim_combo.currentText().strip().lower() == "2d":
            return 2
        return 1

    def _render_svg_to_preview(self, svg_text: str) -> bool:
        plot_preview = getattr(self, "plot_preview", None)
        if not svg_text or QSvgRenderer is None or plot_preview is None:
            return False
        try:
            phi = 1.61803398875
            renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
            if not renderer.isValid():
                return False
            size = renderer.defaultSize()
            target_w = max(700, int(plot_preview.width() or 900))
            target_h = max(360, min(1100, int(round(target_w / phi))))
            svg_w = max(1, int(size.width()) if size.width() > 0 else target_w)
            svg_h = max(1, int(size.height()) if size.height() > 0 else target_h)
            scale = min(target_w / max(1, svg_w), target_h / max(1, svg_h))
            out_w = max(1, int(svg_w * scale))
            out_h = max(1, int(svg_h * scale))

            image = QImage(out_w, out_h, QImage.Format.Format_ARGB32)
            image.fill(QColor("#ffffff"))
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            plot_preview.setPixmap(QPixmap.fromImage(image))
            return True
        except Exception:
            return False

    def _draw_with_lets_plot(self, draw_df, chart: str, x_label: str, y_label: str) -> bool:
        if lp_ggplot is None or lp_aes is None:
            self.message.emit("lets-plot is unavailable. Please install lets-plot.")
            return False
        try:
            phi = 1.61803398875
            chart_kind = chart.strip().lower()
            plot_w = 1120
            plot_h = max(640, int(round(plot_w / phi)) + 70)
            p = lp_ggplot(draw_df, lp_aes(x="x", y="y")) + lp_labs(x=x_label, y=y_label)
            if lp_theme_minimal is not None:
                p += lp_theme_minimal()
            if lp_theme is not None:
                theme_kwargs: dict[str, object] = {
                    "axis_text_spacing_x": 12,
                }
                if lp_margin is not None:
                    theme_kwargs["plot_margin"] = lp_margin(t=18, r=24, b=72, l=34)
                if lp_element_text is not None and lp_margin is not None:
                    theme_kwargs["axis_text_x"] = lp_element_text(margin=lp_margin(t=8))
                try:
                    p += lp_theme(**theme_kwargs)
                except Exception:
                    pass
            if lp_ggsize is not None:
                p += lp_ggsize(plot_w, plot_h)

            if chart_kind == "scatter":
                p += lp_geom_point()
            elif chart_kind == "line":
                p += lp_geom_line()
            elif chart_kind == "area":
                p += lp_geom_area()
            elif chart_kind == "bar":
                p += lp_geom_bar(stat="identity")
            elif chart_kind == "histogram":
                p += lp_geom_histogram(bins=30)
            elif chart_kind == "density":
                p += lp_geom_density()
            elif chart_kind == "boxplot":
                p += lp_geom_boxplot()
            else:
                p += lp_geom_bar(stat="identity")

            self._last_plot_obj = p
            self._last_plot_svg = p.to_svg()
            self._last_plot_html = _lets_plot_html_with_local_js(p)
            QTimer.singleShot(0, self._open_plot_zoom_dialog)
            return True
        except Exception as exc:
            self._append_report(f"lets-plot render failed: {exc}")
            return False

    def _build_plot_payload(
        self,
        headers: list[str],
        rows: list[list[str]],
        selected_cols: list[str],
        chart: str,
        required_cols: int,
        single_mode: str,
    ) -> dict[str, object]:
        if pd is None:
            raise ValueError("pandas unavailable in current environment.")
        df = pd.DataFrame([dict(zip(headers, row)) for row in rows])
        if df.empty:
            raise ValueError("no rows in selected data scope.")
        selected_cols = [c for c in selected_cols if c in df.columns]
        if not selected_cols:
            raise ValueError("selected columns are not available.")
        if required_cols == 2 and len(selected_cols) < 2:
            raise ValueError("this plot type requires two columns.")

        if required_cols == 1:
            col = selected_cols[0]
            if chart in {"bar", "line", "scatter", "area"}:
                draw_df = self._single_col_distribution(df, col, single_mode)
                x_label = col
                y_label = "frequency" if single_mode != "probability" else "probability"
            elif chart in {"histogram", "density"}:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if s.empty:
                    raise ValueError(f"{chart} requires numeric values in '{col}'.")
                draw_df = pd.DataFrame({"x": s, "y": [0] * len(s)})
                x_label = col
                y_label = "density" if chart == "density" else "count"
            else:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if s.empty:
                    raise ValueError(f"{chart} requires numeric values in '{col}'.")
                draw_df = pd.DataFrame({"x": ["all"] * len(s), "y": s})
                x_label = ""
                y_label = col
        else:
            x_col, y_col = selected_cols[0], selected_cols[1]
            draw_df = self._double_col_points(df, x_col, y_col)
            x_label = x_col
            y_label = y_col
        if draw_df is None or draw_df.empty or ("x" not in draw_df.columns) or ("y" not in draw_df.columns):
            raise ValueError("selected columns have no plottable data.")
        return {"draw_df": draw_df, "chart": chart, "x_label": x_label, "y_label": y_label}

    def plot_current_tab(self) -> None:
        if pd is None or lp_ggplot is None:
            return
        scope = "filtered"
        dataset = self.current_result_dataset(scope)
        if not dataset:
            return
        headers, rows = dataset
        if not rows:
            self.message.emit("No rows to plot in selected data scope.")
            return

        col_a = self.plot_col_a_combo.currentText().strip()
        col_b = self.plot_col_b_combo.currentText().strip()
        selected_cols: list[str] = []
        if col_a and col_a != "none":
            selected_cols.append(col_a)
        if col_b and col_b != "none" and col_b != col_a:
            selected_cols.append(col_b)
        if not selected_cols:
            return
        selected_cols = [c for c in selected_cols if c in headers]
        if not selected_cols:
            self._refresh_plot_columns()
            return

        chart = self.chart_type.currentText().strip().lower()
        required_cols = self._required_cols_for_plot(chart)
        if required_cols == 2 and len(selected_cols) < 2:
            self.message.emit("This plot type requires two columns.")
            return

        single_mode = self.single_mode_combo.currentText()
        self._plot_token += 1
        token = self._plot_token
        self.plot_btn.setEnabled(False)
        scope_label = "filtered rows"
        self.message.emit(f"Preparing plot data from {scope_label}...")

        def worker() -> None:
            try:
                payload = self._build_plot_payload(headers, rows, selected_cols, chart, required_cols, single_mode)
                payload["token"] = token
                payload["ok"] = True
                self._plot_data_done.emit(payload)
            except Exception as exc:
                self._plot_data_done.emit({"token": token, "ok": False, "error": str(exc)})

        self._plot_thread = threading.Thread(target=worker, daemon=True)
        self._plot_thread.start()

    def _on_plot_data_done_async(self, payload: object) -> None:
        if not isinstance(payload, dict) or payload.get("token") != self._plot_token:
            return
        self.plot_btn.setEnabled(True)
        if not payload.get("ok"):
            self.message.emit(str(payload.get("error", "Plot data preparation failed.")))
            return
        draw_df = payload.get("draw_df")
        chart = str(payload.get("chart", "bar"))
        x_label = str(payload.get("x_label", ""))
        y_label = str(payload.get("y_label", ""))
        if not self._draw_with_lets_plot(draw_df, chart, x_label, y_label):
            self.message.emit("Render failed with lets-plot.")

    def _on_plot_context_menu(self, pos: QPoint) -> None:
        if lp_ggplot is None or getattr(self, "_last_plot_obj", None) is None:
            return
        menu = QMenu(self)
        zoom_action = menu.addAction("Open Zoom")
        export_action = menu.addAction("Save Image...")
        sender_obj = self.sender()
        if isinstance(sender_obj, QWidget):
            global_pos = sender_obj.mapToGlobal(pos)
        else:
            global_pos = self.mapToGlobal(pos)
        chosen = menu.exec(global_pos)
        if chosen is zoom_action:
            self._open_plot_zoom_dialog()
        elif chosen is export_action:
            self._export_plot_image_dialog()

    def _open_plot_zoom_dialog(self) -> None:
        if lp_ggplot is None or getattr(self, "_last_plot_obj", None) is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("DepVal Plot")
        dlg.resize(1200, 760)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        shown = False
        svg_doc = str(getattr(self, "_last_plot_svg", "") or "").strip()
        if svg_doc and QSvgRenderer is not None:
            try:
                renderer = QSvgRenderer(QByteArray(svg_doc.encode("utf-8")))
                if renderer.isValid():
                    # Ensure zoom preview is rendered at least at ~300 DPI quality.
                    target_dpi = 300.0
                    base_dpi = 96.0
                    dpi_factor = max(1.0, target_dpi / base_dpi)
                    dsize = renderer.defaultSize()
                    base_w = max(800, int(dsize.width()) if dsize.width() > 0 else 1400)
                    base_h = max(500, int(dsize.height()) if dsize.height() > 0 else 900)
                    w = min(8000, max(800, int(round(base_w * dpi_factor))))
                    h = min(8000, max(500, int(round(base_h * dpi_factor))))
                    image = QImage(w, h, QImage.Format.Format_ARGB32)
                    image.fill(QColor("#ffffff"))
                    painter = QPainter(image)
                    renderer.render(painter)
                    painter.end()
                    scene = QGraphicsScene(dlg)
                    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
                    scene.addItem(item)
                    view = ZoomableGraphicsView(dlg)
                    view.setScene(scene)
                    view.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    view.customContextMenuRequested.connect(self._on_plot_context_menu)
                    lay.addWidget(view, 1)
                    shown = True
            except Exception:
                shown = False
        if not shown and QWebEngineView is not None:
            try:
                web = QWebEngineView(dlg)
                _reject_web_fullscreen(web)
                if QWebEngineSettings is not None:
                    try:
                        s = web.settings()
                        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                    except Exception:
                        pass
                html_doc = str(getattr(self, "_last_plot_html", "") or "").strip()
                if html_doc:
                    web.setHtml(html_doc, QUrl.fromLocalFile(str(_runtime_base_dir()) + os.sep))
                    shown = True
                elif svg_doc:
                    fallback_html = (
                        "<html><body style='margin:0;background:#ffffff;display:flex;"
                        "align-items:center;justify-content:center;'>"
                        f"{svg_doc}</body></html>"
                    )
                    web.setHtml(fallback_html, QUrl.fromLocalFile(str(_runtime_base_dir()) + os.sep))
                    shown = True
                if shown:
                    web.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    web.customContextMenuRequested.connect(self._on_plot_context_menu)
                    lay.addWidget(web, 1)
            except Exception:
                shown = False
        if not shown:
            reason = "No plot data to preview."
            if svg_doc and QSvgRenderer is None:
                reason = "SVG render failed."
            lbl = QLabel(reason)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl, 1)
        dlg.exec()

    def _prompt_plot_export_options(self) -> tuple[str, int | None] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Options")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        fmt_combo = QComboBox(dialog)
        fmt_combo.addItem("PNG", "png")
        fmt_combo.addItem("JPG", "jpg")
        fmt_combo.addItem("BMP", "bmp")
        fmt_combo.addItem("WEBP", "webp")
        fmt_combo.addItem("SVG", "svg")
        fmt_combo.addItem("PDF", "pdf")
        fmt_combo.addItem("EPS", "eps")
        dpi_spin = QSpinBox(dialog)
        dpi_spin.setRange(72, 1200)
        dpi_spin.setValue(300)
        dpi_spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        dpi_spin.setAccelerated(True)
        dpi_spin.setMinimumHeight(28)
        dpi_spin.setStyleSheet(
            "QSpinBox { padding-right: 22px; }"
            "QSpinBox::up-button, QSpinBox::down-button { "
            "subcontrol-origin: border; width: 18px; }"
            "QSpinBox::up-button { subcontrol-position: top right; }"
            "QSpinBox::down-button { subcontrol-position: bottom right; }"
        )
        dpi_label = QLabel("DPI (raster only)")
        form.addRow("Format", fmt_combo)
        form.addRow(dpi_label, dpi_spin)
        layout.addLayout(form)

        def _refresh_dpi_enabled() -> None:
            fmt = str(fmt_combo.currentData() or "png").lower()
            raster = fmt in {"png", "jpg", "bmp", "webp"}
            dpi_spin.setEnabled(raster)
            dpi_label.setEnabled(raster)

        fmt_combo.currentIndexChanged.connect(lambda _idx: _refresh_dpi_enabled())
        _refresh_dpi_enabled()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        fmt = str(fmt_combo.currentData() or "png").lower()
        return fmt, int(dpi_spin.value())

    def _export_plot_image_dialog(self) -> None:
        if lp_ggplot is None or getattr(self, "_last_plot_obj", None) is None:
            _show_info_dialog(self, "No image", "No plot available to save.")
            return
        options = self._prompt_plot_export_options()
        if options is None:
            return
        fmt, dpi = options
        filter_map = {
            "png": "PNG Image (*.png)",
            "jpg": "JPG Image (*.jpg *.jpeg)",
            "bmp": "BMP Image (*.bmp)",
            "webp": "WEBP Image (*.webp)",
            "svg": "SVG Image (*.svg)",
            "pdf": "PDF Document (*.pdf)",
            "eps": "EPS Image (*.eps)",
        }
        out_path, _ = _themed_get_save_file_name(
            self,
            "Export plot",
            f"depval_plot.{fmt}",
            filter_map.get(fmt, "All Files (*)"),
        )
        if not out_path:
            return
        out_file = Path(out_path)
        suffix_map = {
            "png": ".png",
            "jpg": ".jpg",
            "bmp": ".bmp",
            "webp": ".webp",
            "svg": ".svg",
            "pdf": ".pdf",
            "eps": ".eps",
        }
        expect_suffix = suffix_map.get(fmt, "")
        if expect_suffix and out_file.suffix.lower() != expect_suffix:
            out_file = out_file.with_suffix(expect_suffix)

        try:
            plot_obj = self._last_plot_obj
            svg_text = getattr(self, "_last_plot_svg", "") or plot_obj.to_svg()
            if fmt == "svg":
                out_file.write_text(svg_text, encoding="utf-8")
            elif fmt == "pdf":
                if not self._export_plot_svg_to_pdf(out_file, svg_text):
                    raise RuntimeError("PDF export requires Qt SVG support or cairosvg.")
            elif fmt == "eps":
                try:
                    import cairosvg  # type: ignore

                    cairosvg.svg2eps(bytestring=svg_text.encode("utf-8"), write_to=str(out_file))
                except Exception as exc:
                    raise RuntimeError(f"EPS export requires cairosvg ({exc})") from exc
            else:
                if not self._export_plot_svg_to_raster(out_file, fmt, dpi if dpi is not None else 300, svg_text):
                    raise RuntimeError("Raster export failed.")
            self.message.emit(f"Exported plot: {out_file}")
            self._append_report(f"Exported plot: {out_file}")
        except Exception as exc:
            _show_warning_dialog(self, "Export failed", str(exc))
            self._append_report(f"Plot export failed: {exc}")

    def _export_plot_svg_to_raster(self, out_file: Path, fmt: str, dpi: int, svg_markup: str) -> bool:
        if QSvgRenderer is None or not svg_markup:
            return False
        try:
            renderer = QSvgRenderer(QByteArray(svg_markup.encode("utf-8")))
            if not renderer.isValid():
                return False
            base_size = renderer.defaultSize()
            base_w = max(1, int(base_size.width()) if base_size.width() > 0 else 1200)
            base_h = max(1, int(base_size.height()) if base_size.height() > 0 else 700)
            scale = max(0.1, float(dpi) / 96.0)
            out_w = max(1, int(base_w * scale))
            out_h = max(1, int(base_h * scale))
            image = QImage(out_w, out_h, QImage.Format.Format_ARGB32)
            image.fill(QColor("#ffffff"))
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            qt_fmt = "JPG" if fmt in {"jpg", "jpeg"} else fmt.upper()
            return image.save(str(out_file), qt_fmt)
        except Exception:
            return False

    def _export_plot_svg_to_pdf(self, out_file: Path, svg_markup: str) -> bool:
        if not svg_markup:
            return False
        try:
            renderer = QSvgRenderer(QByteArray(svg_markup.encode("utf-8")))
            if not renderer.isValid():
                return False
            writer = QPdfWriter(str(out_file))
            writer.setResolution(300)
            painter = QPainter(writer)
            renderer.render(painter)
            painter.end()
            return True
        except Exception:
            try:
                import cairosvg  # type: ignore

                cairosvg.svg2pdf(bytestring=svg_markup.encode("utf-8"), write_to=str(out_file))
                return True
            except Exception:
                return False

    def _table_to_rows(self, table, scope: str = "filtered") -> tuple[list[str], list[list[str]]]:
        model = self._result_model(table)
        if model is not None:
            return model.to_rows(scope)
        headers = [
            (table.horizontalHeaderItem(i).text() if table.horizontalHeaderItem(i) else f"col_{i}")
            for i in range(table.columnCount())
        ]
        rows: list[list[str]] = []
        use_filtered = str(scope).strip().lower() != "all"
        for r in range(table.rowCount()):
            if use_filtered and table.isRowHidden(r):
                continue
            rows.append([(table.item(r, c).text() if table.item(r, c) else "") for c in range(table.columnCount())])
        return headers, rows

    def _write_table_file(self, out_path: Path, headers: list[str], rows: list[list[str]], fmt: str) -> None:
        fmt = (fmt or "csv").lower()
        if fmt == "json":
            data = [dict(zip(headers, row)) for row in rows]
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return
        delimiter = "\t" if fmt == "tsv" else ","
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(headers)
            writer.writerows(rows)

    def save_current_result(self, fmt: str = "csv") -> None:
        table = self._current_table()
        if table is None or self._table_row_count(table) == 0:
            _show_info_dialog(self, "No data", "No result available to save.")
            return
        headers, rows = self._table_to_rows(table, "all")
        suffix = fmt.lower()
        out_path, _ = _themed_get_save_file_name(
            self,
            "Save depval result",
            f"depval_{self.result_tabs.tabText(self.result_tabs.currentIndex())}.{suffix}",
            f"{suffix.upper()} Files (*.{suffix})",
        )
        if not out_path:
            return
        out_file = Path(out_path)
        if out_file.suffix.lower() != f".{suffix}":
            out_file = out_file.with_suffix(f".{suffix}")
        self._write_table_file(out_file, headers, rows, suffix)
        self.message.emit(f"Saved: {out_file}")
        self._append_report(f"Saved current table: {out_file}")

    def save_current_result_dialog(self) -> None:
        self.save_current_result(self.table_format_combo.currentText().strip() or "csv")

    def save_all_results(self, output_root: str, treebank_paths: list[str], fmt: str = "csv") -> str:
        root_dir = Path(output_root)
        root_dir.mkdir(parents=True, exist_ok=True)

        treebanks = [Path(p) for p in treebank_paths if Path(p).exists()]
        if not treebanks:
            raise ValueError("No imported treebanks available.")

        tb_folder_map = {tb.name: (root_dir / tb.stem) for tb in treebanks}
        for folder in tb_folder_map.values():
            folder.mkdir(parents=True, exist_ok=True)
        suffix = (fmt or "csv").lower()

        # dep_metrics.csv and sent_metrics.csv by treebank
        for tb in treebanks:
            dep_key = f"dep:{tb.name}"
            sent_key = f"sent:{tb.name}"
            if dep_key in self._tables:
                headers, rows = self._table_to_rows(self._tables[dep_key], "all")
                self._write_table_file(tb_folder_map[tb.name] / f"dep_metrics.{suffix}", headers, rows, suffix)
            if sent_key in self._tables:
                headers, rows = self._table_to_rows(self._tables[sent_key], "all")
                self._write_table_file(tb_folder_map[tb.name] / f"sent_metrics.{suffix}", headers, rows, suffix)

        # each distribution csv by treebank
        for key, table in self._tables.items():
            if not key.startswith("distribution:"):
                continue
            _, metric, tb_name = key.split(":", 2)
            if tb_name not in tb_folder_map:
                continue
            headers, rows = self._table_to_rows(table, "all")
            self._write_table_file(tb_folder_map[tb_name] / f"{metric}_distribution.{suffix}", headers, rows, suffix)

        # pvp csv per treebank folder (aggregated from current pvp tabs)
        pvp_rows: list[list[str]] = []
        for key, table in self._tables.items():
            if not key.startswith("pvp:"):
                continue
            _, cls, role = key.split(":", 2)
            headers, rows = self._table_to_rows(table, "all")
            label_idx = headers.index("label") if "label" in headers else 0
            prob_idx = headers.index("probability") if "probability" in headers else 1
            for row in rows:
                pvp_rows.append([cls, role, row[label_idx], row[prob_idx]])
        if pvp_rows:
            for tb in treebanks:
                self._write_table_file(
                    tb_folder_map[tb.name] / f"pvp.{suffix}",
                    ["target", "role", "label", "probability"],
                    pvp_rows,
                    suffix,
                )

        # text_metrics.csv under data folder (global)
        if "text" in self._tables:
            headers, rows = self._table_to_rows(self._tables["text"], "all")
            self._write_table_file(root_dir / f"text_metrics.{suffix}", headers, rows, suffix)

        self.message.emit(f"Saved all tables to: {root_dir}")
        self._append_report(f"Saved all tables to: {root_dir}")
        return str(root_dir)

    def save_all_results_dialog(self) -> None:
        if not self._imported_treebanks:
            _show_info_dialog(self, "No treebanks", "No imported treebanks available.")
            return
        output_dir = _themed_get_existing_directory(self, "Select output directory", str(_runtime_base_dir()))
        if not output_dir:
            return
        try:
            saved_dir = self.save_all_results(
                output_dir,
                [str(p) for p in self._imported_treebanks],
                self.table_format_combo.currentText().strip() or "csv",
            )
            self.message.emit(f"Saved all tables to: {saved_dir}")
        except Exception as exc:
            _show_warning_dialog(self, "Save all failed", str(exc))

    def save_converted_treebanks_dialog(self) -> None:
        if not self._converted_treebank_cache:
            _show_info_dialog(self, "No converted cache", "No converted treebanks found in cache.")
            return
        output_dir = _themed_get_existing_directory(self, "Select output directory", str(_runtime_base_dir()))
        if not output_dir:
            return
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        scope_widget = getattr(self, "cache_save_scope_combo", None)
        scope = str(scope_widget.currentText() if scope_widget is not None else "selected").strip().lower()
        selected_sources = self._selected_convert_sources() if scope != "all" else []
        source_keys = {str(p.resolve()) for p in selected_sources}
        saved = 0
        for src_key, cached_path in self._converted_treebank_cache.items():
            if source_keys and src_key not in source_keys:
                continue
            src = Path(src_key)
            cached = Path(cached_path)
            if not cached.exists():
                continue
            target = out_root / cached.name
            if target.exists():
                # Avoid overwrite collisions across multiple saves.
                target = out_root / f"{src.stem}_{cached.name}"
            shutil.copy2(str(cached), str(target))
            saved += 1
        if saved == 0:
            _show_info_dialog(self, "Nothing saved", "No cached converted treebanks matched selection.")
            return
        self.message.emit(f"Saved converted treebanks: {saved}")
        self._append_report(f"Saved converted treebanks: {saved} -> {out_root}")

    def _dep_rows_from_payload(
        self, dep_payload: object, metrics: list[str]
    ) -> tuple[list[str], list[list[str]]]:
        if not isinstance(dep_payload, dict):
            return [], []
        dep_data = dep_payload.get("dep_data", {})
        lemma_by_sent = dep_payload.get("lemma_by_sent", [])
        if not isinstance(dep_data, dict):
            return [], []
        cols = ["sent id", "id", "form", "lemma", "upos", "deprel", "head"] + list(metrics or [])
        rows: list[list[str]] = []
        ids_by_sent = dep_data.get("id", []) or []
        for sent_idx, sent_ids in enumerate(ids_by_sent):
            if not isinstance(sent_ids, list):
                continue
            for word_idx, word_id in enumerate(sent_ids):
                lemma = "_"
                try:
                    if (
                        isinstance(lemma_by_sent, list)
                        and sent_idx < len(lemma_by_sent)
                        and isinstance(lemma_by_sent[sent_idx], list)
                        and word_idx < len(lemma_by_sent[sent_idx])
                    ):
                        lemma = str(lemma_by_sent[sent_idx][word_idx])
                except Exception:
                    lemma = "_"
                row = [
                    self._format_table_value(sent_idx + 1),
                    self._format_table_value(word_id),
                    self._format_table_value(self._safe_nested_value(dep_data.get("form", []), sent_idx, word_idx, "")),
                    lemma,
                    self._format_table_value(self._safe_nested_value(dep_data.get("dpos", []), sent_idx, word_idx, "")),
                    self._format_table_value(self._safe_nested_value(dep_data.get("deprel", []), sent_idx, word_idx, "")),
                    self._format_table_value(self._safe_nested_value(dep_data.get("head", []), sent_idx, word_idx, "")),
                ]
                for metric in metrics:
                    row.append(
                        self._format_table_value(
                            self._safe_nested_value(dep_data.get(metric, []), sent_idx, word_idx, "")
                        )
                    )
                rows.append(row)
        return cols, rows

    def _sent_rows_from_payload(
        self, sent_payload: object, metrics: list[str]
    ) -> tuple[list[str], list[list[str]]]:
        if not isinstance(sent_payload, dict):
            return [], []
        cols = ["sent id"] + list(metrics or [])
        sent_count = max([len(sent_payload.get(m, []) or []) for m in metrics] + [0])
        rows: list[list[str]] = []
        for r in range(sent_count):
            row = [self._format_table_value(r + 1)]
            for metric in metrics:
                vals = sent_payload.get(metric, []) or []
                val = vals[r] if r < len(vals) else ""
                row.append(self._format_table_value(val))
            rows.append(row)
        return cols, rows

    def _text_rows_from_payloads(
        self, files: list[Path], text_payloads: object, metrics: list[str], indices: list[int]
    ) -> tuple[list[str], list[list[str]]]:
        payload_list = text_payloads if isinstance(text_payloads, list) else []
        cols = ["treebank"] + list(metrics or [])
        rows: list[list[str]] = []
        for idx in indices:
            if idx < 0 or idx >= len(files):
                continue
            payload = payload_list[idx] if idx < len(payload_list) and isinstance(payload_list[idx], dict) else {}
            row = [files[idx].name]
            for metric in metrics:
                row.append(self._format_table_value(payload.get(metric, "")))
            rows.append(row)
        return cols, rows

    def _distribution_rows_from_payload(
        self, dist_payload: object
    ) -> dict[str, tuple[list[str], list[list[str]]]]:
        out: dict[str, tuple[list[str], list[list[str]]]] = {}
        if not isinstance(dist_payload, dict):
            return out
        headers = ["value", "frequency/probability"]
        for metric, metric_payload in dist_payload.items():
            if not isinstance(metric_payload, (tuple, list)) or len(metric_payload) < 2:
                continue
            x_vals = metric_payload[0] if isinstance(metric_payload[0], list) else []
            y_vals = metric_payload[1] if isinstance(metric_payload[1], list) else []
            rows = [
                [self._format_table_value(x), self._format_table_value(y)]
                for x, y in zip(x_vals, y_vals)
            ]
            out[str(metric)] = (headers, rows)
        return out

    def _pvp_rows_for_treebank(self, pvp_payloads: object, tb_idx: int) -> tuple[list[str], list[list[str]]]:
        if not isinstance(pvp_payloads, dict):
            return [], []
        rows: list[list[str]] = []
        for cls, per_tb_payloads in pvp_payloads.items():
            if not isinstance(per_tb_payloads, list) or tb_idx >= len(per_tb_payloads):
                continue
            payload = per_tb_payloads[tb_idx]
            if not isinstance(payload, dict):
                continue
            for key, role in (("act as a gov", "gov"), ("act as a dep", "dep")):
                pairs = payload.get(key, [])
                if not isinstance(pairs, list):
                    continue
                for pair in pairs:
                    if not isinstance(pair, (tuple, list)) or len(pair) < 2:
                        continue
                    rows.append(
                        [
                            str(cls),
                            role,
                            self._format_table_value(pair[0]),
                            self._format_table_value(pair[1]),
                        ]
                    )
        return ["target", "role", "label", "probability"], rows

    def save_cached_content_dialog(self) -> None:
        if not isinstance(self._render_cache, dict):
            _show_info_dialog(self, "No data", "No computed cache available. Please Compute first.")
            return
        output_dir = _themed_get_existing_directory(self, "Select output directory", str(_runtime_base_dir()))
        if not output_dir:
            return
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        fmt = (self.table_format_combo.currentText().strip() or "csv").lower()
        table_mode = str(self.save_table_combo.currentData() or "all").strip().lower()
        selected_tb_data = self.save_treebank_combo.currentData()
        selected_tb_name = ""
        if selected_tb_data not in {None, "__all__"}:
            try:
                selected_tb_name = Path(str(selected_tb_data)).name
            except Exception:
                selected_tb_name = ""
        cache = self._render_cache
        files: list[Path] = cache.get("files", [])  # type: ignore[assignment]
        level_payloads: dict[str, object] = cache.get("level_payloads", {})  # type: ignore[assignment]
        level_metrics_map: dict[str, list[str]] = cache.get("level_metrics_map", {})  # type: ignore[assignment]
        if not files:
            _show_info_dialog(self, "No data", "Computed cache has no treebank payload.")
            return

        selected_indices = [i for i, tb in enumerate(files) if not selected_tb_name or tb.name == selected_tb_name]
        if not selected_indices:
            _show_info_dialog(self, "No data", "Selected treebank is not in current compute cache.")
            return

        def _write_if_rows(path: Path, headers: list[str], rows: list[list[str]]) -> int:
            if not headers or not rows:
                return 0
            self._write_table_file(path, headers, rows, fmt)
            return 1

        save_count = 0
        for idx in selected_indices:
            tb = files[idx]
            tb_dir = out_root / tb.stem
            tb_dir.mkdir(parents=True, exist_ok=True)

            if table_mode in {"all", "dep"} and "dep" in level_payloads:
                dep_payloads = level_payloads.get("dep")
                payload = dep_payloads[idx] if isinstance(dep_payloads, list) and idx < len(dep_payloads) else {}
                headers, rows = self._dep_rows_from_payload(payload, level_metrics_map.get("dep", []))
                save_count += _write_if_rows(tb_dir / f"dep_metrics.{fmt}", headers, rows)

            if table_mode in {"all", "sent"} and "sent" in level_payloads:
                sent_payloads = level_payloads.get("sent")
                payload = sent_payloads[idx] if isinstance(sent_payloads, list) and idx < len(sent_payloads) else {}
                headers, rows = self._sent_rows_from_payload(payload, level_metrics_map.get("sent", []))
                save_count += _write_if_rows(tb_dir / f"sent_metrics.{fmt}", headers, rows)

            if table_mode in {"all", "distribution"} and "distribution" in level_payloads:
                dist_payloads = level_payloads.get("distribution")
                payload = dist_payloads[idx] if isinstance(dist_payloads, list) and idx < len(dist_payloads) else {}
                metric_rows = self._distribution_rows_from_payload(payload)
                for metric, (headers, rows) in metric_rows.items():
                    save_count += _write_if_rows(tb_dir / f"{metric}_distribution.{fmt}", headers, rows)

            if table_mode in {"all", "pvp"} and "pvp" in level_payloads:
                headers, rows = self._pvp_rows_for_treebank(level_payloads.get("pvp"), idx)
                save_count += _write_if_rows(tb_dir / f"pvp.{fmt}", headers, rows)

        if table_mode in {"all", "text"} and "text" in level_payloads:
            headers, rows = self._text_rows_from_payloads(
                files, level_payloads.get("text"), level_metrics_map.get("text", []), selected_indices
            )
            save_count += _write_if_rows(out_root / f"text_metrics.{fmt}", headers, rows)

        if save_count == 0:
            _show_info_dialog(self, "Nothing saved", "No computed payload matched current save filters.")
            return
        self.message.emit(f"Saved compute cache results: {save_count} file(s) -> {out_root}")
        self._append_report(f"Saved compute cache results: {save_count} file(s) -> {out_root}")

    def save_current_plot_dialog(self) -> None:
        if lp_ggplot is None or getattr(self, "_last_plot_obj", None) is None:
            _show_info_dialog(self, "No image", "No plot available to save.")
            return
        image_fmt = self.image_format_combo.currentText().strip().lower() or "png"
        out_path, _ = _themed_get_save_file_name(
            self,
            "Save current image",
            f"depval_plot.{image_fmt}",
            f"{image_fmt.upper()} Files (*.{image_fmt})",
        )
        if not out_path:
            return
        out_file = Path(out_path)
        if out_file.suffix.lower() != f".{image_fmt}":
            out_file = out_file.with_suffix(f".{image_fmt}")
        try:
            plot_obj = self._last_plot_obj
            svg_text = getattr(self, "_last_plot_svg", "") or plot_obj.to_svg()
            if image_fmt == "svg":
                out_file.write_text(svg_text, encoding="utf-8")
            elif image_fmt in {"png", "jpg", "jpeg"}:
                if QSvgRenderer is None:
                    raise RuntimeError("QSvgRenderer is unavailable.")
                renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
                if not renderer.isValid():
                    raise RuntimeError("Invalid SVG generated by lets-plot.")
                size = renderer.defaultSize()
                w = max(1200, int(size.width()) if size.width() > 0 else 1200)
                h = max(700, int(size.height()) if size.height() > 0 else 700)
                image = QImage(w, h, QImage.Format.Format_ARGB32)
                image.fill(QColor("#ffffff"))
                painter = QPainter(image)
                renderer.render(painter)
                painter.end()
                image.save(str(out_file), "JPG" if image_fmt in {"jpg", "jpeg"} else "PNG")
            elif image_fmt == "pdf":
                if QSvgRenderer is None:
                    raise RuntimeError("QSvgRenderer is unavailable.")
                renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
                if not renderer.isValid():
                    raise RuntimeError("Invalid SVG generated by lets-plot.")
                size = renderer.defaultSize()
                w = max(1200, int(size.width()) if size.width() > 0 else 1200)
                h = max(700, int(size.height()) if size.height() > 0 else 700)
                writer = QPdfWriter(str(out_file))
                writer.setPageSizeMM(QSizeF(297, 210))
                painter = QPainter(writer)
                renderer.render(painter)
                painter.end()
            else:
                raise RuntimeError(f"Unsupported image format: {image_fmt}")
            self.message.emit(f"Saved image: {out_file}")
            self._append_report(f"Saved current image: {out_file}")
        except Exception as exc:
            _show_warning_dialog(self, "Save image failed", str(exc))
            self._append_report(f"Save image failed: {exc}")


class LingnetWorker(QThread):
    finished = pyqtSignal(object, str)
    failed = pyqtSignal(str)
    note = pyqtSignal(str)

    def __init__(
        self,
        treebanks: list[Path],
        relation_mode: str,
        directed: bool,
        weighted: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._treebanks = treebanks
        self._relation_mode = relation_mode
        self._directed = bool(directed)
        self._weighted = bool(weighted)

    def run(self) -> None:
        try:
            converter_note = ""
            try:
                mod = importlib.import_module("quansyn.lingnet")
                converter = getattr(mod, "conllu2edge", None)
                if not callable(converter):
                    raise RuntimeError("quansyn.lingnet.conllu2edge is unavailable.")
            except Exception as exc:
                converter = _lingnet_fallback_conllu2edge
                converter_note = f"Using built-in LingNet edge extractor fallback: {exc}"
            outputs: dict[str, list[tuple[str, str]]] = {}
            if converter_note:
                self.note.emit(converter_note)
            for tb in self._treebanks:
                edges: list[tuple[str, str]] = []
                seen: set[tuple[str, str]] = set()
                with tb.open("r", encoding="utf-8", errors="ignore") as f:
                    raw_edges = converter(f, mode=self._relation_mode)
                for item in raw_edges or []:
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    left = str(item[0]).strip()
                    right = str(item[1]).strip()
                    if not left or not right:
                        continue
                    # Enforce dependency direction as: head -> dependent
                    # (source=head, target=dependent).
                    if self._relation_mode == "dependency":
                        src = right
                        dst = left
                    else:
                        src = left
                        dst = right
                    if src == dst:
                        continue
                    if _is_punct_token(src) or _is_punct_token(dst):
                        continue
                    edge = (src, dst)
                    if not self._directed:
                        edge = (src, dst) if src <= dst else (dst, src)
                    if not self._weighted:
                        if edge in seen:
                            continue
                        seen.add(edge)
                    edges.append(edge)
                outputs[str(tb)] = edges
            self.finished.emit(outputs, self._relation_mode)
        except Exception as exc:
            self.failed.emit(str(exc))


class LingnetMetricWorker(QThread):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        edge_weights: dict[tuple[str, str], int],
        directed: bool,
        weighted: bool,
        selected_global_keys: list[str],
        selected_local_keys: list[str],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._edge_weights = edge_weights
        self._directed = bool(directed)
        self._weighted = bool(weighted)
        self._selected_global_keys = set(str(k) for k in selected_global_keys)
        self._selected_local_keys = set(str(k) for k in selected_local_keys)

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        n = len(xs)
        if n < 2 or n != len(ys):
            return None
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = 0.0
        var_x = 0.0
        var_y = 0.0
        for x, y in zip(xs, ys):
            dx = x - mean_x
            dy = y - mean_y
            cov += dx * dy
            var_x += dx * dx
            var_y += dy * dy
        if var_x <= 0.0 or var_y <= 0.0:
            return None
        return cov / math.sqrt(var_x * var_y)

    @staticmethod
    def _degree_exponent_text(values: list[float]) -> str:
        if powerlaw is None:
            return "n/a"
        pos_vals = [int(round(float(v))) for v in values if float(v) > 0.0]
        if len(pos_vals) < 3:
            return "n/a"
        try:
            fit = powerlaw.Fit(pos_vals, discrete=True, verbose=False)
            alpha = float(getattr(fit.power_law, "alpha", 0.0) or 0.0)
            if alpha <= 0.0 or math.isnan(alpha) or math.isinf(alpha):
                return "n/a"
            return f"{alpha:.4f}"
        except Exception:
            return "n/a"

    def _run_with_igraph(self) -> dict[str, object]:
        if ig is None:
            raise RuntimeError("Neither networkit nor igraph is available.")
        node_names = sorted({n for a, b in self._edge_weights.keys() for n in (a, b)})
        if not node_names:
            raise RuntimeError("No network data.")
        idx_map = {name: i for i, name in enumerate(node_names)}
        edges_idx: list[tuple[int, int]] = []
        w_list: list[float] = []
        for (a, b), w in self._edge_weights.items():
            u = idx_map[a]
            v = idx_map[b]
            if u == v:
                continue
            edges_idx.append((u, v))
            w_list.append(float(w) if self._weighted else 1.0)
        g = ig.Graph(n=len(node_names), edges=edges_idx, directed=self._directed)
        g.vs["name"] = node_names
        if self._weighted:
            g.es["weight"] = w_list

        n = int(g.vcount())
        m = int(g.ecount())
        if self._directed:
            # Keep the same UI semantics as current networkit branch.
            out_raw = [float(x) for x in g.degree(mode="in")]
            in_raw = [float(x) for x in g.degree(mode="out")]
            deg_raw = [in_raw[i] + out_raw[i] for i in range(n)]
        else:
            deg_raw = [float(x) for x in g.degree(mode="all")]
            in_raw = [0.0 for _ in range(n)]
            out_raw = [0.0 for _ in range(n)]

        local_degree = {node_names[i]: float(deg_raw[i]) for i in range(n)}
        local_in_degree = {node_names[i]: float(in_raw[i]) for i in range(n)}
        local_out_degree = {node_names[i]: float(out_raw[i]) for i in range(n)}
        degree_values = [float(local_degree[node_names[i]]) for i in range(n)]
        avg_in_degree = (sum(in_raw) / float(n)) if (n > 0 and self._directed) else None
        avg_out_degree = (sum(out_raw) / float(n)) if (n > 0 and self._directed) else None

        GU = g.as_undirected(combine_edges="first") if self._directed else g
        need_components = any(
            k in self._selected_global_keys for k in {"components", "largest_cc_ratio", "avg_path_length", "diameter"}
        ) or ("out_avg_path" in self._selected_local_keys)
        components: list[list[int]] = []
        comp_count = 0
        largest_ratio = 0.0
        largest_nodes_set: set[int] = set()
        if need_components:
            comps = GU.components()
            components = [list(c) for c in comps]
            comp_count = len(components)
            largest = max(components, key=len) if components else []
            largest_nodes_set = set(int(x) for x in largest)
            largest_ratio = (len(largest) / float(n)) if n > 0 else 0.0

        density = 0.0
        if n > 1 and "density" in self._selected_global_keys:
            density = float(g.density(loops=False))

        global_clust = 0.0
        if "global_clustering" in self._selected_global_keys:
            try:
                global_clust = float(GU.transitivity_undirected(mode="zero"))
            except Exception:
                global_clust = 0.0

        avg_path = None
        diameter = None
        pair_shortest_paths: list[tuple[str, str, float]] = []
        need_path_matrix = ("avg_path_length" in self._selected_global_keys) or ("diameter" in self._selected_global_keys)
        if need_path_matrix and largest_nodes_set:
            try:
                ids = sorted(largest_nodes_set)
                sub = GU.induced_subgraph(ids)
                dist = sub.distances()
                names_sub = [str(x) for x in sub.vs["name"]]
                pair_sum = 0.0
                pair_cnt = 0
                diam = 0.0
                for i in range(len(dist)):
                    row = dist[i]
                    for j in range(i + 1, len(row)):
                        dij = float(row[j])
                        if math.isinf(dij) or dij <= 0.0:
                            continue
                        pair_sum += dij
                        pair_cnt += 1
                        if dij > diam:
                            diam = dij
                        if "avg_path_length" in self._selected_global_keys:
                            pair_shortest_paths.append((names_sub[i], names_sub[j], dij))
                if pair_cnt > 0:
                    if "avg_path_length" in self._selected_global_keys:
                        avg_path = pair_sum / float(pair_cnt)
                    if "diameter" in self._selected_global_keys:
                        diameter = diam
            except Exception:
                avg_path = None
                diameter = None

        local_out_avg_path: dict[str, float] = {}
        if "out_avg_path" in self._selected_local_keys and components:
            try:
                for comp in components:
                    if len(comp) <= 1:
                        only = node_names[int(comp[0])] if comp else None
                        if only is not None:
                            local_out_avg_path[only] = 0.0
                        continue
                    sub = GU.induced_subgraph(comp)
                    dist = sub.distances()
                    names_sub = [str(x) for x in sub.vs["name"]]
                    for i in range(len(dist)):
                        vals = [float(v) for j, v in enumerate(dist[i]) if i != j and not math.isinf(float(v)) and float(v) > 0.0]
                        local_out_avg_path[names_sub[i]] = (sum(vals) / float(len(vals))) if vals else 0.0
            except Exception:
                local_out_avg_path = {name: 0.0 for name in node_names}

        local_clustering: dict[str, float] = {}
        if "clustering" in self._selected_local_keys:
            try:
                cc = GU.transitivity_local_undirected(vertices=None, mode="zero")
                local_clustering = {node_names[i]: float(cc[i]) for i in range(n)}
            except Exception:
                local_clustering = {name: 0.0 for name in node_names}

        local_betweenness: dict[str, float] = {}
        if "betweenness" in self._selected_local_keys:
            try:
                bw = g.betweenness(directed=self._directed, weights=("weight" if self._weighted else None))
                local_betweenness = {node_names[i]: float(bw[i]) for i in range(n)}
            except Exception:
                local_betweenness = {name: 0.0 for name in node_names}

        local_eigenvector: dict[str, float] = {}
        if "eigenvector" in self._selected_local_keys:
            try:
                ec = g.eigenvector_centrality(directed=self._directed, weights=("weight" if self._weighted else None))
                local_eigenvector = {node_names[i]: float(ec[i]) for i in range(n)}
            except Exception:
                local_eigenvector = {name: 0.0 for name in node_names}

        local_closeness: dict[str, float] = {}
        if "closeness" in self._selected_local_keys:
            try:
                cl = GU.closeness(vertices=None, mode="all", normalized=True)
                local_closeness = {node_names[i]: float(cl[i]) for i in range(n)}
            except Exception:
                local_closeness = {name: 0.0 for name in node_names}

        assortativity = None
        if "assortativity" in self._selected_global_keys:
            try:
                assortativity = float(g.assortativity_degree(directed=self._directed))
            except Exception:
                assortativity = None

        degree_exponent_text = self._degree_exponent_text(degree_values)
        in_degree_exponent_text = self._degree_exponent_text(list(local_in_degree.values())) if self._directed else "n/a"
        out_degree_exponent_text = self._degree_exponent_text(list(local_out_degree.values())) if self._directed else "n/a"

        return {
            "nodes": node_names,
            "degree_values": degree_values,
            "global_map": {
                "nodes": str(n),
                "edges": str(m),
                "largest_cc_ratio": f"{largest_ratio:.4f}",
                "components": str(comp_count),
                "density": f"{density:.4f}",
                "global_clustering": f"{global_clust:.4f}",
                "avg_path_length": f"{avg_path:.4f}" if avg_path is not None else "n/a",
                "diameter": f"{diameter:.4f}" if diameter is not None else "n/a",
                "avg_degree": f"{((sum(local_degree.values()) / float(n)) if n > 0 else 0.0):.4f}",
                "avg_in_degree": f"{avg_in_degree:.4f}" if avg_in_degree is not None else "n/a",
                "avg_out_degree": f"{avg_out_degree:.4f}" if avg_out_degree is not None else "n/a",
                "degree_exponent": degree_exponent_text,
                "in_degree_exponent": in_degree_exponent_text,
                "out_degree_exponent": out_degree_exponent_text,
                "assortativity": f"{assortativity:.4f}" if assortativity is not None else "n/a",
            },
            "pair_shortest_paths": pair_shortest_paths,
            "meta": {"directed": self._directed, "weighted": self._weighted, "backend": "igraph"},
            "local_values_map": {
                "degree": local_degree,
                "in_degree": local_in_degree,
                "out_degree": local_out_degree,
                "out_avg_path": local_out_avg_path,
                "clustering": local_clustering,
                "betweenness": local_betweenness,
                "eigenvector": local_eigenvector,
                "closeness": local_closeness,
            },
        }

    def _run_with_networkx(self) -> dict[str, object]:
        if nx is None:
            raise RuntimeError("networkx is unavailable.")
        node_names = sorted({n for a, b in self._edge_weights.keys() for n in (a, b)})
        if not node_names:
            raise RuntimeError("No network data.")
        G = nx.DiGraph() if self._directed else nx.Graph()
        G.add_nodes_from(node_names)
        for (a, b), w in self._edge_weights.items():
            if a == b:
                continue
            if self._weighted:
                ww = float(w)
                if G.has_edge(a, b):
                    G[a][b]["weight"] = float(G[a][b].get("weight", 0.0)) + ww
                else:
                    G.add_edge(a, b, weight=ww)
            else:
                G.add_edge(a, b)

        n = int(G.number_of_nodes())
        m = int(G.number_of_edges())
        if self._directed:
            # Keep UI convention aligned with existing code path.
            out_raw = {k: float(v) for k, v in G.in_degree()}
            in_raw = {k: float(v) for k, v in G.out_degree()}
            deg_raw = {k: float(in_raw.get(k, 0.0) + out_raw.get(k, 0.0)) for k in node_names}
        else:
            deg_raw = {k: float(v) for k, v in G.degree()}
            in_raw = {k: 0.0 for k in node_names}
            out_raw = {k: 0.0 for k in node_names}

        local_degree = {k: float(deg_raw.get(k, 0.0)) for k in node_names}
        local_in_degree = {k: float(in_raw.get(k, 0.0)) for k in node_names}
        local_out_degree = {k: float(out_raw.get(k, 0.0)) for k in node_names}
        degree_values = [float(local_degree.get(k, 0.0)) for k in node_names]
        avg_in_degree = (sum(local_in_degree.values()) / float(n)) if (n > 0 and self._directed) else None
        avg_out_degree = (sum(local_out_degree.values()) / float(n)) if (n > 0 and self._directed) else None

        GU = G.to_undirected() if self._directed else G
        need_components = any(
            k in self._selected_global_keys for k in {"components", "largest_cc_ratio", "avg_path_length", "diameter"}
        ) or ("out_avg_path" in self._selected_local_keys)
        components: list[list[str]] = []
        comp_count = 0
        largest_ratio = 0.0
        largest_nodes_set: set[str] = set()
        if need_components:
            components = [list(c) for c in nx.connected_components(GU)]
            comp_count = len(components)
            largest = max(components, key=len) if components else []
            largest_nodes_set = set(str(x) for x in largest)
            largest_ratio = (len(largest) / float(n)) if n > 0 else 0.0

        density = float(nx.density(G)) if (n > 1 and "density" in self._selected_global_keys) else 0.0
        global_clust = 0.0
        if "global_clustering" in self._selected_global_keys:
            try:
                global_clust = float(nx.transitivity(GU))
            except Exception:
                global_clust = 0.0

        avg_path = None
        diameter = None
        pair_shortest_paths: list[tuple[str, str, float]] = []
        need_path_matrix = ("avg_path_length" in self._selected_global_keys) or ("diameter" in self._selected_global_keys)
        if need_path_matrix and largest_nodes_set:
            try:
                sub = GU.subgraph(largest_nodes_set).copy()
                sp_iter = nx.all_pairs_shortest_path_length(sub)
                pair_sum = 0.0
                pair_cnt = 0
                diam = 0.0
                for src, row in sp_iter:
                    s = str(src)
                    for dst, dd in row.items():
                        d = str(dst)
                        if s >= d:
                            continue
                        dij = float(dd)
                        if dij <= 0.0:
                            continue
                        pair_sum += dij
                        pair_cnt += 1
                        if dij > diam:
                            diam = dij
                        if "avg_path_length" in self._selected_global_keys:
                            pair_shortest_paths.append((s, d, dij))
                if pair_cnt > 0:
                    if "avg_path_length" in self._selected_global_keys:
                        avg_path = pair_sum / float(pair_cnt)
                    if "diameter" in self._selected_global_keys:
                        diameter = diam
            except Exception:
                avg_path = None
                diameter = None

        local_out_avg_path: dict[str, float] = {}
        if "out_avg_path" in self._selected_local_keys and components:
            try:
                for comp in components:
                    if len(comp) <= 1:
                        if comp:
                            local_out_avg_path[str(comp[0])] = 0.0
                        continue
                    sub = GU.subgraph(comp).copy()
                    for src, row in nx.all_pairs_shortest_path_length(sub):
                        vals = [float(v) for dst, v in row.items() if dst != src and float(v) > 0.0]
                        local_out_avg_path[str(src)] = (sum(vals) / float(len(vals))) if vals else 0.0
            except Exception:
                local_out_avg_path = {name: 0.0 for name in node_names}

        local_clustering: dict[str, float] = {}
        if "clustering" in self._selected_local_keys:
            try:
                local_clustering = {str(k): float(v) for k, v in nx.clustering(GU).items()}
            except Exception:
                local_clustering = {name: 0.0 for name in node_names}

        local_betweenness: dict[str, float] = {}
        if "betweenness" in self._selected_local_keys:
            try:
                local_betweenness = {
                    str(k): float(v)
                    for k, v in nx.betweenness_centrality(
                        G, normalized=True, weight=("weight" if self._weighted else None)
                    ).items()
                }
            except Exception:
                local_betweenness = {name: 0.0 for name in node_names}

        local_eigenvector: dict[str, float] = {}
        if "eigenvector" in self._selected_local_keys:
            try:
                local_eigenvector = {
                    str(k): float(v)
                    for k, v in nx.eigenvector_centrality(
                        G, max_iter=300, tol=1.0e-6, weight=("weight" if self._weighted else None)
                    ).items()
                }
            except Exception:
                local_eigenvector = {name: 0.0 for name in node_names}

        local_closeness: dict[str, float] = {}
        if "closeness" in self._selected_local_keys:
            try:
                local_closeness = {str(k): float(v) for k, v in nx.closeness_centrality(GU).items()}
            except Exception:
                local_closeness = {name: 0.0 for name in node_names}

        assortativity = None
        if "assortativity" in self._selected_global_keys:
            try:
                assortativity = float(nx.degree_assortativity_coefficient(G))
                if math.isnan(assortativity) or math.isinf(assortativity):
                    assortativity = None
            except Exception:
                assortativity = None

        degree_exponent_text = self._degree_exponent_text(degree_values)
        in_degree_exponent_text = self._degree_exponent_text(list(local_in_degree.values())) if self._directed else "n/a"
        out_degree_exponent_text = self._degree_exponent_text(list(local_out_degree.values())) if self._directed else "n/a"

        return {
            "nodes": node_names,
            "degree_values": degree_values,
            "global_map": {
                "nodes": str(n),
                "edges": str(m),
                "largest_cc_ratio": f"{largest_ratio:.4f}",
                "components": str(comp_count),
                "density": f"{density:.4f}",
                "global_clustering": f"{global_clust:.4f}",
                "avg_path_length": f"{avg_path:.4f}" if avg_path is not None else "n/a",
                "diameter": f"{diameter:.4f}" if diameter is not None else "n/a",
                "avg_degree": f"{((sum(local_degree.values()) / float(n)) if n > 0 else 0.0):.4f}",
                "avg_in_degree": f"{avg_in_degree:.4f}" if avg_in_degree is not None else "n/a",
                "avg_out_degree": f"{avg_out_degree:.4f}" if avg_out_degree is not None else "n/a",
                "degree_exponent": degree_exponent_text,
                "in_degree_exponent": in_degree_exponent_text,
                "out_degree_exponent": out_degree_exponent_text,
                "assortativity": f"{assortativity:.4f}" if assortativity is not None else "n/a",
            },
            "pair_shortest_paths": pair_shortest_paths,
            "meta": {"directed": self._directed, "weighted": self._weighted, "backend": "networkx"},
            "local_values_map": {
                "degree": local_degree,
                "in_degree": local_in_degree,
                "out_degree": local_out_degree,
                "out_avg_path": local_out_avg_path,
                "clustering": local_clustering,
                "betweenness": local_betweenness,
                "eigenvector": local_eigenvector,
                "closeness": local_closeness,
            },
        }

    def run(self) -> None:
        try:
            nk_mod = _ensure_networkit()
            if nk_mod is None:
                detail = _networkit_import_error or "unknown import error"
                raise RuntimeError(f"networkit is unavailable: {detail}")
            try:
                cpus = max(1, int((__import__("os").cpu_count() or 1)))
                nk_mod.setNumberOfThreads(cpus)
            except Exception:
                pass
            node_names = sorted({n for a, b in self._edge_weights.keys() for n in (a, b)})
            if not node_names:
                raise RuntimeError("No network data.")
            idx_map = {name: i for i, name in enumerate(node_names)}
            G = nk_mod.Graph(n=len(node_names), weighted=self._weighted, directed=self._directed)
            for (a, b), w in self._edge_weights.items():
                u = idx_map[a]
                v = idx_map[b]
                if u == v:
                    continue
                if self._weighted:
                    G.addEdge(u, v, float(w))
                else:
                    G.addEdge(u, v)

            n = int(G.numberOfNodes())
            m = int(G.numberOfEdges())
            # Degree variants from networkit API.
            in_degree_vals = {name: 0.0 for name in node_names}
            out_degree_vals = {name: 0.0 for name in node_names}
            local_degree = {name: 0.0 for name in node_names}

            for u, name in enumerate(node_names):
                try:
                    if self._directed:
                        # Follow UI convention for dependency direction labels:
                        # out-degree counts edges from target-node perspective,
                        # and in-degree is the opposite.
                        outdeg = float(G.degreeIn(u))
                        indeg = float(G.degreeOut(u))
                        deg = indeg + outdeg
                    else:
                        deg = float(G.degree(u))
                        indeg = 0.0
                        outdeg = 0.0
                except Exception:
                    deg = float(G.degree(u))
                    if self._directed:
                        indeg = 0.0
                        outdeg = 0.0
                    else:
                        indeg = 0.0
                        outdeg = 0.0
                in_degree_vals[name] = indeg
                out_degree_vals[name] = outdeg
                local_degree[name] = deg
            degree_values = [float(local_degree.get(node_names[u], 0.0)) for u in range(n)]
            local_in_degree = in_degree_vals
            local_out_degree = out_degree_vals
            avg_in_degree = (sum(in_degree_vals.values()) / float(n)) if (n > 0 and self._directed) else None
            avg_out_degree = (sum(out_degree_vals.values()) / float(n)) if (n > 0 and self._directed) else None
            def _degree_exponent_text(values: list[float]) -> str:
                if powerlaw is None:
                    return "n/a"
                pos_vals = [int(round(float(v))) for v in values if float(v) > 0.0]
                if len(pos_vals) < 3:
                    return "n/a"
                try:
                    fit = powerlaw.Fit(pos_vals, discrete=True, verbose=False)
                    alpha = float(getattr(fit.power_law, "alpha", 0.0) or 0.0)
                    if alpha <= 0.0 or math.isnan(alpha) or math.isinf(alpha):
                        return "n/a"
                    return f"{alpha:.4f}"
                except Exception:
                    return "n/a"

            # Connected components and path/clustering.
            GU = nk_mod.graphtools.toUndirected(G) if self._directed else G
            need_components = any(
                k in self._selected_global_keys for k in {"components", "largest_cc_ratio", "avg_path_length", "diameter"}
            ) or ("out_avg_path" in self._selected_local_keys)
            components: list[list[int]] = []
            comp_count = 0
            largest_comp_size = 0
            largest_ratio = 0.0
            if need_components:
                cc = nk_mod.components.ConnectedComponents(GU)
                cc.run()
                components = cc.getComponents()
                comp_count = int(len(components))
                largest_comp_size = max((len(c) for c in components), default=0)
                largest_ratio = (largest_comp_size / n) if n > 0 else 0.0
            largest_nodes_set: set[int] = set(max(components, key=len)) if components else set()

            density = 0.0
            if n > 1 and "density" in self._selected_global_keys:
                density = (float(m) / float(n * (n - 1))) if self._directed else (2.0 * float(m) / float(n * (n - 1)))

            global_clust = 0.0
            if "global_clustering" in self._selected_global_keys:
                try:
                    global_clust = float(nk_mod.globals.ClusteringCoefficient().exactGlobal(GU))
                except Exception:
                    global_clust = 0.0

            avg_path = None
            diameter = None
            local_out_avg_path: dict[str, float] = {}
            need_path_matrix = ("avg_path_length" in self._selected_global_keys) or ("diameter" in self._selected_global_keys)
            pair_shortest_paths: list[tuple[str, str, float]] = []
            if need_path_matrix:
                # exact APSP only when requested (very expensive on large graphs)
                try:
                    # Use undirected graph and only largest connected component to avoid infinite distances.
                    apsp = nk_mod.distance.APSP(GU)
                    apsp.run()
                    dists = apsp.getDistances()
                    pair_sum = 0.0
                    pair_cnt = 0
                    diam = 0.0
                    for i in range(n):
                        if largest_nodes_set and i not in largest_nodes_set:
                            continue
                        row = dists[i]
                        j_start = i + 1
                        for j in range(j_start, n):
                            if largest_nodes_set and j not in largest_nodes_set:
                                continue
                            if i == j:
                                continue
                            dij = float(row[j])
                            if math.isinf(dij) or dij <= 0.0:
                                continue
                            if dij > diam:
                                diam = dij
                            pair_sum += dij
                            pair_cnt += 1
                            if "avg_path_length" in self._selected_global_keys:
                                pair_shortest_paths.append((node_names[i], node_names[j], dij))
                    if pair_cnt > 0:
                        if "avg_path_length" in self._selected_global_keys:
                            avg_path = pair_sum / float(pair_cnt)
                        if "diameter" in self._selected_global_keys:
                            diameter = diam
                except Exception:
                    avg_path = None
                    diameter = None

            if "out_avg_path" in self._selected_local_keys:
                try:
                    apsp_out = nk_mod.distance.APSP(GU)
                    apsp_out.run()
                    d_out = apsp_out.getDistances()
                    comp_index: dict[int, int] = {}
                    comp_nodes: dict[int, list[int]] = {}
                    if components:
                        for cid, comp in enumerate(components):
                            comp_nodes[cid] = list(comp)
                            for u in comp:
                                comp_index[int(u)] = cid
                    else:
                        comp_nodes[0] = list(range(n))
                        for u in range(n):
                            comp_index[u] = 0
                    for i in range(n):
                        row = d_out[i]
                        s = 0.0
                        c = 0
                        cid = comp_index.get(i, -1)
                        if cid < 0:
                            local_out_avg_path[node_names[i]] = 0.0
                            continue
                        for j in comp_nodes.get(cid, []):
                            if i == j:
                                continue
                            dij = float(row[j])
                            if math.isinf(dij) or dij <= 0.0:
                                continue
                            s += dij
                            c += 1
                        local_out_avg_path[node_names[i]] = (s / float(c)) if c > 0 else 0.0
                except Exception:
                    local_out_avg_path = {name: 0.0 for name in node_names}

            local_clustering: dict[str, float] = {}
            if "clustering" in self._selected_local_keys:
                try:
                    cl_local = nk_mod.centrality.LocalClusteringCoefficient(GU)
                    cl_local.run()
                    local_clustering = {node_names[i]: float(cl_local.scores()[i]) for i in range(n)}
                except Exception:
                    local_clustering = {name: 0.0 for name in node_names}

            local_betweenness: dict[str, float] = {}
            if "betweenness" in self._selected_local_keys:
                try:
                    bet = nk_mod.centrality.Betweenness(G, normalized=True)
                    bet.run()
                    local_betweenness = {node_names[i]: float(bet.scores()[i]) for i in range(n)}
                except Exception:
                    local_betweenness = {name: 0.0 for name in node_names}

            local_eigenvector: dict[str, float] = {}
            if "eigenvector" in self._selected_local_keys:
                try:
                    eig = nk_mod.centrality.EigenvectorCentrality(G)
                    eig.run()
                    local_eigenvector = {node_names[i]: float(eig.scores()[i]) for i in range(n)}
                except Exception:
                    local_eigenvector = {name: 0.0 for name in node_names}

            local_closeness: dict[str, float] = {}
            if "closeness" in self._selected_local_keys:
                try:
                    close_alg = nk_mod.centrality.Closeness(GU, False, nk_mod.centrality.ClosenessVariant.Generalized)
                    close_alg.run()
                    local_closeness = {node_names[i]: float(close_alg.scores()[i]) for i in range(n)}
                except Exception:
                    local_closeness = {name: 0.0 for name in node_names}

            # Degree assortativity as Pearson correlation between endpoint degrees.
            assortativity = None
            if "assortativity" in self._selected_global_keys:
                xs: list[float] = []
                ys: list[float] = []
                for (a, b), _w in self._edge_weights.items():
                    da = float(degree_values[idx_map[a]])
                    db = float(degree_values[idx_map[b]])
                    xs.append(da)
                    ys.append(db)
                    if not self._directed:
                        xs.append(db)
                        ys.append(da)
                assortativity = self._pearson(xs, ys)

            degree_exponent_text = _degree_exponent_text([float(v) for v in degree_values])
            in_degree_exponent_text = _degree_exponent_text(list(local_in_degree.values())) if self._directed else "n/a"
            out_degree_exponent_text = _degree_exponent_text(list(local_out_degree.values())) if self._directed else "n/a"

            payload = {
                "nodes": node_names,
                "degree_values": degree_values,
                "global_map": {
                    "nodes": str(n),
                    "edges": str(m),
                    "largest_cc_ratio": f"{largest_ratio:.4f}",
                    "components": str(comp_count),
                    "density": f"{density:.4f}",
                    "global_clustering": f"{global_clust:.4f}",
                    "avg_path_length": f"{avg_path:.4f}" if avg_path is not None else "n/a",
                    "diameter": f"{diameter:.4f}" if diameter is not None else "n/a",
                    "avg_degree": f"{((sum(local_degree.values()) / float(n)) if n > 0 else 0.0):.4f}",
                    "avg_in_degree": f"{avg_in_degree:.4f}" if avg_in_degree is not None else "n/a",
                    "avg_out_degree": f"{avg_out_degree:.4f}" if avg_out_degree is not None else "n/a",
                    "degree_exponent": degree_exponent_text,
                    "in_degree_exponent": in_degree_exponent_text,
                    "out_degree_exponent": out_degree_exponent_text,
                    "assortativity": f"{assortativity:.4f}" if assortativity is not None else "n/a",
                },
                "pair_shortest_paths": pair_shortest_paths,
                "meta": {"directed": self._directed, "weighted": self._weighted, "backend": "networkit"},
                "local_values_map": {
                    "degree": local_degree,
                    "in_degree": local_in_degree,
                    "out_degree": local_out_degree,
                    "out_avg_path": local_out_avg_path,
                    "clustering": local_clustering,
                    "betweenness": local_betweenness,
                    "eigenvector": local_eigenvector,
                    "closeness": local_closeness,
                },
            }
            self.finished.emit(payload)
        except Exception as exc:
            self.failed.emit(str(exc))


class LingnetAnalyzeDialog(QDialog):
    def __init__(self, stats_payload: dict[str, object], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("QuanSyn Studio")
        if parent is not None:
            try:
                self.setWindowIcon(parent.windowIcon())
            except Exception:
                pass
        self.resize(980, 680)
        self._payload = stats_payload
        self._last_svg = ""
        self._last_html = ""
        self._last_image: QImage | None = None
        self._feature_key_map: dict[str, str] = {
            "Degree": "degree",
            "In-Degree": "in_degree",
            "Out-Degree": "out_degree",
            "Clustering Coefficient": "clustering",
            "Betweenness Centrality": "betweenness",
            "Eigenvector Centrality": "eigenvector",
            "Closeness Centrality": "closeness",
            "Out Average Path Length": "out_avg_path",
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        ctrl = QFrame()
        ctrl.setObjectName("vizParamWrap")
        ctrl_l = QGridLayout(ctrl)
        ctrl_l.setContentsMargins(10, 8, 10, 8)
        ctrl_l.setSpacing(8)
        ctrl_l.addWidget(QLabel("Mode"), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["1D", "2D"])
        ctrl_l.addWidget(self.mode_combo, 0, 1)

        ctrl_l.addWidget(QLabel("Chart"), 0, 2)
        self.chart_combo = QComboBox()
        self.chart_combo.addItems(["histogram", "bar", "line", "scatter", "area", "boxplot", "density"])
        ctrl_l.addWidget(self.chart_combo, 0, 3)

        self.dist_source_label = QLabel("Distribution source")
        ctrl_l.addWidget(self.dist_source_label, 1, 0)
        self.dist_source_combo = QComboBox()
        self.dist_source_combo.addItems(["Node feature"])
        ctrl_l.addWidget(self.dist_source_combo, 1, 1)

        self.dist_feature_label = QLabel("Feature")
        ctrl_l.addWidget(self.dist_feature_label, 1, 2)
        self.dist_feature_combo = QComboBox()
        ctrl_l.addWidget(self.dist_feature_combo, 1, 3)

        self.x_feature_label = QLabel("X feature")
        ctrl_l.addWidget(self.x_feature_label, 2, 0)
        self.x_feature_combo = QComboBox()
        ctrl_l.addWidget(self.x_feature_combo, 2, 1)

        self.y_feature_label = QLabel("Y feature")
        ctrl_l.addWidget(self.y_feature_label, 2, 2)
        self.y_feature_combo = QComboBox()
        ctrl_l.addWidget(self.y_feature_combo, 2, 3)

        self.log_scale_chk = QCheckBox("Log scale")
        ctrl_l.addWidget(self.log_scale_chk, 3, 0)
        self.fit_line_chk = QCheckBox("Powerlaw fit line")
        ctrl_l.addWidget(self.fit_line_chk, 3, 1)
        self.grid_chk = QCheckBox("Show grid")
        self.grid_chk.setChecked(True)
        ctrl_l.addWidget(self.grid_chk, 3, 2)
        self.draw_btn = QPushButton("Draw")
        self.draw_btn.setObjectName("accentButton")
        ctrl_l.addWidget(self.draw_btn, 3, 3, 1, 1, Qt.AlignmentFlag.AlignRight)
        root.addWidget(ctrl, 0)

        self.preview_web = None
        self.preview_scene = None
        self.preview = None
        self._preview_item: QGraphicsPixmapItem | None = None
        if QWebEngineView is not None:
            self.preview_web = QWebEngineView(self)
            _reject_web_fullscreen(self.preview_web)
            if QWebEngineSettings is not None:
                try:
                    s = self.preview_web.settings()
                    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                except Exception:
                    pass
            self.preview_web.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.preview_web.customContextMenuRequested.connect(self._open_preview_menu)
            root.addWidget(self.preview_web, 1)
        else:
            self.preview_scene = QGraphicsScene(self)
            self.preview = ZoomableGraphicsView(self)
            self.preview.setScene(self.preview_scene)
            self.preview.setMinimumHeight(520)
            self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.preview.customContextMenuRequested.connect(self._open_preview_menu)
            root.addWidget(self.preview, 1)

        self.draw_btn.clicked.connect(self.draw_current)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.dist_source_combo.currentTextChanged.connect(self._sync_controls)
        self.dist_feature_combo.currentTextChanged.connect(self._sync_controls)
        self._reload_feature_options()
        self._update_chart_options()
        self._sync_controls()
        self.draw_current()

    def _on_mode_changed(self, *_args) -> None:
        self._update_chart_options()
        self._sync_controls()

    def _update_chart_options(self) -> None:
        is_dist = self.mode_combo.currentText().strip().lower() == "1d"
        opts_1d = ["histogram", "bar", "line", "scatter", "area", "boxplot", "density"]
        opts_2d = ["scatter", "line"]
        desired = opts_1d if is_dist else opts_2d
        prev = self.chart_combo.currentText().strip().lower()
        self.chart_combo.blockSignals(True)
        self.chart_combo.clear()
        self.chart_combo.addItems(desired)
        idx = self.chart_combo.findText(prev)
        if idx >= 0:
            self.chart_combo.setCurrentIndex(idx)
        self.chart_combo.blockSignals(False)

    def _reload_feature_options(self) -> None:
        meta = dict(self._payload.get("meta", {}) or {})
        directed = bool(meta.get("directed", False))
        names: list[str] = ["Degree"]
        if directed:
            names.extend(["In-Degree", "Out-Degree"])
        names.extend(
            [
                "Clustering Coefficient",
                "Betweenness Centrality",
                "Eigenvector Centrality",
                "Closeness Centrality",
                "Out Average Path Length",
            ]
        )
        self.dist_feature_combo.clear()
        self.dist_feature_combo.addItems(["Degree distribution"] + names)
        self.x_feature_combo.clear()
        self.x_feature_combo.addItems(names)
        self.y_feature_combo.clear()
        self.y_feature_combo.addItems(names)
        if "Closeness Centrality" in names:
            self.y_feature_combo.setCurrentText("Closeness Centrality")

    def _sync_controls(self) -> None:
        is_dist = self.mode_combo.currentText().strip().lower() == "1d"
        self.dist_source_label.setVisible(is_dist)
        self.dist_source_combo.setVisible(is_dist)
        self.dist_feature_label.setVisible(is_dist)
        self.dist_feature_combo.setVisible(is_dist)
        self.x_feature_label.setVisible(not is_dist)
        self.x_feature_combo.setVisible(not is_dist)
        self.y_feature_label.setVisible(not is_dist)
        self.y_feature_combo.setVisible(not is_dist)
        feat = self.dist_feature_combo.currentText().strip().lower()
        can_fit = is_dist and feat.startswith("degree distribution")
        self.fit_line_chk.setVisible(is_dist)
        self.fit_line_chk.setEnabled(can_fit)
        self.log_scale_chk.setVisible(True)
        if (not is_dist) or (not can_fit):
            self.fit_line_chk.setChecked(False)

    def _set_preview_message(self, text: str) -> None:
        if self.preview_web is not None:
            html_msg = (
                "<html><body style='margin:0;padding:12px;font-family:Segoe UI,Arial,sans-serif;"
                "color:#1f2937;background:#ffffff;'>"
                f"{html.escape(str(text))}</body></html>"
            )
            self.preview_web.setHtml(html_msg, QUrl.fromLocalFile(str(_runtime_base_dir()) + os.sep))
        elif self.preview_scene is not None:
            self.preview_scene.clear()
            msg_item = self.preview_scene.addText(str(text))
            msg_item.setDefaultTextColor(QColor("#1f2937"))
            msg_item.setPos(12, 12)
        self._preview_item = None
        self._last_image = None
        self._last_html = ""

    def _open_preview_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        act = menu.addAction("Export")
        sender_obj = self.sender()
        if isinstance(sender_obj, QWidget):
            global_pos = sender_obj.mapToGlobal(pos)
        elif self.preview_web is not None:
            global_pos = self.preview_web.mapToGlobal(pos)
        elif self.preview is not None:
            global_pos = self.preview.mapToGlobal(pos)
        else:
            global_pos = self.mapToGlobal(pos)
        chosen = menu.exec(global_pos)
        if chosen == act:
            self._export_preview()

    def _export_preview(self) -> None:
        if not self._last_svg and self._last_image is None:
            _show_info_dialog(self, "Export", "No plot to export.")
            return
        out_path, _ = _themed_get_save_file_name(
            self,
            "Export plot",
            str(Path.home() / "lingnet_plot.png"),
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;TIFF (*.tif *.tiff);;SVG (*.svg);;PDF (*.pdf)",
        )
        if not out_path:
            return
        out_file = Path(out_path)
        ext = out_file.suffix.lower()
        try:
            if self._last_image is None and self._last_svg and QSvgRenderer is not None:
                renderer = QSvgRenderer(QByteArray(self._last_svg.encode("utf-8")))
                if renderer.isValid():
                    sz = renderer.defaultSize()
                    w = max(1600, int(sz.width()) if sz.width() > 0 else 0)
                    h = max(1000, int(sz.height()) if sz.height() > 0 else 0)
                    img = QImage(w, h, QImage.Format.Format_ARGB32)
                    img.fill(QColor("#ffffff"))
                    p = QPainter(img)
                    renderer.render(p)
                    p.end()
                    self._last_image = img
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                if self._last_image is None:
                    raise RuntimeError("No raster image available.")
                fmt = "JPEG" if ext in {".jpg", ".jpeg"} else ext.lstrip(".").upper()
                if fmt == "TIF":
                    fmt = "TIFF"
                self._last_image.save(str(out_file), fmt)
            elif ext == ".svg":
                out_file.write_text(self._last_svg, encoding="utf-8")
            elif ext == ".pdf":
                if QSvgRenderer is None or not self._last_svg:
                    raise RuntimeError("SVG renderer unavailable.")
                renderer = QSvgRenderer(QByteArray(self._last_svg.encode("utf-8")))
                writer = QPdfWriter(str(out_file))
                writer.setResolution(300)
                painter = QPainter(writer)
                renderer.render(painter)
                painter.end()
            else:
                out_file = out_file.with_suffix(".png")
                if self._last_image is None:
                    raise RuntimeError("No raster image available.")
                self._last_image.save(str(out_file), "PNG")
            _show_info_dialog(self, "Export", f"Saved: {out_file}")
        except Exception as exc:
            _show_warning_dialog(self, "Export failed", str(exc))

    def _render_svg(self, svg_text: str) -> None:
        if not svg_text or QSvgRenderer is None:
            self._set_preview_message("Preview unavailable.")
            return
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        if not renderer.isValid():
            self._set_preview_message("Invalid chart output.")
            return
        size = renderer.defaultSize()
        if self.preview is not None:
            vw = max(1, int(self.preview.viewport().width()))
            vh = max(1, int(self.preview.viewport().height()))
        else:
            vw, vh = 900, 560
        # Hi-res rasterization for sharper preview in the scalable view.
        w = max(1600, vw * 2, int(size.width()) if size.width() > 0 else 0)
        h = max(1000, vh * 2, int(size.height()) if size.height() > 0 else 0)
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        renderer.render(p)
        p.end()
        self._last_image = img
        if self.preview_scene is not None and self.preview is not None:
            self.preview_scene.clear()
            self._preview_item = self.preview_scene.addPixmap(QPixmap.fromImage(img))
            self.preview_scene.setSceneRect(0.0, 0.0, float(img.width()), float(img.height()))
            self.preview.resetTransform()
            self.preview.fitInView(self.preview_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def draw_current(self) -> None:
        if pd is None or lp_ggplot is None or lp_aes is None:
            self._set_preview_message("lets-plot/pandas is unavailable.")
            return
        local_map = dict(self._payload.get("local_values_map", {}) or {})
        degree_values = [int(x) for x in (self._payload.get("degree_values", []) or [])]
        use_log = bool(self.log_scale_chk.isChecked())
        mode = self.mode_combo.currentText().strip().lower()
        chart = self.chart_combo.currentText().strip().lower()
        try:
            fit_df = None
            if mode == "1d":
                feat = self.dist_feature_combo.currentText().strip()
                series: list[float] = []
                if feat.lower().startswith("degree distribution"):
                    series = [float(v) for v in degree_values if int(v) > 0]
                else:
                    mk = self._feature_key_map.get(feat, "degree")
                    vals = dict(local_map.get(mk, {}) or {})
                    series = [float(v) for _k, v in vals.items()]
                x_label = feat.lower()
                series = [float(v) for v in series if not math.isnan(float(v)) and not math.isinf(float(v))]
                if not series:
                    self._set_preview_message("No data for selected distribution.")
                    return
                df_raw = pd.DataFrame({"x": series})
                if chart in {"histogram", "density", "boxplot"}:
                    if use_log:
                        df = df_raw[df_raw["x"] > 0].copy()
                        df["x"] = df["x"].map(lambda v: math.log10(float(v)))
                        x_label = f"log10({x_label})"
                    else:
                        df = df_raw
                    if chart == "histogram":
                        p = lp_ggplot(df, lp_aes(x="x")) + lp_geom_histogram(bins=40)
                        y_label = "count"
                    elif chart == "density":
                        p = lp_ggplot(df, lp_aes(x="x")) + lp_geom_density()
                        y_label = "density"
                    else:
                        df = df.copy()
                        df["grp"] = "all"
                        p = lp_ggplot(df, lp_aes(x="grp", y="x")) + lp_geom_boxplot()
                        y_label = "value"
                    p = p + lp_labs(x=x_label, y=y_label)
                else:
                    c = Counter(int(round(v)) for v in series)
                    xs = sorted(c.keys())
                    ys = [int(c[x]) for x in xs]
                    df = pd.DataFrame({"x": xs, "y": ys})
                    y_label = "frequency"
                    if use_log:
                        df = df[(df["x"] > 0) & (df["y"] > 0)].copy()
                        df["x"] = df["x"].map(lambda v: math.log10(float(v)))
                        df["y"] = df["y"].map(lambda v: math.log10(float(v)))
                        x_label = f"log10({x_label})"
                        y_label = "log10(frequency)"
                    p = lp_ggplot(df, lp_aes(x="x", y="y"))
                    if chart == "bar":
                        p += lp_geom_bar(stat="identity")
                    elif chart == "line":
                        p += lp_geom_line()
                    elif chart == "area":
                        p += lp_geom_area()
                    else:
                        p += lp_geom_point(color="#d62828")
                    if self.fit_line_chk.isChecked() and powerlaw is not None and self.dist_feature_combo.currentText().strip().lower().startswith("degree distribution"):
                        try:
                            d_int = [int(v) for v in degree_values if int(v) > 0]
                            if len(d_int) < 3:
                                raise ValueError("not enough positive degree samples")
                            fit = powerlaw.Fit(d_int, discrete=True, verbose=False)
                            alpha = float(getattr(fit.power_law, "alpha", 0.0) or 0.0)
                            xmin = float(getattr(fit.power_law, "xmin", 1.0) or 1.0)
                            anchor_x = None
                            anchor_y = None
                            for x in xs:
                                if float(x) >= xmin:
                                    anchor_x = float(x)
                                    anchor_y = float(c[int(x)])
                                    break
                            if anchor_x and anchor_y and alpha > 0:
                                C = anchor_y * (anchor_x ** alpha)
                                fit_x = [float(x) for x in xs if float(x) >= xmin]
                                fit_y = [C * (x ** (-alpha)) for x in fit_x]
                                fit_df = pd.DataFrame({"x": fit_x, "y": fit_y})
                                if use_log:
                                    fit_df = fit_df[(fit_df["x"] > 0) & (fit_df["y"] > 0)].copy()
                                    fit_df["x"] = fit_df["x"].map(lambda v: math.log10(float(v)))
                                    fit_df["y"] = fit_df["y"].map(lambda v: math.log10(float(v)))
                                p = p + lp_geom_line(data=fit_df, mapping=lp_aes(x="x", y="y"), color="#b91c1c")
                        except Exception:
                            pass
                    p = p + lp_labs(x=x_label, y=y_label)
            else:
                x_name = self.x_feature_combo.currentText().strip()
                y_name = self.y_feature_combo.currentText().strip()
                x_key = self._feature_key_map.get(x_name, "degree")
                y_key = self._feature_key_map.get(y_name, "clustering")
                x_vals = dict(local_map.get(x_key, {}) or {})
                y_vals = dict(local_map.get(y_key, {}) or {})
                nodes = sorted(set(x_vals.keys()) & set(y_vals.keys()))
                if not nodes:
                    self._set_preview_message("No overlapping node feature data for 2D plotting.")
                    return
                df = pd.DataFrame({"x": [float(x_vals[n]) for n in nodes], "y": [float(y_vals[n]) for n in nodes]})
                x_label = x_name
                y_label = y_name
                if use_log:
                    df = df[(df["x"] > 0) & (df["y"] > 0)].copy()
                    df["x"] = df["x"].map(lambda v: math.log10(float(v)))
                    df["y"] = df["y"].map(lambda v: math.log10(float(v)))
                    x_label = f"log10({x_label})"
                    y_label = f"log10({y_label})"
                p = lp_ggplot(df, lp_aes(x="x", y="y"))
                if chart == "line":
                    p += lp_geom_line()
                p += lp_geom_point(color="#d62828")
                p += lp_labs(x=x_label, y=y_label)

            if (not bool(self.grid_chk.isChecked())) and lp_theme is not None and lp_element_blank is not None:
                p = p + lp_theme(panel_grid_major=lp_element_blank(), panel_grid_minor=lp_element_blank())
            if lp_scale_x_discrete is not None and chart == "boxplot":
                p = p + lp_scale_x_discrete(position="bottom")
            elif lp_scale_x_continuous is not None:
                p = p + lp_scale_x_continuous(position="bottom")
            if lp_ggsize is not None:
                p = p + lp_ggsize(900, 560)
            self._last_svg = p.to_svg()
            self._last_html = _lets_plot_html_with_local_js(p)
            if self.preview_web is not None and self._last_html:
                self.preview_web.setHtml(self._last_html, QUrl.fromLocalFile(str(_runtime_base_dir()) + os.sep))
            else:
                self._render_svg(self._last_svg)
        except Exception as exc:
            self._set_preview_message(f"Plot failed: {exc}")


class LingnetPage(QWidget):
    message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        _bootstrap_cache_layout()
        self._imported_treebanks: list[Path] = []
        self._converted_treebank_cache: dict[str, str] = {}
        self._parser_cache_dir = _quansyn_cache_path("parser", "current")
        self._parser_cache_file = self._parser_cache_dir / "parser_current.conllu"
        self._source_mode = "imported"
        self._edge_cache: dict[str, list[tuple[str, str]]] = {}
        self._current_relation = "dependency"
        self._current_directed = False
        self._current_weighted = False
        self._worker: LingnetWorker | None = None
        self._metric_worker: LingnetMetricWorker | None = None
        self._stats_cache: dict[str, dict[str, object]] = {}
        self._stats_cache_key_current = ""
        self._lingnet_pos_cache: dict[str, dict[str, tuple[float, float]]] = {}
        self._lingnet_current_key = ""
        self._lingnet_current_graph = None
        self._lingnet_drag_node: str | None = None
        self._lingnet_hover_annot = None
        self._lingnet_hover_text = ""
        self._lingnet_edge_pairs: list[tuple[str, str]] = []
        self._lingnet_last_non_empty_edges: list[tuple[str, str]] = []
        self._lingnet_last_non_empty_key = ""
        self._lingnet_layout_cache: dict[str, dict[str, dict[str, float]]] = {}
        self._lingnet_selected_node: str | None = None
        self._lingnet_selected_edge: tuple[str, str] | None = None
        self._lingnet_cid_press = None
        self._lingnet_cid_release = None
        self._lingnet_cid_motion = None
        self._example_key = "example"
        self._example_edges: list[tuple[str, str]] = []
        self._viz_node_color = "#d83a3a"
        self._viz_edge_width = 0.6
        self._viz_show_node_labels = True
        self._viz_show_weight_labels = True
        self._viz_layout_mode = "auto"
        self._viz_directed = False
        self._viz_weighted = False
        self._global_metrics: list[tuple[str, str]] = [
            ("nodes", "Nodes"),
            ("edges", "Edges"),
            ("largest_cc_ratio", "Largest Component Ratio"),
            ("components", "Connected Components"),
            ("density", "Density"),
            ("global_clustering", "Global Clustering Coefficient"),
            ("avg_path_length", "Average Path Length"),
            ("diameter", "Diameter"),
            ("avg_degree", "Average Degree"),
            ("avg_in_degree", "Average In-Degree"),
            ("avg_out_degree", "Average Out-Degree"),
            ("degree_exponent", "Degree Exponent"),
            ("in_degree_exponent", "In-Degree Exponent"),
            ("out_degree_exponent", "Out-Degree Exponent"),
            ("assortativity", "Assortativity"),
            ("centralization", "Centralization"),
        ]
        self._local_metrics: list[tuple[str, str]] = [
            ("degree", "Degree"),
            ("in_degree", "In-Degree"),
            ("out_degree", "Out-Degree"),
            ("out_avg_path", "Out Average Path Length"),
            ("clustering", "Clustering Coefficient"),
            ("betweenness", "Betweenness Centrality"),
            ("eigenvector", "Eigenvector Centrality"),
            ("closeness", "Closeness Centrality"),
        ]
        self._metric_checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._wire()
        self._load_default_example_edges()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left = QWidget()
        left.setObjectName("lingnetLeftPane")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(10, 8, 10, 8)
        left_l.setSpacing(8)

        left_title = QLabel("Edge Extraction")
        left_title.setObjectName("sectionTitle")
        left_l.addWidget(left_title)

        form = QFormLayout()
        self.lingnet_source_combo = QComboBox()
        self.lingnet_source_combo.addItem("imported", "imported")
        form.addRow("Source", self.lingnet_source_combo)
        self.lingnet_treebank_combo = QComboBox()
        self.lingnet_treebank_combo.addItem("all", "__all__")
        form.addRow("Treebank", self.lingnet_treebank_combo)
        self.lingnet_relation_combo = QComboBox()
        self.lingnet_relation_combo.addItems(["dependency", "adjacency"])
        form.addRow("Relation", self.lingnet_relation_combo)
        self.lingnet_directed_chk = QCheckBox("Directed")
        self.lingnet_directed_chk.setChecked(False)
        self.lingnet_weighted_chk = QCheckBox("Weighted")
        self.lingnet_weighted_chk.setChecked(False)
        option_row = QWidget()
        option_row_l = QHBoxLayout(option_row)
        option_row_l.setContentsMargins(0, 0, 0, 0)
        option_row_l.setSpacing(8)
        option_row_l.addWidget(self.lingnet_directed_chk)
        option_row_l.addWidget(self.lingnet_weighted_chk)
        option_row_l.addStretch(1)
        form.addRow("Options", option_row)
        left_l.addLayout(form)

        self.lingnet_run_btn = QPushButton("Run")
        self.lingnet_run_btn.setObjectName("accentButton")
        self.lingnet_save_btn = QPushButton("Save")
        self.lingnet_save_btn.setObjectName("accentButton")
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        self.lingnet_run_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lingnet_save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_row.addWidget(self.lingnet_run_btn, 1)
        btn_row.addWidget(self.lingnet_save_btn, 1)
        left_l.addLayout(btn_row)

        edge_title = QLabel("Edge List")
        edge_title.setObjectName("sectionTitle")
        left_l.addWidget(edge_title)
        self.lingnet_edges_tabs = QTabWidget()
        left_l.addWidget(self.lingnet_edges_tabs, 1)
        report_title = QLabel("Report")
        report_title.setObjectName("sectionTitle")
        left_l.addWidget(report_title)
        self.lingnet_report = QTextEdit()
        self.lingnet_report.setReadOnly(True)
        self.lingnet_report.setObjectName("reportBox")
        self.lingnet_report.setMinimumHeight(90)
        self.lingnet_report.setMaximumHeight(140)
        left_l.addWidget(self.lingnet_report, 0)

        middle = QWidget()
        middle_l = QVBoxLayout(middle)
        middle_l.setContentsMargins(0, 0, 0, 0)
        middle_l.setSpacing(8)

        middle_split = QSplitter(Qt.Orientation.Vertical)
        middle_split.setChildrenCollapsible(False)
        middle_l.addWidget(middle_split, 1)

        plot_wrap = QWidget()
        plot_l = QVBoxLayout(plot_wrap)
        plot_l.setContentsMargins(0, 0, 0, 0)
        plot_l.setSpacing(4)
        plot_title = QLabel("Network Visualization")
        plot_title.setObjectName("sectionTitle")
        plot_l.addWidget(plot_title)
        self._lingnet_cache_dir = _quansyn_cache_path("lingnet", "render")
        self._lingnet_html_path = self._lingnet_cache_dir / "lingnet_graph.html"
        self._lingnet_cytoscape_js_path = self._lingnet_cache_dir / "cytoscape.min.js"
        self._ensure_lingnet_js_runtime()
        if QWebEngineView is not None:
            self.lingnet_web = QWebEngineView()
            _reject_web_fullscreen(self.lingnet_web)
            self.lingnet_web.setMinimumHeight(320)
            self.lingnet_web.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.lingnet_web.customContextMenuRequested.connect(self._on_lingnet_context_menu)
            if QWebEnginePage is not None:
                try:
                    self._lingnet_web_page = LingnetWebPage(self.lingnet_web)
                    self._lingnet_web_page.jsConsole.connect(self._append_report)
                    self.lingnet_web.setPage(self._lingnet_web_page)
                except Exception:
                    self._lingnet_web_page = None
            else:
                self._lingnet_web_page = None
            if QWebEngineSettings is not None:
                try:
                    s = self.lingnet_web.settings()
                    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                    if hasattr(QWebEngineSettings.WebAttribute, "ShowScrollBars"):
                        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
                except Exception:
                    pass
            plot_l.addWidget(self.lingnet_web, 1)
            self.lingnet_figure = None
            self.lingnet_canvas = None
        else:
            self.lingnet_web = None
            self.lingnet_figure = None
            self.lingnet_canvas = None
            self.lingnet_plot_fallback = QLabel("Interactive HTML graph will open in your default browser.")
            self.lingnet_plot_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            plot_l.addWidget(self.lingnet_plot_fallback, 1)
            self.lingnet_open_html_btn = QPushButton("Open Interactive Graph")
            self.lingnet_open_html_btn.setObjectName("accentButton")
            self.lingnet_open_html_btn.clicked.connect(self._open_lingnet_html_in_browser)
            plot_l.addWidget(self.lingnet_open_html_btn, 0, Qt.AlignmentFlag.AlignRight)

        stats_wrap = QWidget()
        stats_l = QVBoxLayout(stats_wrap)
        stats_l.setContentsMargins(0, 0, 0, 0)
        stats_l.setSpacing(4)
        stats_title = QLabel("Statistics")
        stats_title.setObjectName("sectionTitle")
        stats_l.addWidget(stats_title)
        self.lingnet_result_tabs = QTabWidget()
        stats_l.addWidget(self.lingnet_result_tabs, 1)
        global_tab = QWidget()
        global_tab_l = QVBoxLayout(global_tab)
        global_tab_l.setContentsMargins(0, 0, 0, 0)
        global_tab_l.setSpacing(4)
        self.lingnet_global_table = QTableWidget()
        self.lingnet_global_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lingnet_global_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.lingnet_global_table.verticalHeader().setVisible(False)
        self.lingnet_global_table.setRowCount(1)
        global_tab_l.addWidget(self.lingnet_global_table, 1)
        node_tab = QWidget()
        node_tab_l = QVBoxLayout(node_tab)
        node_tab_l.setContentsMargins(0, 0, 0, 0)
        node_tab_l.setSpacing(4)
        self.lingnet_node_table = QTableWidget()
        self.lingnet_node_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lingnet_node_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lingnet_node_table.verticalHeader().setVisible(False)
        self.lingnet_node_table.setSortingEnabled(True)
        node_tab_l.addWidget(self.lingnet_node_table, 1)
        self.lingnet_result_tabs.addTab(global_tab, "Global")
        self.lingnet_result_tabs.addTab(node_tab, "Node")

        middle_split.addWidget(plot_wrap)
        middle_split.addWidget(stats_wrap)
        middle_split.setStretchFactor(0, 2)
        middle_split.setStretchFactor(1, 1)
        middle_split.setSizes([600, 300])

        metrics = QWidget()
        metrics_l = QVBoxLayout(metrics)
        metrics_l.setContentsMargins(0, 0, 0, 0)
        metrics_l.setSpacing(8)
        metrics_title = QLabel("Metric Selection")
        metrics_title.setObjectName("sectionTitle")
        metrics_l.addWidget(metrics_title)

        metric_scroll = QScrollArea()
        metric_scroll.setWidgetResizable(True)
        metric_scroll.setFrameShape(QFrame.Shape.NoFrame)
        metric_content = QWidget()
        metric_content_l = QVBoxLayout(metric_content)
        metric_content_l.setContentsMargins(2, 2, 2, 2)
        metric_content_l.setSpacing(4)

        gl_title = QLabel("Global Metrics")
        gl_title.setObjectName("sectionTitle")
        metric_content_l.addWidget(gl_title)
        for key, label in self._global_metrics:
            chk = QCheckBox(label)
            chk.setChecked(key in {"nodes", "edges"})
            self._metric_checks[key] = chk
            metric_content_l.addWidget(chk)

        lc_title = QLabel("Local Metrics")
        lc_title.setObjectName("sectionTitle")
        metric_content_l.addWidget(lc_title)
        for key, label in self._local_metrics:
            chk = QCheckBox(label)
            chk.setChecked(False)
            self._metric_checks[key] = chk
            metric_content_l.addWidget(chk)
        metric_content_l.addStretch(1)

        metric_scroll.setWidget(metric_content)
        metrics_l.addWidget(metric_scroll, 1)
        metric_btn_row = QWidget()
        metric_btn_l = QHBoxLayout(metric_btn_row)
        metric_btn_l.setContentsMargins(0, 0, 0, 0)
        metric_btn_l.setSpacing(6)
        self.lingnet_metric_compute_btn = QPushButton("Compute")
        self.lingnet_metric_compute_btn.setObjectName("accentButton")
        self.lingnet_metric_compute_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        metric_btn_l.addWidget(self.lingnet_metric_compute_btn, 1)
        self.lingnet_analyze_btn = QPushButton("Plot")
        self.lingnet_analyze_btn.setObjectName("accentButton")
        self.lingnet_analyze_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        metric_btn_l.addWidget(self.lingnet_analyze_btn, 1)
        self.lingnet_metric_save_btn = QPushButton("Save")
        self.lingnet_metric_save_btn.setObjectName("accentButton")
        self.lingnet_metric_save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        metric_btn_l.addWidget(self.lingnet_metric_save_btn, 1)
        metrics_l.addWidget(metric_btn_row, 0)
        viz_sep = QFrame()
        viz_sep.setFrameShape(QFrame.Shape.HLine)
        viz_sep.setFrameShadow(QFrame.Shadow.Plain)
        metrics_l.addWidget(viz_sep, 0)
        viz_title = QLabel("Visualization Setting")
        viz_title.setObjectName("sectionTitle")
        metrics_l.addWidget(viz_title, 0)
        viz_box = QFrame()
        viz_box.setObjectName("vizParamWrap")
        viz_l = QFormLayout(viz_box)
        viz_l.setContentsMargins(10, 10, 10, 10)
        viz_l.setSpacing(8)
        self.lingnet_node_color_combo = QComboBox()
        self.lingnet_node_color_combo.setIconSize(QSize(26, 14))
        self.lingnet_node_color_combo.setMinimumWidth(68)
        set1_colors = [
            "#e41a1c",
            "#377eb8",
            "#4daf4a",
            "#984ea3",
            "#ff7f00",
            "#ffff33",
            "#a65628",
            "#f781bf",
            "#999999",
        ]
        for hex_color in set1_colors:
            swatch = QPixmap(26, 14)
            swatch.fill(QColor(hex_color))
            self.lingnet_node_color_combo.addItem(QIcon(swatch), "", hex_color)
        idx = self.lingnet_node_color_combo.findData(self._viz_node_color)
        if idx >= 0:
            self.lingnet_node_color_combo.setCurrentIndex(idx)
        self.lingnet_edge_width_spin = QDoubleSpinBox()
        self.lingnet_edge_width_spin.setRange(0.1, 5.0)
        self.lingnet_edge_width_spin.setSingleStep(0.1)
        self.lingnet_edge_width_spin.setValue(self._viz_edge_width)
        self.lingnet_layout_combo = QComboBox()
        self.lingnet_layout_combo.addItems(["auto", "spring-out", "circle", "concentric", "grid"])
        self.lingnet_layout_combo.setCurrentText("auto")
        self.lingnet_viz_directed_chk = QCheckBox("Directed (viz)")
        self.lingnet_viz_directed_chk.setChecked(False)
        self.lingnet_viz_weighted_chk = QCheckBox("Weighted (viz)")
        self.lingnet_viz_weighted_chk.setChecked(False)
        self.lingnet_show_node_label_chk = QCheckBox("Show node labels")
        self.lingnet_show_node_label_chk.setChecked(True)
        self.lingnet_show_weight_label_chk = QCheckBox("Show weight labels")
        self.lingnet_show_weight_label_chk.setChecked(True)
        self.lingnet_viz_show_btn = QPushButton("Show")
        self.lingnet_viz_show_btn.setObjectName("accentButton")
        self.lingnet_viz_export_btn = QPushButton("Export")
        self.lingnet_viz_export_btn.setObjectName("accentButton")
        viz_l.addRow("Node color", self.lingnet_node_color_combo)
        viz_l.addRow("Edge width", self.lingnet_edge_width_spin)
        viz_l.addRow("Layout", self.lingnet_layout_combo)
        viz_l.addRow(self.lingnet_viz_directed_chk)
        viz_l.addRow(self.lingnet_viz_weighted_chk)
        viz_l.addRow(self.lingnet_show_node_label_chk)
        viz_l.addRow(self.lingnet_show_weight_label_chk)
        show_row = QWidget()
        show_row_l = QHBoxLayout(show_row)
        show_row_l.setContentsMargins(0, 0, 0, 0)
        show_row_l.setSpacing(8)
        self.lingnet_viz_show_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lingnet_viz_export_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        show_row_l.addWidget(self.lingnet_viz_show_btn, 1)
        show_row_l.addWidget(self.lingnet_viz_export_btn, 1)
        viz_l.addRow(show_row)
        metrics_l.addWidget(viz_box, 0)

        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(metrics)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([360, 720, 360])
        self._main_splitter = splitter
        self._middle_splitter = middle_split

    def _wire(self) -> None:
        self.lingnet_run_btn.clicked.connect(self.run_lingnet)
        self.lingnet_save_btn.clicked.connect(self.save_lingnet_edges_dialog)
        self.lingnet_source_combo.currentTextChanged.connect(self._on_source_changed)
        self.lingnet_edges_tabs.currentChanged.connect(self._on_edge_tab_changed)
        self.lingnet_metric_compute_btn.clicked.connect(self._on_metric_selection_changed)
        self.lingnet_metric_save_btn.clicked.connect(self.save_lingnet_metrics_dialog)
        self.lingnet_viz_show_btn.clicked.connect(self._on_lingnet_viz_settings_changed)
        self.lingnet_viz_export_btn.clicked.connect(self._export_lingnet_network_image)
        self.lingnet_viz_directed_chk.toggled.connect(self._sync_lingnet_metric_checks_by_direction)
        self.lingnet_analyze_btn.clicked.connect(self._open_lingnet_analyze_dialog)
        self._sync_lingnet_metric_checks_by_direction()

    def apply_ui_scale(self, scale: float) -> None:
        try:
            s = max(0.55, min(1.0, float(scale)))
        except Exception:
            s = 1.0
        try:
            if hasattr(self, "_main_splitter") and self._main_splitter is not None:
                self._main_splitter.setSizes([max(220, int(360 * s)), max(420, int(720 * s)), max(220, int(360 * s))])
        except Exception:
            pass
        try:
            if hasattr(self, "_middle_splitter") and self._middle_splitter is not None:
                self._middle_splitter.setSizes([max(260, int(600 * s)), max(160, int(300 * s))])
        except Exception:
            pass
        try:
            if hasattr(self, "lingnet_web") and self.lingnet_web is not None:
                self.lingnet_web.setMinimumHeight(max(220, int(320 * s)))
        except Exception:
            pass
        try:
            if hasattr(self, "lingnet_node_color_combo") and self.lingnet_node_color_combo is not None:
                self.lingnet_node_color_combo.setMinimumWidth(max(56, int(68 * s)))
        except Exception:
            pass

    def _sync_lingnet_metric_checks_by_direction(self, *_args) -> None:
        directed = bool(self.lingnet_viz_directed_chk.isChecked()) if hasattr(self, "lingnet_viz_directed_chk") else bool(getattr(self, "_viz_directed", False))
        for key in ("avg_in_degree", "avg_out_degree", "in_degree_exponent", "out_degree_exponent", "in_degree", "out_degree"):
            chk = self._metric_checks.get(key)
            if chk is None:
                continue
            chk.setVisible(directed)
            chk.setEnabled(directed)
            if not directed:
                chk.setChecked(False)

    def _on_lingnet_viz_settings_changed(self, *_args) -> None:
        color = str(self.lingnet_node_color_combo.currentData() or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            self._viz_node_color = color
        self._viz_edge_width = float(self.lingnet_edge_width_spin.value())
        self._viz_directed = bool(self.lingnet_viz_directed_chk.isChecked())
        self._viz_weighted = bool(self.lingnet_viz_weighted_chk.isChecked())
        self._viz_show_node_labels = bool(self.lingnet_show_node_label_chk.isChecked())
        self._viz_show_weight_labels = bool(self.lingnet_show_weight_label_chk.isChecked())
        self._viz_layout_mode = self.lingnet_layout_combo.currentText().strip().lower() or "auto"
        key, edges = self._resolve_edges_for_render()
        if edges:
            self._append_report(f"Show render edges: {len(edges)}")
            self._draw_network(edges, key)
            return
        # If user already imported treebanks but edge list has not been generated yet,
        # make Show actionable by triggering extraction once.
        if self._imported_treebanks and (self._worker is None or not self._worker.isRunning()):
            self._append_report("No edge list ready. Running edge extraction...")
            self.run_lingnet()
            return
        self._show_lingnet_placeholder("Edge list is not ready. Click Run in Edge Extraction.")

    def _bind_lingnet_drag_events(self) -> None:
        if self.lingnet_canvas is None:
            return
        if self._lingnet_cid_press is None:
            self._lingnet_cid_press = self.lingnet_canvas.mpl_connect("button_press_event", self._on_lingnet_press)
        if self._lingnet_cid_release is None:
            self._lingnet_cid_release = self.lingnet_canvas.mpl_connect("button_release_event", self._on_lingnet_release)
        if self._lingnet_cid_motion is None:
            self._lingnet_cid_motion = self.lingnet_canvas.mpl_connect("motion_notify_event", self._on_lingnet_motion)

    def set_converted_treebank_cache(self, cache: dict[str, str]) -> None:
        self._converted_treebank_cache = cache
        self._refresh_source_options()

    def _parsed_cache_files(self) -> list[Path]:
        by_src_dir = self._parser_cache_dir / "by_source"
        files: list[Path] = []
        if by_src_dir.exists():
            files.extend(sorted([p for p in by_src_dir.glob("*.conllu") if p.is_file()], key=lambda p: p.name.lower()))
        return files

    def _converted_source_entries(self) -> list[tuple[str, Path]]:
        raw: list[tuple[str, Path]] = []
        for src, cached in self._converted_treebank_cache.items():
            cp = Path(str(cached))
            if not cp.exists():
                continue
            label = Path(str(src)).stem or cp.stem
            raw.append((label, cp))
        raw.sort(key=lambda x: (x[0].lower(), x[1].name.lower()))
        used: dict[str, int] = {}
        out: list[tuple[str, Path]] = []
        for label, path in raw:
            idx = used.get(label, 0)
            used[label] = idx + 1
            final_label = label if idx == 0 else f"{label}_{idx+1}"
            out.append((final_label, path))
        return out

    def _source_entries(self, source: str) -> list[tuple[str, Path]]:
        src = str(source or "").strip().lower()
        if src == "parsed":
            return [(p.stem, p) for p in self._parsed_cache_files()]
        if src == "converted":
            return self._converted_source_entries()
        return [(p.stem, p) for p in self._imported_treebanks]

    def _treebanks_for_source(self, source: str) -> list[Path]:
        return [p for _, p in self._source_entries(source)]

    def _refresh_treebank_options_by_source(self) -> None:
        source = str(self.lingnet_source_combo.currentData() or self._source_mode or "imported")
        entries = self._source_entries(source)
        prev = self.lingnet_treebank_combo.currentData()
        self.lingnet_treebank_combo.blockSignals(True)
        self.lingnet_treebank_combo.clear()
        self.lingnet_treebank_combo.addItem("all", "__all__")
        for label, tb in entries:
            self.lingnet_treebank_combo.addItem(label, str(tb))
        idx = self.lingnet_treebank_combo.findData(prev)
        self.lingnet_treebank_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lingnet_treebank_combo.blockSignals(False)

    def _available_sources(self) -> list[str]:
        options: list[str] = []
        if self._imported_treebanks:
            options.append("imported")
        has_converted = any(
            Path(p).exists() for p in self._converted_treebank_cache.values() if str(p or "").strip()
        )
        if has_converted:
            options.append("converted")
        if self._parsed_cache_files():
            options.append("parsed")
        if not options:
            options.append("imported")
        return options

    def _refresh_source_options(self) -> None:
        current = str(self.lingnet_source_combo.currentData() or self._source_mode or "imported")
        options = self._available_sources()
        self.lingnet_source_combo.blockSignals(True)
        self.lingnet_source_combo.clear()
        for src in options:
            self.lingnet_source_combo.addItem(src, src)
        idx = self.lingnet_source_combo.findData(current)
        if idx < 0:
            idx = 0
        self.lingnet_source_combo.setCurrentIndex(max(0, idx))
        self.lingnet_source_combo.blockSignals(False)
        self._source_mode = str(self.lingnet_source_combo.currentData() or "imported")
        self._refresh_treebank_options_by_source()

    def _on_source_changed(self, _value: str) -> None:
        self._source_mode = str(self.lingnet_source_combo.currentData() or "imported")
        self._refresh_treebank_options_by_source()

    def refresh_data_sources(self) -> None:
        self._refresh_source_options()

    def set_imported_treebanks(self, paths: list[str]) -> None:
        self._imported_treebanks = [Path(p) for p in sorted(set(paths))]
        self._refresh_source_options()
        if not self._imported_treebanks:
            self._load_default_example_edges()
        else:
            # Keep example tab available for quick fallback preview.
            if self._example_edges:
                self._edge_cache = {self._example_key: list(self._example_edges)}
                self._rebuild_edge_tabs()

    def _show_lingnet_placeholder(self, text: str, force: bool = False) -> None:
        if (not force) and self._lingnet_last_non_empty_edges:
            return
        msg = str(text or "").strip() or "No edge data"
        html_doc = (
            "<html><body style=\"margin:0;background:#1f1f1f;color:#d4d4d4;font-family:Segoe UI;\">"
            f"<div style=\"padding:14px;\">{html.escape(msg)}</div></body></html>"
        )
        try:
            self._lingnet_html_path.write_text(html_doc, encoding="utf-8")
        except Exception:
            pass
        self._load_lingnet_html_into_view(html_doc)

    def _ensure_lingnet_js_runtime(self) -> str:
        runtime = getattr(self, "_lingnet_cytoscape_js_path", None)
        if isinstance(runtime, Path):
            try:
                if not runtime.exists() and BUNDLED_CYTOSCAPE_JS.exists():
                    runtime.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(BUNDLED_CYTOSCAPE_JS, runtime)
                if runtime.exists():
                    # Keep src relative and provide cache dir as baseUrl in setHtml.
                    return runtime.name
            except Exception:
                pass
        try:
            if BUNDLED_CYTOSCAPE_JS.exists():
                if isinstance(runtime, Path):
                    runtime.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(BUNDLED_CYTOSCAPE_JS, runtime)
                    if runtime.exists():
                        return runtime.name
        except Exception:
            pass
        return ""

    @staticmethod
    def _qt_safe_local_path(path_obj: Path) -> str:
        p = str(path_obj)
        # Windows extended-length paths (\\?\) are not accepted by QWebEngine file URLs.
        if p.startswith("\\\\?\\UNC\\"):
            return "\\\\" + p[8:]
        if p.startswith("\\\\?\\"):
            return p[4:]
        return p

    def _load_lingnet_html_into_view(self, html_doc: str) -> None:
        if getattr(self, "lingnet_web", None) is None:
            return
        cache_dir = getattr(self, "_lingnet_cache_dir", _runtime_base_dir())
        path = getattr(self, "_lingnet_html_path", None)
        wrote_ok = False
        render_path = None
        if isinstance(cache_dir, Path):
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                render_path = cache_dir / f"lingnet_graph_{int(time.time() * 1000)}.html"
            except Exception:
                render_path = None
        if render_path is None and isinstance(path, Path):
            render_path = path
        if isinstance(render_path, Path):
            try:
                render_path.parent.mkdir(parents=True, exist_ok=True)
                render_path.write_text(html_doc, encoding="utf-8")
                wrote_ok = True
                self._lingnet_html_path = render_path
            except Exception:
                wrote_ok = False
        try:
            # IMPORTANT: use file loading instead of setHtml for large graphs.
            # QWebEngine setHtml may fail for big documents due data-url size limits.
            if wrote_ok and isinstance(render_path, Path) and render_path.exists():
                local_file = self._qt_safe_local_path(render_path)
                u = QUrl.fromLocalFile(local_file)
                self.lingnet_web.setUrl(u)
                return
        except Exception:
            pass
        try:
            base_dir = self._qt_safe_local_path(Path(cache_dir))
            base = QUrl.fromLocalFile(base_dir.rstrip("\\/") + "/")
            self.lingnet_web.setHtml(html_doc, base)
        except Exception:
            pass

    def _selected_treebanks(self) -> list[Path]:
        source = str(self.lingnet_source_combo.currentData() or self._source_mode or "imported")
        files = self._treebanks_for_source(source)
        if not files:
            return []
        selected_data = self.lingnet_treebank_combo.currentData()
        if selected_data in (None, "__all__"):
            selected = files
        else:
            target = str(selected_data)
            selected = []
            for tb in files:
                if str(tb) == target:
                    selected = [tb]
                    break
            if not selected:
                selected = files
        return selected

    def _current_tab_edges(self) -> tuple[str, list[tuple[str, str]]]:
        index = self.lingnet_edges_tabs.currentIndex()
        if index < 0:
            return "", []
        table = self._edge_table_from_tab_widget(self.lingnet_edges_tabs.widget(index))
        if table is None:
            return "", []
        key = str(table.property("treebank_path") or "")
        edges = self._edge_rows_from_table_widget(table)
        if not edges:
            edges = self._resolve_edges_for_table(table, key)
        return key, edges

    def _edge_table_from_tab_widget(self, tab_widget):
        if tab_widget is None:
            return None
        if isinstance(tab_widget, QTableWidget):
            return tab_widget
        if isinstance(tab_widget, QTableView):
            return tab_widget
        try:
            nested = tab_widget.findChild(QTableWidget)
            if nested is not None:
                return nested
        except Exception:
            pass
        try:
            nested_view = tab_widget.findChild(QTableView)
            if nested_view is not None:
                return nested_view
        except Exception:
            pass
        return None

    def _edge_rows_from_table_widget(self, table_widget) -> list[tuple[str, str]]:
        if table_widget is None:
            return []
        # Generic model-based extractor first: works for QTableWidget/QTableView.
        try:
            model = table_widget.model() if hasattr(table_widget, "model") else None
        except Exception:
            model = None
        if model is not None:
            row_count = 0
            col_count = 0
            try:
                row_count = int(model.rowCount())
            except Exception:
                row_count = 0
            try:
                col_count = int(model.columnCount())
            except Exception:
                col_count = 0
            if row_count > 0 and col_count >= 2:
                src_col = 0
                dst_col = 1
                try:
                    labels: list[str] = []
                    for c in range(col_count):
                        labels.append(str(model.headerData(c, Qt.Orientation.Horizontal) or "").strip().lower())
                    def _find_col(names: tuple[str, ...], default_idx: int) -> int:
                        for i, name in enumerate(labels):
                            if any(tok in name for tok in names):
                                return i
                        return default_idx
                    src_col = _find_col(("source", "head", "from"), 0)
                    dst_col = _find_col(("target", "dependent", "dep", "to"), 1 if col_count > 1 else 0)
                    if src_col == dst_col and col_count > 1:
                        dst_col = 1 if src_col != 1 else 0
                except Exception:
                    src_col, dst_col = 0, 1
                out: list[tuple[str, str]] = []
                for r in range(row_count):
                    try:
                        a = str(model.index(r, src_col).data() or "").strip()
                    except Exception:
                        a = ""
                    try:
                        b = str(model.index(r, dst_col).data() or "").strip()
                    except Exception:
                        b = ""
                    if a and b:
                        out.append((a, b))
                if out:
                    return out
        edges: list[tuple[str, str]] = []
        try:
            row_count = int(table_widget.rowCount())
        except Exception:
            row_count = 0
        if row_count > 0:
            for r in range(row_count):
                src = ""
                dst = ""
                try:
                    src_item = table_widget.item(r, 0)
                    if src_item is not None:
                        src = str(src_item.text() or "").strip()
                except Exception:
                    src = ""
                try:
                    dst_item = table_widget.item(r, 1)
                    if dst_item is not None:
                        dst = str(dst_item.text() or "").strip()
                except Exception:
                    dst = ""
                if (not src or not dst) and table_widget.model() is not None:
                    try:
                        src = src or str(table_widget.model().index(r, 0).data() or "").strip()
                        dst = dst or str(table_widget.model().index(r, 1).data() or "").strip()
                    except Exception:
                        pass
                if src and dst:
                    edges.append((src, dst))
        if edges:
            return edges
        prop_rows = getattr(table_widget, "property", lambda _x: None)("edge_rows")
        if isinstance(prop_rows, list) and prop_rows:
            parsed: list[tuple[str, str]] = []
            for it in prop_rows:
                if not isinstance(it, (list, tuple)) or len(it) < 2:
                    continue
                a = str(it[0]).strip()
                b = str(it[1]).strip()
                if a and b:
                    parsed.append((a, b))
            if parsed:
                return parsed
        return []

    def _first_non_empty_edge_tab(self) -> tuple[int, str, list[tuple[str, str]]]:
        for i in range(self.lingnet_edges_tabs.count()):
            tab = self._edge_table_from_tab_widget(self.lingnet_edges_tabs.widget(i))
            if tab is None:
                continue
            key = str(tab.property("treebank_path") or "")
            edges = self._edge_rows_from_table_widget(tab)
            if not edges:
                edges = self._resolve_edges_for_table(tab, key)
            if edges:
                return i, key, edges
        return -1, "", []

    def _first_non_empty_cached_edges(self) -> tuple[str, list[tuple[str, str]]]:
        for key, rows in self._edge_cache.items():
            edges: list[tuple[str, str]] = []
            for it in rows or []:
                if not isinstance(it, (list, tuple)) or len(it) < 2:
                    continue
                a = str(it[0]).strip()
                b = str(it[1]).strip()
                if a and b:
                    edges.append((a, b))
            if edges:
                return str(key), edges
        return "", []

    def _resolve_edges_for_render(self) -> tuple[str, list[tuple[str, str]]]:
        key, edges = self._current_tab_edges()
        if edges:
            return key, edges
        i, key_i, edges_i = self._first_non_empty_edge_tab()
        if i >= 0 and edges_i:
            return key_i, edges_i
        key_c, edges_c = self._first_non_empty_cached_edges()
        if edges_c:
            return key_c, edges_c
        if self._lingnet_last_non_empty_edges:
            return self._lingnet_last_non_empty_key, list(self._lingnet_last_non_empty_edges)
        return "", []

    def _edge_signature(self, edge_pairs: list[tuple[str, str]]) -> str:
        h = hashlib.blake2b(digest_size=10)
        for a, b in edge_pairs:
            h.update(str(a).encode("utf-8", errors="ignore"))
            h.update(b"\x1f")
            h.update(str(b).encode("utf-8", errors="ignore"))
            h.update(b"\x1e")
        return h.hexdigest()

    def _compute_preset_positions(
        self,
        node_names: list[str],
        edge_pairs: list[tuple[str, str]],
        directed: bool,
    ) -> dict[str, dict[str, float]]:
        if not node_names:
            return {}
        # Speed-first deterministic radial/spiral layout (no heavy backend layout computation).
        count = len(node_names)
        radius_base = max(120.0, math.sqrt(count) * 26.0)
        out: dict[str, dict[str, float]] = {}
        golden = 2.399963229728653  # golden angle
        for i, n in enumerate(node_names):
            # Deterministic tiny jitter by node name hash to avoid strict rings/grid look.
            hv = int(hashlib.blake2b(str(n).encode("utf-8", errors="ignore"), digest_size=2).hexdigest(), 16)
            jitter = ((hv % 1000) / 1000.0 - 0.5) * 6.0
            r = math.sqrt(i + 1) * 12.0 + radius_base * 0.08 + jitter
            ang = i * golden + (hv % 360) * (math.pi / 1800.0)
            out[n] = {"x": float(r * math.cos(ang)), "y": float(r * math.sin(ang))}
        return out

    def _build_static_network_svg(
        self,
        node_names: list[str],
        edge_pairs: list[tuple[str, str]],
        positions: dict[str, dict[str, float]],
        directed: bool,
        node_color: str,
    ) -> str:
        if not node_names:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 800 500">'
                '<text x="20" y="40" fill="#222" font-size="16">No edge data</text></svg>'
            )
        w = 1200.0
        h = 760.0
        pad = 40.0
        xs = []
        ys = []
        for n in node_names:
            p = positions.get(n, {"x": 0.0, "y": 0.0})
            xs.append(float(p.get("x", 0.0)))
            ys.append(float(p.get("y", 0.0)))
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1e-9, max_x - min_x)
        span_y = max(1e-9, max_y - min_y)

        def map_xy(x: float, y: float) -> tuple[float, float]:
            nx = pad + ((x - min_x) / span_x) * (w - 2 * pad)
            ny = pad + ((y - min_y) / span_y) * (h - 2 * pad)
            return nx, ny

        node_pt: dict[str, tuple[float, float]] = {}
        for n in node_names:
            p = positions.get(n, {"x": 0.0, "y": 0.0})
            node_pt[n] = map_xy(float(p.get("x", 0.0)), float(p.get("y", 0.0)))

        lines: list[str] = []
        lines.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 {int(w)} {int(h)}">'
        )
        lines.append('<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>')
        if directed:
            lines.append(
                '<defs><marker id="arr" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">'
                '<path d="M0,0 L10,4 L0,8 Z" fill="#000"/></marker></defs>'
            )
        for a, b in edge_pairs:
            x1, y1 = node_pt.get(a, (pad, pad))
            x2, y2 = node_pt.get(b, (pad, pad))
            mk = ' marker-end="url(#arr)"' if directed else ""
            lines.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#000" stroke-width="1"{mk}/>'
            )
        r = 6.0
        for n in node_names:
            x, y = node_pt.get(n, (pad, pad))
            label = html.escape(str(n))
            lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{node_color}" stroke="#000" stroke-width="1"/>')
            lines.append(f'<text x="{x + 8:.2f}" y="{y - 8:.2f}" font-size="12" fill="#111">{label}</text>')
        lines.append("</svg>")
        return "".join(lines)

    def _refresh_from_current_edge_table(self) -> None:
        key, edges = self._resolve_edges_for_render()
        if not edges:
            # Keep current rendering when there is no new edge data.
            return
        self._draw_network(edges, key)

    def _on_edge_table_rows_changed(self, *_args) -> None:
        sender = self.sender()
        current = self.lingnet_edges_tabs.currentWidget()
        if sender is None or current is None:
            return
        # model() signal sender may be model object, itemChanged sender is table
        is_current = False
        if isinstance(sender, QTableWidget):
            is_current = sender is current
        else:
            try:
                is_current = hasattr(current, "model") and sender is current.model()
            except Exception:
                is_current = False
        if is_current:
            self._refresh_from_current_edge_table()

    def _attach_edge_table_watchers(self, table: QTableWidget) -> None:
        try:
            table.itemChanged.connect(self._on_edge_table_rows_changed)
        except Exception:
            pass
        try:
            model = table.model()
            if model is not None:
                model.rowsInserted.connect(self._on_edge_table_rows_changed)
                model.rowsRemoved.connect(self._on_edge_table_rows_changed)
                model.modelReset.connect(self._on_edge_table_rows_changed)
                model.dataChanged.connect(self._on_edge_table_rows_changed)
        except Exception:
            pass

    def _edges_from_edge_table(self, table_widget) -> list[tuple[str, str]]:
        if not isinstance(table_widget, QTableWidget):
            return []
        edges: list[tuple[str, str]] = []
        for r in range(table_widget.rowCount()):
            src_item = table_widget.item(r, 0)
            dst_item = table_widget.item(r, 1)
            src = (src_item.text().strip() if src_item is not None else "")
            dst = (dst_item.text().strip() if dst_item is not None else "")
            if not src or not dst:
                continue
            edges.append((src, dst))
        if edges:
            return edges
        # Fallback: read directly from model data in case QTableWidgetItem objects are not materialized.
        try:
            model = table_widget.model()
            if model is None:
                return []
            for r in range(model.rowCount()):
                src = str(model.index(r, 0).data() or "").strip()
                dst = str(model.index(r, 1).data() or "").strip()
                if src and dst:
                    edges.append((src, dst))
        except Exception:
            pass
        return edges

    def _resolve_edges_for_key(self, key: str) -> list[tuple[str, str]]:
        if key in self._edge_cache:
            return list(self._edge_cache.get(key, []))
        norm_target = self._norm_key(key)
        for k, v in self._edge_cache.items():
            if self._norm_key(str(k)) == norm_target:
                return list(v)
        try:
            target_stem = Path(key).stem
        except Exception:
            target_stem = ""
        if target_stem:
            for k, v in self._edge_cache.items():
                try:
                    if Path(str(k)).stem == target_stem:
                        return list(v)
                except Exception:
                    continue
        return []

    def _resolve_edges_for_table(self, table_widget, key: str) -> list[tuple[str, str]]:
        edges = self._edges_from_edge_table(table_widget)
        if edges:
            return edges
        prop_rows = getattr(table_widget, "property", lambda _x: None)("edge_rows")
        if isinstance(prop_rows, list) and prop_rows:
            out: list[tuple[str, str]] = []
            for item in prop_rows:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                a = str(item[0]).strip()
                b = str(item[1]).strip()
                if a and b:
                    out.append((a, b))
            if out:
                return out
        # Fallback by current tab text(stem) -> cache, when key binding is stale.
        try:
            parent_tabs = table_widget.parentWidget()
            if isinstance(parent_tabs, QTabWidget):
                idx = parent_tabs.indexOf(table_widget)
                if idx >= 0:
                    tab_name = parent_tabs.tabText(idx).strip()
                    for k, v in self._edge_cache.items():
                        try:
                            if Path(str(k)).stem == tab_name:
                                return list(v)
                        except Exception:
                            continue
        except Exception:
            pass
        return self._resolve_edges_for_key(key)

    def _set_edge_table_equal_columns(self, table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _edge_table_headers(self) -> list[str]:
        return ["head", "dependent"]

    def _load_default_example_edges(self) -> None:
        # Build default example from the same RetriVis demo sentence dependency relations.
        example_key = self._example_key
        example_tokens: list[dict[str, object]] = [
            {"id": 1, "form": "I", "upos": "PRON", "head": 2},
            {"id": 2, "form": "used", "upos": "VERB", "head": 0},
            {"id": 3, "form": "QuanSyn", "upos": "PROPN", "head": 2},
            {"id": 4, "form": "for", "upos": "ADP", "head": 7},
            {"id": 5, "form": "quantitative", "upos": "ADJ", "head": 7},
            {"id": 6, "form": "syntactic", "upos": "ADJ", "head": 7},
            {"id": 7, "form": "analysis", "upos": "NOUN", "head": 2},
            {"id": 8, "form": ".", "upos": "PUNCT", "head": 2},
        ]
        by_id = {
            int(t["id"]): str(t["form"])
            for t in example_tokens
            if str(t.get("upos", "")).upper() != "PUNCT" and not _is_punct_token(str(t.get("form", "")))
        }
        example_edges: list[tuple[str, str]] = []
        for tok in example_tokens:
            dep_id = int(tok.get("id", 0) or 0)
            head_id = int(tok.get("head", 0) or 0)
            if dep_id <= 0 or head_id <= 0:
                continue
            if str(tok.get("upos", "")).upper() == "PUNCT" or _is_punct_token(str(tok.get("form", ""))):
                continue
            src = by_id.get(head_id, str(head_id))
            dst = by_id.get(dep_id, str(dep_id))
            if _is_punct_token(src) or _is_punct_token(dst):
                continue
            if src == dst:
                continue
            example_edges.append((src, dst))
        self._example_edges = [(str(a), str(b)) for a, b in example_edges]
        self._edge_cache = {example_key: self._example_edges}
        self.lingnet_edges_tabs.blockSignals(True)
        self.lingnet_edges_tabs.clear()
        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(self._edge_table_headers())
        table.setRowCount(len(self._example_edges))
        for r, (src, dst) in enumerate(self._example_edges):
            table.setItem(r, 0, QTableWidgetItem(str(src)))
            table.setItem(r, 1, QTableWidgetItem(str(dst)))
        self._set_edge_table_equal_columns(table)
        table.verticalHeader().setVisible(False)
        table.setProperty("treebank_path", example_key)
        table.setProperty("edge_rows", [(str(src), str(dst)) for src, dst in self._example_edges])
        self.lingnet_edges_tabs.addTab(table, "example")
        self.lingnet_edges_tabs.blockSignals(False)
        self.lingnet_edges_tabs.setCurrentIndex(0)
        self._draw_network(self._example_edges, example_key)
        self._append_report("Loaded default example from RetriVis sentence dependencies.")

    def _on_metric_selection_changed(self, *_args) -> None:
        key, edges = self._resolve_edges_for_render()
        if not edges:
            key, edges = self._current_tab_edges()
        self._fill_stats(key, edges)

    def _append_report(self, text: str) -> None:
        if not text:
            return
        self.lingnet_report.append(text)

    def _selected_edge_payloads(self) -> list[tuple[Path, list[tuple[str, str]]]]:
        selected_treebanks = self._selected_treebanks()
        out: list[tuple[Path, list[tuple[str, str]]]] = []
        for tb in selected_treebanks:
            key = self._resolve_edge_cache_key(tb)
            edges = self._edge_cache.get(key) if key else None
            if edges is None:
                continue
            out.append((tb, edges))
        return out

    def _norm_key(self, key: str) -> str:
        try:
            return str(Path(key).resolve())
        except Exception:
            return str(key)

    def _resolve_edge_cache_key(self, tb: Path) -> str | None:
        direct = str(tb)
        if direct in self._edge_cache:
            return direct
        resolved = self._norm_key(str(tb))
        for k in self._edge_cache.keys():
            if self._norm_key(str(k)) == resolved:
                return str(k)
        # last resort by stem
        for k in self._edge_cache.keys():
            try:
                if Path(str(k)).stem == tb.stem:
                    return str(k)
            except Exception:
                continue
        return None

    def _save_edge_file(self, out_path: Path, edges: list[tuple[str, str]]) -> None:
        suffix = out_path.suffix.lower()
        delimiter = "," if suffix == ".csv" else "\t"
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(["source", "target"])
            for src, dst in edges:
                writer.writerow([src, dst])

    def _save_table_csv(self, out_path: Path, table: QTableWidget) -> int:
        headers: list[str] = []
        for c in range(table.columnCount()):
            h = table.horizontalHeaderItem(c)
            headers.append(h.text() if h is not None else f"col_{c+1}")
        written = 0
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in range(table.rowCount()):
                if table.isRowHidden(r):
                    continue
                row_vals: list[str] = []
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    row_vals.append(item.text() if item is not None else "")
                writer.writerow(row_vals)
                written += 1
        return written

    def save_lingnet_metrics_dialog(self) -> None:
        gtab = getattr(self, "lingnet_global_table", None)
        ntab = getattr(self, "lingnet_node_table", None)
        if not isinstance(gtab, QTableWidget) or not isinstance(ntab, QTableWidget):
            _show_info_dialog(self, "Lingnet", "No statistics tables available.")
            return
        if gtab.columnCount() == 0 and ntab.columnCount() == 0:
            _show_info_dialog(self, "Lingnet", "No statistics to save. Please click Compute first.")
            return
        out_dir = _themed_get_existing_directory(self, "Select output directory", str(_runtime_base_dir()))
        if not out_dir:
            return
        out_root = Path(out_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        global_csv = out_root / "lingnet_global.csv"
        node_csv = out_root / "lingnet_node.csv"
        try:
            g_rows = self._save_table_csv(global_csv, gtab) if gtab.columnCount() > 0 else 0
            n_rows = self._save_table_csv(node_csv, ntab) if ntab.columnCount() > 0 else 0
            self.message.emit(f"Saved metrics: global({g_rows}) -> {global_csv.name}, node({n_rows}) -> {node_csv.name}")
            self._append_report(f"Saved metrics tables to: {out_root}")
        except Exception as exc:
            _show_warning_dialog(self, "Save failed", str(exc))

    def save_lingnet_edges_dialog(self) -> None:
        if not self._edge_cache:
            _show_info_dialog(self, "Lingnet", "No edge lists available. Please run Lingnet first.")
            return
        payloads = self._selected_edge_payloads()
        if not payloads:
            _show_info_dialog(self, "Lingnet", "No edge list matched the selected treebank.")
            return

        if len(payloads) == 1:
            tb, edges = payloads[0]
            mode_tag = "directed" if self._current_directed else "undirected"
            weight_tag = "weighted" if self._current_weighted else "unweighted"
            default_name = f"{tb.stem}_{self._current_relation}_{mode_tag}_{weight_tag}_edges.tsv"
            out_path, _ = _themed_get_save_file_name(
                self,
                "Save edge list",
                default_name,
                "TSV Files (*.tsv);;CSV Files (*.csv);;Text Files (*.txt)",
            )
            if not out_path:
                return
            target = Path(out_path)
            if target.suffix.lower() not in {".tsv", ".csv", ".txt"}:
                target = target.with_suffix(".tsv")
            self._save_edge_file(target, edges)
            self.message.emit(f"Saved edge list: {target}")
            self._append_report(f"Saved edge list: {target}")
            return

        out_dir = _themed_get_existing_directory(self, "Select output directory", str(_runtime_base_dir()))
        if not out_dir:
            return
        out_root = Path(out_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        saved = 0
        for tb, edges in payloads:
            mode_tag = "directed" if self._current_directed else "undirected"
            weight_tag = "weighted" if self._current_weighted else "unweighted"
            target = out_root / f"{tb.stem}_{self._current_relation}_{mode_tag}_{weight_tag}_edges.tsv"
            self._save_edge_file(target, edges)
            saved += 1
        self.message.emit(f"Saved {saved} edge lists to: {out_root}")
        self._append_report(f"Saved {saved} edge lists to: {out_root}")

    def run_lingnet(self) -> None:
        selected = self._selected_treebanks()
        if not selected:
            _show_info_dialog(self, "Lingnet", "No treebanks available for selected source.")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        mode = self.lingnet_relation_combo.currentText().strip().lower() or "dependency"
        directed = self.lingnet_directed_chk.isChecked()
        weighted = self.lingnet_weighted_chk.isChecked()
        self._current_relation = mode
        self._current_directed = directed
        self._current_weighted = weighted
        self.lingnet_run_btn.setEnabled(False)
        tag_dir = "directed" if directed else "undirected"
        tag_w = "weighted" if weighted else "unweighted"
        self.message.emit(f"Lingnet running ({mode}, {tag_dir}, {tag_w})...")
        self._append_report(f"Lingnet running ({mode}, {tag_dir}, {tag_w})...")
        self._worker = LingnetWorker(selected, mode, directed, weighted, self)
        self._worker.note.connect(self._append_report)
        self._worker.finished.connect(self._on_lingnet_finished)
        self._worker.failed.connect(self._on_lingnet_failed)
        self._worker.start()

    def _on_lingnet_finished(self, payload: object, mode: str) -> None:
        self.lingnet_run_btn.setEnabled(True)
        self._worker = None
        if not isinstance(payload, dict):
            self._on_lingnet_failed("Invalid lingnet output payload.")
            return
        normalized: dict[str, list[tuple[str, str]]] = {}
        for k, v in payload.items():
            normalized[str(k)] = list(v)
        if self._example_edges:
            normalized[self._example_key] = list(self._example_edges)
        self._edge_cache = normalized
        self._lingnet_layout_cache.clear()
        first_key = ""
        first_edges: list[tuple[str, str]] = []
        for k, rows in normalized.items():
            parsed: list[tuple[str, str]] = []
            for it in rows or []:
                if not isinstance(it, (list, tuple)) or len(it) < 2:
                    continue
                a = str(it[0]).strip()
                b = str(it[1]).strip()
                if a and b:
                    parsed.append((a, b))
            if parsed:
                first_key = str(k)
                first_edges = parsed
                break
        self._current_relation = mode
        self._lingnet_selected_node = None
        self._lingnet_selected_edge = None
        self._lingnet_pos_cache.clear()
        self._rebuild_edge_tabs()
        # Hard guarantee: draw from worker output directly, bypassing tab/key resolution.
        if first_edges:
            self._lingnet_last_non_empty_edges = list((str(a), str(b)) for a, b in first_edges)
            self._lingnet_last_non_empty_key = str(first_key)
            self._draw_network(first_edges, first_key)
        else:
            self._show_lingnet_placeholder("No edge data")
        tag_dir = "directed" if self._current_directed else "undirected"
        tag_w = "weighted" if self._current_weighted else "unweighted"
        self.message.emit(f"Lingnet completed ({mode}, {tag_dir}, {tag_w}).")
        self._append_report(f"Lingnet completed ({mode}, {tag_dir}, {tag_w}).")

    def _on_lingnet_failed(self, text: str) -> None:
        self.lingnet_run_btn.setEnabled(True)
        self._worker = None
        _show_warning_dialog(self, "Lingnet failed", text)
        self.message.emit(f"Lingnet failed: {text}")
        self._append_report(f"Lingnet failed: {text}")

    def _rebuild_edge_tabs(self) -> None:
        self.lingnet_edges_tabs.blockSignals(True)
        self.lingnet_edges_tabs.clear()
        if not self._edge_cache:
            self.lingnet_global_table.clear()
            self.lingnet_global_table.setColumnCount(0)
            self.lingnet_global_table.setRowCount(1)
            self.lingnet_node_table.clear()
            self.lingnet_node_table.setColumnCount(0)
            self.lingnet_node_table.setRowCount(0)
            self._draw_network([])
            self.lingnet_edges_tabs.blockSignals(False)
            return
        used_keys: set[str] = set()
        for tb in self._imported_treebanks:
            key = self._resolve_edge_cache_key(tb)
            if key is None or key not in self._edge_cache:
                continue
            used_keys.add(key)
            edges = self._edge_cache[key]
            table = QTableWidget()
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(self._edge_table_headers())
            table.setRowCount(len(edges))
            for r, (src, dst) in enumerate(edges):
                table.setItem(r, 0, QTableWidgetItem(str(src)))
                table.setItem(r, 1, QTableWidgetItem(str(dst)))
            self._set_edge_table_equal_columns(table)
            table.verticalHeader().setVisible(False)
            table.setProperty("treebank_path", str(key))
            table.setProperty("edge_rows", [(str(src), str(dst)) for src, dst in edges])
            self.lingnet_edges_tabs.addTab(table, tb.stem)
        # Fallback: show payload keys not mapped to imported list, to avoid stale example display.
        for key, edges in self._edge_cache.items():
            if key in used_keys:
                continue
            table = QTableWidget()
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(self._edge_table_headers())
            table.setRowCount(len(edges))
            for r, (src, dst) in enumerate(edges):
                table.setItem(r, 0, QTableWidgetItem(str(src)))
                table.setItem(r, 1, QTableWidgetItem(str(dst)))
            self._set_edge_table_equal_columns(table)
            table.verticalHeader().setVisible(False)
            table.setProperty("treebank_path", str(key))
            table.setProperty("edge_rows", [(str(src), str(dst)) for src, dst in edges])
            tab_name = Path(str(key)).stem if str(key).strip() else "edges"
            self.lingnet_edges_tabs.addTab(table, tab_name)
        self.lingnet_edges_tabs.blockSignals(False)
        if self.lingnet_edges_tabs.count() > 0:
            self.lingnet_edges_tabs.setCurrentIndex(0)
            for i in range(self.lingnet_edges_tabs.count()):
                w = self.lingnet_edges_tabs.widget(i)
                if isinstance(w, QTableWidget):
                    self._attach_edge_table_watchers(w)
            self._refresh_from_current_edge_table()
        else:
            self.lingnet_global_table.clear()
            self.lingnet_global_table.setColumnCount(0)
            self.lingnet_global_table.setRowCount(1)
            self.lingnet_node_table.clear()
            self.lingnet_node_table.setColumnCount(0)
            self.lingnet_node_table.setRowCount(0)
            self._draw_network([])

    def _on_edge_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        self._refresh_from_current_edge_table()

    def _open_lingnet_html_in_browser(self) -> None:
        if not getattr(self, "_lingnet_html_path", None):
            return
        path = Path(self._lingnet_html_path)
        if not path.exists():
            return
        try:
            webbrowser.open(path.as_uri(), new=2)
        except Exception:
            pass

    def _on_lingnet_context_menu(self, pos: QPoint) -> None:
        if getattr(self, "lingnet_web", None) is None:
            return
        menu = QMenu(self)
        export_action = menu.addAction("Export")
        chosen = menu.exec(self.lingnet_web.mapToGlobal(pos))
        if chosen is export_action:
            self._export_lingnet_network_image()

    def _prompt_lingnet_export_options(self) -> tuple[str, int | None] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Options")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        fmt_combo = QComboBox(dialog)
        fmt_combo.addItems(["png", "jpg", "bmp", "tiff", "pdf"])
        form.addRow("Format", fmt_combo)

        dpi_label = QLabel("DPI", dialog)
        dpi_spin = QSpinBox(dialog)
        dpi_spin.setRange(72, 1200)
        dpi_spin.setValue(300)
        dpi_spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        dpi_spin.setAccelerated(True)
        dpi_spin.setMinimumHeight(28)
        form.addRow(dpi_label, dpi_spin)
        layout.addLayout(form)

        def _sync() -> None:
            fmt = fmt_combo.currentText().strip().lower()
            raster = fmt in {"png", "jpg", "jpeg", "bmp", "tif", "tiff"}
            dpi_label.setVisible(raster)
            dpi_spin.setVisible(raster)
            dpi_spin.setEnabled(raster)

        fmt_combo.currentTextChanged.connect(lambda _v: _sync())
        _sync()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        fmt = fmt_combo.currentText().strip().lower() or "png"
        if fmt in {"png", "jpg", "jpeg", "bmp", "tif", "tiff"}:
            return fmt, int(dpi_spin.value())
        return fmt, None

    def _export_lingnet_network_image(self) -> None:
        if getattr(self, "lingnet_web", None) is None:
            _show_info_dialog(self, "Export", "No network view available.")
            return
        options = self._prompt_lingnet_export_options()
        if options is None:
            return
        fmt, dpi = options
        save_filter = {
            "png": "PNG Image (*.png)",
            "jpg": "JPEG Image (*.jpg *.jpeg)",
            "jpeg": "JPEG Image (*.jpg *.jpeg)",
            "bmp": "Bitmap Image (*.bmp)",
            "tiff": "TIFF Image (*.tiff *.tif)",
            "tif": "TIFF Image (*.tiff *.tif)",
            "pdf": "PDF File (*.pdf)",
        }.get(fmt, "All Files (*.*)")
        default_name = f"lingnet_network.{ 'jpg' if fmt == 'jpeg' else ('tiff' if fmt == 'tif' else fmt) }"
        out_path, _ = _themed_get_save_file_name(
            self,
            "Export network image",
            str(Path.home() / default_name),
            save_filter,
        )
        if not out_path:
            return
        out_file = Path(out_path)
        target_suffix = "." + ("jpg" if fmt == "jpeg" else "tiff" if fmt == "tif" else fmt)
        if out_file.suffix.lower() != target_suffix:
            out_file = out_file.with_suffix(target_suffix)

        if fmt == "pdf":
            try:
                page = self.lingnet_web.page()

                def _on_pdf_bytes(data: QByteArray) -> None:
                    try:
                        if data is None or data.size() <= 0:
                            raise RuntimeError("No PDF data returned by renderer.")
                        out_file.write_bytes(bytes(data))
                        self.message.emit(f"Exported network image: {out_file}")
                        self._append_report(f"Exported network image: {out_file}")
                    except Exception as exc:
                        _show_warning_dialog(self, "Export failed", str(exc))
                        self._append_report(f"LingNet export failed: {exc}")

                page.printToPdf(_on_pdf_bytes)
                self._append_report("LingNet export started...")
            except Exception as exc:
                _show_warning_dialog(self, "Export failed", str(exc))
                self._append_report(f"LingNet export failed: {exc}")
            return

        js_api = "jpg" if fmt in {"jpg", "jpeg"} else "png"
        js_bg = "#ffffff" if js_api == "jpg" else "transparent"
        js = (
            "(function(){"
            "try{"
            f"if(window.cy && typeof window.cy.{js_api}==='function'){{"
            f"return window.cy.{js_api}({{full:true,bg:'{js_bg}',output:'base64uri'}});"
            "}"
            "return '';"
            "}catch(e){return '';}"
            "})();"
        )

        def _on_js_done(data_uri: object) -> None:
            saved_ok = False
            try:
                txt = str(data_uri or "")
                if txt.startswith("data:image/") and ";base64," in txt:
                    raw = txt.split(",", 1)[1]
                    image = QImage.fromData(base64.b64decode(raw))
                    if not image.isNull():
                        try:
                            dpi_value = int(dpi or 300)
                            dpm = max(1, int(round(dpi_value / 0.0254)))
                            image.setDotsPerMeterX(dpm)
                            image.setDotsPerMeterY(dpm)
                        except Exception:
                            pass
                        qt_fmt = "JPG" if fmt in {"jpg", "jpeg"} else "TIFF" if fmt in {"tif", "tiff"} else fmt.upper()
                        saved_ok = bool(image.save(str(out_file), qt_fmt))
                    if not saved_ok:
                        out_file.write_bytes(base64.b64decode(raw))
                        saved_ok = out_file.exists() and out_file.stat().st_size > 0
                    if saved_ok:
                        self.message.emit(f"Exported network image: {out_file}")
                        self._append_report(f"Exported network image: {out_file}")
                        return
            except Exception:
                pass
            try:
                # Fallback: widget grab (may not be transparent depending on renderer).
                pix = self.lingnet_web.grab()
                saved_ok = bool(pix.save(str(out_file), "PNG"))
                if not saved_ok:
                    raise RuntimeError("Failed to save PNG from WebEngine snapshot.")
                self.message.emit(f"Exported network image: {out_file}")
                self._append_report(f"Exported network image: {out_file}")
            except Exception as exc:
                _show_warning_dialog(self, "Export failed", str(exc))
                self._append_report(f"LingNet export failed: {exc}")

        try:
            self._append_report("LingNet export started...")
            self.lingnet_web.page().runJavaScript(js, _on_js_done)
        except Exception as exc:
            _show_warning_dialog(self, "Export failed", str(exc))
            self._append_report(f"LingNet export failed: {exc}")

    def _draw_network(self, edges: list[tuple[str, str]], cache_key: str = "") -> None:
        new_key = cache_key or ""
        self._lingnet_current_key = new_key
        self._lingnet_current_graph = None
        # Hard fallback at render entry: if incoming edges are empty, re-resolve
        # from current visible edge table / table-bound rows / cache.
        if not edges:
            try:
                idx = self.lingnet_edges_tabs.currentIndex()
            except Exception:
                idx = -1
            if idx >= 0:
                tab = self._edge_table_from_tab_widget(self.lingnet_edges_tabs.widget(idx))
                if tab is not None:
                    key_from_tab = str(tab.property("treebank_path") or new_key)
                    edges = self._edge_rows_from_table_widget(tab)
                    if not edges:
                        edges = self._resolve_edges_for_table(tab, key_from_tab)
                    if not new_key:
                        new_key = key_from_tab
                        self._lingnet_current_key = new_key
            if not edges and new_key:
                edges = self._resolve_edges_for_key(new_key)
            if not edges and idx >= 0:
                # Final fallback by current tab name -> cache mapping.
                tab = self._edge_table_from_tab_widget(self.lingnet_edges_tabs.widget(idx))
                if tab is not None:
                    try:
                        tab_name = self.lingnet_edges_tabs.tabText(idx).strip()
                        for k, v in self._edge_cache.items():
                            try:
                                if Path(str(k)).stem == tab_name:
                                    edges = list(v)
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass
            if not edges:
                # Absolute final fallback: scan all edge-list tabs.
                i, key_i, edges_i = self._first_non_empty_edge_tab()
                if i >= 0 and edges_i:
                    edges = edges_i
                    if not new_key:
                        new_key = key_i
                        self._lingnet_current_key = new_key
            if not edges:
                key_c, edges_c = self._first_non_empty_cached_edges()
                if edges_c:
                    edges = edges_c
                    if not new_key:
                        new_key = key_c
                        self._lingnet_current_key = new_key
            if not edges and self._lingnet_last_non_empty_edges:
                edges = list(self._lingnet_last_non_empty_edges)
                if not new_key:
                    new_key = self._lingnet_last_non_empty_key
                    self._lingnet_current_key = new_key
        self._lingnet_edge_pairs = [(str(a), str(b)) for a, b in edges]
        if edges:
            self._lingnet_last_non_empty_edges = list(self._lingnet_edge_pairs)
            if new_key:
                self._lingnet_last_non_empty_key = str(new_key)
        if not edges:
            self._show_lingnet_placeholder("No edge data")
            return
        directed = bool(getattr(self, "_viz_directed", False))
        weighted = bool(getattr(self, "_viz_weighted", False))
        node_color = str(getattr(self, "_viz_node_color", "#d83a3a"))
        edge_width = float(getattr(self, "_viz_edge_width", 0.6))
        show_node_labels = bool(getattr(self, "_viz_show_node_labels", True))
        show_weight_labels = bool(getattr(self, "_viz_show_weight_labels", True))

        edge_weights: dict[tuple[str, str], int] = {}
        if weighted:
            for src, dst in edges:
                a = str(src)
                b = str(dst)
                key = (a, b) if directed else ((a, b) if a <= b else (b, a))
                edge_weights[key] = edge_weights.get(key, 0) + 1
            edge_pairs = list(edge_weights.keys())
        else:
            seen_pairs: set[tuple[str, str]] = set()
            edge_pairs: list[tuple[str, str]] = []
            for a_raw, b_raw in edges:
                a = str(a_raw)
                b = str(b_raw)
                key = (a, b) if directed else ((a, b) if a <= b else (b, a))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                edge_pairs.append(key)

        node_names = sorted({n for a, b in edge_pairs for n in (a, b)})
        if not node_names:
            node_names = sorted({str(a) for a, _b in edges} | {str(b) for _a, b in edges})

        n_nodes = max(1, len(node_names))
        n_edges = max(0, len(edge_pairs))
        # Large graphs: reduce label pressure for faster first paint.
        if n_nodes >= 1200:
            show_node_labels = False
        if n_edges >= 6000:
            show_weight_labels = False
        layout_mode = str(getattr(self, "_viz_layout_mode", "auto")).lower()
        auto_large = n_nodes >= 1200 or n_edges >= 6000
        if layout_mode == "auto":
            layout_name = "cose"
        elif layout_mode == "spring-out":
            layout_name = "cose"
        elif layout_mode in {"circle", "concentric", "grid"}:
            layout_name = layout_mode
        else:
            layout_name = "cose"
        fast_cose = layout_name == "cose" and (n_nodes >= 900 or n_edges >= 3500)
        huge_graph = n_nodes >= 1500 or n_edges >= 6000
        # Default behavior for large networks: show preset immediately under auto mode.
        # Explicit spring-out always uses force-directed layout after user clicks Show.
        use_preset = layout_name == "cose" and layout_mode == "auto" and auto_large
        preset_positions: dict[str, dict[str, float]] = {}
        if use_preset:
            sig = self._edge_signature(edge_pairs)
            cache_key_layout = f"{sig}|{n_nodes}|{n_edges}|{'d' if directed else 'u'}|seed"
            preset_positions = self._lingnet_layout_cache.get(cache_key_layout, {})
            if not preset_positions:
                preset_positions = self._compute_preset_positions(node_names, edge_pairs, directed)
                if preset_positions:
                    self._lingnet_layout_cache[cache_key_layout] = preset_positions
        if layout_name == "grid":
            layout_kwargs = '{"name":"grid","fit":true,"padding":20}'
        elif layout_name == "circle":
            layout_kwargs = '{"name":"circle","fit":true,"padding":20}'
        elif layout_name == "concentric":
            layout_kwargs = '{"name":"concentric","fit":true,"padding":20}'
        elif use_preset and preset_positions:
            layout_kwargs = '{"name":"preset","fit":true,"padding":20}'
        elif fast_cose:
            layout_kwargs = (
                '{"name":"cose","animate":false,"fit":true,"padding":10,'
                '"nodeRepulsion":700,"idealEdgeLength":16,"numIter":56,'
                '"gravity":0.28,"initialTemp":42,"coolingFactor":0.96}'
            )
        else:
            layout_kwargs = '{"name":"cose","animate":false,"fit":true,"padding":20,"nodeRepulsion":4500,"idealEdgeLength":40}'
        if preset_positions:
            nodes_json = [{"data": {"id": n, "label": n}, "position": preset_positions.get(n, {"x": 0.0, "y": 0.0})} for n in node_names]
        else:
            nodes_json = [{"data": {"id": n, "label": n}} for n in node_names]
        refine_layout_js = ""
        edges_json = []
        for idx, (a, b) in enumerate(edge_pairs, start=1):
            wt = int(edge_weights.get((a, b), 1)) if weighted else 1
            edges_json.append(
                {
                    "data": {
                        "id": f"e{idx}",
                        "source": a,
                        "target": b,
                        "weight": wt,
                        "weight_label": str(wt) if (weighted and show_weight_labels) else "",
                        "tip": f"{a} {'->' if directed else '--'} {b}",
                    }
                }
            )
        arrow_shape = "triangle" if directed else "none"
        node_size = 8 if n_nodes >= 3000 else (10 if n_nodes >= 1200 else 14)
        node_label_expr = "'data(label)'" if show_node_labels else "''"
        script_src = self._ensure_lingnet_js_runtime()
        script_block = f"<script src=\"{script_src}\"></script>" if script_src else ""
        html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  {script_block}
  <style>
    html, body, #cy {{
      width: 100%; height: 100%; margin: 0; padding: 0; background: #ffffff; overflow: hidden;
      font-family: Segoe UI, Arial, sans-serif;
    }}
    #tip {{
      position: fixed; display: none; pointer-events: none; z-index: 9999;
      background: rgba(255,255,255,0.95); border: 1px solid #000; border-radius: 4px;
      color: #000; font-size: 12px; padding: 3px 6px;
    }}
  </style>
</head>
<body>
  <div id="cy"></div>
  <div id="tip"></div>
  <script>
    window.onerror = function(msg, src, line, col) {{
      try {{ console.error('LingNet render error:', msg, '@', line + ':' + col, src || ''); }} catch (_) {{}}
    }};
    if (typeof cytoscape === 'undefined') {{
      try {{ console.error('LingNet: cytoscape script not loaded.'); }} catch (_) {{}}
    }} else {{
    const elements = {json.dumps(nodes_json + edges_json, ensure_ascii=False)};
    window.cy = cytoscape({{
      container: document.getElementById('cy'),
      elements: elements,
      textureOnViewport: true,
      motionBlur: false,
      hideEdgesOnViewport: false,
      pixelRatio: 1,
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      autoungrabify: false,
      autounselectify: false,
      style: [
        {{
          selector: 'node',
          style: {{
            'border-color': '#000000',
            'border-width': 1,
            'background-color': '{node_color}',
            'label': {node_label_expr},
            'color': '#000000',
            'font-size': 9,
            'font-weight': 300,
            'text-valign': 'center',
            'text-halign': 'center',
            'width': {node_size},
            'height': {node_size}
          }}
        }},
        {{
          selector: 'edge',
          style: {{
            'line-color': '#000000',
            'target-arrow-color': '#000000',
            'target-arrow-shape': '{arrow_shape}',
            'curve-style': 'bezier',
            'width': {edge_width},
            'label': 'data(weight_label)',
            'font-size': 9,
            'text-background-color': '#ffffff',
            'text-background-opacity': 1,
            'text-background-padding': 2,
            'text-rotation': 'autorotate'
          }}
        }},
        {{
          selector: 'node:selected',
          style: {{
            'background-color': '#ffd34d',
            'border-color': '#111111',
            'border-width': 2
          }}
        }},
        {{
          selector: 'edge:selected',
          style: {{
            'line-color': '#ff8c00',
            'target-arrow-color': '#ff8c00',
            'width': 2
          }}
        }}
      ],
      layout: {layout_kwargs}
    }});
    const cy = window.cy;
    const tip = document.getElementById('tip');
    const showTip = (x, y, txt) => {{
      tip.style.left = (x + 10) + 'px';
      tip.style.top = (y + 10) + 'px';
      tip.textContent = txt;
      tip.style.display = 'block';
    }};
    const hideTip = () => {{
      tip.style.display = 'none';
    }};
    const LARGE_GRAPH = {str(huge_graph).lower()};
    const NODE_HOVER_ENABLED = true;
    const EDGE_HOVER_ENABLED = !LARGE_GRAPH;
    const MIN_ZOOM_FOR_NODE_HOVER = 0.0;
    const HOVER_THROTTLE_MS = LARGE_GRAPH ? 120 : 16;
    let lastHoverTs = 0;
    cy.on('mouseover', 'node', (evt) => {{
      if (!NODE_HOVER_ENABLED) return;
      if (MIN_ZOOM_FOR_NODE_HOVER > 0 && cy.zoom() < MIN_ZOOM_FOR_NODE_HOVER) return;
      const now = Date.now();
      if (now - lastHoverTs < HOVER_THROTTLE_MS) return;
      lastHoverTs = now;
      const n = evt.target;
      showTip(evt.originalEvent.clientX, evt.originalEvent.clientY, n.data('label') || n.id());
    }});
    cy.on('mouseover', 'edge', (evt) => {{
      if (!EDGE_HOVER_ENABLED) return;
      const e = evt.target;
      showTip(evt.originalEvent.clientX, evt.originalEvent.clientY, e.data('tip') || '');
    }});
    cy.on('mousemove', (evt) => {{
      if (tip.style.display === 'block') {{
        tip.style.left = (evt.originalEvent.clientX + 10) + 'px';
        tip.style.top = (evt.originalEvent.clientY + 10) + 'px';
      }}
    }});
    cy.on('mouseout', 'node,edge', () => hideTip());
    cy.on('zoom', () => {{
      if (MIN_ZOOM_FOR_NODE_HOVER > 0 && cy.zoom() < MIN_ZOOM_FOR_NODE_HOVER) {{
        hideTip();
      }}
    }});
    cy.on('tap', (evt) => {{
      if (evt.target === cy) {{
        cy.$(':selected').unselect();
      }}
    }});
    cy.nodes().grabify();
    setTimeout(() => {{
      try {{
        cy.resize();
        cy.fit(undefined, 20);
        cy.center();
      }} catch (_) {{}}
    }}, 60);
    window.addEventListener('resize', () => {{
      try {{
        cy.resize();
      }} catch (_) {{}}
    }});
    {refine_layout_js}
    }}
  </script>
</body>
</html>"""
        try:
            self._lingnet_html_path.write_text(html_doc, encoding="utf-8")
        except Exception:
            pass
        self._load_lingnet_html_into_view(html_doc)
        try:
            self._append_report(
                f"LingNet rendered: nodes={n_nodes}, edges={len(edge_pairs)} (raw={len(edges)}), "
                f"layout={layout_name}"
                f"{'|preset' if (use_preset and bool(preset_positions)) else ''}"
            )
        except Exception:
            pass
    def _on_lingnet_press(self, event) -> None:
        if event is None or event.inaxes is None:
            return
        if event.button != 1:
            return
        if self._lingnet_current_graph is None:
            return
        pos = self._lingnet_pos_cache.get(self._lingnet_current_key, {})
        if not pos:
            return
        x = event.xdata
        y = event.ydata
        if x is None or y is None:
            return
        target = self._lingnet_pick_target(float(x), float(y))
        if target is None:
            if self._lingnet_selected_node is not None or self._lingnet_selected_edge is not None:
                self._lingnet_selected_node = None
                self._lingnet_selected_edge = None
                edges = self._edge_cache.get(self._lingnet_current_key, [])
                self._draw_network(edges, self._lingnet_current_key)
            return
        kind, value = target
        if kind == "node":
            node = str(value)
            self._lingnet_selected_node = node
            self._lingnet_selected_edge = None
            self._lingnet_drag_node = node
            edges = self._edge_cache.get(self._lingnet_current_key, [])
            self._draw_network(edges, self._lingnet_current_key)
        elif kind == "edge":
            u, v = value
            self._lingnet_selected_node = None
            self._lingnet_selected_edge = (str(u), str(v))
            self._lingnet_drag_node = None
            edges = self._edge_cache.get(self._lingnet_current_key, [])
            self._draw_network(edges, self._lingnet_current_key)

    def _on_lingnet_motion(self, event) -> None:
        if event is None:
            return
        if self._lingnet_drag_node is not None:
            if event.inaxes is None or self._lingnet_current_graph is None:
                return
            x = event.xdata
            y = event.ydata
            if x is None or y is None:
                return
            pos = self._lingnet_pos_cache.get(self._lingnet_current_key, {})
            if self._lingnet_drag_node not in pos:
                return
            pos[self._lingnet_drag_node] = (float(x), float(y))
            # Live redraw while dragging.
            edges = self._edge_cache.get(self._lingnet_current_key, [])
            self._draw_network(edges, self._lingnet_current_key)
            return
        self._update_lingnet_hover(event)

    def _on_lingnet_release(self, _event) -> None:
        self._lingnet_drag_node = None

    def _point_to_segment_distance(
        self, px: float, py: float, ax: float, ay: float, bx: float, by: float
    ) -> float:
        vx = bx - ax
        vy = by - ay
        wx = px - ax
        wy = py - ay
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            return math.hypot(px - ax, py - ay)
        c2 = vx * vx + vy * vy
        if c2 <= 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, c1 / c2))
        proj_x = ax + t * vx
        proj_y = ay + t * vy
        return math.hypot(px - proj_x, py - proj_y)

    def _lingnet_pick_target(self, x: float, y: float):
        if self._lingnet_current_graph is None:
            return None
        pos = self._lingnet_pos_cache.get(self._lingnet_current_key, {})
        if not pos:
            return None
        xs = [float(p[0]) for p in pos.values()]
        ys = [float(p[1]) for p in pos.values()]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        node_thr = span * 0.035
        edge_thr = span * 0.018

        nearest_node = None
        nearest_nd = None
        for node, (nxp, nyp) in pos.items():
            d = math.hypot(float(nxp) - x, float(nyp) - y)
            if nearest_nd is None or d < nearest_nd:
                nearest_nd = d
                nearest_node = str(node)
        if nearest_node is not None and nearest_nd is not None and nearest_nd <= node_thr:
            return ("node", nearest_node)

        best_edge = None
        best_ed = None
        for u, v in self._lingnet_edge_pairs:
            if u not in pos or v not in pos:
                continue
            ux, uy = pos[u]
            vx, vy = pos[v]
            d = self._point_to_segment_distance(x, y, float(ux), float(uy), float(vx), float(vy))
            if best_ed is None or d < best_ed:
                best_ed = d
                best_edge = (str(u), str(v))
        if best_edge is not None and best_ed is not None and best_ed <= edge_thr:
            return ("edge", best_edge)
        return None

    def _update_lingnet_hover(self, event) -> None:
        annot = self._lingnet_hover_annot
        if annot is None or self._lingnet_current_graph is None:
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            if annot.get_visible():
                annot.set_visible(False)
                self._lingnet_hover_text = ""
                self.lingnet_canvas.draw_idle()
            return

        x = float(event.xdata)
        y = float(event.ydata)
        target = self._lingnet_pick_target(x, y)
        if target is not None and target[0] == "node":
            text = str(target[1])
            if text != self._lingnet_hover_text or not annot.get_visible():
                annot.xy = (x, y)
                annot.set_text(text)
                annot.set_visible(True)
                self._lingnet_hover_text = text
                self.lingnet_canvas.draw_idle()
            return
        if target is not None and target[0] == "edge":
            best_edge = target[1]
            directed = bool(getattr(self, "_current_directed", False))
            text = f"{best_edge[0]} -> {best_edge[1]}" if directed else f"{best_edge[0]} -- {best_edge[1]}"
            if text != self._lingnet_hover_text or not annot.get_visible():
                annot.xy = (x, y)
                annot.set_text(text)
                annot.set_visible(True)
                self._lingnet_hover_text = text
                self.lingnet_canvas.draw_idle()
            return

        if annot.get_visible():
            annot.set_visible(False)
            self._lingnet_hover_text = ""
            self.lingnet_canvas.draw_idle()

    def _metric_enabled(self, key: str) -> bool:
        chk = self._metric_checks.get(key)
        return bool(chk.isChecked()) if chk is not None else False

    def _degree_exponent_powerlaw(self, degrees: list[float]) -> float | None:
        pos_degrees = [int(round(float(v))) for v in degrees if float(v) > 0.0]
        if len(pos_degrees) < 3 or powerlaw is None:
            return None
        try:
            fit = powerlaw.Fit(pos_degrees, discrete=True, verbose=False)
            alpha = float(getattr(fit.power_law, "alpha", 0.0) or 0.0)
            if alpha <= 0.0 or math.isnan(alpha) or math.isinf(alpha):
                return None
            return alpha
        except Exception:
            return None

    def _centralization_from_degrees(self, degrees: list[int]) -> float | None:
        n = len(degrees)
        if n <= 2:
            return None
        degs = [int(d) for d in degrees]
        if not degs:
            return None
        max_deg = max(degs)
        numerator = sum(max_deg - d for d in degs)
        denominator = (n - 1) * (n - 2)
        if denominator <= 0:
            return None
        return float(numerator) / float(denominator)

    def _append_top_local(self, lines: list[str], title: str, values: dict[str, float], limit: int = 12) -> None:
        lines.append(f"{title}:")
        if not values:
            lines.append("  no data")
            return
        ranked = sorted(values.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        for node, value in ranked:
            lines.append(f"  {node}: {value:.4f}")

    def _build_metric_edge_weights(self, edges: list[tuple[str, str]], directed: bool) -> dict[tuple[str, str], int]:
        edge_weights: dict[tuple[str, str], int] = {}
        for src, dst in edges:
            a = str(src).strip()
            b = str(dst).strip()
            if not a or not b or a == b:
                continue
            key = (a, b)
            if not directed and a > b:
                key = (b, a)
            edge_weights[key] = edge_weights.get(key, 0) + 1
        return edge_weights

    def _metric_cache_key(
        self,
        edge_weights: dict[tuple[str, str], int],
        directed: bool,
        weighted: bool,
        selected_global_keys: list[str],
        selected_local_keys: list[str],
    ) -> str:
        rows: list[tuple[str, str]] = []
        for (a, b), w in sorted(edge_weights.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            repeat = int(w) if weighted else 1
            if repeat <= 0:
                continue
            for _ in range(repeat):
                rows.append((a, b))
        sig = self._edge_signature(rows)
        gk = ",".join(sorted(str(k) for k in selected_global_keys))
        lk = ",".join(sorted(str(k) for k in selected_local_keys))
        # Cache schema version: bump when metric payload structure/logic changes.
        return f"v2|{sig}|{'d' if directed else 'u'}|{'w' if weighted else 'uw'}|g:{gk}|l:{lk}"

    def _render_stats_from_payload(self, payload: dict[str, object]) -> None:
        node_names = [str(x) for x in (payload.get("nodes", []) or [])]
        global_map = dict(payload.get("global_map", {}) or {})
        local_values_map = dict(payload.get("local_values_map", {}) or {})
        degree_values = [int(x) for x in (payload.get("degree_values", []) or [])]
        directed = bool(getattr(self, "lingnet_viz_directed_chk", None).isChecked()) if hasattr(self, "lingnet_viz_directed_chk") else bool(getattr(self, "_viz_directed", False))

        degree_exp = self._degree_exponent_powerlaw([float(v) for v in degree_values])
        centralization = self._centralization_from_degrees(degree_values)
        deg_raw = str(global_map.get("degree_exponent", "")).strip().lower()
        if (not deg_raw) or deg_raw in {"n/a", "na", "none", "nan"}:
            if degree_exp is not None:
                global_map["degree_exponent"] = f"{degree_exp:.4f}"
            else:
                global_map["degree_exponent"] = "n/a"
        in_raw = str(global_map.get("in_degree_exponent", "")).strip().lower()
        if (not in_raw) or in_raw in {"n/a", "na", "none", "nan"}:
            in_vals = list((local_values_map.get("in_degree", {}) or {}).values())
            in_exp = self._degree_exponent_powerlaw([float(v) for v in in_vals]) if in_vals else None
            if in_exp is not None:
                global_map["in_degree_exponent"] = f"{in_exp:.4f}"
            else:
                global_map["in_degree_exponent"] = "n/a"
        out_raw = str(global_map.get("out_degree_exponent", "")).strip().lower()
        if (not out_raw) or out_raw in {"n/a", "na", "none", "nan"}:
            out_vals = list((local_values_map.get("out_degree", {}) or {}).values())
            out_exp = self._degree_exponent_powerlaw([float(v) for v in out_vals]) if out_vals else None
            if out_exp is not None:
                global_map["out_degree_exponent"] = f"{out_exp:.4f}"
            else:
                global_map["out_degree_exponent"] = "n/a"
        global_map["centralization"] = f"{centralization:.4f}" if centralization is not None else "n/a"

        selected_global = [(k, label) for k, label in self._global_metrics if self._metric_enabled(k)]
        if not directed:
            selected_global = [
                (k, label) for k, label in selected_global if k not in {"avg_in_degree", "avg_out_degree", "in_degree_exponent", "out_degree_exponent"}
            ]
        if not selected_global:
            selected_global = [("nodes", "Nodes"), ("edges", "Edges")]
        self.lingnet_global_table.clear()
        self.lingnet_global_table.setRowCount(1)
        self.lingnet_global_table.setColumnCount(len(selected_global))
        self.lingnet_global_table.setHorizontalHeaderLabels([label for _k, label in selected_global])
        for col, (key, _label) in enumerate(selected_global):
            self.lingnet_global_table.setItem(0, col, QTableWidgetItem(str(global_map.get(key, "n/a"))))
        self.lingnet_global_table.resizeColumnsToContents()
        self.lingnet_global_table.horizontalHeader().setStretchLastSection(True)

        selected_local = [(k, label) for k, label in self._local_metrics if self._metric_enabled(k)]
        if not directed:
            selected_local = [(k, label) for k, label in selected_local if k not in {"in_degree", "out_degree"}]
        self.lingnet_node_table.clear()
        columns = ["node"] + [label for _k, label in selected_local]
        self.lingnet_node_table.setColumnCount(len(columns))
        self.lingnet_node_table.setHorizontalHeaderLabels(columns)
        nodes = sorted(node_names, key=lambda x: str(x))
        self.lingnet_node_table.setSortingEnabled(False)
        self.lingnet_node_table.setRowCount(len(nodes))
        for r, node in enumerate(nodes):
            node_key = str(node)
            self.lingnet_node_table.setItem(r, 0, QTableWidgetItem(node_key))
            for c, (metric_key, _label) in enumerate(selected_local, start=1):
                metric_vals = local_values_map.get(metric_key, {}) or {}
                value = float(metric_vals.get(node_key, 0.0))
                self.lingnet_node_table.setItem(r, c, NumericSortableTableWidgetItem(f"{value:.4f}"))
        self.lingnet_node_table.resizeColumnsToContents()
        self.lingnet_node_table.horizontalHeader().setStretchLastSection(True)
        self.lingnet_node_table.setSortingEnabled(True)
        try:
            pairs = payload.get("pair_shortest_paths", []) or []
            if isinstance(pairs, list) and pairs:
                self._append_report(f"Cached pair shortest paths: {len(pairs)}")
        except Exception:
            pass

    def _on_metric_compute_finished(self, payload: object) -> None:
        self.lingnet_metric_compute_btn.setEnabled(True)
        self._metric_worker = None
        if not isinstance(payload, dict):
            self._append_report("Metrics compute failed: invalid payload")
            return
        backend = str((payload.get("meta", {}) or {}).get("backend", "unknown"))
        if self._stats_cache_key_current:
            self._stats_cache[self._stats_cache_key_current] = dict(payload)
            cached = self._stats_cache.get(self._stats_cache_key_current, {})
            self._render_stats_from_payload(cached)
            self._append_report(f"Metrics computed ({backend}, cached).")
            return
        self._render_stats_from_payload(dict(payload))
        self._append_report(f"Metrics computed ({backend}).")

    def _on_metric_compute_failed(self, text: str) -> None:
        self.lingnet_metric_compute_btn.setEnabled(True)
        self._metric_worker = None
        self._append_report(f"Metrics compute failed: {text}")

    def _open_lingnet_analyze_dialog(self) -> None:
        key = str(getattr(self, "_stats_cache_key_current", "") or "")
        payload = self._stats_cache.get(key) if key else None
        if not isinstance(payload, dict):
            _show_info_dialog(self, "Plot", "No cached statistics found. Please click Compute first.")
            return
        dlg = LingnetAnalyzeDialog(payload, self)
        dlg.exec()

    def _fill_stats(self, treebank_key: str, edges: list[tuple[str, str]]) -> None:
        directed = bool(getattr(self, "lingnet_viz_directed_chk", None).isChecked()) if hasattr(self, "lingnet_viz_directed_chk") else bool(getattr(self, "_viz_directed", False))
        weighted = bool(getattr(self, "lingnet_viz_weighted_chk", None).isChecked()) if hasattr(self, "lingnet_viz_weighted_chk") else bool(getattr(self, "_viz_weighted", False))
        self._viz_directed = directed
        self._viz_weighted = weighted
        selected_global = [k for k, _label in self._global_metrics if self._metric_enabled(k)]
        selected_local = [k for k, _label in self._local_metrics if self._metric_enabled(k)]
        if not directed:
            selected_global = [
                k for k in selected_global if k not in {"avg_in_degree", "avg_out_degree", "in_degree_exponent", "out_degree_exponent"}
            ]
            selected_local = [k for k in selected_local if k not in {"in_degree", "out_degree"}]
        if not selected_global:
            selected_global = ["nodes", "edges"]
        edge_weights = self._build_metric_edge_weights(edges, directed)
        if not edge_weights:
            self.lingnet_global_table.clear()
            self.lingnet_global_table.setColumnCount(1)
            self.lingnet_global_table.setRowCount(1)
            self.lingnet_global_table.setHorizontalHeaderLabels(["status"])
            self.lingnet_global_table.setItem(0, 0, QTableWidgetItem("No network data"))
            self.lingnet_node_table.clear()
            self.lingnet_node_table.setColumnCount(1)
            self.lingnet_node_table.setRowCount(0)
            self.lingnet_node_table.setHorizontalHeaderLabels(["node"])
            return

        cache_key = self._metric_cache_key(edge_weights, directed, weighted, selected_global, selected_local)
        self._stats_cache_key_current = cache_key
        cached = self._stats_cache.get(cache_key)
        if isinstance(cached, dict):
            self._render_stats_from_payload(cached)
            self._append_report("Metrics loaded from cache.")
            return

        if self._metric_worker is not None and self._metric_worker.isRunning():
            self._append_report("Metrics computation is already running...")
            return
        self.lingnet_metric_compute_btn.setEnabled(False)
        self._append_report("Computing metrics in background...")
        self._metric_worker = LingnetMetricWorker(
            edge_weights,
            directed,
            weighted,
            selected_global,
            selected_local,
            self,
        )
        self._metric_worker.finished.connect(self._on_metric_compute_finished)
        self._metric_worker.failed.connect(self._on_metric_compute_failed)
        self._metric_worker.start()


class SyntaxPage(QWidget):
    message = pyqtSignal(str)
    _task_done = pyqtSignal(object)
    MAX_SENTENCES = 1000
    PAGE_SIZE = 100

    def __init__(self):
        super().__init__()
        _bootstrap_cache_layout()
        self._pipeline_cache: dict[str, object] = {}
        self._models_root = _runtime_base_dir() / "models"
        self._spacy_root = self._models_root / "spacy"
        self._stanza_root = self._models_root / "stanza"
        try:
            self._spacy_root.mkdir(parents=True, exist_ok=True)
            self._stanza_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._txt_sources: list[Path] = []
        self._txt_source_order: list[str] = []
        self._clean_by_source: dict[str, list[str]] = {}
        self._clean_sentences: list[str] = []
        self._parsed_sentences: list[dict[str, object]] = []
        self._view_sentences: list[dict[str, object]] = []
        self._imported_treebanks: list[Path] = []
        self._converted_treebank_cache: dict[str, str] = {}
        self._external_source_cache: dict[str, list[dict[str, object]]] = {}
        self._all_conllu = ""
        self._parser_cache_dir = _quansyn_cache_path("parser", "current")
        self._parser_cache_file = self._parser_cache_dir / "parser_current.conllu"
        self._current_page = 0
        self._current_index = -1
        self._task_token = 0
        self._task_thread: threading.Thread | None = None
        self._build_ui()
        self._wire()
        self._task_done.connect(self._on_task_done)
        self._sync_default_model(force=True)
        self._render_no_graph("Import txt files and run parser to visualize dependency trees.")

    def set_imported_treebanks(self, paths: list[str]) -> None:
        self._imported_treebanks = [Path(p) for p in paths if Path(p).exists()]
        self._external_source_cache.clear()
        self._refresh_treebank_choices()

    def set_converted_treebank_cache(self, cache: dict[str, str]) -> None:
        self._converted_treebank_cache = dict(cache or {})
        self._external_source_cache.clear()
        self._refresh_treebank_choices()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        self.main_split.setChildrenCollapsible(False)
        root.addWidget(self.main_split, 1)

        # Left column (1)
        left = QFrame()
        left.setObjectName("plotCard")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(8, 8, 8, 8)
        left_l.setSpacing(8)

        cfg_wrap = QFrame()
        cfg_wrap.setObjectName("vizParamWrap")
        cfg_l = QVBoxLayout(cfg_wrap)
        cfg_l.setContentsMargins(8, 8, 8, 8)
        cfg_l.setSpacing(6)

        self.syntax_import_file_btn = QPushButton("Import TXT File")
        self.syntax_import_file_btn.setObjectName("accentButton")
        cfg_l.addWidget(self.syntax_import_file_btn, 0)

        self.syntax_import_folder_btn = QPushButton("Import TXT Folder")
        self.syntax_import_folder_btn.setObjectName("accentButton")
        cfg_l.addWidget(self.syntax_import_folder_btn, 0)

        self.syntax_txt_select_combo = QComboBox()
        self.syntax_txt_select_combo.addItem("all", "__all__")
        cfg_l.addWidget(QLabel("Select TXT File"), 0)
        cfg_l.addWidget(self.syntax_txt_select_combo, 0)

        form = QFormLayout()
        self.syntax_backend_combo = QComboBox()
        self.syntax_backend_combo.addItems(["spacy", "stanza"])
        self.syntax_lang_combo = QComboBox()
        self.syntax_lang_combo.addItem("English", "en")
        self.syntax_lang_combo.addItem("Chinese", "zh")
        self.syntax_model_edit = QComboBox()
        self.syntax_model_edit.setEditable(True)
        self.syntax_model_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.syntax_model_edit.lineEdit() is not None:
            self.syntax_model_edit.lineEdit().setPlaceholderText("Model name or local model folder name")
        form.addRow("Parser", self.syntax_backend_combo)
        form.addRow("Language", self.syntax_lang_combo)
        form.addRow("Model", self.syntax_model_edit)
        cfg_l.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.syntax_load_btn = QPushButton("Load Model")
        self.syntax_load_btn.setObjectName("accentButton")
        self.syntax_run_btn = QPushButton("Run Parser")
        self.syntax_run_btn.setObjectName("accentButton")
        btn_row.addWidget(self.syntax_load_btn, 1)
        btn_row.addWidget(self.syntax_run_btn, 1)
        cfg_l.addLayout(btn_row)

        self.syntax_save_btn = QPushButton("Save CoNLL-U")
        cfg_l.addWidget(self.syntax_save_btn, 0)

        self.syntax_sources_info = QLabel("No txt sources imported.")
        self.syntax_sources_info.setObjectName("statusInfo")
        self.syntax_sources_info.setWordWrap(True)
        cfg_l.addWidget(self.syntax_sources_info, 0)

        left_l.addWidget(cfg_wrap, 1)
        self.main_split.addWidget(left)

        # Right column (3.5)
        right = QFrame()
        right.setObjectName("plotCard")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 8, 8, 8)
        right_l.setSpacing(6)

        graph_title = QLabel("Dependency Tree (Editable)")
        graph_title.setObjectName("sectionTitle")
        right_l.addWidget(graph_title, 0)
        self.syntax_graph_web = None
        self.syntax_graph_fallback = None
        if QWebEngineView is not None:
            self.syntax_graph_web = QWebEngineView()
            _reject_web_fullscreen(self.syntax_graph_web)
            self.syntax_graph_web.setMinimumHeight(420)
            right_l.addWidget(self.syntax_graph_web, 1)
        else:
            self.syntax_graph_fallback = QTextEdit()
            self.syntax_graph_fallback.setReadOnly(True)
            right_l.addWidget(self.syntax_graph_fallback, 1)

        lower_split = QSplitter(Qt.Orientation.Horizontal)
        lower_split.setChildrenCollapsible(False)
        right_l.addWidget(lower_split, 0)

        search_wrap = QFrame()
        search_wrap.setObjectName("vizParamWrap")
        search_l = QVBoxLayout(search_wrap)
        search_l.setContentsMargins(8, 8, 8, 8)
        search_l.setSpacing(6)
        search_l.addWidget(QLabel("Search"), 0)
        sform = QFormLayout()
        self.syntax_search_source_combo = QComboBox()
        self.syntax_search_source_combo.addItems(["parsed", "imported", "converted"])
        self.syntax_search_treebank_combo = QComboBox()
        self.syntax_search_treebank_combo.addItem("all", "__all__")
        self.syntax_search_form = QLineEdit()
        self.syntax_search_lemma = QLineEdit()
        self.syntax_search_upos = QLineEdit()
        self.syntax_search_deprel = QLineEdit()
        sform.addRow("Source", self.syntax_search_source_combo)
        sform.addRow("Treebank", self.syntax_search_treebank_combo)
        search_l.addLayout(sform)
        fields_grid = QGridLayout()
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(8)
        fields_grid.setVerticalSpacing(6)
        fields_grid.addWidget(QLabel("form"), 0, 0)
        fields_grid.addWidget(self.syntax_search_form, 0, 1)
        fields_grid.addWidget(QLabel("lemma"), 0, 2)
        fields_grid.addWidget(self.syntax_search_lemma, 0, 3)
        fields_grid.addWidget(QLabel("upos"), 1, 0)
        fields_grid.addWidget(self.syntax_search_upos, 1, 1)
        fields_grid.addWidget(QLabel("deprel"), 1, 2)
        fields_grid.addWidget(self.syntax_search_deprel, 1, 3)
        search_l.addLayout(fields_grid)
        self.syntax_search_btn = QPushButton("Search")
        self.syntax_search_btn.setObjectName("accentButton")
        search_l.addWidget(self.syntax_search_btn, 0)
        lower_split.addWidget(search_wrap)

        list_wrap = QFrame()
        list_l = QVBoxLayout(list_wrap)
        list_l.setContentsMargins(0, 0, 0, 0)
        list_l.setSpacing(6)
        list_head = QHBoxLayout()
        list_head.setContentsMargins(0, 0, 0, 0)
        self.syntax_list_title = QLabel("Sentences (max 1000)")
        self.syntax_list_title.setObjectName("sectionTitle")
        list_head.addWidget(self.syntax_list_title, 0)
        list_head.addStretch(1)
        self.syntax_page_info = QLabel("Page 0/0")
        list_head.addWidget(self.syntax_page_info, 0)
        list_l.addLayout(list_head)
        self.syntax_sentence_list = QListWidget()
        self.syntax_sentence_list.setMaximumHeight(220)
        list_l.addWidget(self.syntax_sentence_list, 1)
        list_nav = QHBoxLayout()
        list_nav.setContentsMargins(0, 0, 0, 0)
        self.syntax_prev_page_btn = QPushButton("Prev")
        self.syntax_next_page_btn = QPushButton("Next")
        list_nav.addWidget(self.syntax_prev_page_btn, 0, Qt.AlignmentFlag.AlignLeft)
        list_nav.addStretch(1)
        list_nav.addWidget(self.syntax_next_page_btn, 0, Qt.AlignmentFlag.AlignRight)
        list_l.addLayout(list_nav)
        lower_split.addWidget(list_wrap)
        lower_split.setStretchFactor(0, 1)
        lower_split.setStretchFactor(1, 3)
        lower_split.setSizes([240, 720])
        self.main_split.addWidget(right)
        self.main_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(1, 5)
        self.main_split.setSizes([220, 1100])

        self.syntax_status = QLabel("Ready.")
        self.syntax_status.setObjectName("statusInfo")
        root.addWidget(self.syntax_status, 0)

    def _wire(self) -> None:
        self.syntax_backend_combo.currentIndexChanged.connect(lambda _i: self._sync_default_model())
        self.syntax_lang_combo.currentIndexChanged.connect(lambda _i: self._sync_default_model())
        self.syntax_load_btn.clicked.connect(self._on_load_model_clicked)
        self.syntax_run_btn.clicked.connect(self._on_run_clicked)
        self.syntax_save_btn.clicked.connect(self._on_save_clicked)
        self.syntax_import_file_btn.clicked.connect(self._on_import_txt_files)
        self.syntax_import_folder_btn.clicked.connect(self._on_import_txt_folder)
        self.syntax_txt_select_combo.currentIndexChanged.connect(lambda _i: self._on_txt_selection_changed())
        self.syntax_search_source_combo.currentIndexChanged.connect(lambda _i: self._refresh_treebank_choices())
        self.syntax_search_btn.clicked.connect(self._apply_sentence_search)
        self.syntax_sentence_list.itemClicked.connect(self._on_sentence_selected)
        self.syntax_prev_page_btn.clicked.connect(lambda: self._navigate_sentence(-1))
        self.syntax_next_page_btn.clicked.connect(lambda: self._navigate_sentence(1))
        if self.syntax_graph_web is not None:
            self.syntax_graph_web.titleChanged.connect(self._on_graph_title_changed)

    def _stanza_lang_dir(self, lang: str) -> str:
        raw = str(lang or "").strip().lower()
        return "zh-hans" if raw in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw

    def _collect_spacy_models(self, lang: str) -> list[str]:
        out: list[str] = []
        try:
            base = self._spacy_root / str(lang).strip().lower()
            if base.exists():
                for p in sorted(base.iterdir()):
                    if p.is_dir():
                        name = str(p.name).strip()
                        if name and ("trf" not in name.lower()):
                            out.append(name)
        except Exception:
            pass
        return out

    def _collect_stanza_models(self, lang: str) -> list[str]:
        out: set[str] = set()
        try:
            lang_dir = self._stanza_root / self._stanza_lang_dir(lang)
            tok_dir = lang_dir / "tokenize"
            if tok_dir.exists():
                for p in tok_dir.glob("*.pt"):
                    stem = p.stem.strip()
                    if stem and not stem.lower().startswith("tmp"):
                        out.add(stem)
        except Exception:
            pass
        return sorted(out)

    def _model_text(self) -> str:
        return self.syntax_model_edit.currentText().strip()

    def _set_model_text(self, value: str) -> None:
        self.syntax_model_edit.setCurrentText(str(value or "").strip())

    def _refresh_model_choices(self, backend: str, lang: str, default_model: str, force: bool = False) -> None:
        current = self._model_text()
        options: list[str] = []
        if backend == "spacy":
            presets = {
                "en": ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"],
                "zh": ["zh_core_web_sm", "zh_core_web_md"],
            }
            options.extend(self._collect_spacy_models(lang))
            options.extend(presets.get(lang, []))
        else:
            presets = {
                "en": ["combined", "ewt", "gum"],
                "zh": ["gsdsimp", "gsd", "hkcancor"],
            }
            options.extend(self._collect_stanza_models(lang))
            options.extend(presets.get(lang, []))
        if default_model:
            options.append(default_model)
        # de-dup while preserving order
        uniq: list[str] = []
        seen: set[str] = set()
        for x in options:
            sx = str(x).strip()
            if not sx or sx in seen:
                continue
            seen.add(sx)
            uniq.append(sx)
        self.syntax_model_edit.blockSignals(True)
        self.syntax_model_edit.clear()
        if uniq:
            self.syntax_model_edit.addItems(uniq)
        chosen = default_model if (force or not current) else current
        if "trf" in str(chosen).lower():
            chosen = default_model if default_model and ("trf" not in default_model.lower()) else (uniq[0] if uniq else "")
        self._set_model_text(chosen)
        self.syntax_model_edit.blockSignals(False)

    def _sync_default_model(self, force: bool = False) -> None:
        backend = self.syntax_backend_combo.currentText().strip().lower()
        lang = str(self.syntax_lang_combo.currentData() or "en").strip().lower()
        defaults = {
            ("spacy", "en"): "en_core_web_sm",
            ("spacy", "zh"): "zh_core_web_sm",
            ("stanza", "en"): "combined",
            ("stanza", "zh"): "gsdsimp",
        }
        new_default = defaults.get((backend, lang), "")
        self._refresh_model_choices(backend, lang, new_default, force=force)

    @staticmethod
    def _split_to_sentences(text: str) -> list[str]:
        raw = str(text or "")
        if cleantext_clean is not None:
            try:
                # Use clean-text for robust multilingual normalization/cleaning.
                raw = cleantext_clean(
                    raw,
                    fix_unicode=True,
                    to_ascii=False,
                    lower=False,
                    normalize_whitespace=False,
                    no_line_breaks=False,
                    strip_lines=False,
                    no_urls=False,
                    no_emails=False,
                    no_phone_numbers=False,
                    no_numbers=False,
                    no_digits=False,
                    no_currency_symbols=False,
                    no_punct=False,
                    no_emoji=False,
                )
            except Exception:
                pass
        # Normalize first to reduce mixed-width/compatibility noise.
        cleaned = unicodedata.normalize("NFKC", raw)
        # Normalize line separators and tabs.
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
        # Remove common mojibake/BOM artifacts and replacement chars.
        cleaned = cleaned.replace("ï»¿", " ").replace("\ufeff", " ").replace("\ufffd", " ")
        # Remove zero-width and format characters often introduced by copy/paste.
        cleaned = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069]", " ", cleaned)
        # Remove control chars except newline which is used as temporary splitter.
        cleaned = "".join(
            ch if (ch == "\n" or (unicodedata.category(ch) not in {"Cc", "Cf"})) else " "
            for ch in cleaned
        )
        # Collapse noisy punctuation-like separators produced by broken encoding.
        cleaned = re.sub(r"[`~^]+", " ", cleaned)
        cleaned = re.sub(r"[ \u00a0]+", " ", cleaned)
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
        merged = " ".join(lines)
        if not merged:
            return []
        # Keep punctuation, but split into one-sentence-per-line chunks.
        chunks = re.split(r"(?<=[。！？.!?；;])\s+", merged)
        out: list[str] = []
        for c in chunks:
            c2 = re.sub(r"\s+", " ", c).strip(" \t\n\r")
            # Drop isolated garbage tokens left after cleaning.
            c2 = re.sub(r"(?:\s|^)[_#@]{2,}(?:\s|$)", " ", c2).strip()
            if c2:
                out.append(c2)
        return out

    def _load_txt_sources(self, paths: list[Path]) -> None:
        sources = [p for p in paths if p.exists() and p.is_file()]
        if not sources:
            self._txt_sources = []
            self._txt_source_order = []
            self._clean_by_source = {}
            self._clean_sentences = []
            self._parsed_sentences = []
            self._view_sentences = []
            self._all_conllu = ""
            self._refresh_sentence_page()
            self._render_no_graph("No txt source.")
            self.syntax_sources_info.setText("No txt sources imported.")
            self.syntax_txt_select_combo.clear()
            self.syntax_txt_select_combo.addItem("all", "__all__")
            return
        self._txt_sources = sources
        self._txt_source_order = [str(p.resolve()) for p in sources]
        self._clean_by_source = {}
        collected: list[str] = []
        for p in sources:
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw = ""
            sents = self._split_to_sentences(raw)
            self._clean_by_source[str(p.resolve())] = list(sents)
            collected.extend(sents)
        self._clean_sentences = collected[: self.MAX_SENTENCES]
        self._parsed_sentences = []
        self._view_sentences = []
        self._all_conllu = ""
        self._current_page = 0
        self._current_index = -1
        self.syntax_txt_select_combo.clear()
        self.syntax_txt_select_combo.addItem("all", "__all__")
        for p in sources:
            self.syntax_txt_select_combo.addItem(p.name, str(p.resolve()))
        self._refresh_sentence_page()
        self._refresh_treebank_choices()
        self.syntax_sources_info.setText(
            f"Imported {len(sources)} txt source(s), cleaned to {len(self._clean_sentences)} sentence(s)."
        )
        self.syntax_status.setText("Text cleaned: one sentence per line format ready.")
        self.message.emit("Parser source imported and cleaned.")

    def _on_txt_selection_changed(self) -> None:
        # selection is applied on next Parse run
        sel = str(self.syntax_txt_select_combo.currentData() or "__all__")
        if sel == "__all__":
            self.syntax_status.setText("TXT selection: all")
        else:
            self.syntax_status.setText(f"TXT selection: {Path(sel).name}")

    def _get_parse_sentences_for_selected_txt(self) -> list[tuple[str, str]]:
        sel = str(self.syntax_txt_select_combo.currentData() or "__all__")
        out: list[tuple[str, str]] = []
        if sel == "__all__":
            for src in self._txt_source_order:
                for s in self._clean_by_source.get(src, []):
                    out.append((src, s))
                    if len(out) >= self.MAX_SENTENCES:
                        return out
            return out
        for s in self._clean_by_source.get(sel, []):
            out.append((sel, s))
            if len(out) >= self.MAX_SENTENCES:
                break
        return out

    def _on_import_txt_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Import txt files",
            str(_runtime_base_dir()),
            "Text files (*.txt);;All files (*.*)",
        )
        if not selected:
            return
        self._load_txt_sources([Path(x) for x in selected])

    def _on_import_txt_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Import txt folder", str(_runtime_base_dir()))
        if not selected:
            return
        root = Path(selected)
        files = sorted(root.glob("*.txt"))
        self._load_txt_sources(files)

    def _on_clear_sources(self) -> None:
        self._load_txt_sources([])

    @staticmethod
    def _tokens_from_spacy_sentence(sent) -> list[dict[str, object]]:
        toks: list[dict[str, object]] = []
        sent_start = int(getattr(sent, "start", 0))
        for i, tok in enumerate(sent, start=1):
            head = 0
            try:
                if tok.head.i != tok.i:
                    head = int(tok.head.i - sent_start + 1)
            except Exception:
                head = 0
            toks.append(
                {
                    "id": i,
                    "form": str(tok.text or "_"),
                    "lemma": str(getattr(tok, "lemma_", "_") or "_"),
                    "upos": str(getattr(tok, "pos_", "_") or "_"),
                    "head": head,
                    "deprel": str(getattr(tok, "dep_", "_") or "_"),
                }
            )
        return toks

    @staticmethod
    def _tokens_from_stanza_sentence(sent) -> list[dict[str, object]]:
        toks: list[dict[str, object]] = []
        for w in list(getattr(sent, "words", []) or []):
            toks.append(
                {
                    "id": int(getattr(w, "id", 0) or 0),
                    "form": str(getattr(w, "text", "_") or "_"),
                    "lemma": str(getattr(w, "lemma", "_") or "_"),
                    "upos": str(getattr(w, "upos", "_") or "_"),
                    "head": int(getattr(w, "head", 0) or 0),
                    "deprel": str(getattr(w, "deprel", "_") or "_"),
                }
            )
        return toks

    @staticmethod
    def _tokens_to_conllu(sent_id: int, text: str, tokens: list[dict[str, object]]) -> str:
        lines = [f"# sent_id = {sent_id}", f"# text = {text}"]
        for tok in tokens:
            i = int(tok.get("id", 0) or 0)
            form = str(tok.get("form", "_")).replace("\t", " ")
            lemma = str(tok.get("lemma", "_")).replace("\t", " ")
            upos = str(tok.get("upos", "_"))
            head = int(tok.get("head", 0) or 0)
            deprel = str(tok.get("deprel", "_"))
            lines.append(f"{i}\t{form}\t{lemma}\t{upos}\t_\t_\t{head}\t{deprel}\t_\t_")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _clean_text(text: str) -> str:
        s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = []
        for ln in s.split("\n"):
            ln2 = re.sub(r"\s+", " ", ln).strip()
            if ln2:
                lines.append(ln2)
        return "\n".join(lines).strip()

    def _cache_key(self, backend: str, lang: str, model_name: str) -> str:
        return f"{backend}:{lang}:{model_name}"

    @staticmethod
    def _find_spacy_model_dir(base_dir: Path) -> Path | None:
        # spaCy model can be either:
        # 1) direct directory containing config.cfg
        # 2) package-like directory with nested `<name>-<version>/config.cfg`
        if (base_dir / "config.cfg").exists():
            return base_dir
        try:
            for child in base_dir.iterdir():
                if child.is_dir() and (child / "config.cfg").exists():
                    return child
        except Exception:
            return None
        return None

    def _load_pipeline(self, backend: str, lang: str, model_name: str):
        key = self._cache_key(backend, lang, model_name)
        if key in self._pipeline_cache:
            return self._pipeline_cache[key]
        if backend == "spacy":
            spacy_mod = _ensure_spacy()
            if spacy_mod is None:
                reason = str(_spacy_import_error or "").strip()
                raise RuntimeError(
                    "spaCy runtime is unavailable. Install or import Parser Runtime first."
                    + (f"\nReason: {reason}" if reason else "")
                )
            lang_l = str(lang or "").strip().lower()
            model_l = str(model_name or "").strip().lower()
            if lang_l.startswith("zh") or model_l.startswith("zh_"):
                ok, reason = _ensure_spacy_zh_runtime()
                if not ok:
                    raise RuntimeError(reason or "Chinese spaCy runtime is unavailable (spacy_pkuseg).")
            local_model_dir = self._spacy_root / lang / model_name
            if local_model_dir.exists():
                resolved_dir = self._find_spacy_model_dir(local_model_dir)
                if resolved_dir is None:
                    raise RuntimeError(
                        f"spaCy local model is missing config.cfg: {local_model_dir}"
                    )
                nlp = spacy_mod.load(str(resolved_dir))
            else:
                nlp = spacy_mod.load(model_name)
            self._pipeline_cache[key] = nlp
            return nlp
        if backend == "stanza":
            st_mod = _ensure_stanza()
            if st_mod is None:
                reason = str(_stanza_import_error or "").strip()
                if reason:
                    raise RuntimeError(f"stanza is unavailable: {reason}")
                raise RuntimeError("stanza is unavailable. Please install stanza.")
            raw_lang = lang.strip().lower()
            stanza_lang = "zh-hans" if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} else raw_lang
            package = model_name.strip().lower()
            if raw_lang == "en" and package in {"", "en", "default"}:
                package = "combined"
            if raw_lang in {"zh", "zh-cn", "chinese", "中文", "汉语"} and package in {"", "zh", "zh-hans", "default"}:
                package = "gsdsimp"
            kwargs = {
                "lang": stanza_lang,
                "processors": "tokenize,pos,lemma,depparse",
                "verbose": False,
                "dir": str(self._stanza_root),
            }
            if package:
                kwargs["package"] = package
            nlp = st_mod.Pipeline(**kwargs)
            self._pipeline_cache[key] = nlp
            return nlp
        raise RuntimeError(f"Unsupported backend: {backend}")

    @staticmethod
    def _to_conllu_from_spacy(nlp, text: str) -> str:
        doc = nlp(text)
        sents = list(doc.sents) if hasattr(doc, "sents") else []
        if not sents:
            sents = [doc[:]]
        chunks: list[str] = []
        sid = 1
        for sent in sents:
            raw_text = str(sent.text).strip()
            if not raw_text:
                continue
            chunks.append(f"# sent_id = {sid}")
            chunks.append(f"# text = {raw_text}")
            sent_start = int(getattr(sent, "start", 0))
            for i, tok in enumerate(sent, start=1):
                head = 0
                try:
                    if tok.head.i != tok.i:
                        head = int(tok.head.i - sent_start + 1)
                except Exception:
                    head = 0
                form = str(tok.text or "_").replace("\t", " ")
                lemma = str(getattr(tok, "lemma_", "_") or "_").replace("\t", " ")
                upos = str(getattr(tok, "pos_", "_") or "_")
                xpos = str(getattr(tok, "tag_", "_") or "_")
                deprel = str(getattr(tok, "dep_", "_") or "_")
                chunks.append(f"{i}\t{form}\t{lemma}\t{upos}\t{xpos}\t_\t{head}\t{deprel}\t_\t_")
            chunks.append("")
            sid += 1
        return "\n".join(chunks).strip() + ("\n" if chunks else "")

    @staticmethod
    def _to_conllu_from_stanza(nlp, text: str) -> str:
        doc = nlp(text)
        chunks: list[str] = []
        sid = 1
        for sent in getattr(doc, "sentences", []):
            words = list(getattr(sent, "words", []) or [])
            if not words:
                continue
            raw_text = str(getattr(sent, "text", "") or "").strip()
            chunks.append(f"# sent_id = {sid}")
            chunks.append(f"# text = {raw_text}")
            for w in words:
                wid = int(getattr(w, "id", 0) or 0)
                form = str(getattr(w, "text", "_") or "_").replace("\t", " ")
                lemma = str(getattr(w, "lemma", "_") or "_").replace("\t", " ")
                upos = str(getattr(w, "upos", "_") or "_")
                xpos = str(getattr(w, "xpos", "_") or "_")
                head = int(getattr(w, "head", 0) or 0)
                deprel = str(getattr(w, "deprel", "_") or "_")
                chunks.append(f"{wid}\t{form}\t{lemma}\t{upos}\t{xpos}\t_\t{head}\t{deprel}\t_\t_")
            chunks.append("")
            sid += 1
        return "\n".join(chunks).strip() + ("\n" if chunks else "")

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.syntax_load_btn.setEnabled(not busy)
        self.syntax_run_btn.setEnabled(not busy)
        if text:
            self.syntax_status.setText(text)
            self.message.emit(text)

    def _start_task(self, kind: str) -> None:
        if self._task_thread is not None and self._task_thread.is_alive():
            self.message.emit("Parser task is already running...")
            return
        backend = self.syntax_backend_combo.currentText().strip().lower()
        lang = str(self.syntax_lang_combo.currentData() or "en").strip().lower()
        model_name = self._model_text()
        if not model_name:
            _show_warning_dialog(self, "Parser", "Model name is required.")
            return
        selected_for_parse = self._get_parse_sentences_for_selected_txt() if kind == "parse" else []
        if kind == "parse" and not selected_for_parse:
            _show_warning_dialog(self, "Parser", "Input text is empty.")
            return
        self._task_token += 1
        token = self._task_token
        self._set_busy(True, "Loading model..." if kind == "load" else "Parsing text to CoNLL-U...")

        def _worker() -> None:
            try:
                nlp = self._load_pipeline(backend, lang, model_name)
                if kind == "load":
                    payload = {"token": token, "ok": True, "kind": "load", "text": f"Model loaded: {backend}/{model_name}"}
                    self._task_done.emit(payload)
                    return
                parsed: list[dict[str, object]] = []
                conllu_chunks: list[str] = []
                for i, pair in enumerate(selected_for_parse[: self.MAX_SENTENCES], start=1):
                    src, s = pair
                    if backend == "spacy":
                        doc = nlp(s)
                        sents = list(doc.sents) if hasattr(doc, "sents") else []
                        if not sents:
                            sents = [doc[:]]
                        sent_obj = sents[0]
                        tokens = self._tokens_from_spacy_sentence(sent_obj)
                    else:
                        doc = nlp(s)
                        sents = list(getattr(doc, "sentences", []) or [])
                        if not sents:
                            continue
                        tokens = self._tokens_from_stanza_sentence(sents[0])
                    parsed.append({"text": s, "tokens": tokens, "source_path": src, "origin": "parsed", "sent_idx": i})
                    conllu_chunks.append(self._tokens_to_conllu(i, s, tokens))
                payload = {
                    "token": token,
                    "ok": True,
                    "kind": "parse",
                    "text": f"Parsed with {backend}/{model_name}",
                    "parsed": parsed,
                    "conllu": "\n".join(conllu_chunks).strip() + ("\n" if conllu_chunks else ""),
                }
                self._task_done.emit(payload)
            except Exception as exc:
                self._task_done.emit({"token": token, "ok": False, "kind": kind, "error": str(exc)})

        self._task_thread = threading.Thread(target=_worker, daemon=True)
        self._task_thread.start()

    def _on_task_done(self, payload: object) -> None:
        self._set_busy(False)
        if not isinstance(payload, dict):
            self.syntax_status.setText("Parser task failed.")
            self.message.emit("Parser task failed.")
            return
        if int(payload.get("token", -1)) != self._task_token:
            return
        ok = bool(payload.get("ok", False))
        kind = str(payload.get("kind", "") or "")
        if not ok:
            err = str(payload.get("error", "unknown error"))
            _show_warning_dialog(self, "Parser failed", err)
            self.syntax_status.setText(f"Failed: {err}")
            self.message.emit(f"Parser failed: {err}")
            return
        info = str(payload.get("text", "Done"))
        if kind == "parse":
            self._parsed_sentences = list(payload.get("parsed", []) or [])
            self._all_conllu = str(payload.get("conllu", ""))
            self._write_parser_cache()
            self._current_page = 0
            self._current_index = -1
            self._refresh_treebank_choices()
            self._apply_sentence_search()
        self.syntax_status.setText(info)
        self.message.emit(info)

    def _on_load_model_clicked(self) -> None:
        self._start_task("load")

    def _on_run_clicked(self) -> None:
        self._start_task("parse")

    def _on_save_clicked(self) -> None:
        text = str(self._all_conllu or "").strip()
        if not text:
            _show_info_dialog(self, "Parser", "No CoNLL-U output to save.")
            return
        out_path, _ = _themed_get_save_file_name(self, "Save CoNLL-U", "syntax_output.conllu", "CoNLL-U (*.conllu)")
        if not out_path:
            return
        out_file = Path(out_path)
        if out_file.suffix.lower() != ".conllu":
            out_file = out_file.with_suffix(".conllu")
        out_file.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        self.syntax_status.setText(f"Saved: {out_file}")
        self.message.emit(f"Saved: {out_file}")

    def _write_parser_cache(self) -> None:
        try:
            text = str(self._all_conllu or "")
            self._parser_cache_file.write_text(text, encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _normalize_query(v: str) -> str:
        s = str(v or "").strip()
        return "" if s.lower() in {"", "all"} else s.lower()

    def _load_external_sentences_for_source(self, source: str) -> list[dict[str, object]]:
        src = str(source or "imported")
        if src in self._external_source_cache:
            return list(self._external_source_cache[src])
        out: list[dict[str, object]] = []
        files: list[Path] = []
        if src == "imported":
            files = list(self._imported_treebanks)
        elif src == "converted":
            for p in self._converted_treebank_cache.values():
                pp = Path(p)
                if pp.exists():
                    files.append(pp)
        if conllu_parse_incr is None:
            self._external_source_cache[src] = []
            return []
        for fp in files:
            try:
                with fp.open("r", encoding="utf-8", errors="ignore") as f:
                    for idx, sent in enumerate(conllu_parse_incr(f), start=1):
                        toks: list[dict[str, object]] = []
                        for tok in list(sent):
                            tid = tok.get("id")
                            if not isinstance(tid, int):
                                continue
                            toks.append(
                                {
                                    "id": int(tid),
                                    "form": str(tok.get("form", "_") or "_"),
                                    "lemma": str(tok.get("lemma", "_") or "_"),
                                    "upos": str(tok.get("upos", "_") or "_"),
                                    "head": int(tok.get("head", 0) or 0),
                                    "deprel": str(tok.get("deprel", "_") or "_"),
                                }
                            )
                        text = str(sent.metadata.get("text", "") if hasattr(sent, "metadata") else "").strip()
                        if not text:
                            text = " ".join([str(t.get("form", "")) for t in toks]).strip()
                        out.append(
                            {
                                "text": text,
                                "tokens": toks,
                                "origin": src,
                                "treebank": fp.stem,
                                "source_path": str(fp.resolve()),
                                "sent_idx": idx,
                            }
                        )
            except Exception:
                continue
        self._external_source_cache[src] = list(out)
        return out

    def _refresh_treebank_choices(self) -> None:
        source = str(self.syntax_search_source_combo.currentText() or "parsed").strip().lower()
        self.syntax_search_treebank_combo.blockSignals(True)
        self.syntax_search_treebank_combo.clear()
        self.syntax_search_treebank_combo.addItem("all", "__all__")
        names: list[str] = []
        if source == "parsed":
            for s in self._txt_source_order:
                names.append(Path(s).stem)
        elif source == "imported":
            names = [p.stem for p in self._imported_treebanks]
        elif source == "converted":
            names = [Path(p).stem for p in self._converted_treebank_cache.values() if Path(p).exists()]
        seen: set[str] = set()
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            self.syntax_search_treebank_combo.addItem(n, n)
        self.syntax_search_treebank_combo.blockSignals(False)

    def _apply_sentence_search(self) -> None:
        source = str(self.syntax_search_source_combo.currentText() or "parsed").strip().lower()
        treebank = str(self.syntax_search_treebank_combo.currentData() or "__all__")
        q_form = self._normalize_query(self.syntax_search_form.text())
        q_lemma = self._normalize_query(self.syntax_search_lemma.text())
        q_upos = self._normalize_query(self.syntax_search_upos.text())
        q_deprel = self._normalize_query(self.syntax_search_deprel.text())

        if source == "parsed":
            base = list(self._parsed_sentences)
            for i, s in enumerate(base, start=1):
                if "treebank" not in s:
                    sp = str(s.get("source_path", "") or "")
                    s["treebank"] = Path(sp).stem if sp else "parsed"
                    s["origin"] = "parsed"
                    s["sent_idx"] = i
        else:
            base = self._load_external_sentences_for_source(source)

        def _sent_match(sent: dict[str, object]) -> bool:
            if treebank != "__all__" and str(sent.get("treebank", "")) != treebank:
                return False
            toks = list(sent.get("tokens", []) or [])
            if not any([q_form, q_lemma, q_upos, q_deprel]):
                return True
            for t in toks:
                form = str(t.get("form", "")).lower()
                lemma = str(t.get("lemma", "")).lower()
                upos = str(t.get("upos", "")).lower()
                deprel = str(t.get("deprel", "")).lower()
                if q_form and q_form not in form:
                    continue
                if q_lemma and q_lemma not in lemma:
                    continue
                if q_upos and q_upos not in upos:
                    continue
                if q_deprel and q_deprel not in deprel:
                    continue
                return True
            return False

        self._view_sentences = [s for s in base if _sent_match(s)][: self.MAX_SENTENCES]
        self._current_page = 0
        self._current_index = -1
        self._refresh_sentence_page()

    def _select_sentence_by_global_index(self, gidx: int) -> None:
        total = len(self._view_sentences)
        if total <= 0:
            return
        gidx = max(0, min(total - 1, int(gidx)))
        pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._current_page = max(0, min(pages - 1, gidx // self.PAGE_SIZE))
        self._refresh_sentence_page()
        local = gidx - self._current_page * self.PAGE_SIZE
        if 0 <= local < self.syntax_sentence_list.count():
            self.syntax_sentence_list.setCurrentRow(local)
            self._on_sentence_selected(self.syntax_sentence_list.currentItem())

    def _navigate_sentence(self, delta: int) -> None:
        total = len(self._view_sentences)
        if total <= 0:
            return
        base = self._current_index if self._current_index >= 0 else 0
        self._select_sentence_by_global_index(base + int(delta))

    def _refresh_sentence_page(self) -> None:
        self.syntax_sentence_list.clear()
        total = len(self._view_sentences)
        if total <= 0:
            self.syntax_page_info.setText("Page 0/0")
            self._render_no_graph("No parsed sentence.")
            self._current_index = -1
            return
        pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._current_page = max(0, min(pages - 1, self._current_page))
        start = self._current_page * self.PAGE_SIZE
        end = min(total, start + self.PAGE_SIZE)
        for i in range(start, end):
            sent = self._view_sentences[i]
            text = str(sent.get("text", "")).strip()
            tb = str(sent.get("treebank", ""))
            prefix = f"[{tb}] " if tb else ""
            it = QListWidgetItem(f"#{i+1} {prefix}{text}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.syntax_sentence_list.addItem(it)
        self.syntax_page_info.setText(f"Page {self._current_page+1}/{pages}")
        if self.syntax_sentence_list.count() <= 0:
            return
        if self._current_index < start or self._current_index >= end:
            self._current_index = start
        local = self._current_index - start
        if local < 0 or local >= self.syntax_sentence_list.count():
            local = 0
            self._current_index = start
        self.syntax_sentence_list.setCurrentRow(local)
        self._on_sentence_selected(self.syntax_sentence_list.currentItem())

    def _on_sentence_selected(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        idx = int(item.data(Qt.ItemDataRole.UserRole) or -1)
        if idx < 0 or idx >= len(self._view_sentences):
            return
        self._current_index = idx
        payload = self._view_sentences[idx]
        self._render_editable_graph(payload, idx + 1)

    def _render_no_graph(self, msg: str) -> None:
        if self.syntax_graph_web is not None:
            self.syntax_graph_web.setHtml(
                f"<html><body style='margin:0;padding:16px;background:#ffffff;color:#333;font-family:Segoe UI'>{html.escape(msg)}</body></html>"
            )
        elif self.syntax_graph_fallback is not None:
            self.syntax_graph_fallback.setPlainText(msg)

    def _render_editable_graph(self, payload: dict[str, object], sent_idx: int) -> None:
        tokens = list(payload.get("tokens", []) or [])
        text = str(payload.get("text", "") or "")
        shown_idx = int(payload.get("sent_idx", sent_idx) or sent_idx)
        if self.syntax_graph_web is None:
            self._render_no_graph("QWebEngineView is unavailable.")
            return
        data = json.dumps({"tokens": tokens, "text": text, "sent_idx": shown_idx}, ensure_ascii=False)
        html_doc = f"""
<html>
<body style="margin:0;background:#ffffff;color:#222;font-family:'Segoe UI';">
<div style="padding:8px 12px;font-weight:600;">Sentence #{shown_idx}</div>
<div style="padding:0 12px 8px 12px;color:#555;">{html.escape(text)}</div>
<div id="wrap" style="padding:6px 8px 10px 8px;">
  <svg id="svg" width="1600" height="520" style="border:1px solid #d3d9e3;background:#fff;"></svg>
</div>
<div id="menu" style="display:none;position:fixed;z-index:9999;background:#fff;border:1px solid #c7cfda;border-radius:6px;box-shadow:0 8px 20px rgba(0,0,0,.12);padding:4px;">
  <div class="mi" data-act="delete" style="padding:6px 10px;cursor:pointer;">Delete edge (Del)</div>
  <div class="mi" data-act="relink" style="padding:6px 10px;cursor:pointer;">Reconnect edge (R)</div>
  <div class="mi" data-act="reverse" style="padding:6px 10px;cursor:pointer;">Reverse direction (V)</div>
</div>
<script>
const state = {data};
let selectedEdge = null;
let selectedNode = null;
const svg = document.getElementById('svg');
const menu = document.getElementById('menu');
function esc(s) {{
  return String(s ?? '');
}}
function buildEdges() {{
  const e = [];
  for (const t of state.tokens) {{
    const id = Number(t.id||0), h = Number(t.head||0);
    if (id>0 && h>0) e.push({{head:h, dep:id, deprel:String(t.deprel||'_')}});
  }}
  return e;
}}
function setHead(dep, head) {{
  for (const t of state.tokens) {{
    if (Number(t.id||0)===Number(dep)) {{
      t.head = Number(head||0);
      return;
    }}
  }}
}}
function notifyUpdate() {{
  try {{
    const payload = encodeURIComponent(JSON.stringify(state.tokens));
    document.title = 'QS_EDIT:' + payload;
  }} catch (e) {{}}
}}
function getToken(id) {{
  return state.tokens.find(t=>Number(t.id||0)===Number(id));
}}
function draw() {{
  const toks = [...state.tokens].sort((a,b)=>Number(a.id)-Number(b.id));
  const edges = buildEdges();
  const left = 70, unit = 110, baseY = 320;
  const x = new Map();
  toks.forEach((t,i)=>x.set(Number(t.id), left+i*unit));
  const parts = [];
  parts.push('<defs><marker id="arr" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M1,1 L9,4 L1,7 L3.6,4 Z" fill="none" stroke="context-stroke" stroke-width="1.2"/></marker></defs>');
  const formY=baseY, lemmaY=baseY+18, uposY=baseY+36, idY=baseY+54;
  for (const t of toks) {{
    const tid = Number(t.id), tx = x.get(tid);
    const cls = selectedNode===tid ? 'node sel' : 'node';
    parts.push(`<text class="${{cls}}" data-node="${{tid}}" x="${{tx}}" y="${{formY}}" text-anchor="middle" font-size="16" fill="#111">${{esc(t.form||'_')}}</text>`);
    parts.push(`<text x="${{tx}}" y="${{lemmaY}}" text-anchor="middle" font-size="13" fill="#111">${{esc(t.lemma||'_')}}</text>`);
    parts.push(`<text x="${{tx}}" y="${{uposY}}" text-anchor="middle" font-size="13" fill="#223">${{esc(t.upos||'_')}}</text>`);
    parts.push(`<text x="${{tx}}" y="${{idY}}" text-anchor="middle" font-size="12" fill="#223">${{tid}}</text>`);
  }}
  let lane=0;
  for (const e of edges) {{
    const xh = x.get(Number(e.head)), xd = x.get(Number(e.dep));
    if (xh==null || xd==null) continue;
    const d = Math.abs(xd-xh);
    const h = 30 + (lane%6)*14 + d*0.13;
    const c1x = xh + (xd-xh)*0.12, c2x = xh + (xd-xh)*0.88, cy = baseY-h;
    const isSel = selectedEdge && Number(selectedEdge.head)===Number(e.head) && Number(selectedEdge.dep)===Number(e.dep);
    const stroke = isSel ? '#f59e0b' : '#5f86b8';
    parts.push(`<path class="edge" data-head="${{e.head}}" data-dep="${{e.dep}}" data-deprel="${{esc(e.deprel)}}" d="M ${{xh}} ${{baseY}} C ${{c1x}} ${{cy}}, ${{c2x}} ${{cy}}, ${{xd}} ${{baseY}}" fill="none" stroke="${{stroke}}" stroke-width="${{isSel?2.6:1.8}}" marker-end="url(#arr)"></path>`);
    const lx=(xh+xd)/2, ly=cy-2;
    parts.push(`<text x="${{lx}}" y="${{ly}}" text-anchor="middle" font-size="13" fill="#c43f3f">${{esc(e.deprel)}}</text>`);
    lane++;
  }}
  svg.innerHTML = parts.join('');
  bindEvents();
}}
function hideMenu() {{
  menu.style.display='none';
}}
function showMenu(x,y) {{
  menu.style.left = x+'px';
  menu.style.top = y+'px';
  menu.style.display = 'block';
}}
function bindEvents() {{
  svg.querySelectorAll('.node').forEach(n=>{{
    n.addEventListener('click', ev=>{{
      ev.stopPropagation();
      selectedNode = Number(n.getAttribute('data-node')||0);
      draw();
    }});
  }});
  svg.querySelectorAll('.edge').forEach(p=>{{
    p.addEventListener('click', ev=>{{
      ev.stopPropagation();
      selectedEdge = {{
        head:Number(p.getAttribute('data-head')||0),
        dep:Number(p.getAttribute('data-dep')||0),
        deprel:String(p.getAttribute('data-deprel')||'_')
      }};
      draw();
    }});
    p.addEventListener('contextmenu', ev=>{{
      ev.preventDefault();
      selectedEdge = {{
        head:Number(p.getAttribute('data-head')||0),
        dep:Number(p.getAttribute('data-dep')||0),
        deprel:String(p.getAttribute('data-deprel')||'_')
      }};
      draw();
      showMenu(ev.clientX, ev.clientY);
    }});
  }});
}}
function deleteSelected() {{
  if (!selectedEdge) return;
  setHead(selectedEdge.dep, 0);
  selectedEdge = null;
  notifyUpdate();
  draw();
}}
function reverseSelected() {{
  if (!selectedEdge) return;
  const h = Number(selectedEdge.head), d = Number(selectedEdge.dep);
  setHead(d, 0);
  setHead(h, d);
  selectedEdge = {{head:d, dep:h, deprel:selectedEdge.deprel}};
  notifyUpdate();
  draw();
}}
function relinkSelected() {{
  if (!selectedEdge) return;
  const v = prompt('New head id for dep='+selectedEdge.dep, String(selectedNode||selectedEdge.head||0));
  if (v===null) return;
  const n = Number(v);
  if (!Number.isFinite(n) || n<0) return;
  setHead(selectedEdge.dep, n);
  selectedEdge.head = n;
  notifyUpdate();
  draw();
}}
menu.querySelectorAll('.mi').forEach(m=>{{
  m.addEventListener('click', ()=>{{
    const a = m.getAttribute('data-act');
    if (a==='delete') deleteSelected();
    if (a==='reverse') reverseSelected();
    if (a==='relink') relinkSelected();
    hideMenu();
  }});
}});
document.addEventListener('click', ()=>{{ hideMenu(); selectedEdge=null; draw(); }});
document.addEventListener('keydown', ev=>{{
  if (ev.key==='Delete') {{ deleteSelected(); ev.preventDefault(); }}
  if (ev.key==='r' || ev.key==='R') {{ relinkSelected(); ev.preventDefault(); }}
  if (ev.key==='v' || ev.key==='V') {{ reverseSelected(); ev.preventDefault(); }}
}});
draw();
</script>
</body>
</html>
"""
        self.syntax_graph_web.setHtml(html_doc)

    def _rebuild_all_conllu_from_parsed(self) -> str:
        chunks: list[str] = []
        for i, sent in enumerate(self._parsed_sentences, start=1):
            chunks.append(self._tokens_to_conllu(i, str(sent.get("text", "")), list(sent.get("tokens", []) or [])))
        return "\n".join(chunks).strip() + ("\n" if chunks else "")

    def _on_graph_title_changed(self, title: str) -> None:
        raw = str(title or "")
        if not raw.startswith("QS_EDIT:"):
            return
        if self._current_index < 0 or self._current_index >= len(self._view_sentences):
            return
        enc = raw[len("QS_EDIT:") :]
        try:
            decoded = urllib.parse.unquote(enc)
            tokens = json.loads(decoded)
        except Exception:
            return
        if not isinstance(tokens, list):
            return
        # Update current visible sentence tokens.
        self._view_sentences[self._current_index]["tokens"] = tokens
        current = self._view_sentences[self._current_index]
        # If this sentence belongs to parsed source, synchronize back to parsed cache.
        if str(current.get("origin", "")) == "parsed":
            sidx = int(current.get("sent_idx", 0) or 0)
            if sidx > 0 and sidx <= len(self._parsed_sentences):
                self._parsed_sentences[sidx - 1]["tokens"] = tokens
                self._all_conllu = self._rebuild_all_conllu_from_parsed()
        else:
            self._all_conllu = self._tokens_to_conllu(
                int(current.get("sent_idx", 1) or 1),
                str(current.get("text", "")),
                list(tokens),
            )
        self._write_parser_cache()
        self.syntax_status.setText("Dependency edges updated and cached.")
        self.message.emit("Dependency edges updated and cached.")


class PlaceholderPage(QWidget):
    def __init__(self, title: str, desc: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        t = QLabel(title)
        t.setObjectName("panelTitle")
        d = QLabel(desc)
        d.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(d)
        layout.addStretch(1)


class StartPage(QWidget):
    @staticmethod
    def _papers_text_en() -> str:
        return (
            "Cite us:\n"
            "Yang, M., & Liu, H. (2025). QuanSyn: A Package for Quantitative Syntax Analysis. "
            "Journal of Quantitative Linguistics, 32(2), 181-198.\n\n"
            "Dependency Distance Minimization:\n"
            "Hudson, R. (1995). Measuring syntactic difficulty. Unpublished. "
            "https://www.dickhudson.com/wp-content/uploads/2013/07/Difficulty.pdf\n\n"
            "Using real corpora to confirm DDM:\n"
            "Ferrer-i-Cancho, R. (2004). Euclidean distance between syntactically linked words. "
            "Physical Review E, 70(5), 056135.\n\n"
            "First large-scale cross-linguistic treebank evidence for DDM:\n"
            "Liu, H. (2008). Dependency Distance as a Metric of Language Comprehension Difficulty. "
            "The Journal of Cognitive Science, 9, 159-191.\n\n"
            "Dependency direction as a new indicator for word-order typology:\n"
            "Liu, H. (2010). Dependency direction as a means of word-order typology: "
            "A method based on dependency treebanks. Lingua, 120, 1567-1578.\n\n"
            "DDM review:\n"
            "Liu, H., Xu, C., & Liang, J. (2017). Dependency distance: A new perspective on syntactic patterns in "
            "natural languages. Physics of life reviews, 21, 171-193.\n"
            "Temperley, D., & Gildea, D. (2018). Minimizing syntactic dependency lengths: Typological/cognitive "
            "universal?. Annual Review of Linguistics, 4, 67-80.\n"
            "Futrell, R., Levy, R. P., & Gibson, E. (2020). Dependency locality as an explanatory principle for word "
            "order. Language, 96(2), 371-412."
        )

    @staticmethod
    def _papers_text_zh() -> str:
        return (
            "引用我们：\n"
            "Yang, M., & Liu, H. (2025). QuanSyn: A Package for Quantitative Syntax Analysis. "
            "Journal of Quantitative Linguistics, 32(2), 181-198.\n\n"
            "依存距离最小化：\n"
            "Hudson, R. (1995). Measuring syntactic difficulty. Unpublished. "
            "https://www.dickhudson.com/wp-content/uploads/2013/07/Difficulty.pdf\n\n"
            "真实语料验证 DDM：\n"
            "Ferrer-i-Cancho, R. (2004). Euclidean distance between syntactically linked words. "
            "Physical Review E, 70(5), 056135.\n\n"
            "大规模跨语言树库验证 DDM：\n"
            "Liu, H. (2008). Dependency Distance as a Metric of Language Comprehension Difficulty. "
            "The Journal of Cognitive Science, 9, 159-191.\n\n"
            "依存方向与语序类型学：\n"
            "Liu, H. (2010). Dependency direction as a means of word-order typology: "
            "A method based on dependency treebanks. Lingua, 120, 1567-1578.\n\n"
            "DDM 综述：\n"
            "Liu, H., Xu, C., & Liang, J. (2017). Dependency distance: A new perspective on syntactic patterns in "
            "natural languages. Physics of life reviews, 21, 171-193.\n"
            "Temperley, D., & Gildea, D. (2018). Minimizing syntactic dependency lengths: Typological/cognitive "
            "universal?. Annual Review of Linguistics, 4, 67-80.\n"
            "Futrell, R., Levy, R. P., & Gibson, E. (2020). Dependency locality as an explanatory principle for word "
            "order. Language, 96(2), 371-412."
        )

    def __init__(self):
        super().__init__()
        self._lang_zh = False
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 4, 8, 12)
        layout.setSpacing(12)

        title = QLabel("")
        title.setObjectName("panelTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-family:'Segoe UI Black','Arial Black','Trebuchet MS'; letter-spacing:0.6px;")
        self.title_label = title
        self.apply_theme("Dark")
        version = QLabel("QuanSyn Studio 0.0.1")
        version.setObjectName("statusInfo")
        subtitle = QLabel("A desktop workspace for quantitative syntax workflow.")
        subtitle.setObjectName("sectionTitle")
        subtitle.setWordWrap(True)
        self.version_label = version
        self.subtitle_label = subtitle
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(subtitle)

        intro = QLabel(
            "QuanSyn is designed for quantitative syntactic analysis, with capabilities for visualization, "
            "statistical analysis, network modeling, and distribution fitting."
        )
        intro.setWordWrap(True)
        self.intro_label = intro
        layout.addWidget(intro)

        papers_title = QLabel("Related Papers / References")
        papers_title.setObjectName("sectionTitle")
        self.papers_title_label = papers_title
        layout.addWidget(papers_title)
        papers = QLabel(self._papers_text_en())
        papers.setOpenExternalLinks(True)
        papers.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        papers.setWordWrap(True)
        self.papers_label = papers
        layout.addWidget(papers)

        developers_title = QLabel("Developers")
        developers_title.setObjectName("sectionTitle")
        self.developers_title_label = developers_title
        layout.addWidget(developers_title)
        developers = QLabel(
            "QuanSyn is led by Mu Yang (Yuhu) and Professor Haitao Liu.\n"
            "GitHub: https://github.com/YuhuYang/QuanSyn\n"
            "PyPI: https://pypi.org/project/quansyn/\n"
            "For any questions, please contact us via GitHub Issues or email: yangmufy@163.com"
        )
        developers.setOpenExternalLinks(True)
        developers.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        developers.setWordWrap(True)
        self.developers_label = developers
        layout.addWidget(developers)

        layout.addStretch(1)
        scroll.setWidget(content)

    def apply_theme(self, theme: str) -> None:
        syn_color = "#000000" if str(theme or "").strip().lower() == "light" else "#ffffff"
        self.title_label.setText(
            "<span style='color:#1f5a47; font-weight:800;'>Quan</span>"
            f"<span style='color:{syn_color}; font-weight:800;'>Syn</span>"
        )

    def apply_language(self, language: str) -> None:
        lang = str(language or "").strip().lower()
        self._lang_zh = lang in {"汉语", "中文", "chinese", "zh", "zh-cn"}
        if self._lang_zh:
            self.subtitle_label.setText("句法计量分析工作台")
            self.intro_label.setText(
                "QuanSyn 专为句法计量分析设计，具备可视化、统计分析、网络建模与分布拟合等功能。"
            )
            self.papers_title_label.setText("相关文献")
            self.papers_label.setText(self._papers_text_zh())
            self.developers_title_label.setText("开发者")
            self.developers_label.setText(
                "QuanSyn 由杨牧与刘海涛教授指导开发。\n"
                "GitHub: https://github.com/YuhuYang/QuanSyn\n"
                "PyPI: https://pypi.org/project/quansyn/\n"
                "如有疑问，请通过 GitHub issue 或邮箱联系：yangmufy@163.com"
            )
        else:
            self.subtitle_label.setText("A desktop workspace for quantitative syntax workflow.")
            self.intro_label.setText(
                "QuanSyn is designed for quantitative syntactic analysis, with capabilities for visualization, "
                "statistical analysis, network modeling, and distribution fitting."
            )
            self.papers_title_label.setText("Related Papers / References")
            self.papers_label.setText(self._papers_text_en())
            self.developers_title_label.setText("Developers")
            self.developers_label.setText(
                "QuanSyn is led by Mu Yang (Yuhu) and Professor Haitao Liu.\n"
                "GitHub: https://github.com/YuhuYang/QuanSyn\n"
                "PyPI: https://pypi.org/project/quansyn/\n"
                "For any questions, please contact us via GitHub Issues or email: yangmufy@163.com"
            )


class BottomStatusBar(QFrame):
    def __init__(self):
        super().__init__()
        self._lang_zh = False
        self._current_module = "home"
        self.setObjectName("bottomStatus")
        self._task_started_at: float | None = None
        self._task_running = False
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed_text)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(10)
        self.project = QLabel("Treebanks: 0")
        self.module = QLabel("Module: home")
        self.language = QLabel("Language: English")
        self.theme = QLabel("Theme: Dark")
        self.font_size = QLabel("Font: 12")
        self.current_treebank = QLabel("Current: -")
        self.progress_text = QLabel("Progress: 0%")
        self.elapsed_text = QLabel("Elapsed: 00:00")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(120)
        self.message = QLabel("Ready.")
        self.message.setObjectName("statusInfo")
        self.note = QLabel("")
        row.addWidget(self.project, 1)
        row.addWidget(self.module, 1)
        row.addWidget(self.language, 1)
        row.addWidget(self.theme, 1)
        row.addWidget(self.font_size, 1)
        row.addWidget(self.current_treebank, 1)
        row.addWidget(self.progress_text, 1)
        row.addWidget(self.elapsed_text, 1)
        row.addWidget(self.progress_bar, 0)
        row.addWidget(self.message, 2)
        row.addWidget(self.note, 1)

    def set_project(self, text: str) -> None:
        self.project.setText(text)

    def set_treebank_count(self, count: int) -> None:
        if self._lang_zh:
            self.project.setText(f"树库数: {count}")
        else:
            self.project.setText(f"Treebanks: {count}")

    def set_module(self, module: str) -> None:
        self._current_module = str(module or "home")
        name_map_en = {
            "home": "home",
            "syntax": "parser",
            "converter": "retrivis",
            "depval": "depval",
            "lingnet": "lingnet",
            "settings": "settings",
            "lawfitter": "depval",
        }
        name_map_zh = {
            "home": "主页",
            "syntax": "句法分析",
            "converter": "检索可视化",
            "depval": "依存计量",
            "lingnet": "句法网络",
            "settings": "设置",
            "lawfitter": "依存计量",
        }
        shown = (name_map_zh if self._lang_zh else name_map_en).get(self._current_module, self._current_module)
        self.module.setText(f"{'模块' if self._lang_zh else 'Module'}: {shown}")

    def set_message(self, msg: str) -> None:
        self.message.setText(_ui_tr(msg))

    def apply_state(self, language: str, theme: str, font_size: int) -> None:
        lang = str(language or "").strip().lower()
        self._lang_zh = lang in {"汉语", "中文", "chinese", "zh", "zh-cn"}
        self.language.setText(f"{'语言' if self._lang_zh else 'Language'}: {language}")
        self.theme.setText(f"{'主题' if self._lang_zh else 'Theme'}: {theme}")
        self.font_size.setText(f"{'字号' if self._lang_zh else 'Font'}: {font_size}")
        self.set_module(self._current_module)
        # Try to preserve current treebank count presentation if parseable.
        m = re.search(r"(\d+)", self.project.text() or "")
        if m:
            try:
                self.set_treebank_count(int(m.group(1)))
            except Exception:
                pass

    def set_note(self, note: str) -> None:
        self.note.setText(note)

    def set_processing(self, treebank: str, percent: int) -> None:
        self.current_treebank.setText(f"{'当前' if self._lang_zh else 'Current'}: {treebank}")
        self.progress_text.setText(f"{'进度' if self._lang_zh else 'Progress'}: {percent}%")
        safe_percent = max(0, min(100, int(percent)))
        self.progress_bar.setValue(safe_percent)
        self._update_task_runtime_state(safe_percent)

    def _update_task_runtime_state(self, percent: int) -> None:
        if percent <= 0:
            self._task_started_at = time.monotonic()
            self._task_running = True
            self.elapsed_text.setText(f"{'耗时' if self._lang_zh else 'Elapsed'}: 00:00")
            if not self._elapsed_timer.isActive():
                self._elapsed_timer.start()
            return

        if percent >= 100:
            if self._task_running:
                self._task_running = False
                if self._elapsed_timer.isActive():
                    self._elapsed_timer.stop()
                self._refresh_elapsed_text()
            return

        if self._task_started_at is None:
            self._task_started_at = time.monotonic()
        if not self._task_running:
            self._task_running = True
        if not self._elapsed_timer.isActive():
            self._elapsed_timer.start()
        self._refresh_elapsed_text()

    def _refresh_elapsed_text(self) -> None:
        if self._task_started_at is None:
            self.elapsed_text.setText(f"{'耗时' if self._lang_zh else 'Elapsed'}: 00:00")
            return
        elapsed = max(0, int(time.monotonic() - self._task_started_at))
        mm, ss = divmod(elapsed, 60)
        hh, mm = divmod(mm, 60)
        if hh > 0:
            self.elapsed_text.setText(f"{'耗时' if self._lang_zh else 'Elapsed'}: {hh:02d}:{mm:02d}:{ss:02d}")
        else:
            self.elapsed_text.setText(f"{'耗时' if self._lang_zh else 'Elapsed'}: {mm:02d}:{ss:02d}")


class SettingsPage(QWidget):
    settingsChanged = pyqtSignal(str, str, int)
    info = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lang_zh = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self.title_label = QLabel("Settings")
        self.title_label.setObjectName("panelTitle")
        layout.addWidget(self.title_label)

        form = QFormLayout()
        self.form = form
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "汉语"])
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 22)
        self.font_size_spin.setValue(12)
        self.lang_row_label = QLabel("Language")
        self.theme_row_label = QLabel("Theme")
        self.font_row_label = QLabel("Font Size")
        self.form.addRow(self.lang_row_label, self.language_combo)
        self.form.addRow(self.theme_row_label, self.theme_combo)
        self.form.addRow(self.font_row_label, self.font_size_spin)
        layout.addLayout(form)

        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setObjectName("accentButton")
        self.apply_btn.clicked.connect(self._apply)
        layout.addWidget(self.apply_btn, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def _apply(self) -> None:
        language = self.language_combo.currentText()
        theme = self.theme_combo.currentText()
        font_size = int(self.font_size_spin.value())
        self.settingsChanged.emit(language, theme, font_size)
        self.info.emit("设置已应用。" if self._is_zh(language) else "Settings applied.")

    @staticmethod
    def _is_zh(language: str) -> bool:
        return str(language or "").strip().lower() in {"汉语", "中文", "chinese", "zh", "zh-cn"}

    def apply_language(self, language: str) -> None:
        self._lang_zh = self._is_zh(language)
        if self._lang_zh:
            self.title_label.setText("设置")
            self.apply_btn.setText("应用设置")
            self.lang_row_label.setText("语言")
            self.theme_row_label.setText("主题")
            self.font_row_label.setText("字号")
        else:
            self.title_label.setText("Settings")
            self.apply_btn.setText("Apply Settings")
            self.lang_row_label.setText("Language")
            self.theme_row_label.setText("Theme")
            self.font_row_label.setText("Font Size")


class MainWorkspace(QWidget):
    _TEXT_ZH_MAP = {
        "Home": "主页",
        "Parser": "句法分析",
        "Settings": "设置",
        "Apply Settings": "应用设置",
        "Language": "语言",
        "Theme": "主题",
        "Font Size": "字号",
        "Search Settings": "检索设置",
        "Matched Sentences": "匹配句子",
        "matched": "匹配结果",
        "example": "示例",
        "Dependency Tree": "依存树",
        "Load Model": "加载模型",
        "Run -> CoNLL-U": "运行 -> CoNLL-U",
        "Save CoNLL-U": "保存 CoNLL-U",
        "Input Text (.txt content)": "输入文本（.txt 内容）",
        "CoNLL-U Output": "CoNLL-U 输出",
        "Backend": "后端",
        "Model": "模型",
        "Ready.": "就绪。",
        "Visualization Setting": "可视化设置",
        "Metric Selection": "指标选择",
        "Compute": "计算",
        "Run": "运行",
        "Save": "保存",
        "Show": "显示",
        "Plot": "绘图",
        "Import TXT": "导入 TXT",
        "Import TXT File": "导入 TXT 文件",
        "Import TXT Folder": "导入 TXT 文件夹",
        "Clear": "清空",
        "Parser Settings": "句法分析设置",
        "Run Parser": "运行句法分析",
        "Dependency Tree (Editable)": "依存树（可编辑）",
        "Sentences (max 1000)": "句子列表（最多1000）",
        "Prev": "上一页",
        "Next": "下一页",
        "Page 0/0": "页码 0/0",
        "Search": "检索",
        "Source": "来源",
        "Treebank": "树库",
        "Relation": "关系",
        "Directed": "有向",
        "Weighted": "有权",
        "Global": "全局",
        "Node": "节点",
        "Statistics": "统计信息",
        "Network Visualization": "网络可视化",
        "Overall Status": "总状态",
        "Test Status": "检验状态",
        "Statistical Tests": "统计检验",
        "Describe/Test": "描述/检验",
        "Option": "选项",
        "Data A": "数据A",
        "Data B": "数据B",
        "Run Test": "运行检验",
        "Dimension": "维度",
        "Plot type": "图类型",
        "1D mode": "一维模式",
        "frequency": "频数",
        "probability": "概率",
        "histogram": "直方图",
        "line": "折线图",
        "scatter": "散点图",
        "area": "面积图",
        "density": "密度图",
        "boxplot": "箱线图",
        "bar": "柱状图",
        "Draw": "绘制",
        "Open Zoom": "放大查看",
        "Export": "导出",
        "Source mode": "来源模式",
        "Input format": "输入格式",
        "Output format": "输出格式",
        "Format Conversion": "格式转换",
        "Visualization": "可视化",
        "Font size": "字体大小",
        "Token spacing": "字间距",
        "Tree-text gap": "树文间距",
        "Reset Defaults": "恢复默认",
        "Import & parse": "导入与解析",
        "import:": "导入：",
        "txt": "文本",
        "folder": "文件夹",
        "TXT file": "TXT 文件",
        "Level": "层级",
        "Metric": "指标",
        "PVP target": "PVP 目标",
        "PVP label": "PVP 标签",
        "Render": "渲染",
        "Fitter": "拟合",
        "Law": "规律",
        "Variant": "变体",
        "Fit": "拟合",
        "Save Cached": "保存缓存",
        "Save current": "保存当前",
        "Save all": "保存全部",
        "Save plot": "保存图像",
        "Run Convert": "运行转换",
        "Load": "加载",
        "matched": "匹配",
        "example": "示例",
        "Page": "页",
        "Metric Selection": "指标选择",
        "Global Metrics": "全局指标",
        "Local Metrics": "局部指标",
        "Visualization Setting": "可视化设置",
        "Node color": "节点颜色",
        "Edge width": "边宽",
        "Layout": "布局",
        "Show node labels": "显示节点标签",
        "Show weight labels": "显示边权标签",
        "Directed (viz)": "有向（可视化）",
        "Weighted (viz)": "有权（可视化）",
        "spring-out": "弹簧布局",
        "circle": "圆形布局",
        "concentric": "同心布局",
        "grid": "网格布局",
        "auto": "自动",
        "Select TXT File": "选择 TXT 文件",
        "parsed": "parsed",
        "imported": "imported",
        "converted": "converted",
    }

    _PLACEHOLDER_ZH_MAP = {
        "Model name": "模型名称",
        "Model name or local model folder name": "模型名称或本地模型目录名",
        "Paste or type raw text here...": "粘贴或输入原始文本...",
    }

    def __init__(self):
        super().__init__()
        self.imported_treebanks: list[str] = []
        self._import_apply_token = 0
        self._language = "English"

        self.sidebar = IconSidebar()
        self.bottombar = BottomStatusBar()
        self.pages = QStackedWidget()
        self.start_page = StartPage()
        self.converter = ConverterPage()
        self.depval = DepvalPage()
        self.converter.set_converted_treebank_cache(self.depval._converted_treebank_cache)
        self.lingnet = LingnetPage()
        self.lingnet.set_converted_treebank_cache(self.depval._converted_treebank_cache)
        self.lawfitter = PlaceholderPage("Lawfitter", "Reserved module page for law fitting.")
        self.settings_page = SettingsPage()

        self.pages.addWidget(self.start_page)
        self.pages.addWidget(self.converter)
        self.pages.addWidget(self.depval)
        self.pages.addWidget(self.lingnet)
        self.pages.addWidget(self.lawfitter)
        self.pages.addWidget(self.settings_page)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar, 0)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.pages, 1)
        right.addWidget(self.bottombar, 0)
        root.addLayout(right, 1)

        self.sidebar.moduleChanged.connect(self._on_module_changed)
        self.converter.message.connect(self.bottombar.set_message)
        self.depval.message.connect(self.bottombar.set_message)
        self.lingnet.message.connect(self.bottombar.set_message)
        self.depval.processingChanged.connect(self.bottombar.set_processing)
        self.settings_page.info.connect(self.bottombar.set_message)
        self.settings_page.settingsChanged.connect(self._apply_settings)
        self._last_style_key: tuple[str, int, int] | None = None
        self._apply_settings("English", "Dark", 12)
        self._on_module_changed("home")

    @staticmethod
    def _is_zh(language: str) -> bool:
        return str(language or "").strip().lower() in {"汉语", "中文", "chinese", "zh", "zh-cn"}

    def _translate_text(self, text: str, to_zh: bool) -> str:
        src = str(text or "")
        if to_zh:
            return self._TEXT_ZH_MAP.get(src, src)
        rev = {v: k for k, v in self._TEXT_ZH_MAP.items()}
        return rev.get(src, src)

    def _translate_placeholder(self, text: str, to_zh: bool) -> str:
        src = str(text or "")
        if to_zh:
            return self._PLACEHOLDER_ZH_MAP.get(src, src)
        rev = {v: k for k, v in self._PLACEHOLDER_ZH_MAP.items()}
        return rev.get(src, src)

    def _current_screen(self):
        screen = None
        win = self.window()
        try:
            if win is not None and hasattr(win, "screen"):
                screen = win.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                app = QApplication.instance()
                if app is not None:
                    screen = app.primaryScreen()
            except Exception:
                screen = None
        return screen

    def _display_scale_ratio(self) -> float:
        screen = self._current_screen()
        if screen is None:
            return 1.0
        try:
            logical_dpi = float(screen.logicalDotsPerInch())
        except Exception:
            logical_dpi = 96.0
        try:
            dpr = float(screen.devicePixelRatio())
        except Exception:
            dpr = 1.0

        # macOS Retina DPR is pixel density, not the same thing as the user's
        # UI scaling preference. Logical DPI is the better signal there.
        dpi_base = 72.0 if sys.platform == "darwin" else 96.0
        dpi_ratio = logical_dpi / dpi_base if logical_dpi > 0 else 1.0
        if sys.platform == "darwin":
            ratio = dpi_ratio
        else:
            ratio = max(dpi_ratio, dpr)
        return max(1.0, min(2.5, float(ratio)))

    def _compute_ui_scale(self) -> float:
        screen = self._current_screen()
        if screen is None:
            return 1.0
        display_scale = self._display_scale_ratio()
        try:
            ag = screen.availableGeometry()
            gw = max(1, int(ag.width()))
            gh = max(1, int(ag.height()))
        except Exception:
            gw, gh = 1920, 1080

        # Qt reports availableGeometry in logical pixels on HiDPI displays.
        # Convert back to a physical-equivalent size before judging whether
        # the screen itself is small, otherwise 150% scaling gets counted twice.
        physical_w = gw * display_scale
        physical_h = gh * display_scale
        geometry_fit = min(1.0, physical_w / 1600.0, physical_h / 900.0)

        # Use the actual OS scale ratio as the main control. This curve is
        # intentionally gentler than a direct inverse so 125%-175% displays
        # stay readable while still lowering visual density.
        display_fit = 1.0 / (display_scale ** 0.42)
        scale = geometry_fit * display_fit
        return max(0.68, min(1.0, float(scale)))

    def apply_adaptive_ui_scale(self, scale_override: float | None = None) -> None:
        s = float(scale_override) if scale_override is not None else self._compute_ui_scale()
        app = QApplication.instance()
        if app is not None:
            theme = str(getattr(self, "_theme", "Dark") or "Dark")
            font_size = int(getattr(self, "_font_size", 12) or 12)
            style_key = (theme, font_size, int(round(s * 1000)))
            if getattr(self, "_last_style_key", None) != style_key:
                app.setStyleSheet(build_app_style(theme, s, font_size))
                self._last_style_key = style_key
        try:
            win = self.window()
            if win is not None and hasattr(win, "titlebar") and getattr(win, "titlebar") is not None:
                win.titlebar.apply_ui_scale(s)
        except Exception:
            pass
        try:
            self.sidebar.apply_ui_scale(s)
        except Exception:
            pass
        try:
            self.depval.apply_ui_scale(s)
        except Exception:
            pass
        try:
            self.converter.apply_ui_scale(s)
        except Exception:
            pass
        try:
            self.lingnet.apply_ui_scale(s)
        except Exception:
            pass

    def _apply_ui_language(self, language: str) -> None:
        to_zh = self._is_zh(language)
        for lbl in self.findChildren(QLabel):
            try:
                lbl.setText(self._translate_text(lbl.text(), to_zh))
            except Exception:
                pass
        for btn in self.findChildren(QPushButton):
            try:
                btn.setText(self._translate_text(btn.text(), to_zh))
            except Exception:
                pass
        for chk in self.findChildren(QCheckBox):
            try:
                chk.setText(self._translate_text(chk.text(), to_zh))
            except Exception:
                pass
        for combo in self.findChildren(QComboBox):
            try:
                for i in range(combo.count()):
                    combo.setItemText(i, self._translate_text(combo.itemText(i), to_zh))
            except Exception:
                pass
        for edit in self.findChildren(QLineEdit):
            try:
                edit.setPlaceholderText(self._translate_placeholder(edit.placeholderText(), to_zh))
            except Exception:
                pass
        for edit in self.findChildren(QTextEdit):
            try:
                edit.setPlaceholderText(self._translate_placeholder(edit.placeholderText(), to_zh))
            except Exception:
                pass
        for tabs in self.findChildren(QTabWidget):
            try:
                for i in range(tabs.count()):
                    tabs.setTabText(i, self._translate_text(tabs.tabText(i), to_zh))
            except Exception:
                pass

    def set_imported_treebanks(self, paths: list[str]) -> None:
        self.imported_treebanks = sorted(set(paths))
        self.bottombar.set_treebank_count(len(self.imported_treebanks))
        self._import_apply_token += 1
        token = self._import_apply_token
        self.bottombar.set_note("Updating modules..." if self._language.lower() not in {"汉语", "中文", "chinese", "zh", "zh-cn"} else "正在更新模块...")
        QTimer.singleShot(0, lambda: self._apply_imported_treebanks_step(token, 0))

    def _apply_imported_treebanks_step(self, token: int, step: int) -> None:
        if token != self._import_apply_token:
            return
        try:
            if step == 0:
                self.depval.set_imported_treebanks(self.imported_treebanks)
            elif step == 1:
                self.lingnet.set_imported_treebanks(self.imported_treebanks)
            elif step == 2:
                if self.imported_treebanks:
                    self.converter.set_imported_treebanks(self.imported_treebanks)
                self.bottombar.set_note("")
                return
        except Exception:
            if step >= 2:
                self.bottombar.set_note("")
                return
        QTimer.singleShot(0, lambda: self._apply_imported_treebanks_step(token, step + 1))

    def _on_module_changed(self, module: str) -> None:
        idx_map = {"home": 0, "syntax": 1, "converter": 1, "depval": 2, "lingnet": 3, "lawfitter": 2, "settings": 5}
        idx = idx_map[module]
        if module not in {"depval", "lawfitter"}:
            self.depval.collapse_all_drawers()
        self.pages.setCurrentIndex(idx)
        try:
            self.depval.refresh_data_sources()
            self.lingnet.refresh_data_sources()
        except Exception:
            pass
        if module == "lawfitter":
            self.depval.open_lawfitter_drawer()
        self.bottombar.set_module(module)

    def _apply_settings(self, language: str, theme: str, font_size: int) -> None:
        self._language = language
        self._theme = theme
        self._font_size = font_size if isinstance(font_size, int) and font_size > 0 else 12
        set_ui_language(language)
        ui_scale = self._compute_ui_scale()
        app = QApplication.instance()
        if app is not None:
            font = app.font()
            safe_font_size = self._font_size
            scaled_font_size = max(9, int(round(safe_font_size * ui_scale)))
            font.setPointSize(scaled_font_size)
            app.setFont(font)
            app.setProperty("quansyn_theme", "light" if theme == "Light" else "dark")
            app.setStyleSheet(build_app_style(theme, ui_scale, safe_font_size))

        lang = str(language or "").strip().lower()
        is_zh = lang in {"汉语", "中文", "chinese", "zh", "zh-cn"}
        title = "句法计量分析工作台" if is_zh else "QuanSyn Studio"
        win = self.window()
        try:
            if win is not None:
                win.setWindowTitle(title)
                if hasattr(win, "titlebar") and getattr(win, "titlebar") is not None:
                    win.titlebar.title_label.setText(title)
        except Exception:
            pass
        self.sidebar.apply_language(language)
        self.start_page.apply_language(language)
        self.start_page.apply_theme(theme)
        self.settings_page.apply_language(language)
        self._apply_ui_language(language)
        self.apply_adaptive_ui_scale(ui_scale)

        try:
            self.converter.apply_theme_to_view()
        except Exception:
            pass
        self.bottombar.apply_state(language, theme, font_size)
        self.bottombar.set_note("设置已更新" if is_zh else "Settings updated")



