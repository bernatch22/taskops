"""Recording what happened to a card's branch — on the BOARD, not on the machine that merged.

The merge runs on a client, because git lives there and the server has no checkout. The FACT
of it belongs on the board, because that is where `attention` reads and where the other
developer looks. Those are two different places for a project with a remote, and until this
existed the outcome was written into the local cache and stopped there: a card could be
unlanded for a week and no sweep anywhere would say so.

A row in the verb registry rather than an endpoint of its own — the rule this project keeps:
a new remote-safe verb is a ROW, and the transport stays thin.
"""

from __future__ import annotations

from pathlib import Path

from ..engine import record
from ._project import caller, project
from ._routing import read_remote_first, whoami

__all__ = ["note_landing"]


def note_landing(start: Path | str, *, task: str, ok: bool, why: str = "", trunk: str = "",
                 sha: str = "", actor: str = "") -> dict[str, object]:
    """Write the `landed` event where the board can see it."""
    body = {"task": task, "ok": ok, "why": why, "trunk": trunk, "sha": sha,
            "actor": whoami(start, actor)}
    if (answer := read_remote_first(start, "landed", body)) is not None:
        return dict(answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        record(store, task=task, actor=who, kind="landed",
               body={"ok": ok, "why": why, "trunk": trunk, "sha": sha})
        return {"ok": ok}
