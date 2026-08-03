"""`SessionStart` — everything a main conversation needs before anybody types.

Three reads, once per session, and each one answers a question the agent would otherwise
answer wrongly: who am I (the orchestrator), what has this project already decided, and what
is waiting on a decision right now.

**It is deliberately not `brief` with more fields.** `brief` answers "what do I hold", which is
a WORKER's question, and shaping the main session's opening around it is exactly how the main
session came to behave like a worker. The two survive side by side: `brief` is still what a
resumed session needs to re-adopt its leases, and it is folded in here rather than replaced.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts.opening import Opening
from ._contextviews import show
from .attention import attention
from .remote import read_remote
from .report import standup
from .session import brief
from .teamnow import team_now

RECENT = "24h"
"""How far the opening looks back. A day: long enough that a morning session sees last
night, short enough that it is not a report."""

__all__ = ["opening"]


def opening(start: Path | str, *, session: str = "", actor: str = "") -> Opening:
    """The opening screen. Reads only — a session that starts by writing is a session that
    has already decided something on nobody's behalf."""
    held = brief(start, session=session, actor=actor)
    # Carries the session, and that is what makes this dev routable at all: presence lives
    # where the routing runs (the server, with a remote), and this is the only call in the
    # opening that both knows the session id and gets there.
    mates = team_now(start, actor=held.actor, session=session)
    # `actor=` and not a bare sweep: without it the opening lists every review on the board,
    # including the ones routed to somebody else and the ones this dev is forbidden to close.
    # `mine=True`: the opening belongs to ONE person, so it carries their page — the project's
    # facts plus their own — and not the overview, which is everybody's and belongs to nobody.
    return Opening(actor=held.actor, session=session, board=_where(start),
                   shared=read_remote(start) is not None,
                   context=show(start, actor=held.actor, mine=True),
                   waiting=attention(start, actor=held.actor)["waiting"], held=held.held,
                   messages=held.messages, team=mates,
                   # Everybody's, not this actor's: "what did the OTHERS do" is half the
                   # question, and a session that only saw its own moves would open believing
                   # it works alone — which is the failure the team brief already exists for.
                   recent=standup(start, since=RECENT)["events"])


def _where(start: Path | str) -> str:
    """The board's address WITHOUT its credential — the server's, or this machine's, or "".

    Stripped on purpose: this line lands in a terminal, a scrollback and whatever gets
    screen-shared next, and `board_url` carries a token so a click lands signed in. One is for
    a browser somebody chose to open, the other prints itself on every session.

    The local UI is READ and never started here. Starting a web server is a side effect, and
    `opening` is the read every session makes — the hook starts it, deliberately, the same way
    it launches the daily sweep and for the same reason: what an event MEANS and what it sets
    in motion are two jobs, and only one of them belongs in a projection.
    """
    from .localui import local_ui

    found = read_remote(start)
    return f"{found['url']}/" if found else local_ui(_root(start), start=False)


def _root(start: Path | str) -> Path:
    from ..storage import find_root

    return find_root(Path(start)) or Path(start)
