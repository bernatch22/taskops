"""filed — a committed report is put on a chapter. The registration DOOR.

Registering is an ACT, never a side effect of committing: a file that appears
under `.taskops/reports/` is just a file, exactly as a commit that names no card
is just a commit (`record.py::bind`). Somebody DECIDED to say this — the board
records the decision, and "I wrote it but never announced it" stays expressible.

The event carries a POINTER and never the prose: `{path, title, milestone,
sha}`, four short strings, so a 200KB narration grows `events.jsonl` by a few
hundred bytes. The bytes are fetched from the reader's own clone at that sha.
The vocabulary and the shape rule are `core/reports.py`; this is the write half.

**Why a verb of its own, and not an op on `project` or on `update`.** A project
fact is ONE value per `op`, folded newest-wins — recording the same one twice
writes nothing and a newer one REPLACES the older (`verbs/project.py`). Reports
are the opposite shape: an append-only series where every entry stays, and
nothing about a second report withdraws the first. Bolting them onto that
surface would put two folds behind one verb, which is how `op` families rot.
`update` is no better a home: it is about a CARD, and a report is about a
CHAPTER. So, a small write of its own, open to BOTH roles — the orchestrator
narrating a landed chapter and a worker filing what it found are the same act,
and the board has no third role to invent for it.

**Idempotent by the same rule as everywhere else.** Filing the same `path` at
the same `sha` twice writes nothing and says so (`recorded: false`): the log has
no delete, so a retry after a dropped connection must not leave two rows in a
list a screen draws. A NEW sha at the same path IS a new report — the file was
rewritten — and both stay in the history, each with the commit it lived at.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts
from .. import _clock
from ..core import reports
from .._errors import Refused, NotFound, BadRequest
from ..core.event import make
from ..core.types import PROJECT, Milestone
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    """`path`, `title`, `sha`, and the chapter — named, or the single open one."""
    now = _clock.now()
    stone = _chapter(stores, _args.text(args, "milestone", default=""))
    body: dict[str, Any] = {
        "path": _path(args),
        "title": _said(args, "title"),
        "milestone": stone["id"],
        "sha": _said(args, "sha"),
    }
    stores.live.renew(actor, now)
    same = [
        row
        for row in reports.of(stores.events(PROJECT))
        if row["path"] == body["path"] and row["sha"] == body["sha"]
    ]
    if same:
        return {"report": same[0], "recorded": False, "seq": stores.head()}
    event = make(PROJECT, actor, reports.KIND, body, now)
    seq = stores.write([event])
    return {"report": reports.of([event])[0], "recorded": True, "seq": seq}


def _path(args: _args.Args) -> str:
    """Under `.taskops/reports/` or refused — the shape `core/reports.py` owns.

    Not a matter of tidiness: this same string later reaches the `/git` door
    that reads bytes out of the reader's own clone, and a door that accepts any
    repo-relative path is a file server sitting behind the dashboard's token.
    One rule, one function, checked at both ends.
    """
    given = _args.text(args, "path")
    path = reports.under(given)
    if not path:
        raise Refused(
            f"{given!r} is not a report path — a report is a file COMMITTED under "
            f"{reports.DIR} (no '..', no absolute path). Move it there, commit it, and file "
            'it: filed path=".taskops/reports/<name>.md" title="…" sha=<the commit>'
        )
    return path


def _said(args: _args.Args, key: str) -> str:
    """`title` and `sha` are required and may not be blank: a report with no
    title is a row nobody can read in a list, and one with no sha is a path with
    no way to fetch the bytes it points at."""
    value = _args.text(args, key)
    if not value:
        raise BadRequest(
            f"{key}= is required to file a report: "
            'filed path=".taskops/reports/<name>.md" title="…" sha=<the commit that carries it>'
        )
    return value


def _chapter(stores: Stores, given: str) -> Milestone:
    """The chapter this report is about. Named by id, else the single open one —
    `taskops_plan`'s bargain, refusal included: a board with several open
    chapters is asked rather than guessed at."""
    if given:
        stone = stores.state()["milestones"].get(given)
        if stone is None:
            raise NotFound(f"milestone {given} does not exist")
        return stone
    stone = _facts.open_milestone(stores)
    if stone is None:
        raise BadRequest(
            "this board has no single open milestone — say which chapter this report is "
            'about: filed milestone=ms-… path=".taskops/reports/<name>.md" title="…" sha=…'
        )
    return stone
