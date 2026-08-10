"""Reading the patch itself, once the refs are already RESOLVED shas.

Split out of `diff.py` at its own seam: that file owns the walls and the range
arithmetic (what may even reach git, and which two commits a reader means);
this one turns a resolved pair into text and numbers. Nothing here ever sees a
string a browser sent — `diff.resolve` is the only door from a string to a
sha, and everything below takes its output.

The patch is capped in BYTES and the cap is stated in the answer: a silently
cut patch is a lie, a flagged one is a fact. `show()` — one committed file at a
sha — lives here for that reason and no other: it is the same sentence (a
resolved sha in, capped text out), and a second copy of the cap is how two
answers start disagreeing about what "truncated" means.
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
    return capped(raw.out, cap) if raw.ok else ("", False)


def show(repo: Path, sha: str, path: str, cap: int = CAP) -> tuple[str, bool] | None:
    """(text, truncated) for ONE file as that RESOLVED commit carries it, or None
    when the commit does not carry it at all.

    `<sha>:<path>` is git's OBJECT syntax, not a pathspec: it names one entry in
    one tree, so nothing here globs, walks or touches the working copy — the
    file on disk may differ, may be dirty, may not exist. None rather than an
    empty string, because a committed empty file is a real and different answer;
    the caller owns the wording of the refusal, as everywhere in this package."""
    raw = run.git("show", f"{sha}:{path}", cwd=repo)
    return capped(raw.out, cap) if raw.ok else None


def capped(text: str, cap: int) -> tuple[str, bool]:
    """(text, truncated) — the byte cap itself, in ONE place. Cut on the ENCODED
    bytes and decoded back with `ignore`, so a cap landing mid-codepoint drops
    that character instead of returning bytes no reader can decode."""
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
