"""Automated quality checks on a finished run.

Each check returns PASS / WARN / FAIL plus a one-line reason, so a run is
never reported as "done" just because the solver exited cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .foam.logs import MeshReport, SolverLog


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str


def _grade(value: float, warn_above: float, fail_above: float) -> Status:
    if value > fail_above:
        return Status.FAIL
    if value > warn_above:
        return Status.WARN
    return Status.PASS


def check_mesh(rep: MeshReport) -> list[CheckResult]:
    out = [
        CheckResult(
            "mesh: checkMesh",
            Status.PASS if rep.mesh_ok else Status.FAIL,
            f"{rep.cells} cells, {rep.failed_checks} failed checks",
        )
    ]
    if rep.max_non_orthogonality is not None:
        out.append(CheckResult(
            "mesh: non-orthogonality",
            _grade(rep.max_non_orthogonality, 65, 80),
            f"max {rep.max_non_orthogonality:.1f} deg (warn > 65, fail > 80)",
        ))
    if rep.max_skewness is not None:
        out.append(CheckResult(
            "mesh: skewness",
            _grade(rep.max_skewness, 2, 4),
            f"max {rep.max_skewness:.2f} (warn > 2, fail > 4)",
        ))
    return out


def check_run(log: SolverLog, residual_target: float) -> list[CheckResult]:
    out = [
        CheckResult(
            "run: finished",
            Status.PASS if log.finished else Status.FAIL,
            "solver reached End" if log.finished else "solver did not finish",
        )
    ]

    if log.converged_at is not None:
        out.append(CheckResult(
            "run: convergence", Status.PASS,
            f"residuals below {residual_target:g} after {log.converged_at} iterations",
        ))
    else:
        drops = {f: log.residual_drop(f) for f in ("p", "Ux", "Uy") if f in log.residuals}
        worst = min((d for d in drops.values() if d is not None), default=0.0)
        status = Status.WARN if worst >= 3 else Status.FAIL
        out.append(CheckResult(
            "run: convergence", status,
            f"target not reached; worst residual drop {worst:.1f} orders "
            f"(warn >= 3, fail < 3)",
        ))

    if log.continuity_local:
        last = log.continuity_local[-1]
        out.append(CheckResult(
            "run: continuity", _grade(last, 1e-6, 1e-4),
            f"local continuity error {last:.2e} (warn > 1e-6, fail > 1e-4)",
        ))
    return out


def check_validation(name: str, rms_error: float, max_error: float) -> CheckResult:
    return CheckResult(
        f"validation: {name}",
        _grade(rms_error, 0.02, 0.05),
        f"RMS error {rms_error:.4f}, max {max_error:.4f} (warn > 0.02, fail > 0.05)",
    )


def overall(results: list[CheckResult]) -> Status:
    statuses = {r.status for r in results}
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.WARN in statuses:
        return Status.WARN
    return Status.PASS
