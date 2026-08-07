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
    """task= integrates a done card into ITS milestone branch. milestone= lands
    a FINISHED milestone into the trunk.

    A card merge has no target argument — merging a card to `main` cannot be
    expressed, which is the only kind of guardrail that never drifts. Landing
    a milestone CAN be expressed, since 2026-08-07, because the alternative was
    worse: with no move to make, the orchestrator reached for raw `git merge`
    in the shared checkout and the board never learned the milestone shipped.
    What stays impossible is landing one with open work: the gate below refuses
    while ANY card of the chapter is not both closed and integrated.
    """
    stone = str(args.get("milestone", ""))
    if stone:
        return _land(board, repo, stone)
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


def _land(board: Board, repo: Path, stone: str) -> str:
    """The gate is the board, the git is the client, the record is a verb —
    the same three-way split as a card merge, one level up."""
    view = board.call("board", {"milestone": stone})
    named = as_object(view.get("milestone"))
    if not named:
        raise BadRequest(f"milestone {stone} does not exist — taskops_board names the open ones")
    open_work = {
        group: rows
        for group, rows in as_object(view.get("groups")).items()
        if rows and group != "mentions"  # mentions are per-viewer, not work
    }
    if open_work:
        listed = " · ".join(f"{g}: {len(r)}" for g, r in sorted(open_work.items()))
        raise Refused(
            f"{stone} still has open work ({listed}) — a milestone lands whole or not at "
            "all. Finish, merge or drop what is left, then taskops_merge milestone= again."
        )
    trunk, sha = trees.land_milestone(repo, str(named.get("branch", "")))
    return render.plain(
        board.call("merged", {"milestone": stone, "into": trunk, "sha": sha})
    )
