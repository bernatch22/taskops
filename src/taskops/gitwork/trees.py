"""Worktrees: branches are not switched, they are inhabited.

    <repo>/                        main         the human's checkout. Untouched.
    <repo>/.taskops/trees/_ms-x/   ms/x         where the orchestrator integrates
    <repo>/.taskops/trees/tk-a1/   tk-a1        one worker, one directory

`git switch` appears nowhere in this package. The MERGES between these
directories — card into chapter, chapter onto the trunk — are `landing.py`,
this file's sibling; here lives only the geometry. A card's branch is pinned to a
directory for its whole life, so two workers on two milestones are two
directory trees that share nothing — and git itself refuses to check out one
branch in two worktrees, which is a third lock nobody has to remember.

Merging happens IN the integration worktree, never in the shared checkout. v1's
`land` ran `git checkout` in the root and moved the ground under everyone.
"""

from __future__ import annotations

from pathlib import Path

from . import run
from .._errors import Refused

TREES = Path(".taskops") / "trees"


def trees_dir(repo: Path) -> Path:
    return repo / TREES


def card_tree(repo: Path, card: str) -> Path:
    return trees_dir(repo) / card


def integration_tree(repo: Path, milestone_branch: str) -> Path:
    """`ms/mvp-facturador` → `.taskops/trees/_ms-mvp-facturador`."""
    return trees_dir(repo) / f"_{milestone_branch.replace('/', '-')}"


def base_ref(repo: Path) -> str:
    """Where a milestone branch is cut from: the remote trunk if there is one.

    Explicitly NOT "wherever HEAD happens to be" — in v1 a branch cut from a
    moving HEAD inherited another card's commits.
    """
    for ref in ("origin/main", "origin/master", "main", "master"):
        if run.git("rev-parse", "--verify", "--quiet", ref, cwd=repo).ok:
            return ref
    return "HEAD"


def ensure_milestone(repo: Path, branch: str) -> Path:
    """The milestone branch and its integration worktree exist after this call."""
    run.git("fetch", "origin", cwd=repo)  # best effort: offline is not an error
    if not run.has_branch(repo, branch):
        run.must("branch", branch, base_ref(repo), cwd=repo, why=f"cannot create {branch}")
    return _worktree(repo, integration_tree(repo, branch), branch, create=False)


def ensure_card(repo: Path, card: str, branch: str, base: str) -> Path:
    """The worker's world: its own directory, its own branch, cut from `base`."""
    if base and not run.has_branch(repo, base):
        ensure_milestone(repo, base)
    return _worktree(repo, card_tree(repo, card), branch, create=True, base=base or base_ref(repo))


def tidy(repo: Path, trunk: str = "") -> list[str]:
    """Remove worktrees and branches whose work is already in the trunk.

    Ancestry is VERIFIED before anything is deleted. v1 accumulated 133
    worktrees because nothing ever cleaned up; the opposite mistake — deleting
    unmerged work — is the one that cannot be undone.
    """
    target = trunk or base_ref(repo)
    removed: list[str] = []
    root = trees_dir(repo)
    if not root.is_dir():
        return removed
    for tree in sorted(root.iterdir()):
        if not tree.is_dir():
            continue
        branch = run.branch_at(tree)
        if not branch or run.dirty(tree):
            continue  # somebody is still working in there
        if not run.git("merge-base", "--is-ancestor", branch, target, cwd=repo).ok:
            continue
        if run.git("worktree", "remove", str(tree), cwd=repo).ok:
            run.git("branch", "-d", branch, cwd=repo)
            removed.append(f"{tree.name} ({branch})")
    run.git("worktree", "prune", cwd=repo)
    return removed


def _worktree(repo: Path, path: Path, branch: str, *, create: bool, base: str = "") -> Path:
    """Idempotent: an existing directory on the right branch is simply reused."""
    if path.is_dir():
        found = run.branch_at(path)
        if found and found != branch:
            raise Refused(f"{path} is on {found}, not {branch} — remove it or use another card")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if create and not run.has_branch(repo, branch):
        run.must("worktree", "add", str(path), "-b", branch, base, cwd=repo, why=_why(branch))
    else:
        run.must("worktree", "add", str(path), branch, cwd=repo, why=_why(branch))
    return path


def _why(branch: str) -> str:
    return (
        f"cannot open a worktree for {branch}. If git says it is already checked out, "
        "that branch lives in another directory — work there instead"
    )
