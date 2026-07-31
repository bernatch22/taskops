"""The three fields the peer rule reads, without assembling the whole of `Facts`.

`usecases._facts.facts_for` is the full picture and it costs several queries — commits, open
children, the lease, the criteria — because a CLOSE has to be judged on all of it. The sweep
asks a much smaller question, once per review card on the board: would this caller be refused
outright. Reusing the big reader there would put four queries per card behind a list somebody
refreshes constantly.
"""

from __future__ import annotations

from ..contracts import Task
from ..storage import Store
from .machine import Facts

__all__ = ["facts_of"]


def facts_of(store: Store, task: Task, actor: str) -> Facts:
    """Enough of `Facts` for `reviewer_is_a_peer`, and honestly shaped: the fields it does not
    read are left at their defaults rather than filled with plausible-looking zeros."""
    from ..usecases._facts import entered_review_by

    return Facts(task=task, actor=actor, has_live_lease=False, commits=0, open_children=0,
                 no_code=False, justification="", unpushed=0,
                 reviewer=str(task.get("reviewer", "")),
                 entered_review_by=entered_review_by(store, task["id"]))
