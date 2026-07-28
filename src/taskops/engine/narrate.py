"""Asking Claude to read the day's dossier and write what it means.

The ONE place in taskops that calls a model, and it is deliberately the cheapest possible shape:
a subprocess running the `claude` binary the developer is already logged into. No SDK, no API
key, no dependency — the package still installs with nothing, and the narration is paid for by
the subscription rather than by the token.

**The model only ever sees the DOSSIER.** Not the transcripts, not the diffs — the facts the
report already assembled from the log. That is what keeps a narration cheap, reproducible enough
to argue with, and unable to leak a conversation into a committed file.

This module decides how a long dossier is CUT and STITCHED. What one reading costs, and how the
text reaches the caller while it is still being written, lives in `_stream`.
"""

from __future__ import annotations

from typing import Callable, Optional

from .._errors import NarrationFailed
from ._chunks import CHUNK_CHARS, slices
from ._prompts import CHUNK_PROMPT, PROMPT, STITCH_PROMPT
from ._stream import TIMEOUT, stream_narration

__all__ = ["narrate", "stream_narration", "PROMPT", "TIMEOUT", "CHUNK_CHARS"]

OnPass = Optional[Callable[[int, int], None]]
"""Told `(this pass, how many)` as each reading starts. A whole-project dossier takes several
minutes per pass, and a caller that cannot say which one is running has nothing to show but a
cursor — which is how this looked like a hang."""

OnText = Optional[Callable[[str], None]]
"""Told every delta as it arrives. The engine does not print: it hands the fragment to whoever
asked, and the transport decides whether that is a terminal, a socket, or nothing."""


def narrate(dossier: str, *, model: str = "", timeout: float = TIMEOUT,
            on_pass: OnPass = None, on_text: OnText = None) -> str:
    """The prose for one dossier. Raises `NarrationFailed` with what to do about it.

    ONE reading when the dossier fits (`_chunks.CHUNK_CHARS`), otherwise one reading per slice
    and a final pass that stitches them. The long path costs N+1 calls and is taken on purpose:
    trimming the prompt instead would produce a report that silently forgets the cards that
    happened to sort last, and nothing on the page would say so.

    Both callbacks are optional and default to nothing, so every existing caller keeps working
    and a narration nobody is watching costs exactly what it did before.
    """
    parts = slices(dossier)
    total = 1 if len(parts) == 1 else len(parts) + 1
    ask = _reader(model, timeout, total, on_pass, on_text)
    if total == 1:
        return ask(1, PROMPT + dossier)
    told = [ask(i, f"{CHUNK_PROMPT}(slice {i} of {len(parts)})\n\n{part}")
            for i, part in enumerate(parts, start=1)]
    return ask(total, STITCH_PROMPT + "\n\n---\n\n".join(told))


def _reader(model: str, timeout: float, total: int,
            on_pass: OnPass, on_text: OnText) -> Callable[[int, str], str]:
    """One pass of the narration: announced, streamed to the watcher, returned whole.

    A closure rather than five arguments threaded through every call site — the three ways a
    dossier is read (single, slice, stitch) differ only in their prompt, and that is the one
    thing the returned function takes.
    """
    def ask(n: int, prompt: str) -> str:
        if on_pass:
            on_pass(n, total)
        written: list[str] = []
        for delta in stream_narration(prompt, model=model, timeout=timeout):
            written.append(delta)
            if on_text:
                on_text(delta)
        return _said("".join(written))

    return ask


def _said(text: str) -> str:
    """The prose, never an empty string.

    A CLI that is installed but not logged in can finish cleanly having emitted no text at all,
    and a report whose narration is a blank section reads as a taskops bug rather than a login
    problem.
    """
    said = text.strip()
    if not said:
        raise NarrationFailed("claude answered with nothing — check `claude` runs and is "
                              "logged in (`claude -p hello`)")
    return said
