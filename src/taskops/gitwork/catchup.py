"""Bring one worktree up to date with a branch — the mechanical half of an
integration, and nothing else.

WHY THIS EXISTS. `landing.behind` diagnosed a stale branch and the board REFUSED,
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

THE UNION SEAM (`union=`). Three conflicts in one real wave were the same
mechanical thing: sibling cards each APPENDING their own entry to one shared
registry file. That is not judgment, it is git's built-in `union` driver. So a
milestone may DECLARE those paths (`Milestone.union_files`) and they — only they
— get `merge=union` for the duration of this one merge. Everything else
conflicts, aborts and refuses exactly as before, byte for byte, and `union=()`
(the default, and what every chapter that declared nothing passes) does not even
write the file.

WHY `core.attributesFile` AND NOT `$GIT_DIR/info/attributes`. Measured in this
repo: `git rev-parse --git-path info/attributes` inside a LINKED worktree
answers the COMMON dir — `.git/info/attributes`, one file shared by every card
worktree at once. Writing there would hand one card's declaration to every
sibling merging concurrently, and a crash between write and delete would leave
it enabled for the whole repo, invisibly. `core.attributesFile` is passed as a
`-c` override for ONE process and points at a temp file OUTSIDE the repository:
nothing to leak into the tree, nothing for `git status` to see, and if the
process dies the next merge simply does not pass the flag. It is deleted in a
`finally` either way — the merge succeeding or aborting is not its business.

The precedence is the other half of the argument. An in-tree `.gitattributes`
BEATS `core.attributesFile`, so this can never override a committed rule: the
repo's own `-merge` on the built dashboard bundle keeps refusing to text-merge
even if a chapter names it, which is exactly the right way round — a committed
attribute is a repo-wide decision, a declaration is one chapter's convenience.
"""

from __future__ import annotations

import tempfile
from typing import Sequence, NamedTuple
from pathlib import Path

from . import run


class CatchUp(NamedTuple):
    sha: str = ""
    conflicts: list[str] = []  # noqa: RUF012 — a NamedTuple default is not shared state
    blocked: str = ""
    said: str = ""


def catch_up(tree: Path, branch: str, union: Sequence[str] = ()) -> CatchUp:
    """Merge `branch` into whatever is checked out in `tree`. Never raises.

    `union` is the declared seam paths; empty means today's behaviour exactly.
    """
    if not tree.is_dir():
        return CatchUp(blocked="missing")
    if run.dirty(tree):
        return CatchUp(blocked="dirty")
    attrs = _attributes(union)
    try:
        prefix = ("-c", f"core.attributesFile={attrs}") if attrs else ()
        result = run.git(*prefix, "merge", "--no-edit", branch, cwd=tree)
    finally:
        if attrs:
            attrs.unlink(missing_ok=True)
    if not result.ok:
        conflicts = run.git("diff", "--name-only", "--diff-filter=U", cwd=tree).out
        run.git("merge", "--abort", cwd=tree)
        return CatchUp(conflicts=conflicts.splitlines(), said=result.err or result.out)
    return CatchUp(sha=run.must("rev-parse", "HEAD", cwd=tree))


def _attributes(union: Sequence[str]) -> Path | None:
    """The ephemeral attributes file, in the system temp dir — never in the repo.

    None when nothing is declared, and the caller then passes no `-c` at all:
    "this chapter declared no seam" and "this merge behaves as it always did"
    have to be the same instruction stream, not the same instruction stream plus
    an empty override.
    """
    paths = [p.strip() for p in union if p.strip()]
    if not paths:
        return None
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 — closed on the next line
        "w", prefix="taskops-union-", suffix=".attributes", delete=False, encoding="utf-8"
    )
    with handle:
        handle.write("".join(f"{path} merge=union\n" for path in paths))
    return Path(handle.name)
