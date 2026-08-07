"""The two tool handlers that run git — split from `tools.py` along the seam
its own docstring names: the tools table versus the git that belongs to some of
them. Every `git` invocation happens HERE, in the client, where the caller's
filesystem actually is. v1's `recover` ran git on the server and reported paths
from a machine that was not the caller's.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import brief, render
from .._json import as_rows, as_object
from ..board import Board
from .._errors import Refused, BadRequest
from ..gitwork import trees

Args = dict[str, Any]


def assign(board: Board, repo: Path, args: Args, now: float) -> str:
    """Assign on the board, cut one worktree per card, hand back the briefs.

    Named for what it DOES. It was `taskops_dispatch`, and that name promised
    something it never delivered: it starts nothing, because spawning the
    sub-agents is the orchestrator's own move, in one message, with these
    briefs. A tool whose name is a lie gets called expecting the lie — and in
    v1 exactly that left cards assigned to workers nobody ever spawned:
    invisible to everyone, claimable by nobody. The name now matches the verb
    underneath it, which was always `assign`.
    """
    worktrees = args.pop("worktrees", True)
    data = board.call("assign", args)
    for card in as_rows(data.get("briefs")):
        if worktrees is not False:
            trees.ensure_card(repo, card["task"], card["branch"], str(card.get("base", "")))
    return brief.briefs(data)


def merge(board: Board, repo: Path, args: Args, now: float) -> str:
    """Integrate a done card into ITS milestone branch.

    There is no target argument. Merging to `main` is not refused here — it
    cannot be expressed, which is the only kind of guardrail that never drifts.
    """
    task = str(args.get("task", ""))
    dossier = board.call("card", {"task": task})
    state = str(dossier.get("state", ""))
    if state != "done":
        # BEFORE git runs, not after: the `merged` verb refuses a non-done card
        # anyway, but by then the branch would already carry the merge — code
        # integrated into ms/* that the board never recorded.
        raise Refused(
            f"{task} is {state or 'unknown'}, not done — nothing merges until the card closes "
            f'(the worker closes it: taskops_update task={task} status=done note="…")'
        )
    branch = str(as_object(dossier.get("milestone")).get("branch", ""))
    if not branch:
        raise BadRequest(f"{task} belongs to no milestone, so there is no branch to integrate into")
    sha = trees.merge_card(repo, branch, str(dossier.get("branch", task)), task)
    return render.plain(board.call("merged", {"task": task, "into": branch, "sha": sha}))
