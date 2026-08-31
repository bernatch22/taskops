"""Which repo answers /git for a board — the window's checkout, or a mirror.

`Mounts.repo` used to be the WHOLE answer: one `Path | None` decided at
construction, `taskops ui` passing its checkout and `taskops serve` passing
nothing. §16's hosted window keeps the spirit — the switch is still a decided
fact, never a per-request sniff — but on a serve-mode host the fact is per
BOARD: the forge its owner declared (`core/forge.py`, read through the one
reader `verbs/project.py::forge`). A board with one gets
`gitwork/mirror.ensure()` lazily, resolved once and cached the way `Mounts`
caches stores; a board without one is refused with the door named, because a
refusal that does not say `taskops board forge` strands the reader in a 404.

The WINDOW case is unchanged and deliberately first: a host constructed with a
checkout answers from it for every board, and no mirror is ever consulted —
the local clone is the reader's own truth, mirrors are the host's.

The second half of the answer is `mirrored`: `gitdoor` may buy a missing ref
ONE bounded fetch on a mirror (`http/stale.py`), and must never do that to a
window's clone — a background fetch inside a read-only door would move a
branch under a worktree somebody is sitting in. It travels as the forge's
LABEL ("host/owner/repo"), "" for a window: the same value that licenses the
fetch also chooses the missing-ref sentence's audience (`stale.sentence`),
because a host's refusal must name the forge and never say "your clone".
"""

from __future__ import annotations

from typing import Callable
from pathlib import Path
from threading import Lock

from ..verbs import project
from .._errors import NotFound
from ..gitwork import bare, mirror
from ..store.stores import Stores

NO_FORGE = (
    "this host serves boards, not a repository — it was started outside a "
    "checkout (taskops serve), and board {board!r} declares no forge to hold a "
    "mirror of. `taskops board forge <owner>/<repo>` is the door: the declared "
    "forge is the one source this host may mirror, read-only."
)
"""The serve-mode refusal, naming the move that opens it (§16: the refusal
names the door). It replaces the old blanket NO_REPO here because on a board
host "no repo" is a board-level fact with a board-level remedy."""


class Repos:
    """Per-board repo resolution for one server process.

    `checkout` is the construction-time window repo, exactly as `Mounts.repo`
    was; `stores` is `Mounts.stores`, so the forge fact is read from the same
    open board every other door reads. The cache holds only RESOLVED mirrors:
    a refusal is re-derived per ask (the fact may be declared any moment), and
    a failed clone leaves nothing behind, so the next ask is a clean retry.
    """

    def __init__(
        self, root: Path, checkout: Path | None, stores: Callable[[str], Stores]
    ) -> None:
        self.root = root
        self.checkout = checkout
        self._stores = stores
        self._lock = Lock()
        self._mirrors: dict[str, Path] = {}
        self._labels: dict[str, str] = {}

    def for_board(self, name: str) -> tuple[Path | None, str]:
        """`(repo, mirrored)` — the repo /git reads for this board, and the
        forge label ("host/owner/repo") when it is a mirror, "" when it is a
        window's clone. Truthiness licenses the one on-demand fetch; the label
        itself is the name the missing-ref sentence speaks (`http/stale.py`)."""
        if self.checkout is not None:
            return self.checkout, ""
        own = bare.at(self.root / name)
        if own is not None:
            # The board's OWN repo (§16, "The host becomes the remote"): once a
            # push has created it, it outranks any mirror — the diffs the window
            # reads are the board's truth, with no dependency on the forge. The
            # label is "" as a window's is: there is nowhere to fetch FROM, this
            # repo IS the source, so the one bounded fetch stays unlicensed.
            return own, ""
        with self._lock:
            found = self._mirrors.get(name)
            if found is not None:
                return found, self._labels[name]
        fact = project.forge(self._stores(name))
        if fact is None:
            raise NotFound(NO_FORGE.format(board=name))
        made = mirror.ensure(self.root / name, fact)
        if made is None:  # clone failed or impossible — gitdoor says NO_REPO
            return None, ""
        label = f"{fact['host']}/{fact['repo']}"
        with self._lock:
            self._mirrors[name] = made
            self._labels[name] = label
        return made, label

    def backed(self, name: str) -> bool:
        """Does a window open for this board here — the FACT, never the mirror.

        /ui asks this instead of `for_board` on purpose: the page it serves is
        the package's own bundle (`static.PACKAGED`), so its bytes need no repo
        at all — resolving one would put a network clone in front of
        `index.html` for nothing, and a clone that FAILS (forge down, key
        missing) would take the page down with it. The declared forge alone
        opens the door; the page's own /git calls go through `for_board` and
        resolve the mirror lazily the moment a diff is actually read — which is
        also where a resolution failure belongs: on the diff pane, in
        gitdoor's words, not on the page load. A window's checkout answers for
        every board, exactly as `for_board`'s first clause does."""
        if self.checkout is not None:
            return True
        if bare.at(self.root / name) is not None:
            return True  # the board's own repo opens the window, forge or no forge
        return project.forge(self._stores(name)) is not None
