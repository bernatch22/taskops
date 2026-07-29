"""Giving a card to somebody, from the BOARD — plus the registry the picker is built from.

Its own module rather than another pair of functions in `api.py`, for the same reason
`agentapi.py` is one: this is a WRITE with a rule of its own (who may be named as an assignee),
and a rule deserves a docstring where the reader is already looking.

**The actor is RESOLVED server-side**, like `post_comment` and unlike the agent endpoints: the
caller here is the board's browser, and a browser that could name its own actor could hand a
card away in somebody else's name — into a permanent event.

**Assignment is one meaning, and it lives in `usecases._handoff.hand_over`.** Nothing is
reimplemented here: this endpoint validates a name and calls the same function `dispatch` and
`capture(assign=...)` call, so a card assigned from the board is assigned exactly as a card
assigned by a fleet — field, handoff event and mention, in one write.

**Why a bare name is checked against the registry and a prefixed id is not.** Assignment HIDES
a card from every other agent, so a typo'd specialist is a card nobody can ever pick up and
nothing in the board says why. A name with no `dev:`/`agent:` prefix is therefore read as "the
specialist called this", and is refused — naming the ones this project has — when no such
specialist exists. A full actor id stays free-form on purpose: it addresses a person or an
ad-hoc worker who was never going to be in a registry, which is how the claim fence already
treats an actor it does not know (`usecases.agents.agent_named`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..._errors import BadRequest
from ...usecases import registry
from ...usecases._handoff import hand_over
from ...usecases._project import caller, project
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["get_agents", "post_assign"]


def get_agents(root: Path, request: Request) -> Reply:
    """The specialist registry, as the picker needs it — and NOT `text` or `path`.

    The file verbatim is what materialisation needs, not what a dropdown needs; putting a
    server-side path and a whole prompt on the wire for three labels would be a bigger payload
    than the board itself.
    """
    return guarded(lambda: json_reply(
        [{"name": spec["name"], "description": spec["description"], "labels": spec["labels"]}
         for spec in registry(root)]))


def post_assign(root: Path, request: Request) -> Reply:
    """Hand `task` to `assignee`. Re-assigning is allowed and records a SECOND handoff event —
    a person changing their mind is normal, and rewriting the first one would erase the fact
    that the card was ever somebody else's."""
    payload = request.payload()
    task_id = str(payload.get("task", "")).strip()
    assignee = str(payload.get("assignee", "")).strip()
    if not task_id or not assignee:
        return error_reply(400, "`task` and `assignee` are required", "bad_request")
    return guarded(lambda: json_reply(_assign(root, task_id, assignee)))


def _assign(root: Path, task_id: str, assignee: str) -> dict[str, Any]:
    with project(root) as store:
        who = caller(store)
        to = _target(store, assignee, who["dev"])
        # `need` first: `set_assignee` is an UPDATE, and an UPDATE that matches no row succeeds
        # silently — so a mistyped id would answer 200 and assign nothing.
        store.tasks.need(task_id)
        hand_over(store, task_id, to, actor=who["id"])
        return {"task": task_id, "assignee": to}


def _target(store: Any, assignee: str, dev: str) -> str:
    # `Any` and not `Store`: a transport may not import `taskops.storage` at all (an invariant
    # test says so), and the store here only travels from `project()` to the use cases.
    """The actor id to write. A registry name is minted under the ASSIGNER's dev, which is what
    makes `agent:berna/collectors` — the shape the claim fence reads the specialist out of."""
    if ":" in assignee:
        # The identity parser, reused rather than re-spelled: it is the one place that says what
        # an actor id is, and it refuses a malformed one with the message that names the fix.
        return caller(store, assignee)["id"]
    known = [spec["name"] for spec in registry(store.root)]
    if assignee not in known:
        raise BadRequest(
            f"`{assignee}` is not a specialist this project registered — it knows "
            f"{', '.join(known) or 'none'}. For a person or an ad-hoc worker, assign to "
            f"`dev:<name>` or `agent:<dev>/<name>` instead.")
    return f"agent:{dev}/{assignee}"
