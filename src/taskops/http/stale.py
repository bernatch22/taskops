"""The MISSING-REF case, in its own words — one per AUDIENCE.

Split out of `gitdoor.py` when the mirror chapter pushed it past the module
budget: this is the cohesive seam, because everything here is about one
question — a ref the repo lacks — and nothing here routes or reads git ranges.

It is not an error and must not read like one: on a shared board most refs
belong to somebody else's card, and until you fetch, "not here yet" is simply
the truth about your disk. Naming the exact command is this codebase's habit —
every refusal names the call that works — and it is also the reason nothing
fetches on a WINDOW's behalf: a background `git fetch` inside a read-only door
would move a branch under a worktree somebody is sitting in. The MIRROR used to
be the exception — the host's own derived copy of the forge, with nobody sitting
in it, where a missing ref bought exactly one bounded fetch. That fetch is GONE
with the mirror (§16, "The host becomes the remote", and `http/repos.py` argues
the retirement): the host now holds the board's OWN repository, which is the
source, and a source has nowhere to fetch from. So nothing fetches for anybody,
and this module only chooses words.

**A refusal has an AUDIENCE, and 0.5.1 shipped one sentence to two of them**
(reported by Berna 2026-08-31, against the live hosted window). `STALE` below
was written for the reader of a local `taskops ui` — somebody sitting in their
own clone, for whom "not in your clone yet, `git fetch origin …` brings it" is
exactly right. The hosted window served those same words to a reader with NO
clone, and every clause inverted: they had nothing to fetch into, they could
not run the command, and the host HAD fetched (the one bounded fetch above).
The same words can be true for one reader and false in every clause for
another, so the vocabulary splits by audience while the module stays one, and
the split OUTLIVED the mirror that prompted it. `HOSTED` is the host's half,
rewritten for what a host now is: it holds the board's own repository and
prunes NOTHING, so a ref missing here was never pushed here — which is a
different fact from the mirror's "the forge pruned it", and needs different
words. The audience is never guessed: `hosted` travels into the door
(`http/repos.py` → `gitdoor.answer`) as the one fact left to carry, True for
the host's own repo and False for a window's clone.
"""

from __future__ import annotations

STALE = (
    "{refs} not in your clone yet — `{fetch}` brings {them}. The board is shared and "
    "the code is not: a card's branch reaches origin when it closes, and this "
    "window reads only the checkout it stands in. Nothing is fetched for you."
)
"""The WINDOW's words — a reader who has a clone and may fetch into it.
Pinned byte-for-byte in tests/test_topology.py: these words are right for
that reader and must not drift toward the host's."""

HOSTED = (
    "{refs} not in this board's own repository on this host. Nothing was "
    "pruned to make that true — this host keeps every branch pushed to it "
    "forever — so {them} was never pushed here: a card worked before this host "
    "became the board's remote, or a worktree whose commits have not left it. "
    "A commit reaches this repository the moment it is made in a worktree "
    "joined to the board; the declared forge is a copy of what is here, never "
    "the other way round, so there is nowhere else this pane could look."
)
"""The HOST's words — a reader with no clone, who can run nothing. No command
is named because there is none they could run, and no forge is named because
the forge is no longer a source: under the reversal it is a projection of this
repository, so "not here" is not "look over there". What replaced the mirror's
"a pruned branch is normal" is the stronger fact — this host prunes nothing —
and therefore a different diagnosis: the commits never arrived."""

SHA = "0123456789abcdef"


def sentence(*refs: str, hosted: bool = False) -> str:
    """Which refs are missing — in the asker's own vocabulary.

    `hosted` is True when the repo is the board's own, on a serve-mode host,
    and False for a window's clone. It is the ONE fact the door carries now
    that the mirror's fetch licence is gone, and it decides only this: which
    reader is being spoken to.

    For the window, a sha is asked for WITHOUT a refspec — `git fetch origin
    <40 hex>` is refused by most servers unless they allow it — while a branch
    is named, so the reader can paste the line and get exactly what the pane
    wanted. The host's sentence names no command at all."""
    names = [ref for ref in refs if ref] or ["that ref"]
    many = len(names) > 1
    listed = f"{' and '.join(names)} {'are' if many else 'is'}"
    them = "them" if many else "it"
    if hosted:
        return HOSTED.format(refs=listed, them=them)
    branches = [ref for ref in names if not _looks_like_a_sha(ref)]
    return STALE.format(
        refs=listed,
        fetch=" ".join(["git fetch origin", *branches]),
        them=them,
    )


def _looks_like_a_sha(ref: str) -> bool:
    return len(ref) >= 7 and all(char in SHA for char in ref.lower())
