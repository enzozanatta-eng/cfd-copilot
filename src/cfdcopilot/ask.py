"""Plain-language request -> validated case spec.

The LLM proposes, the physics checks dispose: every proposal goes through the
same pydantic validation as a hand-written spec. Rejections are sent back to
the model with the validator's reason, so it can correct itself, up to a fixed
number of attempts. The model can also decline requests the tool cannot build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from .llm import LLMClient, LLMError, Tool, ToolResult, Turn, UserText, inline_refs
from .spec import CaseSpec, CavitySpec, parse_spec

SYSTEM_PROMPT = """\
You turn CFD requests into simulation specs for cfd-copilot, an OpenFOAM front end.

Supported case types:
- lid_driven_cavity: 2D square cavity, top wall moving, steady laminar,
  non-dimensional (L = 1, U = 1, so Re sets the viscosity). Published benchmark
  data (Ghia et al. 1982) exists for Re = 100, 400 and 1000.

Rules:
- If the request fits a supported case, call propose_spec.
- If it does not (other geometry, turbulence, heat transfer, 3D, compressible...),
  call cannot_build with a short reason and the closest supported alternative.
- Use the smallest mesh that resolves the physics: it keeps runs fast.
- name: short lowercase slug, e.g. cavity-re400.
- If a proposal is rejected, read the reason and fix the spec; do not repeat it.
"""

PROPOSE = Tool(
    name="propose_spec",
    description="Propose a cfd-copilot case spec for the request.",
    input_schema=inline_refs(CavitySpec.model_json_schema()),
)

DECLINE = Tool(
    name="cannot_build",
    description="Decline a request that no supported case type can represent.",
    input_schema={
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
            "closest_supported": {"type": "string"},
        },
        "required": ["reason"],
    },
)


class RequestDeclined(Exception):
    def __init__(self, reason: str, closest: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.closest = closest


class NoValidSpec(Exception):
    pass


@dataclass
class Attempt:
    proposal: dict
    error: str | None  # None if the proposal was accepted


@dataclass
class AskResult:
    spec: CaseSpec
    attempts: list[Attempt] = field(default_factory=list)


def _explain(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'spec'}: {err['msg']}" for err in e.errors()
    )


def propose_spec(request: str, client: LLMClient, max_attempts: int = 3) -> AskResult:
    history: list[Turn] = [UserText(request)]
    attempts: list[Attempt] = []

    for _ in range(max_attempts):
        call = client.call(SYSTEM_PROMPT, history, [PROPOSE, DECLINE])

        if call.name == DECLINE.name:
            raise RequestDeclined(call.input.get("reason", ""), call.input.get("closest_supported"))
        if call.name != PROPOSE.name:
            raise LLMError(f"unexpected tool '{call.name}'")

        try:
            spec = parse_spec(call.input)
        except ValidationError as e:
            reason = _explain(e)
            attempts.append(Attempt(call.input, reason))
            history += [
                call,
                ToolResult(call.id, f"Rejected by the spec validator: {reason}", is_error=True),
            ]
            continue

        attempts.append(Attempt(call.input, None))
        return AskResult(spec, attempts)

    last = json.dumps(attempts[-1].proposal) if attempts else "-"
    raise NoValidSpec(
        f"no valid spec after {max_attempts} attempts; last proposal {last} "
        f"was rejected: {attempts[-1].error if attempts else '-'}"
    )
