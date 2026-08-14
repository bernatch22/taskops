"""The two tool handlers that run git — split from `tools.py` along the seam
its own docstring names: the tools table versus the git that belongs to some of
them. Every `git` invocation happens HERE, in the client, where the caller's
filesystem actually is. v1's `recover` ran git on the server and reported paths
from a machine that was not the caller's.

The one move that is a whole policy — landing a MILESTONE into the trunk: its
gate, its catch-up and its record — lives in `chapter.py`, the same way the
card batch lives in `integrate.py`. What stays here is the dispatch.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import brief, chapter, integrate
from .._json import as_rows, as_object
from ..board import Board
from .fields import _flag, _list, _text, _object
from ..gitwork import trees, remote

Args = dict[str, Any]

MERGE_SCHEMA: dict[str, Any] = _object(
    {
        "task": _text("a DONE card → into its milestone branch"),
        "tasks": _list(
            "integrate exactly these DONE cards, in the order given — each through the "
            "same single-card path. Stops at the first failure and reports per card."
        ),
        "done": _flag(
            "integrate every card the board groups under MERGE (done, not integrated), "
            "in that group's order. Re-run it after a stop: it continues where it left off."
        ),
        "milestone": _text(
            "ms-… → land the WHOLE milestone into the trunk. Refused while any card "
            "of it is open or unintegrated. The human's call — never do this with "
            "raw git in the shared checkout; the board must record the landing."
        ),
        "criteria_met": _flag(
            "with milestone=: the human's answer to its criteria — recorded, never "
            "judged. true, or false with note= saying which are unmet and why landing "
            "is still right (a criterion that can only be checked after the trunk "
            "moves). Omitted, a chapter with criteria is refused and shown them."
        ),
        "note": _text(
            "with milestone= criteria_met=false: REQUIRED — which criteria are unmet "
            "and why landing is still right. It lands on the record beside the answer."
        ),
    }
)
"""taskops_merge's argument schema — beside the dispatch that answers it, the
way each verbs/ file is its own registry entry. Moved here when schema.py hit
the 200-line budget: the split follows the tool's owner, never the line count
alone."""


def after_update(repo: Path, args: Args, data: Args) -> None:
    """The git that follows an ACCEPTED update — today, exactly one move: a card
    that closed `done` gets its branch pushed.

    THE PLACEMENT. `done` travels through the generic `taskops_update` handler,
    and the only place that knows both "this update carried status=done" and
    "the board took it" is the point right after `board.call("update", …)`
    returns: every refusal — not yours, no commit, needs review — raises out of
    that call, so the refusal path never reaches here and pushes nothing. It
    lives in `gitmoves` rather than in `tools._update` because this module is
    where the MCP layer keeps its git, and it takes the RESULT rather than the
    board because the fact it acts on is the answer, not a second question:
    the branch is `card["id"]` (verbs/_facts.py::branch_of — a card's branch is
    its id), so nothing has to be looked up and nothing can disagree.

    Not in a verb: `verbs/` may not touch git and `tests/test_architecture.py`
    enforces it. Not in the commit hook either — a push there would be on the
    critical path of every commit, and the milestone's rule is that a push is
    never a gate.
    """
    if str(args.get("status", "")) != "done":
        return
    remote.push(repo, str(as_object(data.get("card")).get("id", "")))


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
    What stays impossible is landing one with open work: `chapter.land` refuses
    while ANY card of the chapter is not both closed and integrated.

    tasks=[…] and done=true are the SAME card merge, N times — the loop lives in
    `integrate.py` and calls the single-card path per card, so there is no second
    merge implementation to keep in step. This function stays the dispatcher.
    """
    stone = str(args.get("milestone", ""))
    if stone:
        return chapter.land(board, repo, stone, args)
    if "tasks" in args or args.get("done"):
        return integrate.batch(board, args, lambda task: integrate.one(board, repo, task)[0])
    return integrate.one(board, repo, str(args.get("task", "")))[1]
