"""Reports across the wire — the half of sync that can destroy something irrecoverable.

Events are safe to move in bulk: they are facts with content-hash ids, so the union of two
logs is the correct log. A report is not. Its dossier regenerates from the log any time, but
the NARRATION under it was written once — by a model somebody paid for, or by a person — and
nothing in the system can reconstruct it. So the rule here is the opposite of the one for
events: never overwrite, ever, unless a human said `--force` after reading what they would
lose.

The comparison is `stamped_seq`: line one of every generated report carries the log's
`max_seq` at the moment it was rendered, so a larger stamp means "this copy saw more of the
history". It is a HEURISTIC and worth saying so — two machines number their own sqlite rows,
so the stamps are strictly comparable only once both have synced. The pathological case (two
independent narrations of the same day, neither machine having seen the other) falls to the
server's equal-seq-different-content 409, which is the honest answer: nobody can decide that
one for you.

This module never regenerates a dossier. Owning the store is what earns the right to render,
and a client that "helpfully" re-rendered what it downloaded would be uploading a report the
server has never seen the events for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import stamped_seq
from ..storage import REPORTS_DIR
from ._wireclient import Wire
from .dossier import report_path

__all__ = ["ReportSwap", "exchange"]


class ReportSwap:
    """Which reports moved, and which ones refused to."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.downloaded: list[str] = []
        self.conflicts: list[str] = []
        """One sentence per stand-off, naming BOTH seqs and the two ways out. A count would
        be useless: the answer is per report, and it is `pull` for one and `--force` for the
        next."""


def exchange(wire: Wire, root: Path, *, upload: bool, force: bool = False) -> ReportSwap:
    """Reconcile every report both sides know about. `upload` is False on a plain `pull`.

    The STAMPS come first, in one request, and they are what keeps this cheap: a label whose server
    copy is not newer than ours needs no body, and on a plain pull it needs nothing at all. Before
    that, every label was downloaded in full to read one number out of it — eleven seconds on a pull
    with nothing to bring, paid by every write, because a write pulls.

    `None` from `report_stamps` means the server cannot say (an older one), and then this does what
    it always did. Slow is a fine answer to "that server is older"; wrong is not.
    """
    swap = ReportSwap()
    stamps = wire.report_stamps()
    for label in _labels(wire, root):
        if _settled(root, label, stamps, upload=upload):
            continue
        _reconcile(wire, root, label, swap, upload=upload, force=force)
    return swap


def _settled(root: Path, label: str, stamps: dict[str, int] | None, *, upload: bool) -> bool:
    """True when this label needs no request at all.

    Only ever on a PULL. With `upload` the local copy may be the newer one and the decision needs
    the server's content to compare against, so a push still fetches — the asymmetry is the point:
    a pull asks "is there anything for me", a push also asks "is there anything of mine".
    """
    if stamps is None or upload:
        return False
    path = report_path(root, label)
    if not path.is_file():
        return False        # we have nothing, so anything the server holds is newer
    return stamps.get(label, -1) <= stamped_seq(path.read_text(encoding="utf-8"))


def _reconcile(wire: Wire, root: Path, label: str, swap: ReportSwap, *,
               upload: bool, force: bool) -> None:
    path = report_path(root, label)
    ours = path.read_text(encoding="utf-8") if path.is_file() else ""
    theirs = wire.get_report(label)
    if not _served(theirs):
        if upload and ours:
            _send(wire, label, ours, swap, force=force)
        return
    content = str(theirs.get("content", ""))
    if not ours or int(theirs.get("max_seq", 0) or 0) > stamped_seq(ours):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        swap.downloaded.append(label)
    elif upload and content != ours:
        _send(wire, label, ours, swap, force=force)


def _send(wire: Wire, label: str, text: str, swap: ReportSwap, *, force: bool) -> None:
    answer = wire.put_report(label, text, force=force)
    if answer.get("status") == 409:
        swap.conflicts.append(_clash(label, answer, stamped_seq(text)))
    else:
        swap.uploaded.append(label)


def _clash(label: str, answer: dict[str, Any], mine: int) -> str:
    """The 409 in a sentence. Note the INVERSION: the body's `ours` is the SERVER's copy and
    its `theirs` is what we just offered, because the server wrote it from where it stands."""
    server = int(answer.get("ours", 0) or 0)
    ours = int(answer.get("theirs", mine) or mine)
    return (f"{label}: the server's copy is stamped at seq {server}, yours at {ours} — "
            f"nothing was overwritten. Run `taskops pull` to take the server's, or "
            f"`taskops push --force` to replace it (any narration there is lost).")


def _served(answer: dict[str, Any]) -> bool:
    return answer.get("status") is None and "content" in answer


def _labels(wire: Wire, root: Path) -> list[str]:
    """Every label either side has, sorted so the output is stable.

    The server's list is best-effort (`Wire.list_reports` explains why): on a server without
    that route this degrades to the labels on this disk, which still reconciles everything
    this machine has ever written — only a report that exists SOLELY on the server stays out
    of reach, and it arrives the moment anyone here generates that window.
    """
    directory = root / REPORTS_DIR
    local: set[str] = set()
    if directory.is_dir():
        local = {path.stem for path in directory.glob("*.md")}
    return sorted(local | set(wire.list_reports()))
