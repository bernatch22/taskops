"""The MISSING-REF case, in its own words — and the one fetch a mirror buys.

Split out of `gitdoor.py` when the mirror chapter pushed it past the module
budget: this is the cohesive seam, because everything here is about one
question — a ref the repo lacks — and nothing here routes or reads git ranges.

It is not an error and must not read like one: on a shared board most refs
belong to somebody else's card, and until you fetch, "not here yet" is simply
the truth about your disk. Naming the exact command is this codebase's habit —
every refusal names the call that works — and it is also the reason nothing
fetches on a WINDOW's behalf: a background `git fetch` inside a read-only door
would move a branch under a worktree somebody is sitting in. A MIRROR is the
host's own derived copy with nobody sitting in it, so there — and only there —
a missing ref buys exactly one bounded fetch before the stale sentence
(`gitwork/mirror.py::refresh_if_missing`, §16's promise).
"""

from __future__ import annotations

from pathlib import Path

from ..gitwork import mirror

STALE = (
    "{refs} not in your clone yet — `{fetch}` brings {them}. The board is shared and "
    "the code is not: a card's branch reaches origin when it closes, and this "
    "window reads only the checkout it stands in. Nothing is fetched for you."
)

SHA = "0123456789abcdef"


def refreshed(repo: Path, mirrored: bool, refs: list[str]) -> bool:
    """True when a fetch may have brought the missing refs — retry the read.

    Only the FIRST missing ref pays: `refresh_if_missing` runs at most one
    fetch, and a mirror's fetch brings every ref at once, so the caller's
    retry covers the rest. `mirrored` False is the window's clone and answers
    False without touching the network, which is the §16 sentence above."""
    if not mirrored or not refs:
        return False
    return mirror.refresh_if_missing(repo, refs[0])


def sentence(*refs: str) -> str:
    """Which refs are missing, and the one command that brings them.

    A sha is asked for WITHOUT a refspec — `git fetch origin <40 hex>` is
    refused by most servers unless they allow it — while a branch is named, so
    the reader can paste the line and get exactly what the pane wanted."""
    names = [ref for ref in refs if ref] or ["that ref"]
    branches = [ref for ref in names if not _looks_like_a_sha(ref)]
    many = len(names) > 1
    return STALE.format(
        refs=f"{' and '.join(names)} {'are' if many else 'is'}",
        fetch=" ".join(["git fetch origin", *branches]),
        them="them" if many else "it",
    )


def _looks_like_a_sha(ref: str) -> bool:
    return len(ref) >= 7 and all(char in SHA for char in ref.lower())
