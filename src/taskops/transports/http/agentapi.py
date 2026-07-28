"""The two writes an AGENT makes, served for agents on other machines.

Its own module for the same reason `exchange.py` is one: the caller here is another taskops,
not the board's browser, so these shapes are a contract a client codes against
(`docs/exchange.md`) rather than something the UI and the server can rename together.

Why they exist: a claim is only atomic inside one database. Two agents on two machines each
claim in their own sqlite and discover the collision at the next sync, which is too late —
by then both have edited the same files. Routing the write here makes the two claims two
INSERTs on one primary key in one store, which is a race the engine already wins.

**`local=True` on every call, without exception.** These functions run the same use cases a
client runs, and those use cases route to the remote when the project has one. A server whose
store carried a `remote.json` would therefore POST to itself, and answer its own POST by
POSTing again. The flag is the cycle breaker and it is passed here, at the only place that
can know it is already the destination.

**The actor is TAKEN FROM THE BODY, and that is a real trust decision.** Everywhere else on
this server — `post_comment` — the actor is resolved server-side, because a browser naming
its own actor could post as somebody else's agent. It cannot work that way here: the server
has neither the remote machine's `$TASKOPS_ACTOR` nor its git config, so it has no way to
learn who is calling. The project TOKEN is therefore the trust boundary: whoever holds it may
act as any actor in the project. That is the same boundary git already draws — whoever can
push to the repository can author a commit under any name — and it is stated here rather than
buried, because a reader deciding where to put this server deserves to know it. What is still
enforced is the SHAPE: a malformed id is refused with a 400 by `identity.parse` inside the use
case, so a typo cannot conjure a ghost identity that half an agent's work then files under.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases import next_task, update
from ._wire import Reply, Request, error_reply, json_reply
from .api import guarded, strings

__all__ = ["post_next", "post_update"]


def post_next(root: Path, request: Request) -> Reply:
    """Claim, decided here. Returns the `NextResult` TypedDict, which is already JSON."""
    payload = request.payload()
    actor = str(payload.get("actor", "")).strip()
    if not actor:
        return error_reply(400, "`actor` is required — this server cannot infer the identity "
                                "of an agent on another machine", "bad_request")
    return guarded(lambda: json_reply(next_task(
        root, actor=actor, session=str(payload.get("session", "")),
        labels=strings(payload, "labels"), task=str(payload.get("task", "")), local=True)))


def post_update(root: Path, request: Request) -> Reply:
    """A transition, a comment and a notification — checked by THIS store's guards.

    Which is the point: the lease that `done` requires, and the commits bound to the task, are
    read from the database every machine writes to, so an agent cannot close a card whose
    lease it lost to somebody else while its own board was stale.
    """
    payload = request.payload()
    task_id = str(payload.get("task", "")).strip()
    actor = str(payload.get("actor", "")).strip()
    if not task_id or not actor:
        return error_reply(400, "`task` and `actor` are required", "bad_request")
    return guarded(lambda: json_reply(update(
        root, task_id, actor=actor, status=str(payload.get("status", "")),
        comment=str(payload.get("comment", "")), mentions=strings(payload, "mentions"),
        blocked_on=str(payload.get("blocked_on", "")),
        no_code=bool(payload.get("no_code")), local=True)))
