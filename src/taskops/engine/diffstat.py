"""How big each commit was, for a whole day's worth of them in ONE subprocess.

`git diff-tree --numstat` takes one commit; handing it several makes it diff the first
against the rest, which is a different question and a wrong answer. `git log --no-walk`
is the batched form: it prints the named commits and nothing they descend from, so N shas
cost one process instead of N — the same reasoning as `gitstate.branch_states`.

Same degrade rule as the rest of `gitio`: never raises. A report that cannot be produced
because a sha was garbage-collected is worse than one that reports zeros.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["numstats", "parse"]


def numstats(root: Path, shas: list[str]) -> dict[str, tuple[int, int]]:
    """`{sha: (additions, deletions)}` for the shas git could resolve. ONE subprocess.

    Shas git does not know are simply absent from the result — the caller reads a missing
    key as zeros, so an unknown commit and an empty commit render the same way, which is
    the honest thing to say when git will not tell us the difference.
    """
    wanted = [sha for sha in dict.fromkeys(shas) if sha]
    if not wanted:
        return {}
    try:
        done = subprocess.run(["git", "log", "--numstat", "--format=%H", "--no-walk",
                               *wanted], cwd=root, capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse(done.stdout) if done.returncode == 0 else {}


def parse(out: str) -> dict[str, tuple[int, int]]:
    """The `--numstat` stream -> totals per commit.

    A bare line is a sha (the `%H` header) and a three-column line is one file. Binary files
    report `-` for both counts, which is not zero but is the only number that can be summed,
    so they contribute nothing rather than breaking the parse.

    Split out and pure so the format can be tested from a literal string: reproducing this
    from a real repository would mean building commits in a fixture to assert on arithmetic.
    """
    totals: dict[str, tuple[int, int]] = {}
    current = ""
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 1 and line.strip():
            current = line.strip()
            totals.setdefault(current, (0, 0))
        elif len(parts) == 3 and current:
            adds, dels = totals[current]
            totals[current] = (adds + _count(parts[0]), dels + _count(parts[1]))
    return totals


def _count(cell: str) -> int:
    return int(cell) if cell.isdigit() else 0
