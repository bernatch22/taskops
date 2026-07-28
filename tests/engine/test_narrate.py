"""The narration: the one call to a model, and the rules that make it safe and cheap.

Every test here fakes `subprocess.Popen` rather than the `narrate` function, so what is asserted
is the command, the environment and the event stream a real `claude` process would produce.
Faking `narrate` itself would test a re-implementation of the rule instead of the rule.

The event shapes below are the real ones, in the real order — the thinking deltas FIRST, with
`"text": None`, because that is the trap an unfiltered reader falls into.
"""

from __future__ import annotations

import importlib
import json
from typing import Any, Iterator

import pytest

from taskops._errors import NarrationFailed
from taskops.engine._chunks import CHUNK_CHARS, slices
from taskops.engine.narrate import narrate

# The package re-exports the FUNCTION under this name, so `from taskops.engine import narrate`
# hands back a callable and not the module. The process lives in `_stream`; patch it there.
module = importlib.import_module("taskops.engine._stream")
from taskops.render.report import NARRATION, PENDING, is_pending, narrated


def _thinking(text: str) -> str:
    return json.dumps({"type": "stream_event",
                       "event": {"delta": {"type": "thinking_delta", "thinking": text,
                                           "text": None}}})


def _delta(text: str) -> str:
    return json.dumps({"type": "stream_event",
                       "event": {"delta": {"type": "text_delta", "text": text}}})


def _result(*, is_error: bool = False, result: str = "") -> str:
    return json.dumps({"type": "result", "is_error": is_error, "result": result,
                       "total_cost_usd": 0.004})


def _events(words: list[str]) -> list[str]:
    """A whole run: two thinking deltas, the text split mid-word, then the result."""
    return [_thinking("hmm"), _thinking(" ok"), *[_delta(w) for w in words], _result()]


class _Reader:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


class _Ran:
    """A stand-in for a running process, and a record of how it was called."""

    def __init__(self, lines: list[str]) -> None:
        self.command: list[str] = []
        self.env: dict[str, str] = {}
        self.lines = lines
        self.killed = 0
        self.returncode = 0
        self.stderr = _Reader("")

    # -- the `subprocess.Popen` surface `_stream` actually uses
    @property
    def stdout(self) -> Iterator[str]:
        return iter(f"{line}\n" for line in self.lines)

    def kill(self) -> None:
        self.killed += 1

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


def _popen(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> _Ran:
    process = _Ran(lines)

    def fake(command: list[str], **kwargs: Any) -> _Ran:
        process.command = command
        process.env = dict(kwargs.get("env") or {})
        return process

    monkeypatch.setattr(module.subprocess, "Popen", fake)
    return process


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    return _popen(monkeypatch, _events(["The day", ", re", "ad."]))


# ---- the process: what it is told, and what it is not


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


def test_the_narration_is_isolated_from_the_developers_world(ran: _Ran) -> None:
    """The cost fix, asserted flag by flag. A bare `claude -p` inherited 43 skills, 6 MCP
    servers, 8 subagents and the hooks — 32,541 cache-creation tokens and USD 0.33 to write
    three lines. Losing one of these flags silently restores that bill."""
    narrate("# a dossier")
    assert "--setting-sources=" in ran.command, "no skills, subagents or hooks"
    assert "--strict-mcp-config" in ran.command, "no MCP servers"
    assert "--max-turns" in ran.command, "one answer, not an agent loop"
    assert ran.command[ran.command.index("--tools") + 1] == "", "reads nothing, runs nothing"


def test_the_command_asks_for_partial_messages(ran: _Ran) -> None:
    """`stream-json` alone emits ONE line with the finished text; the deltas need
    `--include-partial-messages`, which is refused without `--verbose`."""
    narrate("x")
    assert ran.command[:2] == ["claude", "-p"], "one-shot, so no session is left behind"
    for flag in ("--output-format", "stream-json", "--verbose", "--include-partial-messages"):
        assert flag in ran.command


def test_the_model_sees_the_dossier_and_the_rules(ran: _Ran) -> None:
    narrate("# 2026-07-28 — 2 closed")
    prompt = ran.command[2]
    assert "# 2026-07-28 — 2 closed" in prompt
    assert "Invent NOTHING" in prompt


def test_a_model_override_is_passed_through(ran: _Ran) -> None:
    narrate("x", model="claude-haiku-4-5")
    assert ran.command[-2:] == ["--model", "claude-haiku-4-5"]


# ---- the event stream


@pytest.mark.usefixtures("ran")
def test_only_the_TEXT_deltas_are_read() -> None:
    """Thinking deltas arrive first and carry `text: None`. Yielding one crashes the join, so
    the filter is on the delta's TYPE and never on the key being present."""
    assert narrate("x") == "The day, read."


@pytest.mark.usefixtures("ran")
def test_the_prose_reaches_the_watcher_while_it_is_written() -> None:
    """The whole point of the card: the caller sees the fragments, in order, before the
    process has exited."""
    seen: list[str] = []
    narrate("x", on_text=seen.append)
    assert seen == ["The day", ", re", "ad."]


def test_a_line_that_is_not_json_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    _popen(monkeypatch, ["a warning nobody asked for", _delta("Fine."), _result()])
    assert narrate("x") == "Fine."


def test_a_failed_result_is_raised_with_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _popen(monkeypatch, [_delta("half a "), _result(is_error=True, result="usage limit")])
    with pytest.raises(NarrationFailed, match="usage limit"):
        narrate("x")


def test_the_process_is_always_killed(ran: _Ran) -> None:
    """A terminal closed mid-narration must not leave an orphan `claude` holding a
    subscription slot — so the kill is in a `finally`, not on the happy path."""
    narrate("x")
    assert ran.killed == 1


def test_a_dribbling_process_is_bounded_by_the_deadline(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """`wait(timeout=)` only bounds the time AFTER stdout closes, so the clock is read on
    every line instead. Here it is already past when the second line arrives."""
    process = _popen(monkeypatch, [_delta("slow"), _delta("er"), _result()])
    ticks = iter([0.0, 0.0, 5.0, 5.0, 5.0])
    monkeypatch.setattr(module, "now", lambda: next(ticks))
    with pytest.raises(NarrationFailed, match="abandoned"):
        narrate("x", timeout=1.0)
    assert process.killed == 1


def test_a_missing_binary_says_what_writes_the_narration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(command: list[str], **_: Any) -> None:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(module.subprocess, "Popen", absent)
    with pytest.raises(NarrationFailed, match="not on PATH"):
        narrate("x")


def test_an_empty_answer_is_a_failure_not_a_blank_section(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """A CLI that is installed but not logged in exits 0 and says nothing, and a report whose
    narration is an empty section reads as a taskops bug rather than a login problem."""
    _popen(monkeypatch, [_result()])
    with pytest.raises(NarrationFailed, match="logged in"):
        narrate("x")


def test_a_nonzero_exit_carries_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _popen(monkeypatch, [])
    process.returncode = 1
    process.stderr = _Reader("Invalid API key\n")
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

    def fake(command: list[str], **_: Any) -> _Ran:
        seen.prompts.append(command[2])
        return _Ran(_events([f"part {len(seen.prompts)}"]))

    monkeypatch.setattr(module.subprocess, "Popen", fake)
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


def test_every_pass_is_announced_with_its_place_in_the_run(counted: _Counted) -> None:
    """`▸ narrating 2/5` is the difference between a long run that is legibly alive and one
    that reads as a hang — which is how this was reported."""
    passes: list[tuple[int, int]] = []
    narrate(_long_dossier(12), on_pass=lambda n, total: passes.append((n, total)))
    assert [n for n, _ in passes] == list(range(1, len(counted.prompts) + 1))
    assert {total for _, total in passes} == {len(counted.prompts)}


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
