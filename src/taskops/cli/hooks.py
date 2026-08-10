"""What the two GIT hooks call — the other half of what `join` installed.

Split off `commands.py` at the seam that file's own docstring named ("the two
commands that CONNECT a repo to a board, **and the git hooks**), the same way
`serving.py` and `watch.py` were: `init` and `join` WRITE a checkout's
configuration once, and these two run on every single commit somebody makes in
it. Nothing here is reachable from a human's fingers — `gitwork/install.py`
writes the shell scripts that call it, and `main.py` routes them.

**Neither of these may ever block a commit.** A failure prints and returns 0.
The hook is a courtesy that binds a commit to its card; a board that is down,
a network that is out or a card that was closed a minute ago must cost somebody
their commit exactly never. That is why the `TaskopsError` below is caught and
written to stderr instead of raised — visible, and never in the way.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..board import find_root, open_board
from .._errors import TaskopsError
from ..gitwork import run, bind, trailer
from .commands import actor


def hook(here: Path, which: str, rest: list[str]) -> int:
    """`hook trailer` stamps the message, `hook commit` binds the commit.

    `hook claude` is a third one and it is routed in `main` instead, because it
    prints NOTHING ever — including the `taskops: …` line every other failure
    here is allowed to write.
    """
    root = find_root(here)
    if which == "trailer":
        if rest:
            trailer.stamp_file(Path(rest[0]), run.branch_at(here))
        return 0
    facts = bind.commit_facts(here)
    if facts is None:
        return 0
    try:
        board = open_board(root, actor())
        bind.record(board, root, facts)
        bind.drain(board, root)
    except TaskopsError as err:
        print(f"taskops: {err}", file=sys.stderr)  # visible, never swallowed
    bind.push_card(here, str(facts["branch"]))
    return 0
