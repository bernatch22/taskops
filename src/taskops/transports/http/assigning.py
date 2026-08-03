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
from ...usecases import registry, update
from ...usecases._handoff import hand_over
from ...usecases._project import caller, project
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded

__all__ = ["get_agents", "post_assign"]


def get_agents(root: Path, request: Request) -> Reply:
    """The specialists a card can be GIVEN to — and NOT `text` or `path`.

    The file verbatim is what a reader of the registry needs, not what a dropdown needs; a
    server-side path and a whole prompt on the wire for three labels would be a bigger payload
    than the board itself.

    Agents that cannot hold a card are left out, and that is the important half. An assignment
    hides the card from everybody else, so offering an orchestrator in this list would let one
    click produce a card nobody can ever claim and nobody can see — the exact dead story this
    board exists to make impossible.
    """
    return guarded(lambda: json_reply(
        [{"name": spec["name"], "description": spec["description"], "labels": spec["labels"]}
         for spec in registry(root) if spec["claims"]]))


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
    """Direct for a person; a REQUEST for a specialist.

    There is exactly one dispatcher, and it is not this endpoint. The board used to write the
    assignee and the channel pushed that handoff into the open session as an order to spawn —
    an order arriving sideways into an orchestrator that already had its own queue, its own
    order, its own cards in flight. Two deciders for one question, and a live run spent an
    afternoon on the disagreement. Now the click SAYS what it is: a request the orchestrator
    fulfils with `taskops_dispatch`, in its own order, or answers with a reason not to.
    """
    with project(root) as store:
        who = caller(store)
        to = _target(store, assignee, who["dev"])
        # `need` first: `set_assignee` is an UPDATE, and an UPDATE that matches no row succeeds
        # silently — so a mistyped id would answer 200 and assign nothing.
        card = store.tasks.need(task_id)
        if to.startswith("agent:") and not card["spec"].strip():
            # Refused HERE, not queued for the orchestrator to discover later as "dispatch
            # skipped it": the human who can write the spec is the one clicking. One card
            # collected two dispatched workers and two releases in a day proving what a
            # spec-less card is worth to an agent.
            raise BadRequest(
                f"{task_id} has no spec — an agent sent to guess releases it and the loop "
                f'repeats. Write one first: `taskops tasks edit {task_id} --spec "…"`, '
                f"or assign it to a dev.")
        if not to.startswith("agent:"):
            hand_over(store, task_id, to, actor=who["id"])
            return {"task": task_id, "assignee": to}
    # A REQUEST, and it lands ON THE CARD with the target MENTIONED. It used to go to the
    # board's chat sidebar, which is gone: that surface assumed exactly one session was
    # listening, which stops being true the moment a board is shared. A mention has none of
    # that ambiguity — it is addressed, it is delivered on the recipient's very next tool call,
    # and it is filed under the work it is about instead of a conversation beside it.
    update(root, task_id, mentions=(to,),
           comment=f"dispatch to `{to.rsplit('/', 1)[-1]}` — assign it and spawn that "
                   f"sub-agent (or say why not)")
    return {"task": task_id, "requested": to}


def _target(store: Any, assignee: str, dev: str) -> str:
    # `Any` and not `Store`: a transport may not import `taskops.storage` at all (an invariant
    # test says so), and the store here only travels from `project()` to the use cases.
    """The actor id to write. A registry name is minted under the ASSIGNER's dev, which is what
    makes `agent:berna/collectors` — the shape the claim fence reads the specialist out of."""
    if ":" in assignee:
        # The identity parser, reused rather than re-spelled: it is the one place that says what
        # an actor id is, and it refuses a malformed one with the message that names the fix.
        return caller(store, assignee)["id"]
    found = {spec["name"]: spec for spec in registry(store.root)}
    workers = [name for name, spec in found.items() if spec["claims"]]
    if assignee not in found:
        raise BadRequest(
            f"`{assignee}` is not a specialist this project registered — it knows "
            f"{', '.join(workers) or 'none'}. For a person or an ad-hoc worker, assign to "
            f"`dev:<name>` or `agent:<dev>/<name>` instead.")
    if not found[assignee]["claims"]:
        # Belt and braces with the list above: the picker no longer offers these, but an API
        # is not a dropdown and this one is reachable by anybody with the token.
        raise BadRequest(
            f"`{assignee}` plans and hands work out — it cannot hold a card, so assigning this "
            f"one to it would hide it from everybody and leave it claimable by nobody. Give it "
            f"to one of {', '.join(workers) or 'a person'}, or let the orchestrator dispatch it.")
    return f"agent:{dev}/{assignee}"
