"""The written report as a FILE: a fingerprint, the dossier, and a slot for a narration.

Separate from `render_day` because the two have different readers. The dossier is printed to
a terminal and posted into a reply; this is the thing that lands in `.taskops/reports/` and
gets committed, and it carries two lines the terminal version must never have — a machine
header, and an empty section a human or a session is expected to fill in.

Pure like everything else here: given a stamp and a dossier it is a string, so the shape of a
committed report is testable without a database, a clock or a disk.
"""

from __future__ import annotations

__all__ = ["render_report", "NARRATION", "PENDING"]

NARRATION = "## Narración"
"""The section `/taskops:digest` replaces. A HEADING and not a comment marker, because the
file is read by people: an editor that hides the narration inside `<!-- -->` fences would be
optimising for the tool that writes it over the reader it is written for."""

PENDING = "_pendiente — generala con /taskops:digest_"
"""The placeholder body. It says how to fill it, so a report opened by somebody who has never
run the skill still tells them what is missing and what produces it."""


def render_report(stamp: str, dossier: str) -> str:
    """Header, dossier, empty narration. The narration goes LAST on purpose.

    A generated report whose first screen is prose invites the reader to trust the prose; put
    the facts first and the narration is read as a reading OF them, which is what it is.
    """
    return "\n".join([stamp, "", dossier.strip("\n"), "", NARRATION, "", PENDING, ""])
