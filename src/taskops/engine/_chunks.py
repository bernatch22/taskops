"""Cutting a long dossier into slices a single reading can actually cover.

A full-detail dossier for a whole project is not three paragraphs of facts: it is every card's
spec, every comment, every file of every commit. Handed to one call it fits in the window long
before it fits in the attention — the answer stops enumerating and starts summarising, which
is precisely the failure this card exists to fix.

So past a threshold the dossier is read in slices and the parts are stitched. The alternative
somebody always reaches for — trimming the prompt to fit — is banned outright: a report that
silently omits the last nine cards is worse than one that took three calls to write.

Pure: given a string it returns strings. The model lives in `narrate`.
"""

from __future__ import annotations

__all__ = ["CHUNK_CHARS", "slices"]

CHUNK_CHARS = 60_000
"""Roughly 15k tokens of dossier per reading.

Not a context limit — the window is far larger. It is an ATTENTION budget, measured against
what the prompt asks for: a paragraph per card, naming that card's spec, files and comments.
Past this much input a single answer reliably starts collapsing cards into sentences, and the
narration silently becomes the summary it was supposed to replace. Lower, and a project pays
for stitching it does not need.
"""

_BOUNDARIES = ("### ", "✓ **")
"""Where a slice may be cut: a day heading in a range report, or a card block. Never mid-card —
half a card's commits under one reading and half under another produces two partial paragraphs
about the same work, and the stitch has no way to know they are the same card.
"""


def slices(dossier: str, limit: int = CHUNK_CHARS) -> list[str]:
    """The dossier as one string, or as several that each start with its title line.

    The header — everything above the first card — rides along on EVERY slice, because it
    carries the window, the counts and the language the narration must be written in.
    """
    if len(dossier) <= limit:
        return [dossier]
    head, blocks = _split(dossier)
    out: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) > limit:
            out.append(head + current)
            current = ""
        current += block
    return [*out, head + current] if current else out or [dossier]


def _split(dossier: str) -> tuple[str, list[str]]:
    """`(header, blocks)`, where a block starts at a boundary line and runs to the next one."""
    head: list[str] = []
    blocks: list[list[str]] = []
    for line in dossier.splitlines(keepends=True):
        if line.startswith(_BOUNDARIES):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            head.append(line)
    return "".join(head), ["".join(block) for block in blocks]
