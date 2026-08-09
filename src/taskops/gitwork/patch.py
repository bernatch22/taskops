"""Reading the patch itself, once the refs are already RESOLVED shas.

Split out of `diff.py` at its own seam: that file owns the walls and the range
arithmetic (what may even reach git, and which two commits a reader means);
this one turns a resolved pair into text and numbers. Nothing here ever sees a
string a browser sent — `diff.resolve` is the only door from a string to a
sha, and everything below takes its output.

The patch is capped in BYTES and the cap is stated in the answer: a silently
cut patch is a lie, a flagged one is a fact.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import run, bind

CAP = 512 * 1024
"""Bytes of patch text returned at most. Comfortably above a human-sized card
diff and far below anything that would stall a browser."""


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
