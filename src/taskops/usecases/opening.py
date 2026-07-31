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
from .attention import attention
from .context import show
from .session import brief
from .teamnow import team_now

__all__ = ["opening"]


def opening(start: Path | str, *, session: str = "", actor: str = "") -> Opening:
    """The opening screen. Reads only — a session that starts by writing is a session that
    has already decided something on nobody's behalf."""
    held = brief(start, session=session, actor=actor)
    mates = team_now(start, actor=held.actor)
    # `actor=` and not a bare sweep: without it the opening lists every review on the board,
    # including the ones routed to somebody else and the ones this dev is forbidden to close.
    return Opening(actor=held.actor, session=session, context=show(start),
                   waiting=attention(start, actor=held.actor)["waiting"], held=held.held,
                   messages=held.messages, team=mates)
