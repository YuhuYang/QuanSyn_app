from __future__ import annotations

import sys
import os
import traceback
import importlib
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from .style import build_app_style


def _startup_log(message: str) -> None:
    try:
        base = Path(sys.executable).resolve().parent if bool(getattr(sys, "frozen", False)) else Path.cwd()
        p = base / "startup.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except Exception:
        pass


def _selftest_log_path() -> Path:
    base = Path(sys.executable).resolve().parent if bool(getattr(sys, "frozen", False)) else Path.cwd()
    return base / "selftest.log"


def _runtime_base_dir() -> Path:
    try:
        if bool(getattr(sys, "frozen", False)):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path.cwd()


def _write_selftest(message: str) -> None:
    try:
        p = _selftest_log_path()
        with p.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass


def _run_selftest(mode: str) -> int:
    m = str(mode or "").strip().lower()
    try:
        if m == "stanza":
            from .ui import widgets as ui_widgets

            st = ui_widgets._ensure_stanza()
            if st is None:
                raise RuntimeError(ui_widgets._stanza_import_error or "stanza runtime unavailable")
            _write_selftest(f"stanza_ok version={getattr(st, '__version__', '?')}")
            return 0
        if m == "spacy":
            from .ui import widgets as ui_widgets

            sp = ui_widgets._ensure_spacy()
            if sp is None:
                raise RuntimeError(ui_widgets._spacy_import_error or "spaCy runtime unavailable")
            _write_selftest(f"spacy_ok version={getattr(sp, '__version__', '?')}")
            return 0
        if m == "networkit":
            from .ui import widgets as ui_widgets

            nk = ui_widgets._ensure_networkit()
            if nk is None:
                raise RuntimeError(ui_widgets._networkit_import_error or "networkit runtime unavailable")
            graph = nk.Graph(3, weighted=False, directed=False)
            graph.addEdge(0, 1)
            graph.addEdge(1, 2)
            cc = nk.components.ConnectedComponents(graph).run().numberOfComponents()
            _write_selftest(
                f"networkit_ok version={getattr(nk, '__version__', '?')} nodes={graph.numberOfNodes()} edges={graph.numberOfEdges()} components={cc}"
            )
            return 0
        if m == "sklearn":
            import sklearn
            from sklearn.metrics import r2_score

            score = r2_score([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
            _write_selftest(f"sklearn_ok version={getattr(sklearn, '__version__', '?')} r2={score:.4f}")
            return 0
        if m == "ui-scale":
            app = QApplication(sys.argv)
            from .ui.widgets import MainWorkspace  # local import

            w = MainWorkspace()
            s = w._compute_ui_scale()  # noqa: SLF001
            display_scale = w._display_scale_ratio()  # noqa: SLF001
            _write_selftest(f"display_scale={display_scale:.4f} ui_scale={s:.4f}")
            app.quit()
            return 0
        _write_selftest(f"unknown_mode={m}")
        return 2
    except Exception:
        _write_selftest("selftest_exception\n" + traceback.format_exc())
        return 1


def _patch_qtwebengine_runtime_env() -> None:
    # In some Nuitka standalone layouts, QtWebEngineProcess.exe is placed in the
    # dist root instead of Qt's default lookup location. Help Qt find it reliably.
    try:
        if not bool(getattr(sys, "frozen", False)):
            return
        exe_dir = Path(sys.executable).resolve().parent
        proc = exe_dir / "QtWebEngineProcess.exe"
        if proc.exists():
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(proc))
    except Exception:
        pass


# Must run before importing modules that may import QtWebEngine.
_patch_qtwebengine_runtime_env()
_startup_log("app.py: env patched")

from .main_window import MainWindow
_startup_log("app.py: MainWindow imported")


def build_app() -> QApplication:
    _startup_log("build_app: begin")
    app = QApplication(sys.argv)
    app.setApplicationName("QuanSyn Studio")
    app.setApplicationVersion("0.0.1")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    icon_candidates = [
        _runtime_base_dir() / "quansyn_desktop" / "assets" / "quansyn_icon.ico",
        _runtime_base_dir() / "quansyn_desktop" / "assets" / "quansyn_icon.png",
        Path(__file__).resolve().parent / "assets" / "quansyn_icon.ico",
        Path(__file__).resolve().parent / "assets" / "quansyn_icon.png",
    ]
    for icon_path in icon_candidates:
        try:
            if icon_path.exists():
                app.setWindowIcon(QIcon(str(icon_path)))
                break
        except Exception:
            pass
    app.setProperty("quansyn_theme", "dark")
    app.setStyleSheet(build_app_style("Dark", 1.0, 12))
    _startup_log("build_app: app created")
    return app


def main() -> int:
    try:
        mode = str(os.environ.get("QUANSYN_SELFTEST", "") or "").strip()
        if mode:
            return _run_selftest(mode)
        _startup_log("main: begin")
        app = build_app()
        _startup_log("main: app built")
        window = MainWindow()
        _startup_log("main: window created")
        window.show()
        _startup_log("main: window shown")
        rc = app.exec()
        _startup_log(f"main: app exec returned {rc}")
        return rc
    except Exception:
        _startup_log("main: exception\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
