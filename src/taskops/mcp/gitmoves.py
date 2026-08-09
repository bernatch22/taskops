"""The two tool handlers that run git — split from `tools.py` along the seam
its own docstring names: the tools table versus the git that belongs to some of
them. Every `git` invocation happens HERE, in the client, where the caller's
filesystem actually is. v1's `recover` ran git on the server and reported paths
from a machine that was not the caller's.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import brief, render, integrate
from .._json import as_rows, as_object, as_strings
from ..board import Board
from .._errors import Refused, BadRequest
from ..gitwork import trees, remote, catchup

Args = dict[str, Any]

SETTLED = frozenset({"mentions", "done"})
"""The two board groups that are NOT open work, for the landing gate.

`mentions` is per-viewer, not work at all. `done` is work that is finished AND
already in the milestone branch — it was added to the payload so closed cards
stay visible (a chapter's history existed in the log and on no screen), and the
gate, which excluded only `mentions`, read the new group as a reason to refuse.
Left that way a chapter could never land again: the FIRST card you integrated
blocked its own chapter permanently. Found landing a real one — "still has open
work (done: 8)" with nothing open (2026-08-08).

The rule the gate enforces is "nothing unfinished and nothing unintegrated".
`done` is the one group that is neither, so it belongs in a named set beside
`mentions` rather than in a second special case.
"""


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
    What stays impossible is landing one with open work: the gate below refuses
    while ANY card of the chapter is not both closed and integrated.

    tasks=[…] and done=true are the SAME card merge, N times — the loop lives in
    `integrate.py` and calls the single-card path per card, so there is no second
    merge implementation to keep in step. This function stays the dispatcher.
    """
    stone = str(args.get("milestone", ""))
    if stone:
        return _land(board, repo, stone, bool(args.get("criteria_met")))
    if "tasks" in args or args.get("done"):
        return integrate.batch(board, args, lambda task: integrate.one(board, repo, task)[0])
    return integrate.one(board, repo, str(args.get("task", "")))[1]


def _land(board: Board, repo: Path, stone: str, criteria_met: bool) -> str:
    """The gate is the board, the git is the client, the record is a verb —
    the same three-way split as a card merge, one level up."""
    view = board.call("board", {"milestone": stone})
    named = as_object(view.get("milestone"))
    if not named:
        raise BadRequest(f"milestone {stone} does not exist — taskops_board names the open ones")
    open_work = {
        group: rows
        for group, rows in as_object(view.get("groups")).items()
        if rows and group not in SETTLED
    }
    if open_work:
        listed = " · ".join(f"{g}: {len(r)}" for g, r in sorted(open_work.items()))
        raise Refused(
            f"{stone} still has open work ({listed}) — a milestone lands whole or not at "
            "all. Finish, merge or drop what is left, then taskops_merge milestone= again."
        )
    crits = as_strings(named.get("criteria"))
    if crits and not criteria_met:
        # The chapter's criteria are the human's question, never the machine's:
        # every card can be green while the assembled thing is not
        # (docs/fan-out.md §4 — six green cards, one placeholder page). Nothing
        # is judged or stored here; the answer travels in the call and is
        # recorded in the `landed` event.
        listed = "\n".join(f"  {n}. {c}" for n, c in enumerate(crits, 1))
        raise Refused(
            f"{stone} is accepted against:\n{listed}\n"
            "Look at the assembled thing, not the board — then, if each one holds, say so: "
            f"taskops_merge milestone={stone} criteria_met=true"
        )
    _catch_up_to_trunk(repo, str(named.get("branch", "")), stone)
    trunk, sha = trees.land_milestone(repo, str(named.get("branch", "")))
    record: Args = {"milestone": stone, "into": trunk, "sha": sha}
    if crits:
        record["criteria_met"] = True  # the human's answer, on the record
    return render.plain(board.call("merged", record))


def _catch_up_to_trunk(repo: Path, branch: str, stone: str) -> None:
    """A finished chapter that is behind a MOVED trunk catches itself up first.

    THE COST, twice in two days, the second time verbatim:

        ✗ ms/the-server-becomes-v2-taskops-be conflicts with master in:
          ARCHITECTURE.md
          CLAUDE.md
          (merge aborted — master is untouched)

    By construction, not by accident: a chapter branch is cut from the trunk AS
    OF ITS FIRST `assign`, chapters overlap, and the docs both of them
    legitimately touch (CLAUDE.md's counts, ARCHITECTURE's status) drift apart.
    Both times the human's fix was `git merge <trunk>` in the integration
    worktree and a second landing call — and the FIRST time it was even clean.

    It is `integrate.catch_up_or_refuse` one level up, on the SAME mechanism
    (`gitwork/catchup.py`: a directory and a branch, no card and no milestone),
    because a card catching up to its chapter and a chapter catching up to the
    trunk are one act on two pairs. What is not shared is the wording, which is
    each caller's own.

    ORDER, and it is load-bearing: this runs AFTER the gate — open work,
    then the criteria. The chapter's criteria are the human's question and no
    git may run before it is answered, so a chapter that is both unanswered and
    behind gets the criteria refusal and an integration worktree whose HEAD has
    not moved. A blocked tree (missing, or dirty because somebody is mid-thought
    in it) is never touched and falls through to exactly today's behaviour:
    `land_milestone` runs, and its own conflict refusal is the one that speaks.
    """
    trunk, count = trees.behind_trunk(repo, branch)
    if not count:
        return  # not behind: from here on the path is byte-for-byte what it was
    tree = trees.integration_tree(repo, branch)
    got = catchup.catch_up(tree, trunk)
    if got.sha or got.blocked:
        return
    raise Refused(
        f"{branch} is {count} commit{'s' if count != 1 else ''} behind {trunk}, "
        f"and catching it up conflicts in:\n"
        + "\n".join(f"  {f}" for f in got.conflicts)
        + f"\n  (merge aborted — {trunk} is untouched, and {tree} is exactly as it was)"
        + f"\n  git said: {got.said}"
        + "\n  → resolve it where the chapter is integrated:\n"
        + f"      cd {tree} && git merge {trunk}\n"
        + f"    fix the conflict, commit, then taskops_merge milestone={stone} again"
    )
