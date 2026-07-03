from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, QSize, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QToolButton, QVBoxLayout, QWidget

from .ui.widgets import (
    MainWorkspace,
    clear_all_quansyn_caches,
    fa_icon,
    ui_tr,
)

IMPORTABLE_TREEBANK_SUFFIXES = ("conll", "conllu", "txt")


def _runtime_base_dir() -> Path:
    try:
        if bool(getattr(sys, "frozen", False)):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path.cwd()


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setObjectName("titleBar")
        self.setFixedHeight(42)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)

        # Keep a left icon slot area reserved.
        self.icon_slot = QLabel(self)
        self.icon_slot.setObjectName("titleBarIconSlot")
        self.icon_slot.setFixedWidth(120)
        self.icon_slot.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.icon_slot.clear()
        row.addWidget(self.icon_slot, 0, Qt.AlignmentFlag.AlignLeft)

        self.title_label = QLabel("QuanSyn Studio", self)
        self.title_label.setObjectName("titleBarStudioTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.title_label, 1, Qt.AlignmentFlag.AlignCenter)

        controls_wrap = QWidget(self)
        self.controls_wrap = controls_wrap
        controls_layout = QHBoxLayout(controls_wrap)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.min_btn = QToolButton(self)
        self.min_btn.setObjectName("titleBarControl")
        self._set_icon_or_text(self.min_btn, "minus", "-")
        self.min_btn.clicked.connect(self._window.showMinimized)
        controls_layout.addWidget(self.min_btn, 0, Qt.AlignmentFlag.AlignRight)

        self.max_btn = QToolButton(self)
        self.max_btn.setObjectName("titleBarControl")
        self._set_icon_or_text(self.max_btn, "window-maximize", "[]")
        self.max_btn.clicked.connect(self._toggle_max_restore)
        controls_layout.addWidget(self.max_btn, 0, Qt.AlignmentFlag.AlignRight)

        self.close_btn = QToolButton(self)
        self.close_btn.setObjectName("titleBarClose")
        self._set_icon_or_text(self.close_btn, "xmark", "x")
        self.close_btn.clicked.connect(self._window.close)
        controls_layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignRight)

        controls_wrap.setFixedWidth(120)
        row.addWidget(controls_wrap, 0, Qt.AlignmentFlag.AlignRight)

    def apply_ui_scale(self, scale: float) -> None:
        try:
            s = max(0.58, min(1.0, float(scale)))
        except Exception:
            s = 1.0
        height = max(34, int(round(42 * s)))
        side_w = max(92, int(round(120 * s)))
        icon_size = max(14, int(round(16 * s)))
        self.setFixedHeight(height)
        try:
            self.icon_slot.setFixedWidth(side_w)
        except Exception:
            pass
        try:
            self.controls_wrap.setFixedWidth(side_w)
        except Exception:
            pass
        controls = [self.min_btn, self.max_btn, self.close_btn]
        for btn in controls:
            try:
                btn.setIconSize(QSize(icon_size, icon_size))
                btn.setFixedHeight(max(26, height - 8))
            except Exception:
                pass
        try:
            self.layout().setContentsMargins(6, max(2, int(round(4 * s))), 6, max(2, int(round(4 * s))))
        except Exception:
            pass

    def _set_icon_or_text(self, button: QToolButton, icon_name: str, fallback_text: str) -> None:
        icon = fa_icon(icon_name)
        if icon.isNull():
            button.setText(fallback_text)
        else:
            button.setIcon(icon)

    def _toggle_max_restore(self) -> None:
        if hasattr(self._window, "_maximize_to_workarea"):
            self._window._maximize_to_workarea()
        else:
            self._window.showNormal()
        self._set_icon_or_text(self.max_btn, "clone", "[]")

    def mousePressEvent(self, event) -> None:  # pragma: no cover - UI behavior
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # pragma: no cover - UI behavior
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._window.isMaximized()
            and not self._window.isFullScreen()
        ):
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # pragma: no cover - UI behavior
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # pragma: no cover - UI behavior
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max_restore()
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    _folder_scan_done = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        icon_path = Path(__file__).resolve().parent / "assets" / "quansyn_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowTitle("QuanSyn Studio")
        # Keep a small hard floor; real geometry is adapted to each screen work area.
        self.setMinimumSize(480, 320)
        self.workspace = MainWorkspace()
        self.titlebar = TitleBar(self)
        self.titlebar_separator = QFrame(self)
        self.titlebar_separator.setObjectName("titleBarSeparator")
        self.titlebar_separator.setFrameShape(QFrame.Shape.HLine)
        self.titlebar_separator.setFrameShadow(QFrame.Shadow.Plain)
        shell = QWidget(self)
        shell.setObjectName("windowRoot")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        app_shell = QFrame(shell)
        app_shell.setObjectName("appShell")
        self.app_shell = app_shell
        app_layout = QVBoxLayout(app_shell)
        app_layout.setContentsMargins(0, 0, 0, 0)
        app_layout.setSpacing(0)
        app_layout.addWidget(self.titlebar, 0)
        app_layout.addWidget(self.titlebar_separator, 0)
        app_layout.addWidget(self.workspace, 1)

        shell_layout.addWidget(app_shell, 1)
        self.setCentralWidget(shell)
        self._recent_dir = str(_runtime_base_dir())
        self._folder_scan_token = 0
        self._folder_scan_thread: threading.Thread | None = None
        self.workspace.sidebar.importTreebankRequested.connect(self._import_treebank)
        self.workspace.sidebar.importTreebanksRequested.connect(self._import_treebanks)
        self.workspace.sidebar.aboutRequested.connect(self._open_quansyn_github)
        self._folder_scan_done.connect(self._on_folder_scan_done)
        self._sync_maximized_shell_style()
        QTimer.singleShot(0, self._maximize_to_workarea)

    def changeEvent(self, event) -> None:  # pragma: no cover - UI behavior
        if event.type() == event.Type.WindowStateChange:
            # If any external action tries to enter full/maximized, normalize back.
            if self.isFullScreen() or self.isMaximized():
                QTimer.singleShot(0, self._maximize_to_workarea)
            self._sync_maximized_shell_style()
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # pragma: no cover - UI behavior
        super().showEvent(event)
        self._disable_windows_rounded_corners()
        QTimer.singleShot(0, self._maximize_to_workarea)

    def _disable_windows_rounded_corners(self) -> None:
        try:
            import ctypes  # local import to avoid hard dependency during frozen startup
            hwnd = int(self.winId())
            dwm_attr_corner_pref = 33  # DWMWA_WINDOW_CORNER_PREFERENCE
            corner_do_not_round = 1    # DWMWCP_DONOTROUND
            value = ctypes.c_int(corner_do_not_round)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(dwm_attr_corner_pref),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass

    def _enforce_maximized(self) -> None:
        if self.isMinimized():
            return
        self._maximize_to_workarea()
        if getattr(self, "titlebar", None) is not None:
            self.titlebar._set_icon_or_text(self.titlebar.max_btn, "clone", "[]")

    def _maximize_to_workarea(self) -> None:
        # Keep window in normal state and fill work area (not true maximize/fullscreen).
        if self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
            self.setWindowState(Qt.WindowState.WindowNoState)
        if self.isFullScreen() or self.isMaximized():
            self.showNormal()
        self._apply_workarea_geometry()

    def _screen_workarea(self) -> QRect | None:
        # Use Qt screen work-area only; this stays in the same coordinate space
        # as QWidget geometry and avoids DPI mismatch on different computers.
        screen = self.screen()
        if screen is None and self.windowHandle() is not None:
            screen = self.windowHandle().screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        ag = screen.availableGeometry()
        if ag.width() <= 0 or ag.height() <= 0:
            return None
        return ag

    def _apply_workarea_geometry(self) -> None:
        ag = self._screen_workarea()
        if ag is None:
            return
        target_x = int(ag.x())
        target_y = int(ag.y())
        target_w = max(200, int(ag.width()))
        target_h = max(160, int(ag.height()))
        # Clamp minimum size to the current work area so small/HiDPI screens
        # never force an oversized window that gets clipped off-screen.
        cur_min = self.minimumSize()
        min_w = min(max(200, int(cur_min.width())), target_w)
        min_h = min(max(160, int(cur_min.height())), target_h)
        if min_w != cur_min.width() or min_h != cur_min.height():
            self.setMinimumSize(min_w, min_h)
        g = self.geometry()
        if g.x() == target_x and g.y() == target_y and g.width() == target_w and g.height() == target_h:
            try:
                self.workspace.apply_adaptive_ui_scale()
            except Exception:
                pass
            return
        self.setGeometry(target_x, target_y, target_w, target_h)
        try:
            self.workspace.apply_adaptive_ui_scale()
        except Exception:
            pass

    def _sync_maximized_shell_style(self) -> None:
        if getattr(self, "app_shell", None) is None:
            return
        self.app_shell.setStyleSheet(
            "QFrame#appShell{border-radius:0px; border:none;}"
            "QWidget#titleBar{border-top-left-radius:0px; border-top-right-radius:0px;}"
            "QFrame#iconSidebar{border-bottom-left-radius:0px;}"
            "QFrame#bottomStatus{border-bottom-right-radius:0px;}"
        )


    def _import_treebank(self) -> None:
        if not self._confirm_replace_imported_treebanks():
            return
        filter_text = "Treebank (" + " ".join([f"*.{ext}" for ext in IMPORTABLE_TREEBANK_SUFFIXES]) + ")"
        selected, _ = QFileDialog.getOpenFileName(self, "Import treebank", self._recent_dir, filter_text)
        if not selected:
            return
        self._recent_dir = str(Path(selected).parent)
        self._folder_scan_token += 1
        token = self._folder_scan_token
        self.workspace.bottombar.set_message(ui_tr("Importing treebank in background..."))
        self._folder_scan_thread = threading.Thread(
            target=self._scan_single_treebank_worker,
            args=(token, selected),
            daemon=True,
        )
        self._folder_scan_thread.start()

    def _import_treebanks(self) -> None:
        if not self._confirm_replace_imported_treebanks():
            return
        selected_dir = QFileDialog.getExistingDirectory(self, "Import treebanks from folder", self._recent_dir)
        if not selected_dir:
            return
        self._recent_dir = selected_dir
        self._folder_scan_token += 1
        token = self._folder_scan_token
        self.workspace.bottombar.set_message(ui_tr("Scanning treebank folder in background..."))
        self._folder_scan_thread = threading.Thread(
            target=self._scan_treebank_folder_worker,
            args=(token, selected_dir),
            daemon=True,
        )
        self._folder_scan_thread.start()

    def _scan_treebank_folder_worker(self, token: int, selected_dir: str) -> None:
        root = Path(selected_dir)
        files: list[str] = []
        try:
            suffixes = {f".{ext.lower()}" for ext in IMPORTABLE_TREEBANK_SUFFIXES}
            with os.scandir(root) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    name = entry.name.lower()
                    dot = name.rfind(".")
                    if dot < 0:
                        continue
                    if name[dot:] in suffixes:
                        files.append(str(Path(entry.path)))
            files.sort()
        except Exception:
            files = []
        self._folder_scan_done.emit({"token": token, "files": files})

    def _scan_single_treebank_worker(self, token: int, selected_file: str) -> None:
        files: list[str] = []
        try:
            p = Path(selected_file)
            if p.exists() and p.is_file():
                files = [str(p)]
        except Exception:
            files = []
        self._folder_scan_done.emit({"token": token, "files": files})

    def _on_folder_scan_done(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        token = int(payload.get("token", -1))
        if token != self._folder_scan_token:
            return
        files = payload.get("files", [])
        if not isinstance(files, list):
            files = []
        files = [str(p) for p in files]
        self.workspace.set_imported_treebanks(files)
        self.workspace.bottombar.set_message(ui_tr(f"Imported {len(files)} treebanks."))

    def _open_quansyn_github(self) -> None:
        QDesktopServices.openUrl(QUrl("https://github.com/YuhuYang/QuanSyn"))

    def _confirm_replace_imported_treebanks(self) -> bool:
        current = getattr(self.workspace, "imported_treebanks", [])
        if not current:
            return True
        ret = QMessageBox.question(
            self,
            ui_tr("QuanSyn Studio"),
            ui_tr("Re-import treebanks") + "\n\n" + ui_tr("Treebanks have already been imported. Clear current treebanks and re-import?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ret == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            clear_all_quansyn_caches()
        except Exception:
            pass
        super().closeEvent(event)

