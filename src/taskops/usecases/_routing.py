"""Where a WRITE happens: here, or in the server that other machines also write to.

Push and pull make two boards converge; they do not make a claim safe. Between two syncs,
two agents on two machines can both find the same card `ready` and both take it — each
sqlite grants its own lease because neither knows about the other. The engine already solves
this *within* one database (two INSERTs on one primary key, one winner, pinned by a
fifty-thread test); the fix is therefore not a new algorithm but a new PLACE: when a project
has a remote, `next` and `update` are executed in the server's sqlite, where the race is the
same race the engine already wins.

**The decision lives here, in the use cases, and not in a transport.** The CLI, the MCP tools
and the local HTTP board all call `next_task` and `update`; putting the routing in any one of
them would mean an agent that claims safely through MCP and unsafely through `taskops claim`.

**The server must never route to itself.** It runs these very use cases, so a `remote.json`
that happened to sit in the store it serves would make it POST to itself, forever. That is
why every server endpoint passes `local=True`: a flag the caller must opt into is checkable,
and `tests/e2e/test_agentwire.py` plants exactly that file and asserts the server answers.

**Offline never falls back to a local claim.** A remote-configured project whose server is
unreachable raises, naming the URL. Quietly claiming locally instead would be the collision
this module exists to prevent, delivered by the very code meant to prevent it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, cast

from .._errors import TaskopsError, Unreachable
from ..contracts import NextResult, Remote, UpdateResult
from ..engine import identity
from ._mirroring import mirror_claim, mirror_update
from ._project import locate
from ._wireclient import Wire
from .remote import read_remote

__all__ = ["routed", "whoami", "claim_remotely", "update_remotely", "call_remote",
           "read_remote_first"]


def routed(start: Path | str, local: bool) -> Remote | None:
    """The remote this write belongs to, or None when it belongs to this disk."""
    return None if local else read_remote(start)


def whoami(start: Path | str, actor: str) -> str:
    """Resolve the actor HERE, before it crosses the wire.

    The server cannot do it: it has neither this machine's `$TASKOPS_ACTOR` nor its git
    config, so an empty actor would arrive and resolve to the server's own identity — every
    remote agent filed as one `dev:` on the box.
    """
    return identity.resolve(locate(start), actor)["id"]


def call_remote(start: Path | str, verb: str, args: dict[str, Any], *,
                local: bool = False) -> Any | None:
    """Run one registered verb in the server's store, or None when this project has none.

    THE door for every verb that is not a claim or a transition (those two predate it and keep
    their endpoints). A verb that writes goes through here unconditionally — the server is the
    source of truth, and a write that "fell back to local" on a network blip would fork the
    board precisely when nobody is watching. Unreachable therefore RAISES, exactly as `next`
    does, naming the URL.
    """
    remote = routed(start, local)
    if remote is None:
        return None
    return _relay(start, remote, lambda wire: wire.rpc(verb, args))


def read_remote_first(start: Path | str, verb: str, args: dict[str, Any]) -> Any | None:
    """A READ from the server, degrading to None — the caller then answers from its cache.

    The asymmetry with `call_remote` is the design: refusing to WRITE without the server keeps
    one truth, refusing to READ without it would make the server a single point of failure for
    looking at your own last-known board. The degradation is loud (stderr), because a silently
    stale answer is the bug the whole mode exists to kill.
    """
    remote = routed(start, False)
    if remote is None:
        return None
    try:
        return _relay(start, remote, lambda wire: wire.rpc(verb, args))
    except TaskopsError as err:
        import sys
        sys.stderr.write(f"taskops: could not reach {remote['url']} ({err}) — answering "
                         f"from the last board this machine saw\n")
        return None


def claim_remotely(start: Path | str, remote: Remote, body: dict[str, Any]) -> NextResult:
    answer = cast("NextResult", _relay(start, remote, lambda wire: wire.claim(body)))
    if answer["claim"] is not None:
        mirror_claim(start, answer["claim"])
    return answer


def update_remotely(start: Path | str, remote: Remote, body: dict[str, Any]) -> UpdateResult:
    answer = cast("UpdateResult", _relay(start, remote, lambda wire: wire.change(body)))
    mirror_update(start, answer["task"])
    return answer


def _relay(start: Path | str, remote: Remote,
           send: Callable[[Wire], dict[str, Any]]) -> dict[str, Any]:
    """Do it there, then pull. The pull is NOT best effort — see below.

    Without it the agent holds a lease the server knows about and its own board does not, and
    the board is what the commit guard, `taskops brief` and every render read. So a failed
    pull fails the whole call: a half-success that reports a claim the local tooling will then
    deny is worse than an error naming the network.

    The pull carries everybody's events; `_mirroring` then writes the one thing an event cannot
    carry — the lease this caller was just granted.
    """
    from .pushpull import pull

    try:
        answer = send(Wire(remote["url"], remote["token"]))
    except Unreachable as gone:
        raise Unreachable(
            f"this project's writes go to {remote['url']}, which did not answer "
            f"({gone}) — taskops will NOT claim locally instead, because a local claim "
            f"could collide with another machine's; retry, or check the network") from gone
    pull(start)
    return answer
