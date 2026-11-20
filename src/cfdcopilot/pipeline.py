"""Spec -> case -> mesh -> solve -> checks -> report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import checks
from .cases import build_case
from .cases.cavity import SAMPLE_FUNC, SAMPLE_SET
from .checks import CheckResult, Status
from .diagnose import Diagnosis, diagnose_or_tail
from .foam.logs import parse_checkmesh, parse_solver_log
from .foam.runner import Runner
from .spec import CaseSpec, dump_spec
from .validation import ghia


@dataclass
class RunReport:
    case_dir: Path
    results: list[CheckResult] = field(default_factory=list)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    failed_step: str | None = None
    profile: tuple[np.ndarray, np.ndarray] | None = None
    reference: ghia.Comparison | None = None

    @property
    def status(self) -> Status:
        if self.failed_step:
            return Status.FAIL
        return checks.overall(self.results)


def read_centreline(case_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Latest sampled (y, Ux) profile written by the ``sets`` function object."""
    root = Path(case_dir) / "postProcessing" / SAMPLE_FUNC
    times = sorted(
        (p for p in root.iterdir() if p.is_dir()), key=lambda p: float(p.name)
    ) if root.is_dir() else []
    if not times:
        raise FileNotFoundError(f"no sampled data under {root}")
    files = sorted(times[-1].glob(f"{SAMPLE_SET}*.xy"))
    if not files:
        raise FileNotFoundError(f"no {SAMPLE_SET}*.xy in {times[-1]}")
    data = np.loadtxt(files[0], comments="#")
    return data[:, 0], data[:, 1]


def run_case(spec: CaseSpec, case_dir: Path, runner: Runner) -> RunReport:
    case_dir = Path(case_dir)
    build_case(spec, case_dir)
    (case_dir / "case.yaml").write_text(dump_spec(spec))
    report = RunReport(case_dir)

    for cmd in (["blockMesh"], ["checkMesh"], ["foamRun"]):
        step = runner.run(cmd, case_dir)
        text = step.text()
        if cmd[0] == "checkMesh":
            report.results += checks.check_mesh(parse_checkmesh(text))
        if not step.ok:
            report.failed_step = step.command
            report.diagnoses = diagnose_or_tail(text)
            return report

    log = parse_solver_log((case_dir / "log.foamRun").read_text(errors="replace"))
    report.results += checks.check_run(log, spec.solver.residual_target)

    if ghia.available(spec.reynolds):
        y, u = read_centreline(case_dir)
        cmp = ghia.compare(spec.reynolds, y, u)
        report.profile, report.reference = (y, u), cmp
        report.results.append(
            checks.check_validation(f"Ghia 1982, Re={cmp.reynolds}", cmp.rms_error, cmp.max_error)
        )
    return report


def write_report(report: RunReport) -> Path:
    """Markdown summary (plus a plot when matplotlib is installed)."""
    lines = [f"# cfd-copilot report: `{report.case_dir.name}`", ""]
    lines.append(f"**Overall: {report.status.value}**")
    lines.append("")
    if report.failed_step:
        lines += [f"Run stopped at `{report.failed_step}`.", ""]
    if report.results:
        lines += ["| Check | Status | Detail |", "|---|---|---|"]
        lines += [f"| {r.name} | {r.status.value} | {r.detail} |" for r in report.results]
        lines.append("")
    for d in report.diagnoses:
        lines += [
            f"## {d.title}",
            f"- Evidence: `{d.evidence}`",
            f"- Cause: {d.cause}",
            f"- Fix: {d.fix}",
            "",
        ]
    if report.profile is not None and _plot_profile(report):
        lines += ["![centreline](centreline.png)", ""]

    path = report.case_dir / "report.md"
    path.write_text("\n".join(lines))
    return path


def _plot_profile(report: RunReport) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    y, u = report.profile
    ref = report.reference
    fig, ax = plt.subplots(figsize=(4.5, 5))
    ax.plot(u, y, label="cfd-copilot (OpenFOAM)")
    ax.plot(ref.u_ref, ref.y_ref, "o", mfc="none", label="Ghia et al. 1982")
    ax.set_xlabel("u / U_lid")
    ax.set_ylabel("y / L")
    ax.set_title(f"Lid-driven cavity, Re = {ref.reynolds}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(report.case_dir / "centreline.png", dpi=120)
    plt.close(fig)
    return True
