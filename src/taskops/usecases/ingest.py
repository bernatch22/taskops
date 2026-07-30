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
from ..storage.sync import event_from
from ._binding import already_bound
from ._committer import committer
from ._project import caller, project
from ._routing import call_remote
from .publish import publish_branch

__all__ = ["ingest_commit", "ingest_branch", "bind"]


def bind(start: Path | str, body: dict[str, object]) -> Event | None:
    """Record a commit or branch fact a CLONE observed, in this store — the rpc half.

    The git repository lives on the developer's machine and the truth lives here, so the clone
    reads git and this records. Only the two kinds the git hooks produce; anything else in
    `kind` is refused by omission (returns None), because this is reachable with a project
    token and a recorder that stored arbitrary kinds would let a token write history.
    """
    kind = str(body.get("kind", ""))
    task = str(body.get("task", ""))
    with project(start) as store:
        if kind not in ("commit", "branch") or store.tasks.get(task) is None:
            return None
        if kind == "commit" and already_bound(store, task, str(body.get("sha", ""))):
            return None
        who = caller(store, str(body.get("actor", "")))["id"]
        if kind == "branch":
            branch = str(body.get("branch", ""))
            store.leases.set_branch(task_id=task, branch=branch)
            return record(store, task=task, actor=who, kind="branch",
                          body={"branch": branch})
        return record(store, task=task, actor=who, kind="commit",
                      body={"sha": str(body.get("sha", "")),
                            "subject": str(body.get("subject", "")),
                            "files": [str(f) for f in body.get("files", [])
                                      if isinstance(f, str)]})


def ingest_commit(start: Path | str, sha: str = "HEAD", *, actor: str = "") -> Event | None:
    """Bind one commit to its task. None if there is no task to bind it to.

    The task comes from the trailer FIRST and the branch second. That order matters
    after a rebase: the branch is whatever is checked out now, the trailer is what the
    author wrote, and when they disagree the author is right.
    """
    with project(start) as store:
        root = store.root
        resolved = gitio.head_sha(root) if sha == "HEAD" else sha
        message = gitio.commit_message(root, resolved)
        task = gitio.task_of_message(message) or \
            gitio.task_of_branch(gitio.current_branch(root))
        if task is None:
            return None
        who = committer(store, gitio.current_branch(root), actor)
    body = {"kind": "commit", "task": task, "actor": who, "sha": resolved,
            "subject": message.splitlines()[0], "files": gitio.changed_files(root, resolved)}
    # THE fact the done-guard reads, so it must land where the guard runs. With a remote that
    # is the server; unreachable, it lands locally and `push` carries it later — recorded in
    # exactly one of the two places, never both, or the same commit binds twice (tk-a6daef).
    # PUBLISHED as soon as it is bound. A peer reviewer on another machine cannot check work
    # that never left this one — seven cards were rejected as "no code" for exactly that.
    publish_branch(root, gitio.current_branch(root))
    if (answer := call_remote(root, "bind", body)) is not None:
        return event_from(answer)
    with project(start) as store:
        if store.tasks.get(task) is None or already_bound(store, task, resolved):
            return None
        return record(store, task=task, actor=who, kind="commit",
                      body={"sha": resolved, "subject": body["subject"],
                            "files": body["files"]})



def ingest_branch(start: Path | str, branch: str = "", *, actor: str = "") -> Event | None:
    """Note that a task's branch exists, and record it on the lease.

    Called from `post-checkout`. The lease carries the branch so the live board can show
    where an agent is working, and so a later `taskops_ask` can name the branch instead
    of asking the agent to remember it.
    """
    with project(start) as project_store:
        root = project_store.root
        name = branch or gitio.current_branch(root)
        task = gitio.task_of_branch(name)
        if not task:
            return None
        who = committer(project_store, name, actor)
    sent = call_remote(root, "bind", {"kind": "branch", "task": task, "actor": who,
                                      "branch": name})
    if sent is not None:
        return event_from(sent)
    with project(start) as project_store:
        if project_store.tasks.get(task) is None:
            return None
        project_store.leases.set_branch(task_id=task, branch=name)
        return record(project_store, task=task, actor=who,
                      kind="branch", body={"branch": name})
