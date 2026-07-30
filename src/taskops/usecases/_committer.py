"""Who is committing — the branch's lease holder before the machine's git identity.

Split from `guard` on its budget, and the seam is the same one `_project.attributed` draws:
that module decides whether a commit may RUN, this one decides WHOSE it is. Identity
inferences deserve to be read on their own, because they go wrong quietly — by writing
somebody else's name on their work.
"""

from __future__ import annotations

from .._clock import now
from ..engine import gitio
from ..storage import Store
from ._project import caller

__all__ = ["committer"]


def committer(store: Store, branch: str, actor: str) -> str:
    """Who is committing — the BRANCH's lease holder before the machine's git identity.

    The same inference `_project.attributed` makes for a card asked for by id, needed here for
    the same reason and found the same way: by running it. A worker sub-agent commits through
    Bash inside its worktree, that Bash has no `$TASKOPS_ACTOR`, so the guard resolved the
    developer — `dev:dev1` instead of `agent:dev1/w2` — and waved the commit through with
    "allowed, you are not an agent". The agent rules did not apply to an agent, and a verifier
    later had to diagnose it from a card comment.

    A task BRANCH with a live lease already knows the answer, and it is a better answer than
    git config: whoever holds the lease is by definition the one doing this work. The same
    fences as `attributed` — only when no actor was stated, only an `agent:` holder (writing a
    person's name on somebody else's commit is the one mistake an apology cannot undo), and
    only on a branch that names a card.
    """
    if actor.strip():
        return caller(store, actor)["id"]
    task = gitio.task_of_branch(branch)
    lease = store.leases.get(task) if task else None
    if lease is not None and lease["actor"].startswith("agent:") \
            and lease["expires"] > now():
        return lease["actor"]
    return caller(store, "")["id"]
