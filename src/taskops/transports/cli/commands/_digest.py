"""`report … --digest` in a terminal: the narration as it is being written.

Its own module because it is the only command that takes MINUTES, and the only one that writes
to stdout before it returns. Everything else here renders a finished answer and hands back a
string for `main` to print.

The user's report was "esto nunca terminó": `report all --digest` on a real project narrates a
whole-project dossier in several passes, and with the output captured the terminal showed
nothing at all for a quarter of an hour. Nothing was broken — nothing was VISIBLE. So this
prints a header before the first pass, names each pass as it starts, and renders the prose live.

The FILE is untouched by any of it: `digest` writes the joined text, and no escape sequence ever
reaches disk.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import IO

from ...._clock import now
from ....render import Ink
from ....usecases import Selector, digest

__all__ = ["stream_digest"]


def stream_digest(where: Path, sel: Selector, *, kind: str, model: str = "",
                  force: bool = False, out: IO[str] | None = None) -> str:
    """Narrate the window, showing it happen. Returns the line `main` prints at the end."""
    to = out or sys.stdout
    ink = Ink(colour=_colour(to))
    started = now()

    def show(text: str) -> None:
        for line in ink.feed(text):
            print(line, file=to)
        to.flush()

    def announce(n: int, total: int) -> None:
        for line in ink.flush():
            print(line, file=to)
        print(f"\n▸ narrating {n}/{total} …" if total > 1 else "", file=to)
        to.flush()

    print(f"▸ reading the {kind} dossier of {where} — this calls Claude and takes minutes",
          file=to)
    to.flush()
    path = digest(where, sel, model=model, force=force, on_pass=announce, on_text=show)
    for line in ink.flush():
        print(line, file=to)
    return f"\nnarrated {path} in {now() - started:.0f}s"


def _colour(to: IO[str]) -> bool:
    """Whether to style at all — decided HERE and not in the renderer, which is pure.

    A pipe, a file and a CI log get the markdown verbatim, which is byte for byte what this
    command emitted before it streamed. `NO_COLOR` is honoured because a person who set it
    means every tool, not the ones that remembered.
    """
    return bool(getattr(to, "isatty", bool)()) and not os.environ.get("NO_COLOR")
