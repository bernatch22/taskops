"""project — a fact about the REPO, recorded once by the side that has it.

The board never reads a repo (the chapter's first rule): a git fact enters as
an EVENT, written by whoever holds the clone. `taskops init` and `taskops join`
already hold it and are already touching the board, so that is where the
repo's web home is read from `origin` and sent here — local or remote, through
the same `Board.call` door, because a remote dashboard has no repo to ask.

Three ops today. `remote` is `{host, slug, url}` (the argument is in
`gitwork/remote.py`). `visibility` is `{"visibility": "public" | "private"}` —
GitHub's flag, and it is a board-level FACT for the same reason `remote` is:
an event in the log, folded newest-wins, so "when did this become public and
who did it" is answerable from the history rather than from a column somebody
overwrote. `forge` is `{host, repo, need}` — the repo whose membership opens
this board. Ops are how this grows: each is a row in `_FACTS`, not a third
event kind and a third fold.

**A board with no `visibility` event is PRIVATE**, which is what makes every
board that existed before this feature — and every board created after it —
behave exactly as it always did without a migration. `is_public` is the ONE
reader of the fact; the HTTP layer never reaches into `state()` for it.

**A board with no `forge` event is invite-only**, by exactly that mechanism —
the chapter's opt-in rule. `forge()` is the ONE reader, `None` is its answer
for every board that never declared one, and nothing else branches on the
fact: that is what keeps a forge-less board's flow identical to the one it had
before this op existed. The SHAPE it stores is `core/forge.py`'s, because the
GitHub door and the CLI have to spell it the same way and neither may own it.

It rides out on the `board` payload (`verbs/pulse.py`) rather than getting a
door of its own, so a viewer can say "you are reading this as nobody" from the
read it already made — a second call would be one more thing to be refused.

**Recording the same value twice writes nothing.** The event id is a hash of
its content and its timestamp, so an unchanged re-run WOULD append a fresh
event every time somebody re-ran `init` — noise in a log that is replayed
forever and has no delete. A CHANGED origin writes, and wins by being later.
"""

from __future__ import annotations

from typing import Any, Callable

from . import _args
from .. import _clock
from ..core import forge as forges
from .._json import as_object
from .._errors import BadRequest
from ..core.event import make
from ..core.types import PROJECT
from ..store.stores import Stores

PUBLIC = "public"
PRIVATE = "private"
VISIBILITIES = (PRIVATE, PUBLIC)


def visibility(stores: Stores) -> str:
    """`private` unless an owner said otherwise — the default is the whole model.

    Read through here and never as `state()["project"]["visibility"]`: an absent
    fact, a fact from a board older than the feature and a fact cleared back to
    `None` all have to mean the same thing, and three call sites would spell
    that three ways.
    """
    fact: object = stores.state()["project"].get("visibility")
    seen = str(as_object(fact).get("visibility", ""))
    return seen if seen in VISIBILITIES else PRIVATE


def is_public(stores: Stores) -> bool:
    return visibility(stores) == PUBLIC


def forge(stores: Stores) -> dict[str, Any] | None:
    """`{host, repo, need}`, or None for a board that declared no forge.

    The ONE reader, for `visibility`'s reason — three spellings of "absent" is
    how a default rots — and re-validated through `core/forge.py::understood`
    on the way out, because a door GRANTS on this answer.
    """
    fact: object = stores.state()["project"].get("forge")
    return forges.understood(fact)


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    op = _args.text(args, "op", default="remote")
    if op not in OPS:
        raise BadRequest(f"op={op!r} is not a project fact — this board knows: {OPS}")
    value = _FACTS[op](args)
    now = _clock.now()
    stores.live.renew(actor, now)
    if stores.state()["project"].get(op) == value:
        return {"op": op, "value": value, "recorded": False, "seq": stores.head()}
    seq = stores.write([make(PROJECT, actor, "project", {"op": op, "value": value}, now)])
    return {"op": op, "value": value, "recorded": True, "seq": seq}


def _visible(args: _args.Args) -> dict[str, Any]:
    """`public` or `private`, and NOTHING between them.

    There is no third state and there must never be one: "public read, keyed
    write" is the whole model, so an `unlisted` or a `read-only-for-members`
    would be a second wall to keep in step with the first. A value outside the
    pair is refused by name rather than defaulted — defaulting a typo would
    silently make a board somebody meant to publish stay private, or worse.
    """
    wanted = _args.text(args, "visibility", default="")
    if wanted not in VISIBILITIES:
        raise BadRequest(
            f"visibility={wanted!r} — a board is {PRIVATE!r} or {PUBLIC!r}, and nothing else: "
            "public means anonymous READ, and writing always needs a registered key"
        )
    return {"visibility": wanted}


def _value(args: _args.Args) -> dict[str, Any] | None:
    """`slug=""` means "there is no origin" — a legal value that clears the fact."""
    slug = _args.text(args, "slug", default="")
    if not slug:
        return None
    host = _args.text(args, "host", default="")
    return {
        "host": host,
        "slug": slug,
        "url": _args.text(args, "url", default="") or f"https://{host}/{slug}",
    }


def _forged(args: _args.Args) -> dict[str, Any] | None:
    """`repo=""` clears the declaration — the way BACK to invite-only, and it
    must exist: opting in is reversible or it is a trap. Every part is refused
    by name rather than defaulted to something plausible: a `need` typo quietly
    defaulted to `push` widens who gets in, and a `repo` typo names a repository
    the caller does not control — the mistake that hands a board to a stranger.
    """
    repo = _args.text(args, "repo", default="")
    if not repo:
        return None
    return forges.declare(
        _args.text(args, "host", default="") or forges.GITHUB,
        repo,
        _args.text(args, "need", default="") or forges.PUSH,
    )


_FACTS: dict[str, Callable[[_args.Args], dict[str, Any] | None]] = {
    "remote": _value,
    "visibility": _visible,
    "forge": _forged,
}
"""The board-level facts, one row each: a fourth is a row plus a reader, never
a branch in `run`. `OPS` — and the refusal — are derived from it."""

OPS = tuple(_FACTS)
