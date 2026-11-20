"""The LLM layer with a scripted fake model: no API key, no network."""

import argparse

import pytest

from cfdcopilot.ask import NoValidSpec, RequestDeclined, propose_spec
from cfdcopilot.cli import EXIT_BAD_SPEC, EXIT_OK, cmd_ask
from cfdcopilot.llm import AnthropicClient, OpenAIClient, ToolCall, ToolResult, UserText


class ScriptedLLM:
    """Replays a fixed list of tool calls and records what it was sent."""

    def __init__(self, *calls):
        self.calls = list(calls)
        self.seen: list[list[dict]] = []

    def call(self, system, history, tools):
        self.seen.append(list(history))
        return self.calls.pop(0)


def propose(i, **spec):
    return ToolCall(id=f"t{i}", name="propose_spec", input={"case": "lid_driven_cavity", **spec})


def test_valid_first_try():
    llm = ScriptedLLM(propose(1, name="cavity-re400", reynolds=400, cells=96))
    result = propose_spec("cavity at Re 400", llm)
    assert result.spec.reynolds == 400
    assert len(result.attempts) == 1


def test_rejected_proposal_is_fed_back_and_fixed():
    llm = ScriptedLLM(
        propose(1, name="cavity-re1000", reynolds=1000, cells=64),  # too coarse
        propose(2, name="cavity-re1000", reynolds=1000, cells=160),
    )
    result = propose_spec("cavity at Re 1000", llm)
    assert result.spec.cells == 160
    assert result.attempts[0].error and "too coarse" in result.attempts[0].error

    # the second call must carry the validator's reason back to the model
    feedback = llm.seen[1][-1]
    assert isinstance(feedback, ToolResult) and feedback.is_error
    assert feedback.call_id == "t1"
    assert "too coarse" in feedback.content


def test_gives_up_after_max_attempts():
    bad = [propose(i, name="c", reynolds=1000, cells=32) for i in range(3)]
    with pytest.raises(NoValidSpec, match="3 attempts"):
        propose_spec("cavity Re 1000", ScriptedLLM(*bad), max_attempts=3)


def test_unsupported_request_is_declined():
    llm = ScriptedLLM(ToolCall("t1", "cannot_build", {
        "reason": "3D turbulent flow is not supported",
        "closest_supported": "lid_driven_cavity",
    }))
    with pytest.raises(RequestDeclined) as e:
        propose_spec("3D turbulent flow over a truck", llm)
    assert "not supported" in e.value.reason


def _args(**kw):
    base = dict(request="r", output=None, run=False, out="runs", attempts=3, provider=None)
    return argparse.Namespace(**{**base, **kw})


def test_cli_ask_writes_spec(tmp_path, capsys):
    out = tmp_path / "s.yaml"
    llm = ScriptedLLM(propose(1, name="cavity-re100", reynolds=100))
    assert cmd_ask(_args(output=str(out)), client=llm) == EXIT_OK
    assert "reynolds: 100" in out.read_text()


def test_cli_ask_declined_exit_code(capsys):
    llm = ScriptedLLM(ToolCall("t1", "cannot_build", {"reason": "no"}))
    assert cmd_ask(_args(), client=llm) == EXIT_BAD_SPEC


HISTORY = [
    UserText("cavity Re 1000"),
    ToolCall("t1", "propose_spec", {"reynolds": 1000, "cells": 64}),
    ToolResult("t1", "too coarse", is_error=True),
]


def test_anthropic_wire_format():
    msgs = AnthropicClient.to_messages(HISTORY)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"][0]["type"] == "tool_use"
    assert msgs[2]["content"][0] == {
        "type": "tool_result", "tool_use_id": "t1", "content": "too coarse", "is_error": True,
    }


def test_openai_wire_format():
    msgs = OpenAIClient.to_messages("sys", HISTORY)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    fn = msgs[2]["tool_calls"][0]["function"]
    assert fn["name"] == "propose_spec" and '"cells": 64' in fn["arguments"]
    assert msgs[3]["tool_call_id"] == "t1" and msgs[3]["content"].startswith("ERROR")


def test_make_client_needs_a_key(monkeypatch):
    from cfdcopilot.llm import LLMError, make_client

    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CFDC_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(LLMError, match="API_KEY"):
        make_client()
