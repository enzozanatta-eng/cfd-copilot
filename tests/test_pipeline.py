"""End-to-end pipeline test with a fake runner replaying recorded logs."""

from pathlib import Path

import numpy as np
import pytest

from cfdcopilot.checks import Status
from cfdcopilot.foam.runner import StepResult
from cfdcopilot.pipeline import run_case, write_report
from cfdcopilot.spec import CavitySpec
from cfdcopilot.validation import ghia

FIX = Path(__file__).parent / "fixtures"


class FakeRunner:
    def __init__(self, fail_solver_with: str | None = None, profile_shift: float = 0.0):
        self.fail_solver_with = fail_solver_with
        self.profile_shift = profile_shift
        self.calls: list[str] = []

    def run(self, command, case_dir):
        name = command[0]
        self.calls.append(name)
        log = Path(case_dir) / f"log.{name}"
        rc = 0
        if name == "checkMesh":
            log.write_text((FIX / "checkMesh_ok.log").read_text())
        elif name == "foamRun":
            if self.fail_solver_with:
                log.write_text((FIX / self.fail_solver_with).read_text())
                rc = 1
            else:
                log.write_text((FIX / "foamRun_converged.log").read_text())
                self._write_profile(Path(case_dir))
        else:
            log.write_text("End\n")
        return StepResult(name, rc, log)

    def _write_profile(self, case_dir):
        out = case_dir / "postProcessing" / "centreline" / "300"
        out.mkdir(parents=True)
        y = np.linspace(0, 1, 129)
        u = np.interp(y, ghia.Y[::-1], ghia.U[100][::-1]) + self.profile_shift
        np.savetxt(out / "vertical.xy", np.column_stack([y, u, 0 * y, 0 * y]))


@pytest.fixture
def spec():
    return CavitySpec(name="cav100", reynolds=100, cells=64)


def test_case_files_generated(spec, tmp_path):
    run_case(spec, tmp_path / "c", FakeRunner())
    for f in ["system/blockMeshDict", "system/controlDict", "system/fvSchemes",
              "system/fvSolution", "constant/physicalProperties", "0/U", "0/p", "case.yaml"]:
        assert (tmp_path / "c" / f).is_file(), f
    assert "0.01;" in (tmp_path / "c/constant/physicalProperties").read_text()


def test_successful_run_passes_all_checks(spec, tmp_path):
    report = run_case(spec, tmp_path / "c", FakeRunner())
    assert report.status is Status.PASS, [(r.name, r.detail) for r in report.results]
    assert any(r.name.startswith("validation") for r in report.results)
    assert write_report(report).read_text().startswith("# cfd-copilot report")


def test_wrong_answer_is_caught(spec, tmp_path):
    report = run_case(spec, tmp_path / "c", FakeRunner(profile_shift=0.1))
    (val,) = [r for r in report.results if r.name.startswith("validation")]
    assert val.status is Status.FAIL


def test_solver_crash_is_diagnosed(spec, tmp_path):
    runner = FakeRunner(fail_solver_with="foamRun_pref.log")
    report = run_case(spec, tmp_path / "c", runner)
    assert report.status is Status.FAIL
    assert report.failed_step == "foamRun"
    assert report.diagnoses[0].title == "Pressure level undefined"
    assert runner.calls == ["blockMesh", "checkMesh", "foamRun"]
