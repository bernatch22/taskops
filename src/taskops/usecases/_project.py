"""Opening the project, and the heartbeat every call pays for.

Two things every use case needs and none of them should re-derive:

**The root.** Callers pass whatever path they happen to be in — an agent its cwd, a
git hook wherever git ran it — so resolution walks up for `.taskops/` exactly once,
here.

**The heartbeat.** Any taskops call an agent makes is proof it is alive, so every
call renews that agent's leases. This is what makes the TTL bound a CRASH rather
than a slow task: an agent working for an hour keeps its claim without doing anything
special, and one whose process died stops renewing within a single call.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .._clock import LEASE_TTL, now
from ..contracts import Actor
from ..engine import identity, record, sweep_dead
from ..storage import Store, resolve_root

__all__ = ["project", "caller", "heartbeat", "locate", "attributed"]


def locate(start: Path | str) -> Path:
    """Which project a path belongs to. Raises `NotInitialized` naming the fix.

    Exported because the studio needs the root BEFORE it opens a port — it serves one repository,
    and binding to a directory with no project would be a server that answers every request with
    the same error. A transport may not call `storage.resolve_root` itself (an invariant test says
    so, and it caught exactly this), so the resolution is a use case like any other.
    """
    return resolve_root(start)


@contextmanager
def project(start: Path | str) -> Generator[Store]:
    """An open Store on the project containing `start`. Commits on a clean exit."""
    with Store(resolve_root(start)) as store:
        yield store


def caller(store: Store, asked: str = "") -> Actor:
    """Who is calling. Resolved from the argument, the environment, then git."""
    return identity.resolve(store.root, asked)


def attributed(start: Path | str, task_id: str, asked: str = "") -> str:
    """Who a call ABOUT ONE CARD belongs to when the caller named nobody.

    A sub-agent is handed a card assigned to `agent:me/api`, passes `actor=` on the claim
    and forgets it on the very next call — which resolves to the developer's `dev:<name>`
    and is then refused its own lease. That happened four times, and each fix was the same
    instruction written somewhere new. An instruction is not a mechanism; a card that is
    assigned to exactly one agent already knows the answer.

    So this is an identity INFERENCE, and identity inferences go wrong quietly — writing
    somebody else's name on their work. Four guards, all of them load-bearing:

    - only when `actor` is ABSENT. A stated actor is never overridden, wrong or not.
    - only when the assignee is an `agent:` id. Impersonating a HUMAN is the one failure
      that cannot be undone by an apology, and a card sitting on a dev is a card nobody
      delegated.
    - only for a NAMED card. A pool call (`next` with no task) has no assignee to speak
      for it, and inferring from whatever it happens to claim would attribute a stranger.
    - and it is RECORDED, ONCE per card and actor. The `inferred` event is what lets a reader
      tell an attribution taskops made from one the agent actually claimed — but a worker
      makes twenty calls to finish a card, and twenty identical markers in a COMMITTED log
      would drown the diff whose readability is the reason that log is a file at all. The
      fact is "taskops named this agent on this card", and that is true once.

    Returns "" when nothing can be inferred, which is exactly what the caller passed in —
    resolution falls through to `$TASKOPS_ACTOR` and then git, as it always did.
    """
    if asked.strip() or not task_id.strip():
        return asked.strip()
    with project(start) as store:
        card = store.tasks.get(task_id.strip())
        if card is None or not card["assignee"].startswith("agent:"):
            return ""
        _mark_once(store, card["id"], card["assignee"])
        return card["assignee"]


def _mark_once(store: Store, task_id: str, actor: str) -> None:
    """Write the marker unless this card already carries one for this actor."""
    already = store.events.of_task(task_id, kinds=("inferred",))
    if any(event["actor"] == actor for event in already):
        return
    record(store, task=task_id, actor=actor, kind="inferred", body={"from": "assignee"})


def heartbeat(store: Store, actor: str, *, at: float | None = None,
              session: str = "") -> None:
    _presence_beat(store, actor, at, session)
    _heartbeat_leases(store, actor, at=at)


def _presence_beat(store: Store, actor: str, at: float | None, session: str = "") -> None:
    """Presence rides the heartbeat: every server call says "this dev is here".

    Never fatal and never fancy — a presence row is a hint for routing and the team brief,
    and refusing a write because an actor id would not parse would break the call carrying it.
    """
    try:
        from ..engine.identity import parse

        store.presence.beat(actor, parse(actor)["dev"], now() if at is None else at, session)
    except Exception:  # noqa: BLE001 — a hint, not a fact anybody depends on
        pass


def _heartbeat_leases(store: Store, actor: str, *, at: float | None = None) -> None:
    """Push this actor's LIVE lease deadlines out, and expire every dead one.

    Both halves belong together: the sweep is what makes another agent's crash
    visible, and running it on every call means no daemon has to exist to notice one.

    An already-expired lease is NOT revived, and that is the important case. By the
    time it lapsed another agent may have claimed the task, so quietly handing it
    back would produce two holders and no error. The late agent instead finds out at
    its next write, where the lease guard names the fix — which is the one path that
    cannot end with two agents editing the same files believing they own them.
    """
    when = now() if at is None else at
    for lease in store.leases.of_actor(actor, when):
        store.leases.renew(task_id=lease["task"], actor=actor, expires=when + LEASE_TTL)
    sweep_dead(store, at=when)
