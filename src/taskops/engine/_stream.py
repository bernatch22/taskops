"""One `claude` process, read a delta at a time — and stripped of the developer's world.

Split from `narrate` because two different things live here. `narrate` decides how a dossier is
cut and stitched; this decides what a single reading COSTS and how soon the caller sees it.

**Why streaming at all.** `subprocess.run(capture_output=True)` returns nothing until the process
exits, and a whole-project dossier is narrated in several passes of minutes each — so
`report all --digest` showed an empty terminal for a quarter of an hour and read as a hang. It
was reported as one. `--output-format stream-json` on its own does NOT fix that: it emits a
single line carrying the finished text. Partial output needs `--include-partial-messages`, which
in turn requires `--verbose` and `-p`.

The wire format itself — which line means what, and the trap in it — is read by `_events`.
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterator

from .._clock import now
from .._errors import NarrationFailed
from ._events import check_result, parsed, text_delta
from .worker import DROPPED_ENV

__all__ = ["stream_narration", "TIMEOUT", "ISOLATION"]

TIMEOUT = 900.0
"""Seconds before ONE reading is abandoned. Long enough for a real read, short enough that
`--digest` cannot hang a terminal somebody left running forever.

240s until a slice of `report all` on axion-v3 (45 closed cards, 340 KB of dossier) ran past
it and the whole digest was thrown away after twenty minutes of work — five good slices lost
with it, which is the worst outcome available.
"""

ISOLATION = ("--tools", "", "--max-turns", "1", "--setting-sources=", "--strict-mcp-config")
"""What a bare `claude -p` must NOT inherit. This is the cost fix, and it is most of the clock.

Measured on this machine against claude CLI 2.1.220: a bare `claude -p` loaded the developer's
whole world — 43 skills, 6 MCP servers, 8 subagents and the hooks — and spent **32,541
cache-creation tokens and USD 0.33 to write three lines**. Every flag deletes one source of it:
`--setting-sources=` (empty) drops the user, project and local settings files, which is where the
skills, the subagents and the hooks come from; `--strict-mcp-config` drops the MCP servers, whose
tool schemas are the bulk of that prompt; `--tools ""` says the narrator reads no files and runs
no commands, because it is handed the dossier and has nothing to look up; `--max-turns 1` makes
that literal — one answer, no agent loop.

The narration is a paragraph about a text the caller already has. None of that machinery could
have helped it, and all of it was being paid for on every pass.
"""

_STREAM = ("--output-format", "stream-json", "--verbose", "--include-partial-messages")
"""Ask for deltas. `--include-partial-messages` is the one that streams; it is refused without
`--verbose`, and `stream-json` alone emits one line with the finished text."""


def stream_narration(prompt: str, *, model: str = "",
                     timeout: float = TIMEOUT) -> Iterator[str]:
    """The prose of one reading, in the order it is written. Raises `NarrationFailed`.

    A plain synchronous generator: the engine is sync and tested that way, and a narration is
    one process read line by line, which asyncio would buy nothing for.
    """
    command = ["claude", "-p", prompt, *_STREAM, *ISOLATION]
    if model:
        command += ["--model", model]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1, env=_env())
    except FileNotFoundError as missing:
        raise NarrationFailed(
            "`claude` is not on PATH — the narration is written by the Claude Code CLI you are "
            "already logged into. Install it, or write the section by hand") from missing
    try:
        yield from _deltas(process, now() + timeout, timeout)
    finally:
        # Unconditional: a terminal killed mid-narration must not leave an orphan `claude`
        # holding a subscription slot, and a generator abandoned early lands here too.
        process.kill()
        process.wait()


def _deltas(process: "subprocess.Popen[str]", deadline: float, timeout: float) -> Iterator[str]:
    """Text deltas until the `result` event, refusing to run past the deadline.

    `wait(timeout=)` alone would only bound the time AFTER stdout closes, so a process that
    dribbles a byte a minute would never hit it. The clock is read on every line instead.
    """
    if process.stdout is None:                       # pragma: no cover - PIPE was requested
        raise NarrationFailed("claude produced no output stream")
    for line in process.stdout:
        if now() > deadline:
            raise NarrationFailed(f"the narration took longer than {int(timeout)}s and was "
                                  f"abandoned — the dossier is still on disk")
        event = parsed(line)
        if event.get("type") == "result":
            check_result(event)
            return
        text = text_delta(event)
        if text:
            yield text
    _ended(process)


def _ended(process: "subprocess.Popen[str]") -> None:
    """stdout closed with no `result`. Say why, using whatever the process left behind."""
    process.wait()
    said = (process.stderr.read() if process.stderr else "").strip().splitlines()
    if process.returncode:
        raise NarrationFailed(f"claude exited {process.returncode}: "
                              f"{said[-1] if said else 'no output'}")
    raise NarrationFailed("claude answered with nothing — check `claude` runs and is "
                          "logged in (`claude -p hello`)")


def _env() -> dict[str, str]:
    """The developer's environment, minus the API credentials.

    `worker.DROPPED_ENV` names them and the reason is identical here: an exported
    `ANTHROPIC_API_KEY` makes the CLI bill per token while the subscription sits unused. One
    constant, two callers — and it is why this stays a subprocess: the flag-translating SDK
    merges its `env` over the parent's, so it cannot DELETE a variable, only add one.
    """
    kept = dict(os.environ)
    for name in DROPPED_ENV:
        kept.pop(name, None)
    return kept
