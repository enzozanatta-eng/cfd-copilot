"""Lid-driven cavity case generator (OpenFOAM 12, foamRun + incompressibleFluid).

Steady laminar solution with the SIMPLEC algorithm (``consistent yes``), and a
``sets`` function object that samples U along the vertical centreline x = 0.5,
the line used by the Ghia et al. (1982) benchmark.
"""

from __future__ import annotations

from pathlib import Path

from ..foam.dicts import Raw, write_foam_file
from ..spec import CavitySpec

DEPTH = 0.1  # 2D: one cell thick in z
SAMPLE_FUNC = "centreline"
SAMPLE_SET = "vertical"


def build(spec: CavitySpec, case_dir: Path) -> Path:
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    _block_mesh(spec, case_dir)
    _initial_conditions(case_dir)
    _constant(spec, case_dir)
    _control(spec, case_dir)
    _schemes(case_dir)
    _solution(spec, case_dir)
    return case_dir


def _block_mesh(spec: CavitySpec, d: Path) -> None:
    n = spec.cells
    write_foam_file(d, "system/blockMeshDict", "dictionary", {
        "convertToMeters": 1,
        "vertices": [
            (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
            (0, 0, DEPTH), (1, 0, DEPTH), (1, 1, DEPTH), (0, 1, DEPTH),
        ],
        "blocks": [Raw(f"hex (0 1 2 3 4 5 6 7) ({n} {n} 1) simpleGrading (1 1 1)")],
        "boundary": Raw(
            "(\n"
            "    movingWall   { type wall;  faces ((3 7 6 2)); }\n"
            "    fixedWalls   { type wall;  faces ((0 4 7 3) (2 6 5 1) (1 5 4 0)); }\n"
            "    frontAndBack { type empty; faces ((0 3 2 1) (4 5 6 7)); }\n"
            ")"
        ),
    })


def _initial_conditions(d: Path) -> None:
    write_foam_file(d, "0/U", "volVectorField", {
        "dimensions": Raw("[0 1 -1 0 0 0 0]"),
        "internalField": Raw("uniform (0 0 0)"),
        "boundaryField": {
            "movingWall": {"type": "fixedValue", "value": Raw("uniform (1 0 0)")},
            "fixedWalls": {"type": "noSlip"},
            "frontAndBack": {"type": "empty"},
        },
    })
    write_foam_file(d, "0/p", "volScalarField", {
        "dimensions": Raw("[0 2 -2 0 0 0 0]"),
        "internalField": Raw("uniform 0"),
        "boundaryField": {
            "movingWall": {"type": "zeroGradient"},
            "fixedWalls": {"type": "zeroGradient"},
            "frontAndBack": {"type": "empty"},
        },
    })


def _constant(spec: CavitySpec, d: Path) -> None:
    write_foam_file(d, "constant/physicalProperties", "dictionary", {
        "viscosityModel": "constant",
        "nu": Raw(f"[0 2 -1 0 0 0 0] {spec.nu:.10g}"),
    })
    write_foam_file(d, "constant/momentumTransport", "dictionary", {
        "simulationType": "laminar",
    })


def _control(spec: CavitySpec, d: Path) -> None:
    n_iter = spec.solver.max_iterations
    write_foam_file(d, "system/controlDict", "dictionary", {
        "application": "foamRun",
        "solver": "incompressibleFluid",
        "startFrom": "startTime",
        "startTime": 0,
        "stopAt": "endTime",
        "endTime": n_iter,
        "deltaT": 1,
        "writeControl": "timeStep",
        "writeInterval": n_iter,
        "purgeWrite": 0,
        "writeFormat": "ascii",
        "writePrecision": 8,
        "timeFormat": "general",
        "runTimeModifiable": True,
        "functions": {
            SAMPLE_FUNC: {
                "type": "sets",
                "libs": Raw('("libsampling.so")'),
                "writeControl": "writeTime",
                "interpolationScheme": "cellPoint",
                "setFormat": "raw",
                "fields": Raw("(U)"),
                # OpenFOAM 12 reads `sets` as a list of named dictionaries
                "sets": Raw(
                    "(\n"
                    f"            {SAMPLE_SET}\n"
                    "            {\n"
                    "                type    lineUniform;\n"
                    "                axis    y;\n"
                    f"                start   (0.5 0 {DEPTH / 2});\n"
                    f"                end     (0.5 1 {DEPTH / 2});\n"
                    "                nPoints 129;\n"
                    "            }\n"
                    "        )"
                ),
            }
        },
    })


def _schemes(d: Path) -> None:
    write_foam_file(d, "system/fvSchemes", "dictionary", {
        "ddtSchemes": {"default": "steadyState"},
        "gradSchemes": {"default": Raw("Gauss linear")},
        "divSchemes": {
            "default": "none",
            "div(phi,U)": Raw("bounded Gauss linearUpwind grad(U)"),
            "div((nuEff*dev2(T(grad(U)))))": Raw("Gauss linear"),
        },
        "laplacianSchemes": {"default": Raw("Gauss linear corrected")},
        "interpolationSchemes": {"default": "linear"},
        "snGradSchemes": {"default": "corrected"},
    })


def _solution(spec: CavitySpec, d: Path) -> None:
    tol = spec.solver.residual_target
    write_foam_file(d, "system/fvSolution", "dictionary", {
        "solvers": {
            '"p.*"': {
                "solver": "GAMG",
                "smoother": "GaussSeidel",
                "tolerance": 1e-8,
                "relTol": 0.05,
            },
            '"U.*"': {
                "solver": "smoothSolver",
                "smoother": "symGaussSeidel",
                "tolerance": 1e-9,
                "relTol": 0.1,
            },
        },
        "PIMPLE": {
            "nOuterCorrectors": 1,
            "nCorrectors": 1,
            "nNonOrthogonalCorrectors": 0,
            "consistent": True,  # SIMPLEC
            "pRefCell": 0,  # closed box: pressure level must be pinned
            "pRefValue": 0,
            "residualControl": {"p": tol, "U": tol},
        },
        "relaxationFactors": {"equations": {'".*"': 0.9}},
    })
