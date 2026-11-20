"""Turn OpenFOAM failures into explanations and fixes.

A rule-based first pass: known error signatures are matched against the log
and mapped to a cause and a concrete fix. Rules are deterministic and tested,
so the later LLM layer only has to handle what the rules do not recognise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    pattern: str
    title: str
    cause: str
    fix: str


@dataclass
class Diagnosis:
    title: str
    evidence: str
    cause: str
    fix: str


RULES: list[Rule] = [
    Rule(
        r"Floating point exception|sigFpe::sigHandler",
        "Solution diverged",
        "A field blew up to inf/NaN. Usual suspects: time step or relaxation too "
        "aggressive, bad mesh cells, or boundary conditions that over-constrain the flow.",
        "Lower the relaxation factors (e.g. U 0.7, p 0.3), run checkMesh, and check "
        "that inlet/outlet conditions are consistent.",
    ),
    Rule(
        r"cannot find file\s+\"?([^\"\n]+)",
        "Missing input file",
        "A required case file was not found: {0}",
        "Create the file, or check the case directory and the time folder (0/).",
    ),
    Rule(
        r"[Kk]eyword (\S+) is undefined in dictionary\s+\"?([^\"\n]+)",
        "Missing dictionary entry",
        "Entry '{0}' is required in {1}.",
        "Add the entry. OpenFOAM versions rename keywords, so check the "
        "version-specific tutorial for the expected name.",
    ),
    Rule(
        r"Unknown (?:patchField|fvPatchField) type (\S+)",
        "Unknown boundary condition",
        "Boundary condition type '{0}' does not exist in this OpenFOAM version.",
        "Run `foamInfo -fvPatchField` (or check the docs) for valid types and fix "
        "the field file in 0/.",
    ),
    Rule(
        r"Cannot find patchField entry for (\S+)",
        "Boundary condition missing for a patch",
        "The mesh has a patch '{0}' that is not listed in a field file in 0/.",
        "Add an entry for this patch to every field in 0/, or use a regex "
        "such as \".*Wall\" to cover several patches.",
    ),
    Rule(
        r"[Ii]nside-out cell|negative volume",
        "Inverted cells",
        "Some cells have negative volume: block vertices are in the wrong order "
        "or the geometry folds over itself.",
        "Order hex vertices with the right-hand rule (bottom face counter-clockwise, "
        "then top face) and rerun blockMesh and checkMesh.",
    ),
    Rule(
        r"[Uu]nable to set reference cell for field (\S+)",
        "Pressure level undefined",
        "No boundary fixes the level of '{0}' (closed domain), so the pressure "
        "equation is singular.",
        "Add pRefCell and pRefValue (or pRefPoint) to the solver dictionary in fvSolution.",
    ),
    Rule(
        r"Attempt to return dictionary entry as a primitive[\s\S]*?file: (\S+)",
        "Wrong dictionary structure",
        "An entry in {0} is written as a sub-dictionary {{ }} where OpenFOAM expects "
        "a value or a list ( ).",
        "Compare the entry with the tutorial for your OpenFOAM version; list-type "
        "entries (e.g. `sets` in OpenFOAM 12) must be written as ( name {{ ... }} ).",
    ),
    Rule(
        r"Maximum number of iterations exceeded",
        "Linear solver not converging",
        "A matrix solve hit maxIter without reaching its tolerance, usually an early "
        "sign of divergence or a poor-quality mesh.",
        "Check mesh quality and relaxation; for p, GAMG is usually the robust choice.",
    ),
]


def diagnose(log_text: str, rules: list[Rule] = RULES) -> list[Diagnosis]:
    found: list[Diagnosis] = []
    for rule in rules:
        m = re.search(rule.pattern, log_text)
        if not m:
            continue
        groups = [g.strip() for g in m.groups() if g is not None]
        line_start = log_text.rfind("\n", 0, m.start()) + 1
        line_end = log_text.find("\n", m.end())
        evidence = log_text[line_start : line_end if line_end != -1 else None].strip()
        found.append(Diagnosis(
            title=rule.title,
            evidence=evidence,
            cause=rule.cause.format(*groups),
            fix=rule.fix,
        ))
    return found


def diagnose_or_tail(log_text: str, n_lines: int = 15) -> list[Diagnosis]:
    """Known diagnoses, or the end of the log when no rule matches."""
    found = diagnose(log_text)
    if found:
        return found
    tail = "\n".join(log_text.strip().splitlines()[-n_lines:])
    return [Diagnosis(
        title="Unrecognised failure",
        evidence=tail,
        cause="No known error signature matched.",
        fix="Read the log tail above; add a rule to diagnose.py once the cause is known.",
    )]
