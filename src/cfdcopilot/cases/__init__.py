"""Case generators, one module per case type, keyed by ``spec.case``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..spec import CaseSpec
from . import cavity

BUILDERS: dict[str, Callable[..., Path]] = {
    "lid_driven_cavity": cavity.build,
}


def build_case(spec: CaseSpec, case_dir: Path) -> Path:
    try:
        builder = BUILDERS[spec.case]
    except KeyError:  # pragma: no cover - guarded by spec validation
        raise ValueError(f"no generator for case type '{spec.case}'") from None
    return builder(spec, case_dir)
