"""Reading a diff out of the clone the viewer already has.

The dashboard shows real patches, and they come from the viewer's OWN repo —
never from the board. `events.jsonl` stores references and measures (sha,
subject, numstat) and is replayed forever; content is DERIVED here, on demand,
and nothing this module returns is ever written back. ARCHITECTURE.md §16.

**A ref that arrives from a browser is never handed to a diff.** Two walls, in
this order:

1. a shape guard — a ref that could be read as an option (`-…`) or that carries
   whitespace/control bytes never reaches git at all;
2. `git rev-parse --verify --quiet <ref>^{commit}` through `gitwork/run`, where
   the ref is one argv element and there is no shell anywhere in the package
   (`run.py` is the only module allowed `subprocess`, and it passes a list).

From there on **only the resolved 40-hex sha is used**. Whatever the browser
sent is dropped after step 2, so the diff commands cannot be reached by it even
in principle. A path filter is user input too, and it goes after `--`, where git
cannot read it as an option.

**The spelling of the commit case, chosen explicitly**: `git diff <first
parent> <sha>` — the first parent resolved by name (`<sha>^1`), NOT `sha^!` and
not a bare `git show`. On a merge commit `sha^!` excludes every parent, so the
patch becomes the whole merged branch: a landed card would render as the diff of
its entire chapter and every card's patch would be useless. First parent only is
the same view GitHub shows for a merge. A ROOT commit has no parent, so it is
diffed against git's empty tree (`EMPTY_TREE`, a constant of git itself).

**The compare case** is `merge-base(a, b) → b`, resolved explicitly with `git
merge-base` rather than written as `a...b`, so the two-dot/three-dot ambiguity
never has to be remembered by a reader — *while the card is still in flight*.

That rule alone made the whole Worktrees screen read `no files differ between
ms/<chapter> and tk-<id>`, on every row, and it was never a bug in the diff
commands: the moment a card is INTEGRATED its branch holds nothing the chapter
branch does not, so `merge-base(chapter, card)` IS the card's head and the range
is empty. The correct answer to the wrong question. Once integrated, the
question a reader is asking is the one GitHub answers for a merged pull request:
what did this branch add to the chapter *when it landed*. So: **when `b` is
already an ancestor of `a`, the base is taken from the merge commit that brought
`b` in** — `taskops_merge` integrates with `--no-ff` (`gitwork/trees.py`), so
for a card this board integrated that commit always exists. The merge is found
by walking `--ancestry-path --merges` and taking the OLDEST such commit, which
is the one that did the bringing in.

Its FIRST PARENT is the chapter as it stood immediately before, and that is the
commit the base is anchored to — but the base is `merge-base(first parent, b)`,
not the first parent itself, and the difference is not academic. Measured on
this repo's own branches: `tk-17d463` against its chapter reads 24 files from
the bare first parent and 7 from the merge-base of it. A chapter integrates card
after card, so by the time a card lands its tip already carries its SIBLINGS'
work, which the card's branch never had — and `git diff` is symmetric, so all of
it renders as the card *deleting* seventeen files it never touched. The
merge-base is the branch point of THIS card and nothing else, which is what
GitHub shows; with no sibling in between the two are the same commit.

If there is no merge commit on that path — a fast-forward integration, which
this board does not do but another clone might — the empty range stands. An
empty diff that is TRUE beats a guessed base. Nothing about this is stored: the
fact lives in the commit graph and is derived per request, ARCHITECTURE.md §16,
and this module still knows nothing about a board (it does not, and must not,
read the `merged` event's sha, even though the board has one).

Turning a resolved range into text and numbers — `stat`, `patch`, `between`,
and the byte cap — is `patch.py`, this file's sibling; here live the walls and
the range arithmetic only.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import run

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""git's own empty tree — what a root commit is diffed against."""

SHAPE = re.compile(r"^[A-Za-z0-9_/.^~@{}+-]{1,200}$")
"""What may even be shown to git. Deliberately narrow: no space, no quote, no
backslash, no control byte, nothing that a shell would find interesting — even
though no shell is ever involved."""


def usable(ref: str) -> bool:
    """The shape guard. A ref starting with `-` would be read as an OPTION by
    any git command, which is the one way an argv element can still misbehave."""
    return bool(ref) and not ref.startswith("-") and bool(SHAPE.match(ref))


def resolve(repo: Path, ref: str) -> str | None:
    """The commit `ref` names, or None — the ONLY door from a string to a sha.

    `^{commit}` peels a tag or a tree-ish, so what comes back is always a commit
    and the callers below never have to peel again."""
    if not usable(ref):
        return None
    got = run.git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=repo)
    out = got.out.strip()
    return out if got.ok and re.fullmatch(r"[0-9a-f]{40}", out) else None


def commit_range(repo: Path, sha: str) -> tuple[str, str] | None:
    """(first parent, commit) — see the module docstring for why first parent."""
    resolved = resolve(repo, sha)
    if resolved is None:
        return None
    parent = run.git("rev-parse", "--verify", "--quiet", f"{resolved}^1", cwd=repo)
    base = parent.out.strip() if parent.ok and parent.out.strip() else EMPTY_TREE
    return base, resolved


def integration_base(repo: Path, base: str, head: str) -> str | None:
    """Where `head` branched off the chapter it was merged into, or None when no
    merge commit brought it in (a fast-forward). Anchored on the first parent of
    that merge; see the module docstring for why the merge-base of it, not it.

    Both arguments are already resolved shas and each stays its own argv element
    — `--not` rather than a `head..base` range, which would splice two refs into
    one string."""
    walked = run.git(
        "rev-list", "--ancestry-path", "--merges", base, "--not", head, cwd=repo
    )
    if not walked.ok:
        return None
    merges = walked.out.split()
    if not merges:
        return None
    parent = run.git("rev-parse", "--verify", "--quiet", f"{merges[-1]}^1", cwd=repo)
    before = parent.out.strip()
    if not parent.ok or not re.fullmatch(r"[0-9a-f]{40}", before):
        return None
    forked = run.git("merge-base", before, head, cwd=repo)
    out = forked.out.strip()
    return out if forked.ok and re.fullmatch(r"[0-9a-f]{40}", out) else None


def compare_range(repo: Path, a: str, b: str) -> tuple[str, str] | None:
    """(base, head) — the card-as-PR read: what `b` adds on top of `a`.

    In flight that base is `merge-base(a, b)`. Integrated — `b` is an ancestor
    of `a`, which is exactly `merge-base(a, b) == b` — it is where `b` forked
    from the chapter, read off the merge that landed it; see the module
    docstring. No merge found: the empty range stands rather than a guessed
    base."""
    left, right = resolve(repo, a), resolve(repo, b)
    if left is None or right is None:
        return None
    got = run.git("merge-base", left, right, cwd=repo)
    base = got.out.strip() if got.ok and got.out.strip() else left
    if base == right:
        return (integration_base(repo, left, right) or base), right
    return base, right
