"""Command line interface: ``cfdc``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .ask import NoValidSpec, RequestDeclined, propose_spec
from .cases import build_case
from .checks import Status
from .diagnose import diagnose
from .foam.runner import LocalRunner, OpenFOAMNotFound
from .llm import LLMError, make_client
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


def _report_run(report) -> int:
    for r in report.results:
        print(f"{ICON[r.status]} {r.name}: {r.detail}")
    if report.failed_step:
        print(f"[FAIL] stopped at '{report.failed_step}'")
    for d in report.diagnoses:
        print(f"\n  {d.title}\n    evidence: {d.evidence}\n    cause: {d.cause}\n    fix: {d.fix}")
    path = write_report(report)
    print(f"\nOverall: {report.status.value}  (report: {path})")
    return EXIT_FAIL if report.status is Status.FAIL else EXIT_OK


def _execute(spec, out: str) -> int:
    try:
        report = run_case(spec, Path(out) / spec.name, LocalRunner())
    except OpenFOAMNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    return _report_run(report)


def cmd_ask(args: argparse.Namespace, client=None) -> int:
    try:
        client = client or make_client(args.provider)
        result = propose_spec(args.request, client, max_attempts=args.attempts)
    except RequestDeclined as e:
        print(f"Cannot build this: {e.reason}")
        if e.closest:
            print(f"Closest supported case: {e.closest}")
        return EXIT_BAD_SPEC
    except (NoValidSpec, LLMError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_SPEC

    for i, a in enumerate(result.attempts, 1):
        if a.error:
            print(f"[retry] proposal {i} rejected: {a.error}")
    text = dump_spec(result.spec)
    print(f"Spec ({len(result.attempts)} attempt(s)):\n{text}")
    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output}")
    if args.run:
        return _execute(result.spec, args.out)
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
    return _execute(_load(args.spec), args.out)


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

    s = sub.add_parser("ask", help="describe a case in plain language (uses an LLM)")
    s.add_argument("request", help='e.g. "cavity at Re 400, compare with literature"')
    s.add_argument("-o", "--output", help="save the spec here")
    s.add_argument("--run", action="store_true", help="run the case right away")
    s.add_argument("--out", default="runs", help="runs folder (with --run)")
    s.add_argument("--attempts", type=int, default=3, help="max proposals before giving up")
    s.add_argument("--provider", choices=["anthropic", "openai"],
                   help="LLM provider (default: whichever API key is set)")
    s.set_defaults(func=cmd_ask)

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
