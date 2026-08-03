"""The task, and the whole of what an agent needs to read to work on one.

`Task` is the row. `TaskView` is the answer to "what am I doing and what does it
touch" — assembled once so an agent does not have to make five calls to find out
that something else is already editing the file it was about to rewrite.
"""

from __future__ import annotations

from typing import TypedDict

from .._types import Status
from .commit import CommitRef
from .event import Event
from .lease import Lease

__all__ = ["Task", "TaskView"]


class Task(TypedDict):
    """One unit of work. Flat on purpose: this IS the row and the wire format."""

    id: str
    title: str

    spec: str
    """The brief, complete enough that an agent reads it and needs nothing else.

    The single most important field in the system and the one most often written
    badly. A title is a label; a spec says what done looks like, what must not
    change, and where to look — because the reader is a fresh context that was
    not in the room when the work was decided.
    """

    status: Status
    priority: int
    """0 urgent … 3 someday. Lower sorts first, which is why it is not a Literal:
    a project that wants five bands should not need an engine change."""

    parent: str | None
    """An epic's id. The TREE is here; the DAG is `deps` — they answer different
    questions ("what is this part of" vs "what must happen first")."""

    labels: list[str]
    files: list[str]
    """The edit surface, as the planner understands it. A hint, never a lock: the
    scheduler uses it to avoid handing two agents the same file, and being wrong
    costs a merge conflict rather than a wrong answer."""

    created_by: str

    assignee: str
    """Who this card is FOR, or "" for the open pool.

    Set by a planner that knows who should do the work, and by `dispatch` before it launches a
    worker. It is not a claim: an assigned card still has to be claimed, so the lease stays the only
    thing that says somebody is actually on it. What assignment changes is the SCHEDULER — an
    assigned card is invisible to every other agent, which is what makes "this one is yours" mean
    something instead of being a label anybody can ignore.
    """

    reviewer: str
    """Who may CLOSE this card, or "" for the stock verifier — decided when it is created.

    A field and not a label, because the two are different kinds of fact: a label is a routing
    hint anybody may edit for search, and this is the policy about who signs off. `human` (or a
    `dev:` id) means a person reads the diff and NO agent may close it; a registered specialist's
    name means spawn that one; "" leaves today's rule — anyone but the agent that asked for the
    review. The project's default lives in the context layer, not in a constant here.
    """

    created: float
    updated: float


class TaskView(TypedDict):
    """Everything about one task, in one read."""

    task: Task
    lease: Lease | None
    blocked_by: list[Task]
    """Open dependencies. Empty is the whole reason a task is pickable."""

    blocks: list[Task]
    """What is waiting on this one — the argument for finishing it today."""

    children: list[Task]
    epic: Task | None
    """The card this one is PART OF, resolved. `task.parent` is only an id, and an id is not
    something a worker can read — so a child never learned it belonged to anything while its
    parent had listed it all along. One direction of a tree is not a tree."""

    neighbours: list[Task]
    """Tasks whose `files` intersect this one's. The collision warning: an agent
    that reads this knows who to message before it starts, not after the merge."""

    thread: list[Event]
    """Comments and directed messages, oldest first. The conversation about this
    task, from every actor that has ever touched it."""

    commits: list[CommitRef]
    """The commits bound to this task, oldest first — with their subjects and the files they touched.

    `list[str]` at first, which threw away the subject and the file list the event already carried: a
    finished card rendered as a column of hashes, and the only substance on the page was whatever the
    agent happened to put in a comment.
    """

    history: list[Event]
