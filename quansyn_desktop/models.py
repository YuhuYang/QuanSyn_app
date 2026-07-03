from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisRequest:
    module: str
    input_path: str
    output_dir: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    status: str
    summary: str
    artifacts: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    error: str = ""
