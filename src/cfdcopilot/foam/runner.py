"""Running OpenFOAM utilities.

``Runner`` is a protocol so the pipeline can be tested with a fake runner that
replays recorded logs instead of calling OpenFOAM.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class OpenFOAMNotFound(RuntimeError):
    pass


@dataclass
class StepResult:
    command: str
    returncode: int
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def text(self) -> str:
        return self.log_path.read_text(errors="replace")


class Runner(Protocol):
    def run(self, command: list[str], case_dir: Path) -> StepResult: ...


class LocalRunner:
    """Runs OpenFOAM commands on this machine; output goes to ``log.<command>``."""

    def __init__(self, timeout_s: float | None = None):
        self.timeout_s = timeout_s

    @staticmethod
    def ensure_available(command: str = "foamRun") -> None:
        if shutil.which(command) is None:
            raise OpenFOAMNotFound(
                f"'{command}' not found. Load OpenFOAM first, e.g.\n"
                "    source /opt/openfoam12/etc/bashrc"
            )

    def run(self, command: list[str], case_dir: Path) -> StepResult:
        self.ensure_available(command[0])
        log_path = Path(case_dir) / f"log.{command[0]}"
        with log_path.open("w") as fh:
            proc = subprocess.run(
                command,
                cwd=case_dir,
                stdout=fh,
                stderr=subprocess.STDOUT,
                timeout=self.timeout_s,
                check=False,
            )
        return StepResult(" ".join(command), proc.returncode, log_path)
