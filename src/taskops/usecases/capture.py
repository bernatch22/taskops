"""One card, created and claimed in a single call — the door for work nobody planned.

`plan` builds a GRAPH and is right for decomposition: an agent that read the code and thought
about five tasks should land them with their edges in one shot. But it is the wrong shape for
the case this exists to serve, which is an agent halfway through something that turns out to
belong to no card at all — a bug it tripped over, a fix a reviewer asked for mid-review. Told
to `plan` that, it has to invent a one-entry batch, then find the id it just made, then claim
it, and only then may it commit. Three calls and an id it has to carry, at exactly the moment
it was thinking about something else.

So this is `plan` plus `next_task`, composed rather than reimplemented: the card is created by
the same code that creates every card, and claimed by the same code that claims every card.
What is new here is only that the two happen together and the caller gets the branch back.

**It claims by default.** A card created because the work is already underway and immediately
left unclaimed is the state the commit guard would refuse anyway — and the refusal would name
this very command, which is how a tool teaches somebody a loop. `claim=False` stays for the
one honest case: recording work for LATER, that the caller is not about to start.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import NextResult
from ._handoff import hand_over
from ._project import project
from ._routing import call_remote, whoami
from .claim import next_task
from .plan import plan
from .update import update

__all__ = ["capture"]


def capture(start: Path | str, title: str, *, spec: str = "", files: str = "",
            labels: str = "", acceptance: object = None, priority: object = None,
            claim: bool = True, assign: str = "", actor: str = "",
            session: str = "") -> dict[str, Any]:
    """Create one card and, unless told otherwise, hold it. Returns the card and its branch."""
    entry: dict[str, Any] = {"title": title, "spec": spec, "files": files, "labels": labels}
    if acceptance is not None:
        entry["acceptance"] = acceptance
    if priority is not None:
        entry["priority"] = priority
    task = plan(start, [entry], actor=actor)["created"][0]
    if assign:
        return {"task": task, "claim": None, "assigned": _hand(start, task["id"], assign, actor)}
    if not claim:
        return {"task": task, "claim": None, "assigned": ""}
    held: NextResult = next_task(start, task=task["id"], actor=actor, session=session)
    return {"task": task, "claim": held.get("claim"), "assigned": ""}


def assign(start: Path | str, task: str, to: str, *, actor: str = "") -> str:
    """Assignment as a start-rooted verb — what the rpc registry runs, and `_hand`'s core."""
    with project(start) as store:
        hand_over(store, task, to, actor=actor)
    return to


def _hand(start: Path | str, task: str, to: str, actor: str) -> str:
    """Give a card to somebody else — the same assignment `dispatch` makes, plus the mention.

    It USED to be a mention alone, and that was a bug rather than a design: `dispatch` set the
    assignee, which hides the card from every other agent, while this left it in the open pool.
    One word, two outcomes, and the reply never said which. Now `hand_over` is the single
    meaning of "assign" and both callers get it.

    Still no lease. Assignment says whose card it is; only a running process may hold a claim.
    The mention stays on top of it because a field the board reads is not a notification — the
    person it was given to has to be TOLD, and their inbox is where they look.
    """
    update(start, task, comment=f"assigned to {to}", mentions=(to,), actor=actor)
    if call_remote(start, "assign", {"task": task, "to": to,
                                     "actor": whoami(start, actor)}) is None:
        assign(start, task, to, actor=actor)
    return to
