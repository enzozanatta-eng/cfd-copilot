"""Parsers for OpenFOAM solver and checkMesh logs.

The parsers are pure functions over text so they can be tested with recorded
logs and no OpenFOAM installation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"

_TIME = re.compile(rf"^Time = ({_NUM})s?\s*$")
_RESIDUAL = re.compile(
    rf"Solving for (\w+), Initial residual = ({_NUM}), Final residual = ({_NUM}), "
    rf"No Iterations (\d+)"
)
_CONTINUITY = re.compile(
    rf"time step continuity errors : sum local = ({_NUM}), global = ({_NUM})"
)
_COURANT = re.compile(rf"Courant Number mean: ({_NUM}) max: ({_NUM})")
_CONVERGED = re.compile(r"converged in (\d+) iterations", re.IGNORECASE)


@dataclass
class SolverLog:
    """What happened during a solver run."""

    times: list[float] = field(default_factory=list)
    # first initial residual of each field per time step / iteration
    residuals: dict[str, list[float]] = field(default_factory=dict)
    continuity_local: list[float] = field(default_factory=list)
    courant_max: list[float] = field(default_factory=list)
    converged_at: int | None = None
    finished: bool = False
    fatal_error: str | None = None

    @property
    def iterations(self) -> int:
        return len(self.times)

    def residual_drop(self, field_name: str) -> float | None:
        """Orders of magnitude the initial residual fell from its peak to the end."""
        import math

        r = self.residuals.get(field_name)
        if not r:
            return None
        peak, last = max(r), r[-1]
        if last <= 0:
            return float("inf")
        return math.log10(peak / last)


def parse_solver_log(text: str) -> SolverLog:
    log = SolverLog()
    seen_this_step: set[str] = set()
    lines = text.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        m = _TIME.match(stripped)
        if m:
            log.times.append(float(m.group(1)))
            seen_this_step = set()
            continue

        m = _RESIDUAL.search(line)
        if m:
            name = m.group(1)
            if name not in seen_this_step:  # keep the first solve of each step
                log.residuals.setdefault(name, []).append(float(m.group(2)))
                seen_this_step.add(name)
            continue

        m = _CONTINUITY.search(line)
        if m:
            log.continuity_local.append(float(m.group(1)))
            continue

        m = _COURANT.search(line)
        if m:
            log.courant_max.append(float(m.group(2)))
            continue

        m = _CONVERGED.search(line)
        if m:
            log.converged_at = int(m.group(1))
            continue

        if stripped == "End":
            log.finished = True
        elif "FOAM FATAL" in stripped or "Floating point exception" in stripped:
            # keep the error banner plus the explanation that follows it
            log.fatal_error = "\n".join(lines[i : i + 12]).strip()

    return log


@dataclass
class MeshReport:
    cells: int | None = None
    max_non_orthogonality: float | None = None
    max_skewness: float | None = None
    max_aspect_ratio: float | None = None
    failed_checks: int = 0
    mesh_ok: bool = False


def parse_checkmesh(text: str) -> MeshReport:
    rep = MeshReport()
    if m := re.search(r"^\s*cells:\s+(\d+)", text, re.M):
        rep.cells = int(m.group(1))
    if m := re.search(rf"Mesh non-orthogonality Max: ({_NUM})", text):
        rep.max_non_orthogonality = float(m.group(1))
    if m := re.search(rf"Max skewness = ({_NUM})", text):
        rep.max_skewness = float(m.group(1))
    if m := re.search(rf"Max aspect ratio = ({_NUM})", text):
        rep.max_aspect_ratio = float(m.group(1))
    if m := re.search(r"Failed (\d+) mesh checks", text):
        rep.failed_checks = int(m.group(1))
    rep.mesh_ok = "Mesh OK." in text and rep.failed_checks == 0
    return rep
