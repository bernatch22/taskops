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
from ..engine import identity, sweep_dead
from ..storage import Store, resolve_root

__all__ = ["project", "caller", "heartbeat", "locate"]


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


def heartbeat(store: Store, actor: str, *, at: float | None = None) -> None:
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
