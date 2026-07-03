from __future__ import annotations

import itertools
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .models import AnalysisRequest, AnalysisResult


class AnalysisWorker(QThread):
    progressUpdated = pyqtSignal(str, int)
    finishedResult = pyqtSignal(object)
    failed = pyqtSignal(str)
    logLine = pyqtSignal(str)

    def __init__(self, request: AnalysisRequest, task_id: int):
        super().__init__()
        self.request = request
        self.task_id = task_id
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            phases = [
                ("Loading corpus", 20),
                ("Validating structures", 45),
                ("Computing metrics", 72),
                ("Preparing artifacts", 92),
                ("Finalizing report", 100),
            ]
            logs: list[str] = []
            for phase, pct in phases:
                if self._cancelled:
                    raise RuntimeError("Task cancelled by user.")
                self.logLine.emit(f"[task-{self.task_id}] {phase}...")
                logs.append(f"{phase} completed.")
                self.progressUpdated.emit(phase, pct)
                time.sleep(0.34)

            result = AnalysisResult(
                status="completed",
                summary=(
                    f"{self.request.module} analysis completed with "
                    f"{len(self.request.params)} parameter groups."
                ),
                artifacts=[
                    str(Path(self.request.output_dir) / f"{self.request.module}_summary.csv"),
                    str(Path(self.request.output_dir) / f"{self.request.module}_report.txt"),
                ],
                log_lines=logs,
            )
            self.finishedResult.emit(result)
        except Exception as exc:  # pragma: no cover - Qt thread boundary
            self.failed.emit(str(exc))


class AnalysisController(QObject):
    runRequested = pyqtSignal(object)
    progressUpdated = pyqtSignal(str, int)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    validationChanged = pyqtSignal(bool, str)
    stateChanged = pyqtSignal(str)
    logAppended = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._worker: AnalysisWorker | None = None
        self._task_seq = itertools.count(1)
        self._task_started = 0.0
        self._state = "Idle"
        self.runRequested.connect(self._on_run_requested)

    @property
    def state(self) -> str:
        return self._state

    @property
    def elapsed_seconds(self) -> float:
        if not self._task_started:
            return 0.0
        return max(0.0, time.time() - self._task_started)

    def validate_request(self, request: AnalysisRequest) -> tuple[bool, str]:
        if not request.input_path.strip():
            return False, "Input path is required."
        input_path = Path(request.input_path)
        if not input_path.exists():
            return False, f"Input path does not exist: {request.input_path}"

        if not request.output_dir.strip():
            return False, "Output directory is required."
        output_path = Path(request.output_dir)
        output_parent = output_path.parent if output_path.parent.as_posix() != "" else Path(".")
        if not output_parent.exists():
            return False, f"Output parent does not exist: {output_parent}"

        return True, ""

    def request_validation(self, request: AnalysisRequest) -> bool:
        self._set_state("Validating")
        is_valid, message = self.validate_request(request)
        self.validationChanged.emit(is_valid, message)
        if is_valid:
            self._set_state("Idle")
        else:
            self._set_state("Failed")
        return is_valid

    def cancel_active_run(self) -> None:
        if self._worker and self._worker.isRunning():
            self.logAppended.emit("Cancellation requested...")
            self._worker.cancel()

    def _on_run_requested(self, request: AnalysisRequest) -> None:
        if self._worker and self._worker.isRunning():
            self.failed.emit("A task is already running.")
            return

        is_valid, message = self.validate_request(request)
        self.validationChanged.emit(is_valid, message)
        if not is_valid:
            self._set_state("Failed")
            self.failed.emit(message)
            return

        task_id = next(self._task_seq)
        self._worker = AnalysisWorker(request, task_id)
        self._worker.progressUpdated.connect(self.progressUpdated.emit)
        self._worker.logLine.connect(self.logAppended.emit)
        self._worker.finishedResult.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)

        self._task_started = time.time()
        self._set_state("Running")
        self.logAppended.emit(f"--- Task {task_id} started: {request.module} ---")
        self._worker.start()

    def _on_worker_finished(self, result: AnalysisResult) -> None:
        self._set_state("Completed")
        self.finished.emit(result)

    def _on_worker_failed(self, message: str) -> None:
        self._set_state("Failed")
        self.failed.emit(message)

    def _set_state(self, state: str) -> None:
        self._state = state
        self.stateChanged.emit(state)

