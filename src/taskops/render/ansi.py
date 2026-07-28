"""Markdown for a terminal, rendered as it arrives. taskops' first ansi vocabulary.

A narration is streamed a delta at a time, and a delta is not a line: it splits words, and it
splits `**bo` from `ld**`. So nothing may be styled until the line it belongs to is COMPLETE —
`Ink.feed` buffers fragments and hands back only the lines that have ended. Anything else
produces a `**` that never closes and an escape sequence in the middle of a word.

Pure, like everything in `render/`: fragments in, rendered lines out. Nothing here prints, opens
a file, or asks whether it is talking to a terminal — the transport that owns stdout decides
that and passes the answer in. With `colour=False` a line comes back byte for byte as it went
in, which is exactly what the digest used to emit, so the plain path costs nothing and a
redirected `--digest` is unchanged.

ANSI never reaches the FILE. The report on disk is written from the joined text, not from this.
"""

from __future__ import annotations

import re

from ._text import STATUS_MARK

__all__ = ["Ink", "BULLET"]

RESET = "\033[0m"
BOLD = "\033[1m"
TITLE = "\033[1;4m"
"""Bold + underline, for `#` only. A narration's one top-level heading is the report's own
title; every deeper level is a section inside it and gets plain bold."""
CODE = "\033[36m"

BULLET = STATUS_MARK["backlog"]
"""The glyph a `- ` becomes. Borrowed from the board's register rather than chosen here: two
vocabularies for "a small thing in a list" is how a terminal ends up with `•` in one command
and `·` in the next, and the reader learns neither."""

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_BULLET = re.compile(r"^(\s*)[-*]\s+")


class Ink:
    """A stream of markdown fragments, turned into finished terminal lines."""

    def __init__(self, *, colour: bool) -> None:
        self._colour = colour
        self._held = ""
        self._fenced = False

    def feed(self, fragment: str) -> list[str]:
        """The lines COMPLETED by this fragment. Usually none — deltas are smaller than lines."""
        self._held += fragment
        if "\n" not in self._held:
            return []
        *done, self._held = self._held.split("\n")
        return [self._paint(line) for line in done]

    def flush(self) -> list[str]:
        """Whatever is left when the narration ends — a last line with no trailing newline is
        still a line, and dropping it loses the final sentence."""
        rest, self._held = self._held, ""
        return [self._paint(rest)] if rest else []

    def _paint(self, line: str) -> str:
        """One whole line, styled. Verbatim when colour is off or a fence is open.

        The fence toggles on its own line and suppresses everything inside it: `**` in a shell
        snippet is a glob, and a `#` is a comment, not a heading.
        """
        if line.lstrip().startswith("```"):
            self._fenced = not self._fenced
            return line
        if not self._colour or self._fenced:
            return line
        head = _HEADING.match(line)
        if head:
            # No inline pass over a heading: an inner RESET would end the heading's own style
            # halfway through it, and the rest of the title would come out plain.
            mark = TITLE if len(head.group(1)) == 1 else BOLD
            return f"{mark}{head.group(2)}{RESET}"
        return _spans(_BULLET.sub(rf"\1{BULLET} ", line))


def _spans(text: str) -> str:
    """Inline styling, applied only WITHIN a finished line.

    Never across the buffer: a `**` whose partner is in the next fragment is not emphasis yet,
    and treating it as one emits an opening escape that nothing ever closes.
    """
    text = _CODE.sub(rf"{CODE}\1{RESET}", text)
    return _BOLD.sub(rf"{BOLD}\1{RESET}", text)
