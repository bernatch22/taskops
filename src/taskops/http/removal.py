"""`board.remove` — the one call in taskops that destroys, and the wall in front.

    {"verb": "board.remove", "args": {"board": "facturador", "held": ["<id>", …]}}
    {"verb": "board.remove", "args": {"board": "facturador", "discard_history": true}}

Until this existed a board could only be taken off a host by ssh-ing to the box
and running `rm -rf` on a directory — the same anomaly `http/admin.py` closed for
creating one, except this end of it deletes the only copy of a history nobody can
regenerate. So the door exists, and the guardrail is the door.

**`held` is what the CALLER can still read, and the judgement is made HERE.**
The client sends the event ids its own copy holds; this side compares them
against the ids the board REALLY has (`core/holding.py`, `theirs ⊆ mine`) and
refuses if anything would be lost. Judging on the client would make the wall a
convention — a hand-written call could skip it and never say so. Judging on the
host means the only way past it is `discard_history`, typed on purpose.

**The flag is named for the thing it destroys.** `--force` is banned here
(ARCHITECTURE.md §11) because it says nothing about what it overrides, and this
is the last command that should be vague about that. Only a literal `true` opens
it: a caller that sends the string "false" is refused rather than obeyed.

**Nothing is recorded.** The board is the log, so the log is gone — a removal has
no board left to write itself into, and recording it on a DIFFERENT board would
be one board holding another's history. What survives instead is the ANSWER: what
was removed and how many events went with it, because a human deserves to see the
size of what they just did while the terminal is still open.

**The handle is dropped before the directory is.** `Mounts` keeps a `Stores` per
board for the life of the process, and an sqlite connection to an unlinked file
keeps answering: without `Mounts.forget` the cache would outlive the removal and
`board.create` on the same name would hand the destroyed history straight back —
which is exactly the smuggling route `board.ingest`'s two-histories wall exists
to close. (The note in `ingest.py::_configuration` is where that bug was first
written down.)
"""

from __future__ import annotations

import shutil
from typing import Any

from ..core import holding
from .mounts import Mounts, named
from .._errors import Refused, NotFound

NO_BOARD = (
    "no board named {name!r} on this host — nothing was removed. `taskops board ls` "
    "says what it actually holds"
)

UNHELD = (
    "removing {name!r} would destroy a history nothing else holds: {gap}. "
    "Two ways forward, and both are explicit:\n"
    "  taskops board pull {name}                    take the history down first, then remove\n"
    "  taskops board rm {name} --discard-history    destroy it anyway; say so out loud\n"
    "(there is no --force: a flag that does not name what it overrides is how somebody "
    "destroys a history they meant to keep.)"
)


def run(mounts: Mounts, args: dict[str, Any], actor: str) -> dict[str, Any]:
    """Take a board off this host. Owner only; gated by `core/scope.py` first.

    The order is the safety, exactly as `cli/push.py`'s is: the board is opened,
    its real ids are read, the comparison is made, and only past all three does
    anything on disk change. A refusal at any point leaves the board untouched.
    """
    name = named(str(args.get("board", "")).strip())
    try:
        stores = mounts.stores(name)
    except NotFound as err:
        raise NotFound(NO_BOARD.format(name=name)) from err

    state = holding.compare(stores.ids(), _held(args))
    if not state["complete"] and args.get("discard_history") is not True:
        raise Refused(UNHELD.format(name=name, gap=holding.phrase(state)))

    mounts.forget(name)
    shutil.rmtree(mounts.root / name)
    return {
        "board": name,
        "removed": True,
        # Read BEFORE the delete, from the board itself — the number a human is
        # about to be shown is the size of what is now gone, not a count the
        # caller sent in and had echoed back.
        "events": state["theirs"],
        "held_elsewhere": state["complete"],
        "gap": holding.phrase(state),
        "by": actor,
    }


def _held(args: dict[str, Any]) -> list[str]:
    """The ids the caller says it still holds — absent means NONE, deliberately.

    A missing `held` is the ordinary case (a checkout that never pulled), and the
    honest answer to "what do you hold" is nothing; a malformed one is treated the
    same way rather than raising, because both land on the refusal that names the
    two ways out, which is more useful than an argument error.
    """
    raw = args.get("held")
    if not isinstance(raw, list):
        return []
    items: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
    return [item for item in items if isinstance(item, str)]
