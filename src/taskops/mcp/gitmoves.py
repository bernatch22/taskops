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
    """
    stone = str(args.get("milestone", ""))
    if stone:
        return _land(board, repo, stone, bool(args.get("criteria_met")))
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
    card_branch = str(dossier.get("branch", task))
    _catch_up_or_refuse(repo, branch, card_branch, task)
    sha = trees.merge_card(repo, branch, card_branch, task)
    return render.plain(board.call("merged", {"task": task, "into": branch, "sha": sha}))


def _stale(task: str, count: int, branch: str) -> str:
    """The cause, counted — every message below starts from this sentence, so
    the fix cannot un-learn WHY the refusal existed: merged blind, a stale
    branch comes back as a conflict about a FILE with the cause nowhere in it.
    ("behind" with no number reads as a bigger problem than three commits.)"""
    return f"{task} is {count} commit{'s' if count != 1 else ''} behind {branch}"


def _by_hand(repo: Path, branch: str, task: str) -> str:
    return f"  cd {trees.card_tree(repo, task)} && git merge {branch}\nthen taskops_merge task={task} again"


def _catch_up_or_refuse(repo: Path, branch: str, card_branch: str, task: str) -> None:
    """A done card that is behind its chapter catches ITSELF up, when git says clean.

    This used to refuse and print the two commands; the human's next act was to
    execute them unchanged, ~9 times in two days (`gitwork/catchup.py` is the
    post-mortem, including why doing it here does not violate "the worker's
    branch is the worker's": the card is `done` and the orchestrator is already
    integrating it).

    It still refuses, and every refusal keeps the cause in the sentence: a dirty
    or absent worktree is NEVER touched — today's message, verbatim, because
    nothing was attempted — and a conflict carries git's own words on top of the
    behind-count, because now the human genuinely is the only one who can decide.
    """
    count = trees.behind(repo, branch, card_branch)
    if not count:
        return  # not behind: from here on the path is byte-for-byte what it was
    got = catchup.catch_up(trees.card_tree(repo, task), branch)
    if got.sha:
        return
    if got.blocked:
        raise Refused(
            f"{_stale(task, count, branch)} — merge it in your own worktree first:\n"
            + _by_hand(repo, branch, task)
        )
    raise Refused(
        f"{_stale(task, count, branch)}, and catching it up conflicts in:\n"
        + "\n".join(f"  {f}" for f in got.conflicts)
        + f"\n  (merge aborted — {trees.card_tree(repo, task)} is exactly as it was)"
        + f"\n  git said: {got.said}"
        + "\n  → only the worker can resolve this, in its own worktree:\n"
        + _by_hand(repo, branch, task)
    )


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
    trunk, sha = trees.land_milestone(repo, str(named.get("branch", "")))
    record: Args = {"milestone": stone, "into": trunk, "sha": sha}
    if crits:
        record["criteria_met"] = True  # the human's answer, on the record
    return render.plain(board.call("merged", record))
