"""The MISSING-REF case, in its own words — one per AUDIENCE.

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

**A refusal has an AUDIENCE, and 0.5.1 shipped one sentence to two of them**
(reported by Berna 2026-08-31, against the live hosted window). `STALE` below
was written for the reader of a local `taskops ui` — somebody sitting in their
own clone, for whom "not in your clone yet, `git fetch origin …` brings it" is
exactly right. The hosted window served those same words to a reader with NO
clone, and every clause inverted: they had nothing to fetch into, they could
not run the command, and the host HAD fetched (the one bounded fetch above).
The same words can be true for one reader and false in every clause for
another, so the vocabulary splits by audience while the module stays one:
`MIRRORED` says what is true on a host — this host mirrors the declared forge,
the ref is not there, and a pruned card branch is normal, not a fault, because
its commits landed on the trunk and the sha still names them. The audience is
never guessed: `mirrored` already travels into the door (`http/repos.py` →
`gitdoor.answer`), carrying the forge label when the repo is a mirror and ""
when it is a window's clone — one traveller, both facts.
"""

from __future__ import annotations

from pathlib import Path

from ..gitwork import mirror

STALE = (
    "{refs} not in your clone yet — `{fetch}` brings {them}. The board is shared and "
    "the code is not: a card's branch reaches origin when it closes, and this "
    "window reads only the checkout it stands in. Nothing is fetched for you."
)
"""The WINDOW's words — a reader who has a clone and may fetch into it.
Pinned byte-for-byte in tests/test_topology.py: these words are right for
that reader and must not drift toward the host's."""

MIRRORED = (
    "{refs} not on {forge}, the one source this host mirrors — it fetched once "
    "just now to be sure. A card's branch is pruned when its chapter lands, so "
    "a landed card's branch being gone is normal, not a fault: the commits "
    "survive on the trunk, and a sha still names {them} there. "
    "https://{forge} holds the history this mirror reflects."
)
"""The HOST's words — a reader with no clone, who can run nothing. No command
is named because there is none they could run; the forge is named because it
is the one place the history keeps living."""

SHA = "0123456789abcdef"


def refreshed(repo: Path, mirrored: str, refs: list[str]) -> bool:
    """True when a fetch may have brought the missing refs — retry the read.

    Only the FIRST missing ref pays: `refresh_if_missing` runs at most one
    fetch, and a mirror's fetch brings every ref at once, so the caller's
    retry covers the rest. `mirrored` "" is the window's clone and answers
    False without touching the network, which is the §16 sentence above."""
    if not mirrored or not refs:
        return False
    return mirror.refresh_if_missing(repo, refs[0])


def sentence(*refs: str, mirrored: str = "") -> str:
    """Which refs are missing — in the asker's own vocabulary.

    `mirrored` is the forge label ("host/owner/repo") when the repo is the
    board's mirror, "" when it is a window's clone: the same value that
    licensed the one fetch chooses the words, so the two facts cannot drift.

    For the window, a sha is asked for WITHOUT a refspec — `git fetch origin
    <40 hex>` is refused by most servers unless they allow it — while a branch
    is named, so the reader can paste the line and get exactly what the pane
    wanted. The mirror's sentence names no command at all."""
    names = [ref for ref in refs if ref] or ["that ref"]
    many = len(names) > 1
    listed = f"{' and '.join(names)} {'are' if many else 'is'}"
    them = "them" if many else "it"
    if mirrored:
        return MIRRORED.format(refs=listed, forge=mirrored, them=them)
    branches = [ref for ref in names if not _looks_like_a_sha(ref)]
    return STALE.format(
        refs=listed,
        fetch=" ".join(["git fetch origin", *branches]),
        them=them,
    )


def _looks_like_a_sha(ref: str) -> bool:
    return len(ref) >= 7 and all(char in SHA for char in ref.lower())
