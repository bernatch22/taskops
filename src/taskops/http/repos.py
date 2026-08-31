"""Which repo answers /git for a board — the window's checkout, or the board's OWN.

`Mounts.repo` used to be the WHOLE answer: one `Path | None` decided at
construction, `taskops ui` passing its checkout and `taskops serve` passing
nothing. §16's hosted window kept the spirit — the switch is still a decided
fact, never a per-request sniff — but made the fact per BOARD. What it made the
fact ABOUT is what this module just reversed.

**The pull mirror is RETIRED, not repurposed** (§16, "The host becomes the
remote"). For one day a serve-mode host answered from `<root>/<board>/mirror.git`,
a read-only clone of the DECLARED forge, and this function tried the board's own
`repo.git` first with the mirror as a fallback. Two sources for one question is
the state this card existed to end, and the fallback was already unreachable on
every board that had ever been pushed to — live as a trap, not as a feature. So
the answer is now one line long: the checkout, or `bare.adopt()`, or nothing.

Why RETIRE rather than keep it for boards that declared a forge but hold no
push? Because the mirror could only ever answer for refs the FORGE has, and the
whole reported failure is refs it does not: a worktree branch nobody pushed,
and a `tk-*` branch pruned when its chapter landed. A fallback that is wrong in
exactly the case the reader asks about is worse than a refusal, which at least
says what to do. `gitwork/mirror.py` is deleted with it; the only thing owed to
a mirror already on disk is the HISTORY in it, and `bare.adopt` seeds `repo.git`
from it once and removes it (§16's "On-disk" paragraph — this module is the
caller because it is the first door that needs the answer, and production has a
populated `mirror.git` for taskops-v2 today).

`NO_FORGE` retired with it, in one word rather than a rewrite: a board with no
declared forge now gets push, clone, the window and the permanence, all standing
on `repo.git` alone — the forge became a projection, so its absence is no longer
a refusal to word. What a board with no `repo.git` gets is `gitdoor.NO_REPO`,
which is the honest fact: nobody has pushed here yet.

The second half of the answer used to be `mirrored`, a forge label that both
licensed one on-demand fetch and chose the missing-ref sentence's audience.
The fetch is gone with the mirror — this repo IS the source, there is nowhere
to fetch FROM — so what travels is the AUDIENCE alone, as `hosted`: True for
the host's own repository, False for a window's clone. The split is the point
(`http/stale.py` argues it): a reader with no clone must never be told to run
`git fetch`.
"""

from __future__ import annotations

from typing import Callable
from pathlib import Path

from ..gitwork import bare
from ..store.stores import Stores

__all__ = ["Repos"]


class Repos:
    """Per-board repo resolution for one server process.

    `checkout` is the construction-time window repo, exactly as `Mounts.repo`
    was. There is no cache any more and that is a simplification, not an
    oversight: the mirror's cache existed because resolving one could CLONE
    over the network, while `bare.adopt` is two `stat`s on the common path —
    caching it would only be a way to keep answering "no repo here" to a board
    somebody pushed to a second ago.

    `stores` is kept as the door onto the board's own state for whatever this
    layer needs to read per board next; nothing here reads the forge fact any
    more, because no answer depends on it.
    """

    def __init__(
        self, root: Path, checkout: Path | None, stores: Callable[[str], Stores]
    ) -> None:
        self.root = root
        self.checkout = checkout
        self._stores = stores

    def for_board(self, name: str) -> tuple[Path | None, bool]:
        """`(repo, hosted)` — the repo /git reads for this board, and WHO is
        asking: `hosted` True on a serve-mode host reading the board's own
        repository, False for a window's clone. The flag chooses the
        missing-ref sentence's audience and nothing else (`http/stale.py`).

        `None` is not an error here: `gitdoor.answer` turns it into `NO_REPO`
        with the fact named, and the UI's cascade falls through to the forge
        link or its own sentence. A board nobody has pushed to is a board with
        no git, which is exactly what the reader is told.
        """
        if self.checkout is not None:
            return self.checkout, False
        return bare.adopt(self.root / name), True

    def backed(self, name: str) -> bool:
        """Does a window open for this board here?

        The FACT is now the board's own repository, where it used to be the
        declared forge: a page whose diffs are read from `repo.git` opens
        exactly when `repo.git` exists. §16's argument is unchanged and only
        its subject moved — a dashboard shows DIFFS, and a window served over a
        history nobody has pushed could only fall through every step of
        `links.tsx::cascade`. That is serving a degraded window and calling it
        *the* window, which is what `static.NO_UI` refuses in words.

        Cheap on purpose, and asked instead of `for_board`: the page's bytes
        are the package's own bundle (`static.PACKAGED`), so its load needs no
        repo — only its own later /git calls do. A window's checkout answers
        for every board, exactly as `for_board`'s first clause does.
        """
        if self.checkout is not None:
            return True
        return bare.adopt(self.root / name) is not None
