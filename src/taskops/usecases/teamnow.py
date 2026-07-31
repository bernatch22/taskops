"""`team` — who else is connected, and what they are holding.

A ROW in the rpc registry rather than a bespoke endpoint, and remote-first for a reason that is
the whole point of the verb: presence rides the heartbeat, and with a remote every heartbeat
lands on the SERVER. Answered from this machine's cache, the brief would report an empty team on
exactly the boards that have one — a project with a remote has one source of truth, and "who is
here" is a fact about the truth, not about my replica of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ..contracts.team import Team
from ..engine.team import team as assemble
from ._project import caller, heartbeat, project
from ._routing import read_remote_first, whoami

__all__ = ["team_now"]


def team_now(start: Path | str, *, actor: str = "", session: str = "") -> Team:
    """The team brief. Reads, and heartbeats — asking who is here says that I am.

    The `session` is the load-bearing argument and it is easy to miss why. Presence is written
    on the server, because with a remote every call routes there; the ONE call that knows a
    session id is the SessionStart read, which is LOCAL. So the id never crossed, every row on
    the server had an empty session, no developer was ever a routing candidate, and three
    handovers in a row were routed to nobody — one of them sat orphaned in review. Shipped and
    caught in a live run. This is the crossing.
    """
    if (answer := read_remote_first(start, "team",
                                    {"actor": whoami(start, actor),
                                     "session": session})) is not None:
        return cast("Team", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who, session=session)
        return assemble(store, who)
