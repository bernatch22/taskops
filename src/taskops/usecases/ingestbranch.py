"""`post-checkout` — noting that a card's branch exists, and putting it on the lease.

Split from `ingest` on its budget. The seam is the git event: that module is about a COMMIT,
which is evidence a card can close on; this is about a BRANCH, which is only ever a convenience
— the live board shows where an agent is working, and `taskops_ask` can name the branch instead
of asking an agent to remember it.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import Event
from ..engine import gitio, record
from ..storage.sync import event_from
from ._committer import committer
from ._project import project
from ._routing import call_remote

__all__ = ["ingest_branch"]


def ingest_branch(start: Path | str, branch: str = "", *, actor: str = "") -> Event | None:
    """Note that a task's branch exists, and record it on the lease.

    Called from `post-checkout`. The lease carries the branch so the live board can show
    where an agent is working, and so a later `taskops_ask` can name the branch instead
    of asking the agent to remember it.
    """
    where = Path(start)
    with project(start) as project_store:
        name = branch or gitio.current_branch(where)
        task = gitio.task_of_branch(name)
        if not task:
            return None
        who = committer(project_store, name, actor)
        root = project_store.root
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
