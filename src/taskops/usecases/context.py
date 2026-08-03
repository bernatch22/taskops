"""The context verbs: state a fact, withdraw one, read what is in force, read what was.

Every write goes through `engine.record`, the same door `plan` and `update` use. There is no
second event path and no file of its own on purpose: as events, these facts replicate through
`git pull` with everything else, are content-hashed so importing them twice is a no-op, and
get their history for free. A `context.json` would have been a third of that and a merge
conflict every time two people edited it.

Nothing is ever deleted. `retire` appends an event that withdraws another, which is the honest
way for an append-only log to say "we stopped believing this" — and it is why `log` can still
show what we used to think while `show` no longer does.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest
from .._types import EventKind
from ..contracts.context import CONTEXT_KIND, CONTEXT_TASK, Fact
from ..engine import identity, record
from ..storage.context import fact_of, facts, matching
from ._joins import chapter_for
from ._project import caller, heartbeat, locate, project
from ._routing import call_remote, whoami
from ._stating import refuse_an_ownerless_objective, refuse_the_shape

__all__ = ["state", "retire"]

_KIND = cast("EventKind", CONTEXT_KIND)
"""`EventKind` is a Literal in layer 0 and this module may not widen it, so the cast names the
one place this kind enters the log. Nothing validates kinds at runtime: an older taskops stores
and forwards one it has never heard of, untouched."""


def state(start: Path | str, sort: str, text: str, *, labels: Sequence[str] = (),
          files: Sequence[str] = (), horizon: str = "", owner: str = "", level: str = "milestone",
          actor: str = "") -> Fact:
    """Record one fact. An objective supersedes the previous one by being NEWER, not by
    touching it — the old one stays in the log, which is what `context log` reads.

    `level` is the LIFETIME, and `milestone` is the default deliberately: a fact that dies with
    its chapter is recovered by restating it, and one that lives forever accumulates silently —
    which is the failure the whole model exists to end. The default falls on the recoverable side.

    The chapter is resolved HERE, from what is in force, and never taken from the caller. Several
    are active at once, so there is a real question of which — and the answer is not the caller's
    to guess: a fact filed under the wrong chapter is a fact that reaches the wrong cards and
    nothing says so. `owner` picks it: a dev's own fact joins the chapter their own objective is
    in, which is the one they are working under.
    """
    refuse_the_shape(sort, text, level)
    _refuse_the_caller(locate(start), sort, owner, actor)
    body: dict[str, Any] = {"sort": sort, "text": text.strip(), "labels": list(labels),
                            "files": list(files), "horizon": horizon, "owner": owner,
                            "level": level}
    # The WHOLE body crosses. It used to send four of the seven fields, so on a board with a
    # remote `--files`, `--horizon` and `--owner` were accepted, echoed back and dropped — and
    # `--files` is how a decision scopes to an edit surface, so a decision written on a remote
    # board reached every card instead of the ones it was about.
    if (answer := call_remote(start, "context_state",
                              {**body, "actor": whoami(start, actor)})) is not None:
        return cast("Fact", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        body["milestone"] = "" if level == "project" else chapter_for(store, owner or who)
        stated = fact_of(record(store, task=CONTEXT_TASK, actor=who, kind=_KIND, body=body))
        if stated is None:                      # unreachable: `sort` was checked above
            raise BadRequest(f"`{sort}` produced no fact")
        return stated


def _refuse_the_caller(where: Path, sort: str, owner: str, actor: str) -> None:
    """WHO may state this, and whether it is filed under anybody.

    An OWN fact needs no person: `agent:ana/w1` is ana with another pair of hands, and there is
    nobody else it could be filing under. Everything else is what a worker is JUDGED against, so a
    worker that could state one could move its own goalposts.

    The ownership check is LAST. An agent stating an unowned objective is refused for who it is,
    and a message about ownership would send it to fix the wrong half — it would fix it, and it
    would still be refused.
    """
    if not owner:
        identity.a_person(where, actor, f"state a project or chapter {sort}")
    else:
        # Parsed, not trusted. `dev_of` answers "" for anything it cannot read, so an owner nothing
        # can parse would file the fact as the PROJECT's. A typo must not erase the north.
        identity.parse(owner)
    if sort == "objective":
        refuse_an_ownerless_objective(owner)


def retire(start: Path | str, fact_id: str, *, actor: str = "") -> Fact:
    """Withdraw a fact. It leaves `show` and stays in `log`, because there is no eraser.

    A PREFIX is accepted, and it had to be: `show` and `log` print the id shortened to eight
    characters, so the string a person can see was the one string this refused — and the error
    sent them to `log`, which shows the same eight. The one action a fact supports could not be
    reached from anything the CLI displayed. Git's answer, for the same reason.
    """
    identity.a_person(locate(start), actor, "retire a standing fact")
    if (answer := call_remote(start, "context_retire", {"id": fact_id,
                                                        "actor": whoami(start, actor)})) is not None:
        return cast("Fact", answer)
    with project(start) as store:
        known = facts(store, retired=True)
        hits = matching(known, fact_id.strip())
        if len(hits) != 1:
            raise BadRequest(f"`{fact_id}` names {len(hits)} context facts — "
                             f"`taskops context log` lists them, and the eight characters it "
                             f"prints are enough to name one")
        gone = next(f for f in known if f["id"] == hits[0])
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        record(store, task=CONTEXT_TASK, actor=who, kind=_KIND, body={"retires": gone["id"]})
        return {**gone, "retired": True}
