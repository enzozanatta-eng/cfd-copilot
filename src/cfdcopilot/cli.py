"""Command line interface: ``cfdc``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .cases import build_case
from .checks import Status
from .diagnose import diagnose
from .foam.runner import LocalRunner, OpenFOAMNotFound
from .pipeline import run_case, write_report
from .spec import CavitySpec, dump_spec, load_spec

EXIT_OK, EXIT_FAIL, EXIT_BAD_SPEC = 0, 1, 2
ICON = {Status.PASS: "[ OK ]", Status.WARN: "[WARN]", Status.FAIL: "[FAIL]"}


def _load(path: str):
    try:
        return load_spec(path)
    except ValidationError as e:
        print(f"Invalid spec {path}:", file=sys.stderr)
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(spec)"
            print(f"  - {loc}: {err['msg']}", file=sys.stderr)
        sys.exit(EXIT_BAD_SPEC)


def cmd_new(args: argparse.Namespace) -> int:
    try:
        spec = CavitySpec(name=args.name, reynolds=args.re, cells=args.cells)
    except ValidationError as e:
        for err in e.errors():
            print(f"error: {err['msg']}", file=sys.stderr)
        return EXIT_BAD_SPEC
    text = dump_spec(spec)
    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    print(f"{args.spec}: valid {spec.case} spec ({spec.name})")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    case_dir = build_case(spec, Path(args.out) / spec.name)
    print(f"OpenFOAM case written to {case_dir}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    spec = _load(args.spec)
    case_dir = Path(args.out) / spec.name
    try:
        report = run_case(spec, case_dir, LocalRunner())
    except OpenFOAMNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL

    for r in report.results:
        print(f"{ICON[r.status]} {r.name}: {r.detail}")
    if report.failed_step:
        print(f"[FAIL] stopped at '{report.failed_step}'")
    for d in report.diagnoses:
        print(f"\n  {d.title}\n    evidence: {d.evidence}\n    cause: {d.cause}\n    fix: {d.fix}")
    path = write_report(report)
    print(f"\nOverall: {report.status.value}  (report: {path})")
    return EXIT_FAIL if report.status is Status.FAIL else EXIT_OK


def cmd_diagnose(args: argparse.Namespace) -> int:
    found = diagnose(Path(args.log).read_text(errors="replace"))
    if not found:
        print("No known failure signature found.")
        return EXIT_OK
    for d in found:
        print(f"{d.title}\n  evidence: {d.evidence}\n  cause: {d.cause}\n  fix: {d.fix}\n")
    return EXIT_FAIL


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cfdc", description="Describe a CFD case, get a verified OpenFOAM simulation."
    )
    p.add_argument("--version", action="version", version=f"cfd-copilot {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("new", help="create a lid-driven cavity spec")
    s.add_argument("--name", required=True)
    s.add_argument("--re", type=float, required=True, help="Reynolds number")
    s.add_argument("--cells", type=int, default=64, help="cells per side")
    s.add_argument("-o", "--output", help="write the spec here instead of stdout")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("validate", help="check a spec without running anything")
    s.add_argument("spec")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("build", help="write the OpenFOAM case only")
    s.add_argument("spec")
    s.add_argument("-o", "--out", default="runs")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("run", help="build, mesh, solve, check and report")
    s.add_argument("spec")
    s.add_argument("-o", "--out", default="runs")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("diagnose", help="explain a failed OpenFOAM log")
    s.add_argument("log")
    s.set_defaults(func=cmd_diagnose)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
