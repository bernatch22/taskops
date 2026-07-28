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
from taskops.engine._chunks import CHUNK_CHARS, slices
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


# ---- chunking: a dossier too long for one reading


class _Counted:
    """Every prompt a run sent, in order — so a chunked narration can be checked for the one
    thing that matters: that nothing was dropped on the way in."""

    def __init__(self) -> None:
        self.prompts: list[str] = []


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> _Counted:
    seen = _Counted()

    def fake(command: list[str], **_: Any) -> "subprocess.CompletedProcess[str]":
        seen.prompts.append(command[2])
        return subprocess.CompletedProcess(command, 0, stdout=f"part {len(seen.prompts)}\n",
                                           stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake)
    return seen


def _long_dossier(cards: int) -> str:
    """A dossier shaped like a real one: a header, then card blocks big enough that a handful
    of them blow past the threshold."""
    body = "".join(f"✓ **tk-{n}** — card {n}\n" + "  detail line\n" * 400
                   for n in range(cards))
    return "# all — some closed\n\n## Cerrado\n\n" + body


def test_a_short_dossier_is_still_ONE_call(counted: _Counted) -> None:
    narrate("# a small day")
    assert len(counted.prompts) == 1


def test_a_long_dossier_is_read_in_slices_and_stitched(counted: _Counted) -> None:
    """N slices plus one stitch. The alternative — sending a prompt trimmed to fit — is what
    this exists to prevent: a report that forgets whatever sorted last and never says so."""
    dossier = _long_dossier(12)
    assert len(dossier) > CHUNK_CHARS

    out = narrate(dossier)

    assert len(counted.prompts) > 2, "several slices and a stitch, not one call"
    assert "PARTS" in counted.prompts[-1], "the last call assembles the earlier answers"
    assert all(f"part {n}" in counted.prompts[-1] for n in range(1, len(counted.prompts)))
    assert out == f"part {len(counted.prompts)}"


def test_NO_card_is_lost_between_the_slices(counted: _Counted) -> None:
    """The invariant of the whole chunking path. Every card id the dossier held has to appear
    in some slice's prompt — a chunker that dropped one would be the silent truncation with
    extra steps."""
    narrate(_long_dossier(12))
    sent = "".join(counted.prompts[:-1])
    assert all(f"tk-{n}" in sent for n in range(12))


def test_each_slice_carries_the_header(counted: _Counted) -> None:
    """The header names the window and the language the narration must be written in. A slice
    without it is a list of cards with no idea what report it belongs to."""
    narrate(_long_dossier(12))
    assert all("# all — some closed" in prompt for prompt in counted.prompts[:-1])


def test_a_slice_is_never_cut_through_the_middle_of_a_card() -> None:
    """Half a card under one reading and half under another produces two partial paragraphs
    about the same work, and the stitch has no way to know they are the same card."""
    parts = slices(_long_dossier(12))
    assert len(parts) > 1
    for part in parts:
        assert part.count("✓ **") >= 1
        assert part.split("✓ **", 1)[1].startswith("tk-")


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
