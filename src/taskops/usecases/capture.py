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


def _hand(start: Path | str, task: str, to: str, actor: str) -> str:
    """Give a card to somebody else — as a MENTION, never as a lease held on their behalf.

    A lease belongs to a process that is alive and heartbeating; minting one for an agent that
    is not running produces a claim that lapses fifteen minutes later with nobody watching, and
    a board that spent that time saying the work was in hand. A mention lands in their inbox,
    the card stays pickable, and whoever actually starts it claims it themselves — which is the
    only moment a lease means anything.
    """
    update(start, task, comment=f"assigned to {to}", mentions=(to,), actor=actor)
    return to
