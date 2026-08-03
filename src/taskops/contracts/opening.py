"""What a session is handed the moment it opens — the reason it knows who it is.

A session used to start knowing only what it HELD, which for a fresh conversation is nothing,
and the injection ended with "Run taskops_next to claim one." That sentence is why two real
sessions did the work themselves and left the cards dead: the first thing the main agent read
told it to be a worker, so it was one, and nobody was left to verify or dispatch anything.

The role is not a preference and not a prompt somebody remembers to write. `SessionStart` fires
for the MAIN conversation only — sub-agents never see it — so the event itself is the proof of
which one this is. That makes "you are the orchestrator" a fact the transport can state.
"""

from __future__ import annotations

from typing import TypedDict

from .attention import Waiting
from .context import ContextSlice
from .event import Event
from .lease import Lease
from .policy import Policy
from .team import Team

__all__ = ["Opening"]


class Opening(TypedDict):
    """The whole first screen: who, what the project has decided, and what is waiting."""

    actor: str
    session: str

    board: str
    """Where this board can be OPENED, or "" when there is nowhere.

    A person reading a session's first line wants somewhere to click. It used to be REMOTE
    ONLY, on the argument that a local `taskops ui` is not running unless somebody started
    one — which was true and was the wrong conclusion: the fix is to start it, not to print
    nothing. The `SessionStart` hook brings a local board up before this is read, so both kinds
    of project answer now, and neither URL carries a credential.
    """

    shared: bool
    """True when that address is a SERVER the team reaches, false when it is this machine.

    Separate from `board` because the URL alone no longer says which — both kinds are non-empty
    now — and everything a reader concludes from the first line depends on it: "5 ready to hand
    out" is five the whole team can see, or five nobody else knows about."""

    policies: list[Policy]
    """The settings the ENGINE obeys, `reviewer` above all. Injected because the orchestrator is
    the one that PLANS: a board on `reviewer: peer` needs cards handed to a session that is not
    the author's, and a session that did not know dispatched them back to the same developer and
    watched the close get refused. A decision is prose it weighs; a policy is a value it cannot
    argue with, so it arrives stated rather than left to be discovered by a refusal."""

    context: ContextSlice
    """The standing objective, decisions and notes. Injected HERE rather than left for
    the agent to fetch, because a session that has to remember to ask about the project's
    constraints is a session that will edit against one of them before it does."""

    waiting: list[Waiting]
    """`attention`, verbatim. The orchestrator's first question is always "what needs a
    decision", so the answer arrives before the question."""

    held: list[Lease]
    """Cards this actor still holds — a resumed session, or leases that outlived a crash."""

    messages: list[Event]

    recent: list[Event]
    """What happened on this board in the last day, everybody's, newest last.

    The one thing an opening could not answer: a session that knows what is WAITING still has
    no idea what just moved, and the difference matters — a card in review because somebody
    finished it an hour ago is a different situation from one that has sat there since Tuesday.
    Summarised by the renderer into a handful of lines, never printed whole.
    """

    team: Team
    """Who else is connected, and what they are holding. The one thing here that is not about
    this session: without it two sessions on one board each behave as though they were alone,
    which is how a card got implemented twice and a review got started by two devs at once."""
