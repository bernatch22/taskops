"""Bring one worktree up to date with a branch — the mechanical half of an
integration, and nothing else.

WHY THIS EXISTS. `trees.behind` diagnosed a stale branch and the board REFUSED,
naming the two commands the human then executed unchanged: ~9 times in two days
the orchestrator ran `cd <tree> && git merge <branch>` and called
`taskops_merge` again. When the diagnosis AND the remedy are both the board's,
and the remedy is mechanical, refusing is not safety — it is toil. So the
refusal became a move, on ONE path only: a card already `done`, inside the
integration flow the orchestrator invoked. The worker handed the card in;
integrating it, including the mechanical half, is the orchestrator's move and
always was. A clean merge decides nothing — it executes the inevitable.

WHY IT IS NOT IN `trees.py`. A card catching up to its chapter and a chapter
catching up to the trunk are the SAME act on different pairs, so the parameters
are a worktree directory and a branch to merge into it — no card, no milestone,
no board. Kept next to `trees` rather than inside it, that generality is
visible instead of implied.

WHY IT RETURNS INSTEAD OF REFUSING. Every guard here is a REPORT, never a
sentence: `gitwork/` knows a tree is dirty, it does not know how the caller
wants to say so, and the card path is required to keep today's refusal verbatim
while other callers say their own thing. One outcome type, three states:

    sha        the merge went through; the tree now contains `branch`
    conflicts  git could not merge; the merge is ABORTED and the tree is
               exactly as it was — never left mid-merge for somebody to find
    blocked    a guard said do not touch this tree at all: "missing" (never
               conjure a worktree) or "dirty" (somebody may be mid-thought in
               it even though the card is done)
"""

from __future__ import annotations

from typing import NamedTuple
from pathlib import Path

from . import run


class CatchUp(NamedTuple):
    sha: str = ""
    conflicts: list[str] = []  # noqa: RUF012 — a NamedTuple default is not shared state
    blocked: str = ""
    said: str = ""


def catch_up(tree: Path, branch: str) -> CatchUp:
    """Merge `branch` into whatever is checked out in `tree`. Never raises."""
    if not tree.is_dir():
        return CatchUp(blocked="missing")
    if run.dirty(tree):
        return CatchUp(blocked="dirty")
    result = run.git("merge", "--no-edit", branch, cwd=tree)
    if not result.ok:
        conflicts = run.git("diff", "--name-only", "--diff-filter=U", cwd=tree).out
        run.git("merge", "--abort", cwd=tree)
        return CatchUp(conflicts=conflicts.splitlines(), said=result.err or result.out)
    return CatchUp(sha=run.must("rev-parse", "HEAD", cwd=tree))
