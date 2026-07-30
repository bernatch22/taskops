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

from ..contracts import Event
from ..engine import gitio, record
from ._project import caller, project

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
        if task is None or store.tasks.get(task) is None:
            return None
        who = caller(store, actor)["id"]
        bound = record(store, task=task, actor=who, kind="commit",
                       body={"sha": resolved, "subject": message.splitlines()[0],
                             "files": gitio.changed_files(store.root, resolved)})
        return bound



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
