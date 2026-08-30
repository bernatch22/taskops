"""The board's bare mirror — the forge's history, held so a host can answer.

ARCHITECTURE §16 ("The hosted window") decided this on 2026-08-30: a board
host MAY hold `<root>/<board>/mirror.git`, a bare `git clone --mirror` of the
forge the owner declared with `board forge` — and only then does it answer
`/git` and `/ui/`. The mirror is DERIVED and disposable in exactly the sense
`cache.sqlite` is: delete it and `ensure` re-clones; nothing in it is truth
the forge does not hold. Its ONLY source is that forge — it takes no client
pushes, it is not a second trunk, and nothing here ever writes to it beyond
what `clone` and `fetch` are.

**The address is derived, never a credential.** The default remote is
`https://<host>/<repo>.git`, spelled straight out of the declared fact
(`core/forge.py` owns that shape) — an anonymous clone, which is all a public
repo needs. A private repo is the owner's business: they point the mirror at
an ssh remote backed by a deploy key on the host's filesystem (`url=` at
clone time, or `git remote set-url` in a mirror that already exists), and
this module neither knows nor stores anything about it. What §11 bans stays
banned: no stored token, no write credential, no dev credential travelling.

**Failures return None/False, never raise into a request.** These functions
sit behind HTTP doors serving readers who cannot fix the host's network; a
mirror that cannot answer is a stale page, not a 500. The same reasoning
gave `remote.py::push` its 10-second budget, and `fetch` inherits the number:
a refresh is never a gate, so it may never cost more than a moment. The one
bounded on-demand fetch lives in `refresh_if_missing` — a requested ref that
is absent buys exactly one fetch, then the answer is whatever is true, stale
included. Answering stale beats blocking a page on a forge that is down.

All subprocess goes through `run.py`, the one module allowed to import it —
and `run.git` RAISES on a timeout (right for workers, wrong for a request),
so the catch here is part of the contract, not belt-and-braces.
"""

from __future__ import annotations

from pathlib import Path

from . import run
from ..core import forge as forge_facts
from .._errors import TaskopsError

__all__ = ["ensure", "fetch", "refresh_if_missing"]

MIRROR = "mirror.git"
"""§16's wording, verbatim: `<root>/<board>/mirror.git`, beside events.jsonl."""

FETCH_TIMEOUT = 10.0
"""`remote.py::PUSH_TIMEOUT`'s argument, pointing the other way: a refresh is
never a gate. Worst case a reader waits ten seconds ONCE and gets the truth
about this disk — which is what `gitdoor` answers anyway."""

CLONE_TIMEOUT = 120.0
"""A first clone moves the whole history, once, at mount time — not per
request — so it gets `run.TIMEOUT`'s patience rather than `fetch`'s."""


def _url(forge: object) -> str:
    """The declared fact → the anonymous https remote, or "".

    `forge_facts.understood` already collapses absent, cleared and
    unintelligible to None, so an https URL is only ever built from a fact a
    door would also act on. No token, no user@ — the address IS the whole
    credential story for a public repo.
    """
    fact = forge_facts.understood(forge)
    if fact is None:
        return ""
    return f"https://{fact['host']}/{fact['repo']}.git"


def ensure(board_dir: Path, forge: object, *, url: str = "") -> Path | None:
    """The mirror's path — cloning it into existence if this is the first ask.

    An EXISTING `mirror.git` is returned untouched, whatever remote it holds:
    that is how an owner's ssh remote (a deploy key's address) survives every
    later call. `url=` overrides the derived address at clone time — the same
    owner's move, and how tests clone from a local fixture instead of the
    network. No forge and no url means no mirror, which is the state every
    board is born in; a clone that fails leaves nothing behind, so the next
    ask is a clean retry rather than a corpse mistaken for a mirror.
    """
    dest = board_dir / MIRROR
    if dest.is_dir():
        return dest
    remote = url or _url(forge)
    if not remote:
        return None
    try:
        result = run.git("clone", "--mirror", remote, str(dest), timeout=CLONE_TIMEOUT)
    except TaskopsError:
        result = None  # timeout, or no git at all — a request never hears it
    if result is None or not result.ok:
        return None
    return dest


def fetch(mirror: Path) -> bool:
    """One bounded fetch from the mirror's own remote. True means it ran clean.

    A `--mirror` clone's fetch refspec already maps every ref one-to-one, so
    plain `git fetch` IS the whole refresh — no refspec spelled here that
    could drift from what clone configured. False covers everything a reader
    cannot fix: a dead remote, a timeout, a directory that stopped being a
    repo. The caller answers with what it has.
    """
    try:
        return run.git("fetch", cwd=mirror, timeout=FETCH_TIMEOUT).ok
    except TaskopsError:  # timeout, or no git at all — never the reader's problem
        return False


def _has(mirror: Path, ref: str) -> bool:
    """`^{commit}` is load-bearing: bare `rev-parse --verify <40-hex>` answers
    ok for ANY well-formed sha, present or not — a ref arriving as a full sha
    (which is what a diff door holds) would always read as here."""
    return run.git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=mirror).ok


def refresh_if_missing(mirror: Path, ref: str) -> bool:
    """Is `ref` here — after at most ONE fetch if it was not?

    §16's exact promise: a missing ref triggers one bounded on-demand fetch
    before answering stale. A ref already present costs nothing — no network
    touched, so a page over known history never waits on a forge. A ref still
    absent after the fetch is answered False, truthfully: "not here" is the
    truth about this disk, and the door already knows how to say so.
    """
    if _has(mirror, ref):
        return True
    fetch(mirror)
    return _has(mirror, ref)
