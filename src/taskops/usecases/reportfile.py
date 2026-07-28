"""Moving a written report between machines WITHOUT losing a narration.

The dossier in a report is regenerable — it is a rendering of the log, and the log replicates.
The NARRATION is not. It is prose a model wrote once, or a person edited by hand, and there is
no second copy anywhere. So this is the one thing in taskops that syncs with a rule instead of
a union, and the rule is built to fail LOUD rather than to be clever.

The rule, in the order it is applied:

1. The server does not have the file → store it.
2. Byte-identical to what we have → store it (a no-op, so a re-push is quiet).
3. Both sides carry a stamp and theirs is HIGHER → store it. A higher `max_seq` means that
   copy was generated over more of the log, so it is the later account of the same day.
4. Anything else → `ReportConflict`, carrying both stamps. That covers theirs being older,
   the two being equal but different, and either side being UNSTAMPED — an unstamped file was
   written or edited outside taskops, which is precisely the copy nobody may clobber.

`force` skips straight to storing, and the refusal says what would be lost so the person
choosing has the sentence in front of them.

**The server NEVER regenerates.** It serves the bytes it has. Regenerating belongs to the
machine that owns the store, because a regeneration here would replace somebody's prose with a
fresh dossier and report success.

**The honest limit of comparing stamps.** `max_seq` is each sqlite's own numbering, so two
machines' stamps are not rigorously comparable. In the real flow they are close enough to be
useful — a report is narrated against ONE store, and after a sync the server's seqs dominate —
which makes rule 3 a heuristic for "who saw more". The pathological case is two independent
narrations of the same day written on two machines that never synced; those land in rule 4,
which is the honest answer, and `force` is the valve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._errors import BadRequest, ReportConflict
from ..engine import NO_STAMP, stamped_seq
from ._project import project
from .dossier import report_path

__all__ = ["read_report_file", "write_report_file"]

_ALLOWED = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_.")
"""Labels are `2026-07-28`, `2026-07-22..2026-07-28`, `all`. A separator can never appear, so
a label from the network cannot address a path outside `.taskops/reports/`."""


def read_report_file(start: Path | str, label: str) -> dict[str, Any] | None:
    """The bytes on disk for one label, with the stamp they carry. None if there is no file.

    None and not a generated dossier: the caller is a replication client deciding whether to
    push, and answering with a report this server never wrote would make it believe there is
    something here to lose.
    """
    with project(start) as store:
        path = report_path(store.root, _checked(label))
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8")
        return {"label": label, "content": content, "max_seq": stamped_seq(content)}


def write_report_file(start: Path | str, label: str, content: str, *,
                      force: bool = False) -> dict[str, bool]:
    """Apply the rule above. Returns `{"stored": True}` or raises `ReportConflict`."""
    with project(start) as store:
        path = report_path(store.root, _checked(label))
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if force or current is None or current == content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"stored": True}
        ours, theirs = stamped_seq(current), stamped_seq(content)
        if ours != NO_STAMP and theirs > ours:
            path.write_text(content, encoding="utf-8")
            return {"stored": True}
        raise _conflict(label, ours=ours, theirs=theirs)


def _conflict(label: str, *, ours: int, theirs: int) -> ReportConflict:
    """The refusal, with the sentence that names what the caller is actually looking at."""
    clash = ReportConflict(f"{label}: {_why(ours, theirs)} — read this server's copy first, "
                           f"or push again with force (its narration is then lost)")
    clash.ours, clash.theirs = ours, theirs
    return clash


def _why(ours: int, theirs: int) -> str:
    if NO_STAMP in (ours, theirs):
        return ("one of the two copies carries no taskops stamp, so it was written or edited "
                "by hand and nothing can tell which is newer")
    if ours == theirs:
        return (f"two different narrations of the same report, both generated at seq {ours} — "
                f"prose cannot be merged and nobody here can pick")
    return (f"this server's copy was generated at seq {ours} and yours at {theirs}, so yours "
            f"saw LESS of the log")


def _checked(label: str) -> str:
    text = label.strip()
    if not text or text.startswith(".") or not set(text) <= _ALLOWED:
        raise BadRequest(f"{label!r} is not a report label — it names a file in "
                         f".taskops/reports/, like `2026-07-28` or `all`")
    return text
