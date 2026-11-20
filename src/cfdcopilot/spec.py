"""Case specifications.

A spec is the single source of truth for a simulation. It is small, human
readable YAML, validated before anything touches OpenFOAM, so physically
inconsistent requests fail fast with an explanation instead of a crashed run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator


class SolverControls(BaseModel):
    max_iterations: int = Field(2000, ge=10, le=200_000)
    residual_target: float = Field(1e-5, gt=0, lt=1e-1)


class CavitySpec(BaseModel):
    """2D lid-driven cavity: square box, top wall moving at U = 1.

    Non-dimensional setup (L = 1, U = 1), so the viscosity is ``1/Re``.
    """

    case: Literal["lid_driven_cavity"] = "lid_driven_cavity"
    name: str = Field(..., pattern=r"^[A-Za-z0-9_.-]+$")
    reynolds: float = Field(..., gt=0)
    cells: int = Field(64, ge=8, le=512, description="cells per side")
    solver: SolverControls = SolverControls()

    @field_validator("reynolds")
    @classmethod
    def _laminar_steady(cls, re: float) -> float:
        # The steady laminar solution loses stability around Re ~ 8000;
        # past that a steady solver will not converge.
        if re > 5000:
            raise ValueError(
                f"Re = {re:g} is beyond the range where a steady laminar cavity "
                "solution is reliable (Re <= 5000). Use a transient solver instead."
            )
        return re

    @model_validator(mode="after")
    def _resolution(self) -> CavitySpec:
        # Corner vortices and the lid boundary layer thin as Re grows;
        # rough rule: need ~ sqrt(Re) * 4 cells across, at least 32.
        needed = max(32, int(4 * self.reynolds**0.5))
        if self.cells < needed:
            raise ValueError(
                f"{self.cells} cells per side is too coarse for Re = {self.reynolds:g}; "
                f"use at least {needed}."
            )
        return self

    @property
    def nu(self) -> float:
        return 1.0 / self.reynolds


# Becomes a discriminated union on ``case`` as more case types are added.
CaseSpec = CavitySpec
_adapter: TypeAdapter[CaseSpec] = TypeAdapter(CaseSpec)


def load_spec(path: str | Path) -> CaseSpec:
    data = yaml.safe_load(Path(path).read_text())
    return parse_spec(data)


def parse_spec(data: dict) -> CaseSpec:
    return _adapter.validate_python(data)


def dump_spec(spec: CaseSpec) -> str:
    return yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False)
