"""Landing a CHAPTER — the gate, the catch-up, the record.

Split out of `gitmoves.py` (2026-08-14) along the seam that module's own
docstring already draws: `gitmoves` is the two tool handlers and their
dispatch, this is the one move that is a whole policy — a milestone reaching
the trunk. Same split, same reason, as `integrate.py` for the card path.

The three-way shape is unchanged by the move: the gate is the BOARD (open work,
then the chapter's criteria), the git is the CLIENT (here, where the caller's
filesystem is), and the record is a VERB (`merged`).
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import render
from .._json import as_object, as_strings
from ..board import Board
from .._errors import Refused, BadRequest
from ..gitwork import trees, catchup, landing

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


def land(board: Board, repo: Path, stone: str, args: Args) -> str:
    """The gate is the board, the git is the client, the record is a verb —
    the same three-way split as a card merge, one level up.

    `criteria_met` is read as THREE states, not a bool: absent (nobody has
    answered — refuse and show the criteria), true, and false. It used to be
    `bool(args.get(...))`, which collapsed absent and false into the same
    refusal, and a criterion that is structurally post-landing ("seven days of
    live rows" for code that only deploys FROM the trunk) deadlocked the chapter
    with no honest way out. The schema's own words are "recorded, never judged":
    so false LANDS, and the one thing it may not be is silent — the note saying
    which criteria are unmet and why landing is still right is mandatory, and
    goes on the record beside the answer (2026-08-14).
    """
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
    answered = "criteria_met" in args
    met = bool(args.get("criteria_met"))
    note = str(args.get("note", "")).strip()
    if crits and not answered:
        # The chapter's criteria are the human's question, never the machine's:
        # every card can be green while the assembled thing is not
        # (six green cards, one placeholder page). Nothing
        # is judged or stored here; the answer travels in the call and is
        # recorded in the `landed` event.
        listed = "\n".join(f"  {n}. {c}" for n, c in enumerate(crits, 1))
        raise Refused(
            f"{stone} is accepted against:\n{listed}\n"
            "Look at the assembled thing, not the board — then say so, either way: "
            f"taskops_merge milestone={stone} criteria_met=true — or, if some are unmet "
            "and landing is still right (a criterion that can only be checked AFTER the "
            f"trunk moves), taskops_merge milestone={stone} criteria_met=false "
            'note="<which are unmet, and why landing is still right>"'
        )
    if crits and not met and not note:
        raise Refused(
            f"criteria_met=false lands {stone}, but never in silence — an unmet criterion "
            "landed with no reason is the one dishonest outcome. Say it and it is on the "
            f"record: taskops_merge milestone={stone} criteria_met=false "
            'note="<which are unmet, and why landing is still right>"'
        )
    _catch_up_to_trunk(repo, str(named.get("branch", "")), stone)
    trunk, sha = landing.land_milestone(repo, str(named.get("branch", "")))
    record: Args = {"milestone": stone, "into": trunk, "sha": sha}
    if answered and crits:
        record["criteria_met"] = met  # the human's answer, on the record
        if note:
            record["note"] = note
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
    trunk, count = landing.behind_trunk(repo, branch)
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
