"""The narration reaching the FILE while it is still being written.

The first version wrote the prose once, at the end. On a day that is one reading that is
thirty seconds of `_pendiente_`; on `report all`, which narrates in several passes, it is a
quarter of an hour during which the file on disk is indistinguishable from one nobody ever
narrated — and if the process dies at minute fourteen, that is exactly what it becomes.

So the text is flushed as it arrives: every `FLUSH_CHARS` of prose, and at every pass
boundary. A flush is a whole-file rewrite through `render.narrated`, which is the same call
the final write makes, so a partial file is never a different SHAPE of file — only a shorter
one. Nothing here decides anything; it is the writing half of `dossier.digest`.
"""

from __future__ import annotations

from pathlib import Path

from ..engine import OnPass, OnText
from ..render import narrated

__all__ = ["Progressive", "FLUSH_CHARS"]

FLUSH_CHARS = 400
"""Prose written since the last flush before the file is rewritten. Roughly a paragraph.

A report is tens of kilobytes and a narration arrives over minutes, so this is a handful of
rewrites per pass — cheap enough to ignore, frequent enough that a person watching the file
sees it grow rather than jump.
"""


class Progressive:
    """Wraps a caller's callbacks so the same deltas also land on disk as they arrive."""

    def __init__(self, path: Path, report: str, *,
                 on_pass: OnPass = None, on_text: OnText = None) -> None:
        self._path = path
        self._report = report
        self._on_pass = on_pass
        self._on_text = on_text
        self._written: list[str] = []
        self._chars = 0
        self._flushed = 0

    def text(self, delta: str) -> None:
        """A fragment: keep it, pass it on, and flush once enough has piled up."""
        self._written.append(delta)
        self._chars += len(delta)
        if self._on_text:
            self._on_text(delta)
        if self._chars - self._flushed >= FLUSH_CHARS:
            self.flush()

    def passed(self, n: int, total: int) -> None:
        """A pass is starting, so the previous one is complete — the natural moment to flush."""
        self.flush()
        if self._on_pass:
            self._on_pass(n, total)

    def finish(self, prose: str) -> Path:
        """The FINAL write, from the text `narrate` returned rather than from the fragments.

        Not the same string as the last flush, and that is why this exists: a multi-pass
        narration returns the STITCHED reading, not the concatenation of the slices somebody
        watched go by. The partial file is a live view; this is the document.
        """
        self._path.write_text(narrated(self._report, prose), encoding="utf-8")
        return self._path

    def flush(self) -> None:
        """The report as it stands, narrated with the prose so far. A no-op before the first
        delta, because a file whose narration section is empty reads as a taskops bug."""
        prose = "".join(self._written)
        if not prose.strip():
            return
        self._path.write_text(narrated(self._report, prose), encoding="utf-8")
        self._flushed = self._chars
