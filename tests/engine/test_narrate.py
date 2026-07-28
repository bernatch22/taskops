"""The narration: the one call to a model, and the two rules that make it safe.

Every test here fakes `subprocess.run` rather than the `narrate` function, so what is asserted is
the command and the environment a real `claude` process would receive. Faking `narrate` itself
would test a re-implementation of the rule instead of the rule.
"""

from __future__ import annotations

import importlib
import subprocess
from typing import Any

import pytest

from taskops._errors import NarrationFailed
from taskops.engine.narrate import narrate

# The package re-exports the FUNCTION under this name, so `from taskops.engine import narrate`
# hands back a callable and not the module — patching `.subprocess` on it fails with a message
# that names neither. Fetch the module explicitly.
module = importlib.import_module("taskops.engine.narrate")
from taskops.render.report import NARRATION, PENDING, is_pending, narrated


class _Ran:
    """A stand-in for a finished process, and a record of how it was called."""

    def __init__(self) -> None:
        self.command: list[str] = []
        self.env: dict[str, str] = {}


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    seen = _Ran()

    def fake(command: list[str], **kwargs: Any) -> "subprocess.CompletedProcess[str]":
        seen.command = command
        seen.env = dict(kwargs.get("env") or {})
        return subprocess.CompletedProcess(command, 0, stdout="The day, read.\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake)
    return seen


def test_the_api_key_never_reaches_the_narration(ran: _Ran,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """The money rule, shared with a dispatched worker: an exported key makes the CLI bill per
    token while the subscription that is already paid for sits unused. It is the same constant
    (`worker.DROPPED_ENV`) precisely so this cannot drift from the worker's version."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-travel")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "also-not")
    monkeypatch.setenv("PATH", "/usr/bin")

    narrate("# a dossier")

    assert "ANTHROPIC_API_KEY" not in ran.env
    assert "ANTHROPIC_AUTH_TOKEN" not in ran.env
    assert ran.env["PATH"] == "/usr/bin", "the rest of the environment still travels"


def test_the_model_sees_the_dossier_and_the_rules(ran: _Ran) -> None:
    narrate("# 2026-07-28 — 2 closed")
    prompt = ran.command[2]
    assert "# 2026-07-28 — 2 closed" in prompt
    assert "Invent NOTHING" in prompt
    assert ran.command[:2] == ["claude", "-p"], "one-shot, so no session is left behind"


def test_a_model_override_is_passed_through(ran: _Ran) -> None:
    narrate("x", model="claude-haiku-4-5")
    assert ran.command[-2:] == ["--model", "claude-haiku-4-5"]


def test_a_missing_binary_says_what_writes_the_narration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(command: list[str], **_: Any) -> None:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(module.subprocess, "run", absent)
    with pytest.raises(NarrationFailed, match="not on PATH"):
        narrate("x")


def test_an_empty_answer_is_a_failure_not_a_blank_section(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """A CLI that is installed but not logged in exits 0 and says nothing, and a report whose
    narration is an empty section reads as a taskops bug rather than a login problem."""
    def silent(command: list[str], **_: Any) -> "subprocess.CompletedProcess[str]":
        return subprocess.CompletedProcess(command, 0, stdout="  \n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", silent)
    with pytest.raises(NarrationFailed, match="logged in"):
        narrate("x")


def test_a_nonzero_exit_carries_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def angry(command: list[str], **_: Any) -> "subprocess.CompletedProcess[str]":
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Invalid API key\n")

    monkeypatch.setattr(module.subprocess, "run", angry)
    with pytest.raises(NarrationFailed, match="Invalid API key"):
        narrate("x")


# ---- the splice, which is pure


def test_the_narration_replaces_only_its_own_section() -> None:
    """The facts above the heading were fingerprinted; rewriting them would make the stamp lie."""
    report = f"<!-- taskops:report date=x max_seq=9 -->\n\n# facts\n\n{NARRATION}\n\n{PENDING}\n"
    out = narrated(report, "What it meant.")
    assert out.startswith("<!-- taskops:report date=x max_seq=9 -->")
    assert "# facts" in out
    assert PENDING not in out
    assert out.rstrip().endswith("What it meant.")


def test_a_report_with_no_section_gains_one() -> None:
    out = narrated("# facts only\n", "Prose.")
    assert NARRATION in out and out.rstrip().endswith("Prose.")


def test_pending_is_true_only_while_nobody_has_written() -> None:
    assert is_pending(f"# facts\n\n{NARRATION}\n\n{PENDING}\n")
    assert is_pending(f"# facts\n\n{NARRATION}\n\n\n")
    assert not is_pending(f"# facts\n\n{NARRATION}\n\nSomebody wrote this by hand.\n")
