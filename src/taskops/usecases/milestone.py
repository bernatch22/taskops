"""Opening, moving and reading a chapter — the verb set a board's story is written with.

Every write here is ONE append to the log and nothing else: a milestone is a fold over its own
events (`storage.milestone`), so there is no row to keep in step and no repair pass to forget.
That is also what makes this replicate through `git pull` for free and route to a server without a
second implementation — the same reason cards work that way.

**What is refused lives in `engine.milestones`, not here.** This module resolves ids, opens the
store and appends; the machine decides whether the move is legal and whether the caller may make
it. A guard in a use case is a guard the other transports have; a guard in argparse is a guard
only a terminal has, which is how a rule once held for a person and not for MCP.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest
from ..contracts.milestone import Milestone
from ..engine import record
from ..storage.milestone import milestones as all_of
from ._contextviews import chapters
from ._moving import _KIND, TASK, as_milestone, moved, need, written
from ._project import caller, heartbeat, project
from ._routing import call_remote, read_remote_first, whoami

__all__ = ["open_chapter", "start", "edit", "hand_over", "verify", "send_back", "abandon",
           "listing", "chapter"]


def listing(start_at: Path | str) -> dict[str, Any]:
    """Every chapter a board has ever had, with the cards of each.

    ALL of them, closed ones included, which is what separates this from the slice: a slice is
    what applies NOW and a listing is the record — "what have we shipped" is the one question the
    whole model exists to answer, and it is unanswerable from the chapters still open.

    An OBJECT and not a bare list: the wire decoder returns `{}` for anything that is not one, so
    a verb answering an array decodes to nothing with no error anywhere. Three did that at once.
    """
    if (answer := read_remote_first(start_at, "milestone_list", {})) is not None:
        return cast("dict[str, Any]", answer)
    with project(start_at) as store:
        return {"milestones": all_of(store), "counts": chapters(store).counts}


def chapter(start_at: Path | str, wanted: str) -> Milestone:
    """One chapter by id or prefix — for reading a closed one on purpose."""
    if (answer := read_remote_first(start_at, "milestone_show", {"milestone": wanted})) is not None:
        return as_milestone(answer)
    with project(start_at) as store:
        return need(store, wanted)

def open_chapter(start_at: Path | str, text: str, *, horizon: str = "", planned: bool = False,
                 actor: str = "") -> Milestone:
    """Create one. `planned` writes it down WITHOUT starting it.

    Never refused for a chapter already running. Several active at once is the normal case — a
    team ships two things in a fortnight — and a board that refused to record the second would be
    a board disagreeing with what is happening, which is the one thing it exists not to do.
    """
    said = text.strip()
    if not said:
        raise BadRequest("a milestone needs text — a chapter with no statement states nothing")
    body: dict[str, Any] = {"op": "create", "text": said, "horizon": horizon.strip(),
                            "planned": bool(planned)}
    if (answer := call_remote(start_at, "milestone_create",
                              {**body, "actor": whoami(start_at, actor)})) is not None:
        return as_milestone(answer)
    return written(start_at, body, actor)


def edit(start_at: Path | str, wanted: str, *, text: str = "", horizon: str = "",
         actor: str = "") -> Milestone:
    """Re-word one, or move its horizon. Neither is a state change, so neither is guarded."""
    if not text.strip() and not horizon.strip():
        raise BadRequest("nothing to edit — pass `text`, a `horizon`, or both")
    if (answer := call_remote(start_at, "milestone_update",
                              {"milestone": wanted, "text": text, "horizon": horizon,
                               "actor": whoami(start_at, actor)})) is not None:
        return as_milestone(answer)
    with project(start_at) as store:
        found = need(store, wanted)
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        record(store, task=TASK, actor=who, kind=_KIND,
               body={"op": "update", "milestone": found["id"], "text": text.strip(),
                     "horizon": horizon.strip()})
        return need(store, found["id"])


def start(start_at: Path | str, wanted: str, *, actor: str = "") -> Milestone:
    """A planned chapter becomes active. An agent may: beginning work is working."""
    return moved(start_at, wanted, "in_force", actor=actor)


def hand_over(start_at: Path | str, wanted: str, *, note: str = "",
              actor: str = "") -> Milestone:
    """Report it finished. It stays ACTIVE — see `OPEN_MILESTONE`: nothing is archived on an
    agent's word, so its cards keep their home until a person closes or returns it."""
    return moved(start_at, wanted, "review", note=note, actor=actor)


def verify(start_at: Path | str, wanted: str, *, carry: tuple[str, ...] = (), into: str = "",
           actor: str = "") -> Milestone:
    """Reached. A PERSON only, and `engine.milestones` is what refuses an agent."""
    return moved(start_at, wanted, "reached", carry=carry, into=into, actor=actor)


def send_back(start_at: Path | str, wanted: str, *, note: str = "",
              actor: str = "") -> Milestone:
    """Back in force, with what is missing. A person only, and `note` is required by the machine."""
    return moved(start_at, wanted, "in_force", note=note, actor=actor)


def abandon(start_at: Path | str, wanted: str, *, note: str = "", actor: str = "") -> Milestone:
    """It will not be done. Kept rather than deleted: "we stopped" is not "we shipped", and the
    reason is what somebody wants three weeks later when the same idea comes back."""
    return moved(start_at, wanted, "abandoned", note=note, actor=actor)
