"""Recording what git actually did. Called from a `post-commit` hook.

This is the half of git-binding that does not need permission. The guard runs before a
commit and can refuse; this runs after one and only records — which is why it also
catches every commit the guard never saw: a human's `git commit` in a terminal, a
`--no-verify`, a merge, a rebase that rewrote history onto a task branch.

Recording is unconditional and idempotent. A commit whose task cannot be determined is
skipped rather than attributed to a guess, because a wrong attribution is worse than a
missing one: the board would show evidence for a task that has none, and the `done`
guard would let it close.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import TaskopsError
from ..contracts import Event, Task
from ..engine import gitio, record
from ..storage import Store
from ._project import caller, project
from ._transition import move

__all__ = ["ingest_commit"]


def ingest_commit(start: Path | str, sha: str = "HEAD", *, actor: str = "") -> Event | None:
    """Bind one commit to its task. None if there is no task to bind it to.

    The task comes from the trailer FIRST and the branch second. That order matters
    after a rebase: the branch is whatever is checked out now, the trailer is what the
    author wrote, and when they disagree the author is right.
    """
    with project(start) as store:
        resolved = gitio.head_sha(store.root) if sha == "HEAD" else sha
        message = gitio.commit_message(store.root, resolved)
        task = gitio.task_of_message(message) or \
            gitio.task_of_branch(gitio.current_branch(store.root))
        card = store.tasks.get(task) if task else None
        if card is None:
            return None
        who = caller(store, actor)["id"]
        bound = record(store, task=task, actor=who, kind="commit",
                       body={"sha": resolved, "subject": message.splitlines()[0],
                             "files": gitio.changed_files(store.root, resolved)})
        _started(store, card, who)
        return bound


def _started(store: Store, card: Task, who: str) -> None:
    """A commit on a `claimed` card means the work landed — so the card says so.

    `in_progress` used to be a call an agent had to remember, and the numbers were blunt about
    it: ONE transition to it in the whole history of this project, written by hand in a test.
    An agent that claims a card starts working on it; asking for a second call to announce the
    obvious is a call that gets skipped, and the board spends the afternoon saying `claimed`
    while a worker commits into it.

    Derived, the distinction finally earns its place: `claimed` is held with nothing landed,
    `in_progress` is work inside — which makes "claimed for twenty minutes and still nothing"
    a signal about a stuck worker rather than the normal state of everything.

    Through `move`, not `set_status`: the state machine has one home, and a status written
    from an ingest path would be the second opinion that eventually disagrees with it.

    AFTER the binding, and refusals are swallowed — both learned the hard way in one run. This
    hook fires as whoever git says made the commit, which is often the DEVELOPER while the lease
    belongs to an agent, so the move hits the lease guard. Attempted first, that refusal took the
    commit binding down with it: the card lost the commit it was supposed to be bound to, which
    is the whole point of this function, over a status nobody had asked for.
    """
    if card["status"] != "claimed":
        return
    try:
        move(store, card, who, "in_progress", "the first commit landed", no_code=False)
    except TaskopsError:
        return


def ingest_branch(start: Path | str, branch: str = "", *, actor: str = "") -> Event | None:
    """Note that a task's branch exists, and record it on the lease.

    Called from `post-checkout`. The lease carries the branch so the live board can show
    where an agent is working, and so a later `taskops_ask` can name the branch instead
    of asking the agent to remember it.
    """
    with project(start) as project_store:
        name = branch or gitio.current_branch(project_store.root)
        task = gitio.task_of_branch(name)
        if not task or project_store.tasks.get(task) is None:
            return None
        project_store.leases.set_branch(task_id=task, branch=name)
        return record(project_store, task=task,
                      actor=caller(project_store, actor)["id"],
                      kind="branch", body={"branch": name})
