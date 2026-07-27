"""A commit, as the card knows it.

`TaskView.commits` used to be `list[str]` — bare shas — while the `commit` event underneath already
carried the subject and the files it touched. So the data was recorded, stored, replicated, and then
thrown away one layer before anybody could read it: a finished card showed `4c13dbd45823` and nothing
else, and the only substance on the page was whatever the agent happened to write in a comment.

Nothing here is new information. It is the event body, given a shape so that a renderer and the studio
can use what was always there.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["CommitRef"]


class CommitRef(TypedDict):
    """One commit bound to a task."""

    sha: str
    subject: str
    """The commit's first line. What makes a list of commits readable at a glance instead of a
    column of hashes — and the reason this contract exists."""

    files: list[str]
    """Paths the commit touched, as `git diff-tree` reported them.

    Empty for a repository's very first commit, which has no parent to diff against. Also the answer
    to "did this task do what its `files` said it would", which is a question a review asks and a
    board could not previously support.
    """

    actor: str
    ts: float
