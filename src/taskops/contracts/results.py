"""What the use cases hand back — the shapes the renderers turn into text.

Separate from the entities because they answer a QUESTION rather than describing
a thing: a `Claim` is not stored anywhere, it is the assembled answer to "what
should I work on", including the parts the agent would otherwise have to ask three
more times for.
"""

from __future__ import annotations

from typing import TypedDict

from .dep import Dep
from .event import Inbox
from .lease import Lease
from .task import Task, TaskView

__all__ = ["PlanResult", "Claim", "NextResult", "UpdateResult", "EditResult"]


class PlanResult(TypedDict):
    """What a decomposition created. Returned in creation order, which is the
    order the caller listed them — so an agent can map its own plan onto ids."""

    created: list[Task]
    deps: list[Dep]
    unblocked: list[str]
    """Ids that came out of `plan` already pickable. Usually the leaves; if this
    is empty the caller built a graph where nothing can start, which is a planning
    bug worth seeing immediately rather than discovering at the first `next`."""


class Claim(TypedDict):
    """A task, claimed, with everything needed to start on it."""

    view: TaskView
    lease: Lease
    branch: str
    """The branch to create: `tk/<id>/<slug>`. Handed over rather than left to the
    agent to compose, because the commit guard matches on this exact shape."""

    inbox: Inbox
    """Delivered with the claim. An agent that just picked up work is the most
    likely to have been messaged about it, and this is a read it was making
    anyway — so the inbox rides along instead of costing another call."""


class NextResult(TypedDict):
    """The answer to "what should I do", including "nothing, and here is why"."""

    claim: Claim | None
    reason: str
    """Empty when a claim was made. Otherwise the actual obstacle — everything is
    blocked, everything is claimed by someone else, or the project is finished.
    An agent told "nothing ready" with no reason asks a human; told which, it can
    often unblock itself."""

    ready: int
    working: int
    blocked: int


class UpdateResult(TypedDict):
    """The effect of one update: the new state, and what it set free."""

    task: Task
    unblocked: list[Task]
    """Tasks that became pickable because this one closed. The auto-unblock, made
    visible: an agent finishing a task learns what it just handed to the fleet."""

    notified: list[str]
    """Actors whose inbox this reached — the mentions, resolved."""

    routed_to: str
    """The dev this handover's review was routed to, or "".

    It rides the RETURN VALUE because that is the one message the author is guaranteed to
    read. Watched live: a session whose two workers handed cards over spawned a verifier for
    each of them a minute later — nothing had told it not to, and silence reads as "nobody
    took this, so I will". Both verifiers were refused at the close. The channel deliberately
    says nothing to the author (that would be the echo), so the author's own call has to."""


class EditResult(TypedDict):
    """The card after a rewrite, and which fields actually moved.

    `changed` rather than a bare task: an edit that asked for a new title and got none —
    because the value was already there — is worth saying out loud, since the alternative
    is a caller believing it landed something the log has no event for.
    """

    task: Task
    changed: list[str]
