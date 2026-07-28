"""Asking Claude to read the day's dossier and write what it means.

The ONE place in taskops that calls a model, and it is deliberately the cheapest possible shape:
a subprocess running the `claude` binary the developer is already logged into. No SDK, no API
key, no dependency — the package still installs with nothing, and the narration is paid for by
the subscription rather than by the token.

**The credential rule is inherited, not re-decided.** `worker.DROPPED_ENV` names the variables a
spawned agent must not see, and the reason is identical here: an exported `ANTHROPIC_API_KEY`
makes the CLI bill per token while the plan sits unused. One constant, two callers.

**The model only ever sees the DOSSIER.** Not the transcripts, not the diffs — the facts the
report already assembled from the log. That is what keeps a narration cheap, reproducible enough
to argue with, and unable to leak a conversation into a committed file.
"""

from __future__ import annotations

import os
import subprocess

from .._errors import NarrationFailed
from .worker import DROPPED_ENV

__all__ = ["narrate", "PROMPT", "TIMEOUT"]

TIMEOUT = 240.0
"""Seconds before the narration is abandoned. Long enough for a real read of a busy day, short
enough that `--digest` cannot hang a terminal somebody left running."""

PROMPT = """You are writing the narration section of a daily engineering report.

Below is the day's dossier: what closed, the commits with their diff sizes, the conversation, and
a roll-up per actor. It was generated from an append-only event log, so every fact in it is true.

Write the narration in the SAME LANGUAGE the cards and comments are written in.

Rules:
- Lead with what needs a human: anything blocked, anything still claimed, anything that looks
  wrong. If there is nothing, say so in one line and move on.
- Then the day in one sentence, and then what changed grouped BY WHAT IT IS FOR, not by card id.
- Name the decisions and the surprises — the thing a reader would not guess from the titles.
- Invent NOTHING. Every claim must trace to a line in the dossier. If the dossier is thin, the
  narration is short; a padded report is worse than a brief one.
- Do not flatter anybody and do not editorialise about pace.
- Markdown, no top-level heading (the section already has one).

Output ONLY the narration text.

--- DOSSIER ---
"""


def narrate(dossier: str, *, model: str = "", timeout: float = TIMEOUT) -> str:
    """The prose for one dossier. Raises `NarrationFailed` with what to do about it.

    `-p` is one-shot mode: no session is resumed and none is left behind, so running this twice
    cannot produce a conversation that drifts.
    """
    command = ["claude", "-p", PROMPT + dossier]
    if model:
        command += ["--model", model]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              check=False, env=_env())
    except FileNotFoundError as missing:
        raise NarrationFailed(
            "`claude` is not on PATH — the narration is written by the Claude Code CLI you are "
            "already logged into. Install it, or write the section by hand") from missing
    except subprocess.TimeoutExpired as slow:
        raise NarrationFailed(f"the narration took longer than {int(timeout)}s and was "
                              f"abandoned — the dossier is still on disk") from slow
    return _text(done)


def _text(done: "subprocess.CompletedProcess[str]") -> str:
    """The prose, or the reason there is none. Never returns empty silently.

    An empty answer with a zero exit is the failure mode of a CLI that is installed but not
    logged in, and a report whose narration is a blank section reads as a taskops bug.
    """
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise NarrationFailed(f"claude exited {done.returncode}: "
                              f"{detail[-1] if detail else 'no output'}")
    said = done.stdout.strip()
    if not said:
        raise NarrationFailed("claude answered with nothing — check `claude` runs and is "
                              "logged in (`claude -p hello`)")
    return said


def _env() -> dict[str, str]:
    """The developer's environment, minus the API credentials."""
    kept = dict(os.environ)
    for name in DROPPED_ENV:
        kept.pop(name, None)
    return kept
