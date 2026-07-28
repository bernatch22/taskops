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
from ._chunks import CHUNK_CHARS, slices
from ._prompts import CHUNK_PROMPT, PROMPT, STITCH_PROMPT
from .worker import DROPPED_ENV

__all__ = ["narrate", "PROMPT", "TIMEOUT", "CHUNK_CHARS"]

TIMEOUT = 900.0
"""Seconds before ONE reading is abandoned. Long enough for a real read, short enough that
`--digest` cannot hang a terminal somebody left running forever.

240s until a slice of `report all` on axion-v3 (45 closed cards, 340 KB of dossier) ran past
it and the whole digest was thrown away after twenty minutes of work — five good slices lost
with it, which is the worst outcome available. The number was sized for a single day's dossier
answered in three paragraphs; the prompt now asks for a paragraph per card over a slice of up
to `CHUNK_CHARS`, and that is minutes of generation, not seconds.
"""


def narrate(dossier: str, *, model: str = "", timeout: float = TIMEOUT) -> str:
    """The prose for one dossier. Raises `NarrationFailed` with what to do about it.

    ONE reading when the dossier fits (`_chunks.CHUNK_CHARS`), otherwise one reading per slice
    and a final pass that stitches them. The long path costs N+1 calls and is taken on purpose:
    trimming the prompt instead would produce a report that silently forgets the cards that
    happened to sort last, and nothing on the page would say so.
    """
    parts = slices(dossier)
    if len(parts) == 1:
        return _ask(PROMPT + dossier, model, timeout)
    told = [_ask(f"{CHUNK_PROMPT}(slice {i} of {len(parts)})\n\n{part}", model, timeout)
            for i, part in enumerate(parts, start=1)]
    return _ask(STITCH_PROMPT + "\n\n---\n\n".join(told), model, timeout)


def _ask(prompt: str, model: str, timeout: float) -> str:
    """One `claude` process, one prompt.

    `-p` is one-shot mode: no session is resumed and none is left behind, so running this twice
    cannot produce a conversation that drifts — and so the slices of a chunked narration cannot
    contaminate each other.
    """
    command = ["claude", "-p", prompt]
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
