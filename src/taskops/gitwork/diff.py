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
never has to be remembered by a reader.

The patch is capped in BYTES and the cap is stated in the answer: a silently cut
patch is a lie, a flagged one is a fact.
"""

from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from . import run, bind

CAP = 512 * 1024
"""Bytes of patch text returned at most. Comfortably above a human-sized card
diff and far below anything that would stall a browser."""

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


def compare_range(repo: Path, a: str, b: str) -> tuple[str, str] | None:
    """(merge-base, head) — the card-as-PR read: what `b` adds on top of `a`."""
    left, right = resolve(repo, a), resolve(repo, b)
    if left is None or right is None:
        return None
    base = run.git("merge-base", left, right, cwd=repo)
    return (base.out.strip() if base.ok and base.out.strip() else left), right


def stat(repo: Path, a: str, b: str) -> dict[str, list[int] | None]:
    """`+/-` per file between two RESOLVED shas, in the exact vocabulary
    `bind.py` writes into a commit event: `[added, deleted]`, or None for a file
    git could not count (a binary — never `[0, 0]`). One vocabulary everywhere."""
    raw = run.git("diff", "--numstat", "-z", a, b, cwd=repo)
    return bind.parse_numstat(raw.out) if raw.ok else {}


def patch(
    repo: Path, a: str, b: str, path: str | None = None, cap: int = CAP
) -> tuple[str, bool]:
    """(text, truncated). The path filter goes after `--`: git cannot read it
    as an option there, whatever it says."""
    args = ["diff", "--patch", "--no-color", a, b]
    if path:
        args += ["--", path]
    raw = run.git(*args, cwd=repo)
    if not raw.ok:
        return "", False
    text = raw.out
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= cap:
        return text, False
    return encoded[:cap].decode("utf-8", "ignore"), True


def between(
    repo: Path, a: str, b: str, path: str | None = None, cap: int = CAP
) -> dict[str, Any]:
    """The whole answer for one range, already resolved. The HTTP door wraps it;
    it decides nothing about transport and knows nothing about a board."""
    text, cut = patch(repo, a, b, path, cap)
    return {
        "base": a,
        "head": b,
        "stat": stat(repo, a, b),
        "patch": text,
        "truncated": cut,
        "cap": cap,
    }
