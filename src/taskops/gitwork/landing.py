"""Integration: a card merges into its chapter, a chapter lands on the trunk.

Split out of `trees.py` at its own seam: that file owns the GEOMETRY (which
branch lives in which directory), this one owns the MERGES between them — and
the two questions (`behind`, `behind_trunk`) a merge conflict answers badly.
Merging happens IN the integration worktree, never in the shared checkout;
`land_milestone` is the one sanctioned write to the human's own checkout, and
only because the human asked for exactly this move.
"""

from __future__ import annotations

from pathlib import Path

from . import run, trees, remote
from .._errors import Refused


def behind(repo: Path, milestone_branch: str, card_branch: str) -> int:
    """How many commits of the milestone branch the card branch does not have.

    0 means the card contains the milestone head. This is the question a merge
    conflict answers badly: git names a FILE, and the real cause — this branch
    never pulled the chapter in — is nowhere in the message. Asked before the
    merge, it is one `merge-base --is-ancestor`.
    """
    if not (run.has_branch(repo, milestone_branch) and run.has_branch(repo, card_branch)):
        return 0  # nothing to be behind yet — the merge itself will say what is missing
    if run.git("merge-base", "--is-ancestor", milestone_branch, card_branch, cwd=repo).ok:
        return 0
    count = run.git("rev-list", "--count", f"{card_branch}..{milestone_branch}", cwd=repo).out
    return int(count) if count.isdigit() else 0


def behind_trunk(repo: Path, milestone_branch: str) -> tuple[str, int]:
    """`behind`, one level up: how far a chapter is from the trunk it lands into.

    A chapter is cut from `base_ref` at its first assign, and chapters overlap —
    while one is in flight another lands — so by landing time the trunk has
    moved. Returns (trunk, count); the trunk is `base_ref`'s to name.
    """
    trunk = trees.base_ref(repo)
    return trunk, behind(repo, trunk, milestone_branch)


def merge_card(repo: Path, milestone_branch: str, card_branch: str, card: str) -> str:
    """Integrate one card. Returns the merge sha, or refuses with git's own words.

    A conflict leaves the milestone branch exactly as it was: the merge is
    aborted and the files are named; the worker then pulls the milestone into its
    own branch and resolves there. Nothing reaches `main` — a person does that.
    """
    tree = trees.ensure_milestone(repo, milestone_branch)
    result = run.git("merge", "--no-ff", "-m", f"merge {card}", card_branch, cwd=tree)
    if not result.ok:
        conflicts = run.git("diff", "--name-only", "--diff-filter=U", cwd=tree).out
        run.git("merge", "--abort", cwd=tree)
        raise Refused(
            f"{card} conflicts with {milestone_branch} in:\n"
            + "\n".join(f"  {f}" for f in conflicts.splitlines())
            + f"\n  (merge aborted — {milestone_branch} is untouched)"
            + f"\n  git said: {result.err or result.out}"
            # The card's worktree is pinned to its branch for life and is REUSED
            # by a re-dispatch (`trees._worktree` is idempotent), so it cannot be
            # "re-cut" from anywhere. Resolution happens where the work is: the
            # worker pulls the milestone into its own branch, fixes it there,
            # and the orchestrator merges again.
            + f"\n  → the worker resolves it in its own worktree:"
            f"\n      cd {trees.card_tree(repo, card)} && git merge {milestone_branch}"
            f"\n    fix the conflict, commit, then taskops_merge task={card} again"
        )
    # The card branch too: its `done` push may have been offline, and a card is
    # only readable as a PR on GitHub if both sides of the compare are there.
    remote.push(repo, milestone_branch, card_branch, cwd=tree)  # best effort; local still merged
    return run.must("rev-parse", "HEAD", cwd=tree)


def land_milestone(repo: Path, milestone_branch: str) -> tuple[str, str]:
    """Merge a FINISHED milestone branch into the trunk — the shared checkout.

    The one sanctioned write to the human's own checkout, and only because the
    human asked for exactly this move: v1's `land` stays banned because it was
    AUTOMATIC (a side effect of closing a card) and ran `git checkout` under
    working agents. This is neither — it is invoked explicitly, it refuses
    unless the checkout already IS the trunk, and a conflict aborts clean.
    Returns (trunk_branch, merge_sha).
    """
    trunk = run.branch_at(repo)
    if not trunk or trunk.startswith("ms/") or trunk.startswith("tk-"):
        raise Refused(
            f"the shared checkout is on {trunk or 'a detached HEAD'}, not a trunk — "
            "landing merges INTO what is checked out there, so put it on main first"
        )
    result = run.git("merge", "--no-ff", "-m", f"land {milestone_branch}", milestone_branch, cwd=repo)
    if not result.ok:
        conflicts = run.git("diff", "--name-only", "--diff-filter=U", cwd=repo).out
        run.git("merge", "--abort", cwd=repo)
        raise Refused(
            f"{milestone_branch} conflicts with {trunk} in:\n"
            + "\n".join(f"  {f}" for f in conflicts.splitlines())
            + f"\n  (merge aborted — {trunk} is untouched)\n  git said: {result.err or result.out}"
        )
    remote.push(repo, trunk)  # best effort; local still landed
    return trunk, run.must("rev-parse", "HEAD", cwd=repo)
