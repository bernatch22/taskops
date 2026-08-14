"""How a DONE card reaches its chapter — the single path, and the loop over it.

Split out of `gitmoves.py` along the seam the batch made visible: that module is
the tool HANDLERS (what `taskops_assign` and `taskops_merge` dispatch to, plus
landing a whole milestone into the trunk); this one is the one move both
spellings of `taskops_merge` make, `tk-<id>` → `ms/<slug>`.

THE BATCH ADDS NO SECOND MERGE IMPLEMENTATION — that is the whole design, and
it is why `batch` takes the single-card function as an argument instead of
knowing anything about git. Every card in a batch goes through `one()`,
catch-up included; a batch of one is byte-for-byte a `task=` call. Two code
paths to integrate a card would mean the behaviour a chapter got depended on
how many cards the orchestrator happened to name, and the second one would
learn every guard the first one has, late and once.

THE COST IT KILLS. The keys chapter integrated six cards: six `taskops_merge
task=` calls, each preceded by the orchestrator noticing a done-notification,
each a full round trip. The board's own attention grouping already says MERGE →
`taskops_merge` and then made the orchestrator say it N times. What this is NOT
is auto-integration on done: the orchestrator still calls it, review-gated
chapters still see their verdicts first, and integrating remains a decision.
What dies is only the N-fold repetition of a decision already taken.

STOPPING IS SAFE BECAUSE RE-RUNNING CONTINUES. A partial batch is not
rollback-able and must not pretend to be — each merge that went through is a
real `--no-ff` commit and a real `merged` event. So the batch stops at the FIRST
failure of any kind and reports all three outcomes by name (`merged <sha>` ·
`stopped: <the refusal, verbatim>` · `not reached`), and `done=true` resolves
the MERGE group again on the next call: the cards already integrated have left
it, so the re-run picks up exactly where it stopped.
"""

from __future__ import annotations

from typing import Any, Callable
from pathlib import Path

from . import render
from .._json import as_rows, as_object
from ..board import Board
from .._errors import Refused, BadRequest, TaskopsError
from ..gitwork import trees, catchup, landing

Args = dict[str, Any]

BOTH_SPELLINGS = (
    "name the cards — taskops_merge tasks=[tk-a, tk-b] — or let the board resolve them: "
    "taskops_merge done=true"
)


def one(board: Board, repo: Path, task: str) -> tuple[str, str]:
    """Integrate ONE done card into its milestone branch. Returns (sha, report)."""
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
    catch_up_or_refuse(repo, branch, card_branch, task)
    sha = landing.merge_card(repo, branch, card_branch, task)
    return sha, render.plain(board.call("merged", {"task": task, "into": branch, "sha": sha}))


def _stale(task: str, count: int, branch: str) -> str:
    """The cause, counted — every message below starts from this sentence, so
    the fix cannot un-learn WHY the refusal existed: merged blind, a stale
    branch comes back as a conflict about a FILE with the cause nowhere in it.
    ("behind" with no number reads as a bigger problem than three commits.)"""
    return f"{task} is {count} commit{'s' if count != 1 else ''} behind {branch}"


def _by_hand(repo: Path, branch: str, task: str) -> str:
    return f"  cd {trees.card_tree(repo, task)} && git merge {branch}\nthen taskops_merge task={task} again"


def catch_up_or_refuse(repo: Path, branch: str, card_branch: str, task: str) -> None:
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
    count = landing.behind(repo, branch, card_branch)
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
        + "\n  → whoever is integrating — orchestrator or worker — resolves it in the card's"
        + f" worktree, {trees.card_tree(repo, task)}:\n"
        + _by_hand(repo, branch, task)
    )


def batch(board: Board, args: Args, merge_one: Callable[[str], str]) -> str:
    """`tasks=[…]` in the order given, or `done=true` for the MERGE group itself."""
    named = args.get("tasks")
    tasks = [str(t) for t in named] if named is not None else _waiting(board)
    if named is not None and not tasks:
        raise BadRequest("tasks=[] names no card — " + BOTH_SPELLINGS)
    if not tasks:
        # Honest, not an error: "integrate everything that is waiting" over an
        # empty group asked for nothing and got nothing. An orchestrator that
        # ends every chapter with this call must not have to guard it.
        return "Nothing to integrate — no done card is waiting for its chapter."
    done: list[str] = []
    stopped = ""
    for task in tasks:
        try:
            done.append(f"  {task}  merged {merge_one(task)}")
        except TaskopsError as refusal:
            stopped = task
            done.append(f"  {task}  stopped: {refusal}")
            break
    rest = [f"  {task}  not reached" for task in tasks[len(done) :]]
    return "\n".join(_head(len(tasks), len(done) - (1 if stopped else 0), stopped) + done + rest)


def _waiting(board: Board) -> list[str]:
    """The MERGE group, in the group's own order — `verbs/pulse.py::run` decides
    both what is in it (done, `merged_into` empty) and what order it is in. Read
    per call and never cached: a card integrated a second ago is already gone
    from it, which is what makes a re-run continue instead of repeat."""
    groups = as_object(board.call("board", {}).get("groups"))
    return [str(row.get("id", "")) for row in as_rows(groups.get("merge"))]


def _head(total: int, merged: int, stopped: str) -> list[str]:
    line = f"{merged} of {total} integrated"
    if not stopped:
        return [line, ""]
    return [
        line + f", stopped at {stopped}",
        "Fix it, then taskops_merge done=true again — it continues from there.",
        "",
    ]
